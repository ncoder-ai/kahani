"""
Chapter Brainstorm Service

Manages AI-powered chapter planning sessions for story development.
Handles conversational interactions and extraction of chapter plot elements.
"""
import json
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator
from sqlalchemy.orm import Session
from datetime import datetime

from ..models.chapter_brainstorm_session import ChapterBrainstormSession
from ..models.story import Story
from ..models.chapter import Chapter
from ..models.character import StoryCharacter
from ..services.llm.service import UnifiedLLMService
from ..services.llm.prompts import PromptManager
from ..utils.content_filter import get_nsfw_prevention_prompt, should_inject_nsfw_filter
from ..config import settings

logger = logging.getLogger(__name__)
prompt_manager = PromptManager()


def clean_llm_json(json_str: str) -> str:
    """Clean common LLM JSON formatting issues."""
    json_str = json_str.strip()
    if json_str.startswith("```json"):
        json_str = json_str[7:]
    if json_str.startswith("```"):
        json_str = json_str[3:]
    if json_str.endswith("```"):
        json_str = json_str[:-3]
    return json_str.strip()


import re

def parse_element_suggestions(ai_response: str) -> tuple:
    """
    Extract element suggestions from AI response.
    
    The AI is instructed to include suggestions in this format:
    ---ELEMENTS---
    {"overview": "...", "tone": "...", "key_events": [...], "characters": "...", "ending": "..."}
    ---END_ELEMENTS---
    
    But also handles raw JSON code blocks (```json ... ```) as fallback.
    
    Returns:
        tuple: (clean_response without markers, suggestions_dict or None)
    """
    json_block = None
    clean_response = ai_response
    
    # First try: Look for ---ELEMENTS--- markers
    pattern = r'---ELEMENTS---\s*(.*?)\s*---END_ELEMENTS---'
    match = re.search(pattern, ai_response, re.DOTALL)
    
    if match:
        json_block = match.group(1).strip()
        clean_response = re.sub(pattern, '', ai_response, flags=re.DOTALL).strip()
    else:
        # Fallback: Look for JSON code blocks (```json ... ``` or ``` ... ```)
        # Match JSON that contains chapter element keys
        code_block_pattern = r'```(?:json)?\s*(\{[^`]*(?:"overview"|"tone"|"key_events"|"characters"|"ending")[^`]*\})\s*```'
        code_match = re.search(code_block_pattern, ai_response, re.DOTALL)
        
        if code_match:
            json_block = code_match.group(1).strip()
            clean_response = re.sub(code_block_pattern, '', ai_response, flags=re.DOTALL).strip()
            logger.info(f"[CHAPTER_BRAINSTORM] Found JSON in code block (no markers)")
    
    if not json_block:
        return ai_response, None
    
    # Parse the JSON
    try:
        # Clean common LLM JSON issues
        json_block = clean_llm_json(json_block)
        suggestions = json.loads(json_block)
        
        # Validate the structure - only keep valid fields
        valid_fields = {'overview', 'tone', 'key_events', 'characters', 'ending'}
        filtered_suggestions = {k: v for k, v in suggestions.items() if k in valid_fields and v}
        
        if not filtered_suggestions:
            return clean_response, None
            
        logger.info(f"[CHAPTER_BRAINSTORM] Parsed element suggestions: {list(filtered_suggestions.keys())}")
        return clean_response, filtered_suggestions
        
    except json.JSONDecodeError as e:
        logger.warning(f"[CHAPTER_BRAINSTORM] Failed to parse element suggestions JSON: {e}")
        return clean_response, None


