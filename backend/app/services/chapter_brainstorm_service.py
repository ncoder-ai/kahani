"""
Chapter Brainstorm Service

Manages AI-powered chapter planning sessions for story development.
Handles conversational interactions and extraction of chapter plot elements.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime
from litellm import acompletion

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
        arc_phase_id: str = None
    ) -> ChapterBrainstormSession:
        """
        Create a new chapter brainstorming session.
        
        Args:
            story_id: The story ID
            arc_phase_id: Optional arc phase this chapter targets
            
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
            messages=[],
            status='brainstorming'
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        
        logger.info(f"[CHAPTER_BRAINSTORM] Created session {session.id} for story {story_id}, arc_phase={arc_phase_id}")
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
            # Build full story context
            story_context = self._build_story_context(session.story_id, session.arc_phase_id)
            
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
                self.user_settings.get('generation_preferences', {}).get('max_tokens', 1000),
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
            
            # Save assistant response
            session.add_message("assistant", ai_response)
            self.db.commit()
            self.db.refresh(session)
            
            logger.info(f"[CHAPTER_BRAINSTORM] Session {session_id} - exchanged messages, total: {len(session.messages)}")
            
            return {
                "session_id": session.id,
                "user_message": user_message,
                "ai_response": ai_response,
                "message_count": len(session.messages)
            }
            
        except Exception as e:
            logger.error(f"[CHAPTER_BRAINSTORM] Error in session {session_id}: {str(e)}")
            raise
    
    async def extract_chapter_plot(
        self,
        session_id: int
    ) -> Dict[str, Any]:
        """
        Extract structured chapter plot from conversation.
        
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
            # Format conversation
            conversation_text = self._format_conversation(session.messages)
            
            # Build story context
            story_context = self._build_story_context(session.story_id, session.arc_phase_id)
            
            # Get arc phase details
            arc_phase_text = ""
            if session.arc_phase_id:
                story = self.db.query(Story).filter(Story.id == session.story_id).first()
                if story and story.story_arc:
                    phase = story.get_arc_phase(session.arc_phase_id)
                    if phase:
                        arc_phase_text = f"Phase: {phase.get('name', 'Unknown')}\nDescription: {phase.get('description', '')}"
            
            # Get extraction prompts
            system_prompt = prompt_manager.get_prompt("chapter_brainstorm.extract", "system")
            user_prompt = prompt_manager.get_prompt(
                "chapter_brainstorm.extract", "user",
                story_context=story_context,
                arc_phase=arc_phase_text or "No specific arc phase",
                conversation=conversation_text
            )
            
            # Call LLM
            response = await self.llm_service.generate(
                prompt=user_prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt=system_prompt,
                max_tokens=2000,
                temperature=0.3
            )
            
            # Parse JSON response
            response_clean = clean_llm_json(response)
            extracted_plot = json.loads(response_clean)
            
            # Normalize the extracted plot
            normalized_plot = self._normalize_chapter_plot(extracted_plot)
            
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
    
    def _build_story_context(self, story_id: int, arc_phase_id: str = None) -> str:
        """Build context string with story, arc, and previous chapters."""
        story = self.db.query(Story).filter(Story.id == story_id).first()
        if not story:
            return "Story not found"
        
        context_parts = []
        
        # Basic story info
        context_parts.append(f"STORY: {story.title}")
        context_parts.append(f"Genre: {story.genre or 'Not specified'}")
        context_parts.append(f"Tone: {story.tone or 'Not specified'}")
        if story.description:
            context_parts.append(f"Description: {story.description}")
        if story.scenario:
            context_parts.append(f"Scenario: {story.scenario}")
        
        # Characters
        if story.story_characters:
            context_parts.append("\nCHARACTERS:")
            for sc in story.story_characters:
                char = sc.character
                if char:
                    context_parts.append(f"- {char.name} ({sc.role or 'unknown'}): {char.description or 'No description'}")
        
        # Story arc
        if story.story_arc:
            context_parts.append("\nSTORY ARC:")
            context_parts.append(f"Structure: {story.story_arc.get('structure_type', 'Unknown')}")
            
            phases = story.story_arc.get('phases', [])
            for phase in phases:
                marker = ">>> " if phase.get('id') == arc_phase_id else "    "
                context_parts.append(f"{marker}{phase.get('name', 'Unknown')}: {phase.get('description', '')[:100]}...")
        
        # Previous chapters summary
        chapters = self.db.query(Chapter).filter(
            Chapter.story_id == story_id
        ).order_by(Chapter.chapter_number).all()
        
        if chapters:
            context_parts.append("\nPREVIOUS CHAPTERS:")
            for ch in chapters[-5:]:  # Last 5 chapters
                summary = ch.auto_summary or ch.description or "No summary"
                context_parts.append(f"- Chapter {ch.chapter_number}: {ch.title or 'Untitled'}")
                context_parts.append(f"  {summary[:150]}...")
        
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