class ChapterBrainstormService:
    """
    Service for managing chapter-level brainstorming sessions.
    
    Responsibilities:
    - Manage conversational brainstorming for chapter plots
    - Provide story context and arc phase information
    - Extract structured chapter plot elements
    - Apply extracted plots to chapters
    """
    
    def __init__(self, user_id: int, user_settings: Dict[str, Any], db: Session):
        self.user_id = user_id
        self.user_settings = user_settings
        self.db = db
        self.llm_service = UnifiedLLMService()
    
    def create_session(
        self,
        story_id: int,
        arc_phase_id: str = None,
        chapter_id: int = None,
        prior_chapter_summary: str = None
    ) -> ChapterBrainstormSession:
        """
        Create a new chapter brainstorming session.
        
        Args:
            story_id: The story ID
            arc_phase_id: Optional arc phase this chapter targets
            chapter_id: Optional chapter ID if editing an existing chapter
            prior_chapter_summary: Optional user-provided summary of the prior chapter
            
        Returns:
            New ChapterBrainstormSession
        """
        # Verify story exists and belongs to user
        story = self.db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == self.user_id
        ).first()
        
        if not story:
            raise ValueError(f"Story {story_id} not found")
        
        session = ChapterBrainstormSession(
            story_id=story_id,
            user_id=self.user_id,
            arc_phase_id=arc_phase_id,
            chapter_id=chapter_id,  # Track which chapter is being edited
            prior_chapter_summary=prior_chapter_summary,  # Store user-provided prior context
            messages=[],
            status='brainstorming'
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        
        logger.info(f"[CHAPTER_BRAINSTORM] Created session {session.id} for story {story_id}, arc_phase={arc_phase_id}, chapter_id={chapter_id}, has_prior_summary={bool(prior_chapter_summary)}")
        return session
    
    def get_session(self, session_id: int) -> Optional[ChapterBrainstormSession]:
        """Get a chapter brainstorming session by ID."""
        session = self.db.query(ChapterBrainstormSession).filter(
            ChapterBrainstormSession.id == session_id,
            ChapterBrainstormSession.user_id == self.user_id
        ).first()
        if session:
            self.db.refresh(session)
        return session
    
    def get_sessions_for_story(self, story_id: int) -> List[Dict[str, Any]]:
        """Get all chapter brainstorming sessions for a story."""
        sessions = self.db.query(ChapterBrainstormSession).filter(
            ChapterBrainstormSession.story_id == story_id,
            ChapterBrainstormSession.user_id == self.user_id
        ).order_by(ChapterBrainstormSession.created_at.desc()).all()
        
        result = []
        for session in sessions:
            result.append({
                "id": session.id,
                "story_id": session.story_id,
                "chapter_id": session.chapter_id,
                "arc_phase_id": session.arc_phase_id,
                "status": session.status,
                "message_count": len(session.messages) if session.messages else 0,
                "has_extracted_plot": bool(session.extracted_plot),
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "updated_at": session.updated_at.isoformat() if session.updated_at else None
            })
        
        return result
    
    def delete_session(self, session_id: int) -> bool:
        """Delete a chapter brainstorming session."""
        session = self.get_session(session_id)
        if not session:
            return False
        
        self.db.delete(session)
        self.db.commit()
        logger.info(f"[CHAPTER_BRAINSTORM] Deleted session {session_id}")
        return True
    
    async def send_message(
        self,
        session_id: int,
        user_message: str
    ) -> Dict[str, Any]:
        """
        Send a user message and get AI response with full story context.
        
        Args:
            session_id: The chapter brainstorming session ID
            user_message: The user's message
            
        Returns:
            Dictionary with AI response and updated session
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Add user message to history
        session.add_message("user", user_message)
        self.db.commit()
        self.db.refresh(session)
        
        try:
            # Build full story context (pass chapter_id to know if editing existing chapter, and prior summary)
            story_context = self._build_story_context(
                session.story_id, 
                session.arc_phase_id, 
                session.chapter_id,
                session.prior_chapter_summary
            )
            
            # Get conversation history
            conversation_history = session.get_conversation_context()
            
            # Get prompts
            system_prompt = prompt_manager.get_prompt("chapter_brainstorm.chat", "system")
            
            # Add story context to system prompt
            full_system_prompt = f"{system_prompt}\n\nSTORY CONTEXT:\n{story_context}"
            
            # Get LLM client
            client = self.llm_service.get_user_client(self.user_id, self.user_settings)
            
            # Build messages array
            messages = []
            
            # Handle NSFW filter
            user_allow_nsfw = self.user_settings.get('allow_nsfw', False) if self.user_settings else False
            if should_inject_nsfw_filter(user_allow_nsfw):
                full_system_prompt = full_system_prompt + "\n\n" + get_nsfw_prevention_prompt()
            
            messages.append({"role": "system", "content": full_system_prompt})
            
            # Add conversation history
            for msg in conversation_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role in ["user", "assistant"]:
                    messages.append({"role": role, "content": content})
            
            # Get generation parameters
            gen_params = client.get_generation_params(
                self.user_settings.get('llm_settings', {}).get('max_tokens', 2048),
                0.7
            )
            gen_params["messages"] = messages
            
            # Get timeout
            user_timeout = None
            if self.user_settings:
                llm_settings = self.user_settings.get('llm_settings', {})
                user_timeout = llm_settings.get('timeout_total')
            timeout_value = user_timeout if user_timeout is not None else settings.llm_timeout_total
            gen_params["timeout"] = timeout_value
            
            # Call LLM
            response = await acompletion(**gen_params)
            ai_response = response.choices[0].message.content
            
            # Parse element suggestions from response
            clean_response, suggested_elements = parse_element_suggestions(ai_response)
            
            # Save assistant response (save the clean version without markers)
            session.add_message("assistant", clean_response)
            self.db.commit()
            self.db.refresh(session)
            
            logger.info(f"[CHAPTER_BRAINSTORM] Session {session_id} - exchanged messages, total: {len(session.messages)}")
            
            result = {
                "session_id": session.id,
                "user_message": user_message,
                "ai_response": clean_response,
                "message_count": len(session.messages)
            }
            
            # Include suggested elements if any were parsed
            if suggested_elements:
                result["suggested_elements"] = suggested_elements
                logger.info(f"[CHAPTER_BRAINSTORM] Session {session_id} - extracted suggestions: {list(suggested_elements.keys())}")
            
            return result
            
        except Exception as e:
            logger.error(f"[CHAPTER_BRAINSTORM] Error in session {session_id}: {str(e)}")
            raise
    
    async def send_message_streaming(
        self,
        session_id: int,
        user_message: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Send a user message and stream AI response with full story context.
        
        Yields dictionaries with:
        - type: 'thinking_start', 'thinking_chunk', 'thinking_end', 'content', 'complete', 'error'
        - For 'content' and 'thinking_chunk': 'chunk' contains the text
        - For 'complete': 'ai_response', 'message_count'
        
        Args:
            session_id: The chapter brainstorming session ID
            user_message: The user's message
            
        Yields:
            Dictionaries with streaming events
        """
        session = self.get_session(session_id)
        if not session:
            yield {"type": "error", "message": f"Session {session_id} not found"}
            return
        
        # Add user message to history
        session.add_message("user", user_message)
        self.db.commit()
        self.db.refresh(session)
        
        try:
            # Build full story context (pass chapter_id to know if editing existing chapter, and prior summary)
            story_context = self._build_story_context(
                session.story_id, 
                session.arc_phase_id, 
                session.chapter_id,
                session.prior_chapter_summary
            )
            
            # Get conversation history
            conversation_history = session.get_conversation_context()
            
            # Get prompts
            system_prompt = prompt_manager.get_prompt("chapter_brainstorm.chat", "system")
            
            # Add story context to system prompt
            full_system_prompt = f"{system_prompt}\n\nSTORY CONTEXT:\n{story_context}"
            
            # Build user prompt from conversation history
            # The last message is the current user message, format the rest as context
            user_prompt = ""
            for msg in conversation_history[:-1]:  # All but last (which is the new user message)
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    user_prompt += f"User: {content}\n\n"
                elif role == "assistant":
                    user_prompt += f"Assistant: {content}\n\n"
            
            # Add the current user message
            user_prompt += f"User: {user_message}"
            
            # Use the UnifiedLLMService._generate_stream - same as scene generation
            full_content = ""
            is_thinking = False
            thinking_content = ""
            
            async for chunk in self.llm_service._generate_stream(
                prompt=user_prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt=full_system_prompt,
                max_tokens=self.user_settings.get('llm_settings', {}).get('max_tokens', 2048),
                temperature=0.7
            ):
                # Check for thinking content (prefixed with __THINKING__:)
                if chunk.startswith("__THINKING__:"):
                    thinking_chunk = chunk[13:]  # Remove prefix
                    if not is_thinking:
                        is_thinking = True
                        yield {"type": "thinking_start"}
                    thinking_content += thinking_chunk
                    yield {"type": "thinking_chunk", "chunk": thinking_chunk}
                else:
                    # Regular content
                    if is_thinking:
                        is_thinking = False
                        yield {"type": "thinking_end", "total_chars": len(thinking_content)}
                    
                    full_content += chunk
                    yield {"type": "content", "chunk": chunk}
            
            # If still thinking at end, close it
            if is_thinking:
                yield {"type": "thinking_end", "total_chars": len(thinking_content)}
            
            # Parse element suggestions from the full response
            clean_response, suggested_elements = parse_element_suggestions(full_content)
            
            # Save assistant response (save the clean version without markers)
            session.add_message("assistant", clean_response)
            self.db.commit()
            self.db.refresh(session)
            
            logger.info(f"[CHAPTER_BRAINSTORM:STREAM] Session {session_id} - exchanged messages, total: {len(session.messages)}")
            
            yield {
                "type": "complete",
                "session_id": session.id,
                "ai_response": clean_response,
                "message_count": len(session.messages)
            }
            
            # Emit suggestions event if any were parsed
            if suggested_elements:
                logger.info(f"[CHAPTER_BRAINSTORM:STREAM] Session {session_id} - extracted suggestions: {list(suggested_elements.keys())}")
                yield {
                    "type": "suggestions",
                    "elements": suggested_elements
                }
            
        except Exception as e:
            logger.error(f"[CHAPTER_BRAINSTORM:STREAM] Error in session {session_id}: {str(e)}")
            yield {"type": "error", "message": str(e)}
    
    def update_structured_element(
        self,
        session_id: int,
        element_type: str,
        value
    ) -> Dict[str, Any]:
        """
        Update a single structured element in the session.
        
        Args:
            session_id: The session ID
            element_type: One of 'overview', 'characters', 'tone', 'key_events', 'ending'
            value: The value to set
            
        Returns:
            Updated structured elements
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        session.update_structured_element(element_type, value)
        self.db.commit()
        
        logger.info(f"[CHAPTER_BRAINSTORM] Updated structured element '{element_type}' for session {session_id}")
        
        return {
            "session_id": session.id,
            "structured_elements": session.get_structured_elements()
        }
    
    async def extract_chapter_plot(
        self,
        session_id: int
    ) -> Dict[str, Any]:
        """
        Extract structured chapter plot from conversation and confirmed structured elements.
        
        Prioritizes confirmed structured elements over parsing conversation.
        
        Args:
            session_id: The chapter brainstorming session ID
            
        Returns:
            Dictionary with extracted plot elements
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if not session.messages or len(session.messages) < 2:
            raise ValueError("Not enough conversation to extract plot")
        
        try:
            # Get confirmed structured elements
            structured_elements = session.get_structured_elements()
            
            # Format conversation
            conversation_text = self._format_conversation(session.messages)
            
            # Build story context (pass chapter_id to know if editing existing chapter, and prior summary)
            story_context = self._build_story_context(
                session.story_id, 
                session.arc_phase_id, 
                session.chapter_id,
                session.prior_chapter_summary
            )
            
            # Get arc phase details
            arc_phase_text = ""
            if session.arc_phase_id:
                story = self.db.query(Story).filter(Story.id == session.story_id).first()
                if story and story.story_arc:
                    phase = story.get_arc_phase(session.arc_phase_id)
                    if phase:
                        arc_phase_text = f"Phase: {phase.get('name', 'Unknown')}\nDescription: {phase.get('description', '')}"
            
            # Format confirmed elements for the prompt
            confirmed_elements_text = self._format_confirmed_elements(structured_elements)
            
            # Get extraction prompts
            system_prompt = prompt_manager.get_prompt("chapter_brainstorm.extract", "system")
            user_prompt = prompt_manager.get_prompt(
                "chapter_brainstorm.extract", "user",
                story_context=story_context,
                arc_phase=arc_phase_text or "No specific arc phase",
                conversation=conversation_text,
                confirmed_elements=confirmed_elements_text
            )
            
            # Call LLM
            response = await self.llm_service.generate(
                prompt=user_prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt=system_prompt,
                max_tokens=self.user_settings.get('llm_settings', {}).get('max_tokens', 2048),
                temperature=0.3
            )
            
            # Parse JSON response
            response_clean = clean_llm_json(response)
            extracted_plot = json.loads(response_clean)
            
            # Merge confirmed structured elements into extracted plot
            # Confirmed elements take priority
            if structured_elements.get('overview'):
                extracted_plot['summary'] = structured_elements['overview']
            if structured_elements.get('key_events'):
                extracted_plot['key_events'] = structured_elements['key_events']
            if structured_elements.get('tone'):
                extracted_plot['mood'] = structured_elements['tone']
            if structured_elements.get('ending'):
                extracted_plot['resolution'] = structured_elements['ending']
            if structured_elements.get('characters'):
                # Merge character data
                extracted_plot['character_arcs'] = structured_elements['characters']
            
            # Normalize the extracted plot
            normalized_plot = self._normalize_chapter_plot(extracted_plot)
            
            # Auto-detect new characters by comparing character_arcs against story's existing characters
            normalized_plot = self._detect_new_characters(session.story_id, normalized_plot)
            
            # Update session
            session.update_extracted_plot(normalized_plot)
            session.status = 'extracted'
            self.db.commit()
            
            logger.info(f"[CHAPTER_BRAINSTORM] Extracted plot from session {session_id}")
            
            return {
                "session_id": session.id,
                "extracted_plot": normalized_plot,
                "status": session.status
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"[CHAPTER_BRAINSTORM] Failed to parse plot JSON: {str(e)}")
            raise ValueError("Failed to extract chapter plot - invalid response format")
        except Exception as e:
            logger.error(f"[CHAPTER_BRAINSTORM] Error extracting plot: {str(e)}")
            raise
    
    def _format_confirmed_elements(self, elements: Dict[str, Any]) -> str:
        """Format confirmed structured elements for the extraction prompt."""
        parts = []
        
        if elements.get('overview'):
            parts.append(f"CONFIRMED OVERVIEW:\n{elements['overview']}")
        
        if elements.get('characters'):
            chars = elements['characters']
            if isinstance(chars, list) and chars:
                char_text = "\n".join([
                    f"  - {c.get('character_name', c.get('name', 'Unknown'))}: {c.get('development', c.get('dynamics', ''))}"
                    for c in chars if isinstance(c, dict)
                ])
                parts.append(f"CONFIRMED CHARACTERS:\n{char_text}")
        
        if elements.get('tone'):
            parts.append(f"CONFIRMED TONE:\n{elements['tone']}")
        
        if elements.get('key_events'):
            events = elements['key_events']
            if isinstance(events, list) and events:
                events_text = "\n".join([f"  {i+1}. {e}" for i, e in enumerate(events)])
                parts.append(f"CONFIRMED KEY EVENTS:\n{events_text}")
        
        if elements.get('ending'):
            parts.append(f"CONFIRMED ENDING:\n{elements['ending']}")
        
        if parts:
            return "\n\n".join(parts)
        return "No elements confirmed yet."
    
    def apply_to_chapter(
        self,
        session_id: int,
        chapter_id: int
    ) -> Chapter:
        """
        Apply extracted plot to a chapter.
        
        Args:
            session_id: The chapter brainstorming session ID
            chapter_id: The chapter to apply the plot to
            
        Returns:
            Updated Chapter
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if not session.extracted_plot:
            raise ValueError("No extracted plot to apply")
        
        # Get the chapter
        chapter = self.db.query(Chapter).filter(
            Chapter.id == chapter_id,
            Chapter.story_id == session.story_id
        ).first()
        
        if not chapter:
            raise ValueError(f"Chapter {chapter_id} not found")
        
        # Apply the plot
        chapter.chapter_plot = session.extracted_plot
        chapter.arc_phase_id = session.arc_phase_id
        chapter.brainstorm_session_id = session.id
        
        # Update session
        session.chapter_id = chapter_id
        session.status = 'applied'
        
        self.db.commit()
        self.db.refresh(chapter)
        
        logger.info(f"[CHAPTER_BRAINSTORM] Applied plot from session {session_id} to chapter {chapter_id}")
        
        return chapter
    
    def update_extracted_plot(
        self,
        session_id: int,
        plot_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update the extracted plot (user edits).
        
        Args:
            session_id: The session ID
            plot_data: Updated plot data
            
        Returns:
            Updated plot data
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        normalized_plot = self._normalize_chapter_plot(plot_data)
        session.update_extracted_plot(normalized_plot)
        self.db.commit()
        
        logger.info(f"[CHAPTER_BRAINSTORM] Updated plot for session {session_id}")
        
        return {
            "session_id": session.id,
            "extracted_plot": normalized_plot
        }
    
    def _build_story_context(self, story_id: int, arc_phase_id: str = None, editing_chapter_id: int = None, prior_chapter_summary: str = None) -> str:
        """Build comprehensive context string with story, arc, and previous chapters.
        
        Args:
            story_id: The story ID
            arc_phase_id: Optional arc phase this chapter targets
            editing_chapter_id: If provided, indicates we're editing an existing chapter (not creating new)
            prior_chapter_summary: Optional user-provided summary of what just happened in the current chapter
        """
        from ..models import Scene, SceneVariant, StoryFlow
        
        story = self.db.query(Story).filter(Story.id == story_id).first()
        if not story:
            return "Story not found"
        
        # Get the chapter being edited (if any)
        editing_chapter = None
        if editing_chapter_id:
            editing_chapter = self.db.query(Chapter).filter(Chapter.id == editing_chapter_id).first()
        
        context_parts = []
        
        # Basic story info
        context_parts.append(f"STORY: {story.title}")
        context_parts.append(f"Genre: {story.genre or 'Not specified'}")
        context_parts.append(f"Tone: {story.tone or 'Not specified'}")
        if story.description:
            context_parts.append(f"Description: {story.description}")
        if story.scenario:
            context_parts.append(f"Scenario: {story.scenario}")
        if story.world_setting:
            context_parts.append(f"World Setting: {story.world_setting}")
        
        # Indicate which chapter we're working on
        if editing_chapter:
            context_parts.append(f"\n*** EDITING CHAPTER {editing_chapter.chapter_number}: {editing_chapter.title or 'Untitled'} ***")
            context_parts.append(f"(We are brainstorming/editing the plot for this existing chapter, NOT creating a new chapter)")
        
        # Characters
        if story.story_characters:
            context_parts.append("\nCHARACTERS:")
            for sc in story.story_characters:
                char = sc.character
                if char:
                    context_parts.append(f"- {char.name} ({sc.role or 'unknown'}): {char.description or 'No description'}")
        
        # Story arc - highlight the target phase
        if story.story_arc:
            context_parts.append("\nSTORY ARC:")
            context_parts.append(f"Structure: {story.story_arc.get('structure_type', 'Unknown')}")
            
            phases = story.story_arc.get('phases', [])
            for phase in phases:
                is_target = phase.get('id') == arc_phase_id
                marker = ">>> TARGET PHASE: " if is_target else "    "
                phase_desc = phase.get('description', '')[:150] if not is_target else phase.get('description', '')
                context_parts.append(f"{marker}{phase.get('name', 'Unknown')}")
                context_parts.append(f"      {phase_desc}")
                if is_target and phase.get('key_events'):
                    context_parts.append(f"      Key events for this phase: {', '.join(phase.get('key_events', [])[:5])}")
        
        # Previous chapters with actual content summaries
        chapters = self.db.query(Chapter).filter(
            Chapter.story_id == story_id
        ).order_by(Chapter.chapter_number).all()
        
        if chapters:
            # Filter out the chapter being edited from "previous chapters"
            previous_chapters = [ch for ch in chapters if ch.id != editing_chapter_id] if editing_chapter_id else chapters
            
            if previous_chapters:
                context_parts.append("\nWHAT HAS HAPPENED IN OTHER CHAPTERS:")
                for ch in previous_chapters:
                    # Get chapter summary - prefer auto_summary, then story_so_far, then description
                    chapter_summary = ch.auto_summary or ch.story_so_far or ch.description
                    
                    if chapter_summary:
                        context_parts.append(f"\nChapter {ch.chapter_number}: {ch.title or 'Untitled'}")
                        context_parts.append(f"  {chapter_summary[:300]}...")
                    else:
                        # If no summary, get a brief from actual scene content
                        scenes = self.db.query(Scene).filter(
                            Scene.chapter_id == ch.id
                        ).order_by(Scene.sequence_number).limit(3).all()
                        
                        if scenes:
                            context_parts.append(f"\nChapter {ch.chapter_number}: {ch.title or 'Untitled'}")
                            # Get content from active variants
                            scene_snippets = []
                            for scene in scenes:
                                # Get active variant content
                                active_flow = self.db.query(StoryFlow).filter(
                                    StoryFlow.scene_id == scene.id,
                                    StoryFlow.is_active == True
                                ).first()
                                if active_flow:
                                    variant = self.db.query(SceneVariant).filter(
                                        SceneVariant.id == active_flow.active_variant_id
                                    ).first()
                                    if variant and variant.content:
                                        scene_snippets.append(variant.content[:100])
                            
                            if scene_snippets:
                                context_parts.append(f"  {' ... '.join(scene_snippets)[:300]}...")
                            else:
                                context_parts.append(f"  (No scene content yet)")
                        else:
                            context_parts.append(f"\nChapter {ch.chapter_number}: {ch.title or 'Untitled'}")
                            context_parts.append(f"  (No scenes written yet)")
            
            if editing_chapter:
                context_parts.append(f"\n(Editing Chapter {editing_chapter.chapter_number} of {len(chapters)} total chapters)")
            else:
                total_chapters = len(chapters)
                context_parts.append(f"\n(Total: {total_chapters} chapter{'s' if total_chapters != 1 else ''} written so far)")
                context_parts.append(f"(You are planning Chapter {total_chapters + 1})")
        else:
            context_parts.append("\nSTORY PROGRESS: This will be the first chapter.")
        
        # Add user-provided prior chapter summary if available
        if prior_chapter_summary:
            context_parts.append("\n*** WHAT JUST HAPPENED (User-provided summary of current chapter) ***")
            context_parts.append(prior_chapter_summary)
            context_parts.append("(Use this context to plan what happens NEXT in the story)")
        
        return "\n".join(context_parts)
    
    def _format_conversation(self, messages: List[Dict]) -> str:
        """Format conversation history for extraction."""
        formatted = []
        for msg in messages:
            role = "User" if msg["role"] == "user" else "AI"
            content = msg["content"]
            formatted.append(f"{role}: {content}")
        return "\n\n".join(formatted)
    
    def _normalize_chapter_plot(self, plot: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and validate chapter plot data."""
        normalized = {
            "summary": plot.get("summary", ""),
            "opening_situation": plot.get("opening_situation", ""),
            "key_events": plot.get("key_events", []),
            "climax": plot.get("climax", ""),
            "resolution": plot.get("resolution", ""),
            "character_arcs": plot.get("character_arcs", []),
            "new_character_suggestions": plot.get("new_character_suggestions", []),
            "recommended_characters": plot.get("recommended_characters", []),
            "mood": plot.get("mood", ""),
            "location": plot.get("location", "")
        }
        
        # Ensure lists are lists
        for list_field in ["key_events", "character_arcs", "new_character_suggestions", "recommended_characters"]:
            if not isinstance(normalized[list_field], list):
                normalized[list_field] = []
        
        return normalized

    def _detect_new_characters(self, story_id: int, plot: Dict[str, Any]) -> Dict[str, Any]:
        """
        Auto-detect new characters by comparing character_arcs against story's existing characters.
        
        Any character in character_arcs that is NOT in the story's character list
        gets moved to new_character_suggestions.
        """
        # Get existing character names from the story (case-insensitive)
        story = self.db.query(Story).filter(Story.id == story_id).first()
        if not story:
            return plot
        
        existing_names = []
        if story.story_characters:
            for sc in story.story_characters:
                if sc.character:
                    existing_names.append(sc.character.name.lower().strip())
        
        logger.debug(f"[CHAPTER_BRAINSTORM] Existing characters in story: {existing_names}")
        
        def is_existing_character(char_name: str) -> bool:
            """Check if a character name matches any existing character (fuzzy matching)."""
            char_lower = char_name.lower().strip()
            
            for existing in existing_names:
                # Exact match
                if char_lower == existing:
                    return True
                
                # Partial match: "Risha" matches "Risha Thorne"
                # Check if the extracted name is contained in existing name
                if char_lower in existing:
                    return True
                
                # Check if existing name is contained in extracted name
                if existing in char_lower:
                    return True
                
                # Word-based matching: any significant word matches
                char_words = set(w for w in char_lower.split() if len(w) > 2)
                existing_words = set(w for w in existing.split() if len(w) > 2)
                if char_words and existing_words and char_words & existing_words:
                    return True
            
            return False
        
        # Separate character_arcs into existing and new
        existing_arcs = []
        new_suggestions = list(plot.get("new_character_suggestions", []))  # Keep any LLM-suggested ones
        
        for arc in plot.get("character_arcs", []):
            char_name = arc.get("character_name") or arc.get("name", "")
            if not char_name or not char_name.strip():
                continue
            
            # Check if this character exists in the story
            if is_existing_character(char_name):
                existing_arcs.append(arc)
                logger.debug(f"[CHAPTER_BRAINSTORM] Matched existing character: {char_name}")
            else:
                # This is a new character - move to new_character_suggestions
                new_suggestion = {
                    "name": char_name,
                    "role": "other",  # Default role
                    "description": arc.get("development", ""),
                    "reason": "Mentioned in chapter brainstorm"
                }
                # Avoid duplicates
                char_lower = char_name.lower().strip()
                if not any(s.get("name", "").lower().strip() == char_lower for s in new_suggestions):
                    new_suggestions.append(new_suggestion)
                    logger.info(f"[CHAPTER_BRAINSTORM] Detected new character: {char_name}")
        
        # Update the plot
        plot["character_arcs"] = existing_arcs
        plot["new_character_suggestions"] = new_suggestions
        
        return plot

