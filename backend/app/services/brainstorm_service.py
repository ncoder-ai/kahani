"""
Brainstorm Service

Manages AI-powered brainstorming sessions for story idea exploration.
Handles conversational interactions and extraction of story elements.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime
from litellm import acompletion

from ..models.brainstorm_session import BrainstormSession
from ..models.story import Story
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


class BrainstormService:
    """
    Service for managing brainstorming sessions.
    
    Responsibilities:
    - Manage conversational brainstorming with AI
    - Track conversation history
    - Extract structured story elements from conversations
    - Generate creative suggestions
    """
    
    def __init__(self, user_id: int, user_settings: Dict[str, Any], db: Session):
        self.user_id = user_id
        self.user_settings = user_settings
        self.db = db
        self.llm_service = UnifiedLLMService()
    
    def create_session(self, pre_selected_character_ids: List[int] = None, content_rating: str = "sfw") -> BrainstormSession:
        """Create a new brainstorming session with optional pre-selected characters and content rating."""
        session = BrainstormSession(
            user_id=self.user_id,
            messages=[],
            status='exploring',
            extracted_elements={
                'preselected_character_ids': pre_selected_character_ids or [],
                'content_rating': content_rating  # Store content rating in session
            }
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        
        logger.info(f"[BRAINSTORM] Created new session {session.id} for user {self.user_id} with {len(pre_selected_character_ids or [])} pre-selected characters, content_rating={content_rating}")
        return session
    
    def get_session(self, session_id: int) -> Optional[BrainstormSession]:
        """Get a brainstorming session by ID."""
        session = self.db.query(BrainstormSession).filter(
            BrainstormSession.id == session_id,
            BrainstormSession.user_id == self.user_id
        ).first()
        if session:
            # Ensure we have the latest data from database
            self.db.refresh(session)
        return session
    
    def delete_session(self, session_id: int) -> bool:
        """Delete a brainstorming session."""
        session = self.get_session(session_id)
        if not session:
            return False
        
        self.db.delete(session)
        self.db.commit()
        logger.info(f"[BRAINSTORM] Deleted session {session_id}")
        return True
    
    async def send_message(
        self,
        session_id: int,
        user_message: str,
        generate_ideas: bool = False
    ) -> Dict[str, Any]:
        """
        Send a user message and get AI response.
        
        Args:
            session_id: The brainstorming session ID
            user_message: The user's message
            generate_ideas: If True, generate structured story ideas (title + synopsis)
            
        Returns:
            Dictionary with AI response and updated session
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Add user message to history
        session.add_message("user", user_message)
        self.db.commit()
        self.db.refresh(session)  # Refresh to ensure we have latest messages
        
        try:
            # Check if we should generate structured story ideas
            logger.info(f"[BRAINSTORM] generate_ideas={generate_ideas}, message_count={len(session.messages)}")
            if generate_ideas and len(session.messages) <= 2:
                logger.info(f"[BRAINSTORM] Generating structured story ideas for session {session_id}")
                
                # Get idea generation prompts
                system_prompt = prompt_manager.get_prompt("brainstorm.generate_ideas", "system")
                user_prompt = prompt_manager.get_prompt(
                    "brainstorm.generate_ideas", "user",
                    user_message=user_message
                )
                
                # Generate ideas with LLM
                response = await self.llm_service.generate(
                    prompt=user_prompt,
                    user_id=self.user_id,
                    user_settings=self.user_settings,
                    system_prompt=system_prompt,
                    max_tokens=self.user_settings.get('llm_settings', {}).get('max_tokens', 2048),
                    temperature=0.8
                )
                
                # Parse JSON response
                try:
                    response_clean = clean_llm_json(response)
                    logger.debug(f"[BRAINSTORM] Raw ideas response: {response[:200]}...")
                    logger.debug(f"[BRAINSTORM] Cleaned ideas response: {response_clean[:200]}...")
                    
                    ideas_data = json.loads(response_clean)
                    
                    # Format as markdown for display
                    formatted_response = "Here are 3 story directions based on your idea:\n\n"
                    for i, idea in enumerate(ideas_data.get('ideas', []), 1):
                        formatted_response += f"**Idea {i}: {idea['title']}**\n{idea['synopsis']}\n\n"
                    
                    # Save formatted response
                    session.add_message("assistant", formatted_response)
                    self.db.commit()
                    self.db.refresh(session)
                    
                    logger.info(f"[BRAINSTORM] Generated {len(ideas_data.get('ideas', []))} story ideas")
                    
                    return {
                        "session_id": session.id,
                        "user_message": user_message,
                        "ai_response": formatted_response,
                        "message_count": len(session.messages)
                    }
                    
                except json.JSONDecodeError as e:
                    logger.error(f"[BRAINSTORM] Failed to parse ideas JSON: {str(e)}")
                    logger.error(f"[BRAINSTORM] Raw response: {response}")
                    # Fall through to regular conversation mode
            
            # Regular conversation mode
            # Get conversation context (includes all messages including the just-added user message)
            conversation_history = session.get_conversation_context()
            
            # Log conversation history for debugging
            logger.debug(f"[BRAINSTORM] Session {session_id} - Conversation history: {len(conversation_history)} messages")
            if len(conversation_history) == 0:
                logger.warning(f"[BRAINSTORM] WARNING: No conversation history found for session {session_id}!")
            
            # Get prompts
            system_prompt = prompt_manager.get_prompt("brainstorm.chat", "system")
            
            # Add pre-selected character context if any
            preselected_char_ids = session.extracted_elements.get('preselected_character_ids', []) if session.extracted_elements else []
            character_context = ""
            if preselected_char_ids:
                from ..models.character import Character
                characters = self.db.query(Character).filter(Character.id.in_(preselected_char_ids)).all()
                if characters:
                    character_context = "\n\nThe user wants to use these existing characters in their story:\n"
                    for char in characters:
                        character_context += f"\n- **{char.name}**: {char.description}"
                        if char.personality_traits:
                            character_context += f" (Personality: {', '.join(char.personality_traits)})"
                    character_context += "\n\nPlease generate story ideas that incorporate these characters, while also suggesting additional characters if needed for the story."
                    logger.info(f"[BRAINSTORM] Added {len(characters)} pre-selected characters to context")
            
            # Get LLM client
            client = self.llm_service.get_user_client(self.user_id, self.user_settings)

            # Build messages array for proper multi-turn conversation
            messages = []

            # Handle system prompt with NSFW filter if needed
            # Check both user permission AND session's content_rating
            user_allow_nsfw = self.user_settings.get('allow_nsfw', False) if self.user_settings else False
            session_content_rating = session.extracted_elements.get('content_rating', 'sfw') if session.extracted_elements else 'sfw'
            # Effective NSFW = user allows AND session is rated NSFW
            effective_allow_nsfw = user_allow_nsfw and session_content_rating.lower() == 'nsfw'

            if system_prompt and system_prompt.strip():
                final_system_prompt = system_prompt.strip() + character_context
                # Inject NSFW filter if content should be filtered
                if should_inject_nsfw_filter(effective_allow_nsfw):
                    final_system_prompt = final_system_prompt + "\n\n" + get_nsfw_prevention_prompt()
                messages.append({"role": "system", "content": final_system_prompt})
            elif should_inject_nsfw_filter(effective_allow_nsfw):
                # No system prompt provided, but we need to inject NSFW filter
                messages.append({"role": "system", "content": get_nsfw_prevention_prompt() + character_context})

            # Add all conversation history as proper message turns
            logger.debug(f"[BRAINSTORM] Building messages array from {len(conversation_history)} conversation messages")
            if len(conversation_history) == 0:
                logger.error(f"[BRAINSTORM] ERROR: Conversation history is empty! This will cause context loss!")

            for msg in conversation_history:
                # Map our roles to chat API roles
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    messages.append({"role": "user", "content": content})
                elif role == "assistant":
                    messages.append({"role": "assistant", "content": content})
                else:
                    logger.warning(f"[BRAINSTORM] Unknown message role: {role}, skipping message")

            logger.debug(f"[BRAINSTORM] Final messages array has {len(messages)} messages (1 system + {len(messages)-1} conversation)")

            # Get generation parameters
            gen_params = client.get_generation_params(
                self.user_settings.get('generation_preferences', {}).get('max_tokens', 1000),
                0.8  # Higher temperature for creative brainstorming
            )
            gen_params["messages"] = messages

            # Get timeout
            user_timeout = None
            if self.user_settings:
                llm_settings = self.user_settings.get('llm_settings', {})
                user_timeout = llm_settings.get('timeout_total')
            timeout_value = user_timeout if user_timeout is not None else settings.llm_timeout_total
            gen_params["timeout"] = timeout_value

            # Call LLM with proper chat messages format
            response = await acompletion(**gen_params)
            ai_response = response.choices[0].message.content

            # Save assistant response to conversation history
            session.add_message("assistant", ai_response)
            self.db.commit()
            self.db.refresh(session)

            logger.info(f"[BRAINSTORM] Session {session_id} - exchanged messages, total: {len(session.messages)}")
            
            return {
                "session_id": session.id,
                "user_message": user_message,
                "ai_response": ai_response,
                "message_count": len(session.messages)
            }
            
        except Exception as e:
            logger.error(f"[BRAINSTORM] Error in session {session_id}: {str(e)}")
            raise
    
    async def extract_elements(
        self,
        session_id: int
    ) -> Dict[str, Any]:
        """
        Extract structured story elements from conversation.
        
        Analyzes the full conversation history and extracts:
        - Genre and tone
        - Character concepts
        - World/setting details
        - Core conflicts and themes
        - Plot hooks
        - Title suggestions
        
        Args:
            session_id: The brainstorming session ID
            
        Returns:
            Dictionary of extracted story elements
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if not session.messages or len(session.messages) < 2:
            raise ValueError("Not enough conversation to extract elements")
        
        try:
            # Format conversation for extraction
            conversation_text = self._format_conversation_for_extraction(session.messages)
            
            # Get extraction prompts
            system_prompt = prompt_manager.get_prompt("brainstorm.extract", "system")
            user_prompt = prompt_manager.get_prompt(
                "brainstorm.extract", "user",
                conversation=conversation_text
            )
            
            # Call LLM to extract elements
            response = await self.llm_service.generate(
                prompt=user_prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt=system_prompt,
                max_tokens=self.user_settings.get('llm_settings', {}).get('max_tokens', 2048),
                temperature=0.3  # Lower temperature for more structured extraction
            )
            
            # Parse JSON response
            response_clean = clean_llm_json(response)
            logger.debug(f"[BRAINSTORM] Raw LLM response: {response[:500]}...")
            logger.debug(f"[BRAINSTORM] Cleaned response: {response_clean[:500]}...")
            
            extracted_elements = json.loads(response_clean)
            logger.info(f"[BRAINSTORM] Parsed elements: {json.dumps(extracted_elements, indent=2)}")
            
            # Validate and normalize extracted elements
            normalized_elements = self._normalize_extracted_elements(extracted_elements)
            logger.info(f"[BRAINSTORM] Normalized elements: {json.dumps(normalized_elements, indent=2)}")
            
            # Update session with extracted elements
            session.update_extracted_elements(normalized_elements)
            session.status = 'refining'
            self.db.commit()
            
            logger.info(f"[BRAINSTORM] Extracted elements from session {session_id}")
            logger.debug(f"[BRAINSTORM] Elements: {json.dumps(normalized_elements, indent=2)}")
            
            return {
                "session_id": session.id,
                "elements": normalized_elements,
                "status": session.status
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"[BRAINSTORM] Failed to parse extraction response: {str(e)}")
            logger.error(f"[BRAINSTORM] Raw response: {response}")
            raise ValueError("Failed to extract elements - invalid response format")
        except Exception as e:
            logger.error(f"[BRAINSTORM] Error extracting elements: {str(e)}")
            raise
    
    def update_elements(
        self,
        session_id: int,
        updated_elements: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update extracted elements (user refinement).
        
        Args:
            session_id: The brainstorming session ID
            updated_elements: The updated story elements
            
        Returns:
            Updated session data
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Normalize and update
        normalized_elements = self._normalize_extracted_elements(updated_elements)
        session.update_extracted_elements(normalized_elements)
        self.db.commit()
        
        logger.info(f"[BRAINSTORM] Updated elements for session {session_id}")
        
        return {
            "session_id": session.id,
            "elements": normalized_elements
        }
    
    def mark_completed(self, session_id: int, story_id: int) -> BrainstormSession:
        """
        Mark session as completed and link to created story.
        
        Args:
            session_id: The brainstorming session ID
            story_id: The ID of the story created from this session
            
        Returns:
            Updated session
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        session.status = 'completed'
        session.story_id = story_id
        self.db.commit()
        
        logger.info(f"[BRAINSTORM] Marked session {session_id} as completed, linked to story {story_id}")
        return session
    
    def _format_conversation_for_extraction(self, messages: List[Dict]) -> str:
        """Format conversation history for extraction prompt."""
        formatted = []
        for msg in messages:
            role = "User" if msg["role"] == "user" else "AI"
            content = msg["content"]
            formatted.append(f"{role}: {content}")
        return "\n\n".join(formatted)
    
    def _normalize_extracted_elements(self, elements: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize and validate extracted story elements.
        
        Ensures all expected fields are present with proper defaults.
        """
        normalized = {
            "genre": elements.get("genre", ""),
            "tone": elements.get("tone", ""),
            "characters": elements.get("characters", []),
            "scenario": elements.get("scenario", ""),
            "world_setting": elements.get("world_setting", ""),
            "suggested_titles": elements.get("suggested_titles", []),
            "description": elements.get("description", ""),
            "plot_points": elements.get("plot_points", []),
            "themes": elements.get("themes", []),
            "conflicts": elements.get("conflicts", [])
        }
        
        # Normalize characters to expected format
        normalized_characters = []
        for char in normalized["characters"]:
            if isinstance(char, dict):
                char_data = {
                    "name": char.get("name", ""),
                    "role": char.get("role", "other"),
                    "description": char.get("description", ""),
                    "gender": char.get("gender", ""),
                    "personality_traits": char.get("personality_traits", []),
                    "background": char.get("background", ""),
                    "goals": char.get("goals", ""),
                    "fears": char.get("fears", ""),
                    "appearance": char.get("appearance", ""),
                    "suggested_voice_style": char.get("suggested_voice_style", ""),
                }
                normalized_characters.append(char_data)
        normalized["characters"] = normalized_characters
        
        # Ensure lists are actually lists
        for list_field in ["characters", "suggested_titles", "plot_points", "themes", "conflicts"]:
            if not isinstance(normalized[list_field], list):
                normalized[list_field] = []
        
        return normalized
    
    def get_user_sessions(self, include_completed: bool = False) -> List[Dict[str, Any]]:
        """
        Get all brainstorming sessions for the current user.
        
        Args:
            include_completed: If True, include completed sessions
            
        Returns:
            List of session summaries
        """
        query = self.db.query(BrainstormSession).filter(
            BrainstormSession.user_id == self.user_id
        )
        
        if not include_completed:
            query = query.filter(BrainstormSession.status != 'completed')
        
        sessions = query.order_by(BrainstormSession.updated_at.desc()).all()
        
        result = []
        for session in sessions:
            # Generate a summary from the conversation
            summary = self._generate_session_summary(session)
            
            result.append({
                "id": session.id,
                "status": session.status,
                "message_count": len(session.messages) if session.messages else 0,
                "summary": summary,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "updated_at": session.updated_at.isoformat() if session.updated_at else None,
                "story_id": session.story_id,
                "has_extracted_elements": bool(session.extracted_elements and 
                    session.extracted_elements.get('genre') or 
                    session.extracted_elements.get('characters'))
            })
        
        logger.info(f"[BRAINSTORM] Retrieved {len(result)} sessions for user {self.user_id}")
        return result
    
    def _generate_session_summary(self, session: BrainstormSession) -> str:
        """Generate a brief summary of the brainstorming session."""
        if not session.messages:
            return "New brainstorming session"
        
        # Get the first user message as the topic
        first_user_msg = None
        for msg in session.messages:
            if msg.get('role') == 'user':
                first_user_msg = msg.get('content', '')
                break
        
        if first_user_msg:
            # Truncate to first 100 chars
            summary = first_user_msg[:100]
            if len(first_user_msg) > 100:
                summary += "..."
            return summary
        
        # If extracted elements exist, use genre/description
        if session.extracted_elements:
            genre = session.extracted_elements.get('genre', '')
            desc = session.extracted_elements.get('description', '')
            if genre and desc:
                return f"{genre}: {desc[:80]}..."
            elif genre:
                return f"{genre} story"
        
        return f"Brainstorming session ({len(session.messages)} messages)"
    
    async def generate_story_arc(
        self,
        story_id: int,
        structure_type: str = 'three_act'
    ) -> Dict[str, Any]:
        """
        Generate a story arc for an existing story.
        
        Args:
            story_id: The story ID to generate arc for
            structure_type: Type of arc structure (three_act, five_act, hero_journey)
            
        Returns:
            Generated story arc data
        """
        # Get the story
        story = self.db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == self.user_id
        ).first()
        
        if not story:
            raise ValueError(f"Story {story_id} not found")
        
        # Build character list for prompt
        characters_text = ""
        if story.story_characters:
            for sc in story.story_characters:
                char = sc.character
                if char:
                    characters_text += f"- {char.name} ({sc.role or 'unknown role'}): {char.description or 'No description'}\n"
        
        # Get arc generation prompts
        system_prompt = prompt_manager.get_prompt("brainstorm.story_arc", "system")
        user_prompt = prompt_manager.get_prompt(
            "brainstorm.story_arc", "user",
            structure_type=structure_type,
            title=story.title or "Untitled",
            genre=story.genre or "General Fiction",
            tone=story.tone or "Balanced",
            description=story.description or story.initial_premise or "",
            characters=characters_text or "No characters defined yet",
            scenario=story.scenario or story.initial_premise or "",
            themes=", ".join(story.story_context.get('themes', [])) if story.story_context else "",
            conflicts=", ".join(story.story_context.get('conflicts', [])) if story.story_context else ""
        )
        
        try:
            # Call LLM to generate arc
            response = await self.llm_service.generate(
                prompt=user_prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt=system_prompt,
                max_tokens=self.user_settings.get('llm_settings', {}).get('max_tokens', 2048),
                temperature=0.7
            )
            
            # Parse JSON response
            response_clean = clean_llm_json(response)
            arc_data = json.loads(response_clean)
            
            # Add timestamps
            arc_data['generated_at'] = datetime.utcnow().isoformat()
            arc_data['last_modified_at'] = datetime.utcnow().isoformat()
            
            # Save to story
            story.story_arc = arc_data
            self.db.commit()
            
            logger.info(f"[BRAINSTORM] Generated {structure_type} story arc for story {story_id}")
            
            return {
                "story_id": story_id,
                "arc": arc_data
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"[BRAINSTORM] Failed to parse arc JSON: {str(e)}")
            logger.error(f"[BRAINSTORM] Raw response: {response}")
            raise ValueError("Failed to generate story arc - invalid response format")
        except Exception as e:
            logger.error(f"[BRAINSTORM] Error generating story arc: {str(e)}")
            raise
    
    def update_story_arc(
        self,
        story_id: int,
        arc_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update the story arc (user edits).
        
        Args:
            story_id: The story ID
            arc_data: Updated arc data
            
        Returns:
            Updated arc data
        """
        story = self.db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == self.user_id
        ).first()
        
        if not story:
            raise ValueError(f"Story {story_id} not found")
        
        # Update timestamp
        arc_data['last_modified_at'] = datetime.utcnow().isoformat()
        
        # Preserve generated_at if it exists
        if story.story_arc and 'generated_at' in story.story_arc:
            arc_data['generated_at'] = story.story_arc['generated_at']
        
        story.update_story_arc(arc_data)
        self.db.commit()
        
        logger.info(f"[BRAINSTORM] Updated story arc for story {story_id}")
        
        return {
            "story_id": story_id,
            "arc": arc_data
        }
    
    def get_story_arc(self, story_id: int) -> Optional[Dict[str, Any]]:
        """
        Get the story arc for a story.
        
        Args:
            story_id: The story ID
            
        Returns:
            Story arc data or None
        """
        story = self.db.query(Story).filter(
            Story.id == story_id,
            Story.owner_id == self.user_id
        ).first()
        
        if not story:
            raise ValueError(f"Story {story_id} not found")
        
        return story.story_arc
    
    async def generate_arc_from_session(
        self,
        session_id: int,
        structure_type: str = 'three_act'
    ) -> Dict[str, Any]:
        """
        Generate a story arc from brainstorm session's extracted elements.
        
        This allows generating an arc before the story is created.
        
        Args:
            session_id: The brainstorm session ID
            structure_type: Type of arc structure (three_act, five_act, hero_journey)
            
        Returns:
            Generated story arc data
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if not session.extracted_elements:
            raise ValueError("Session has no extracted elements. Please extract story elements first.")
        
        elements = session.extracted_elements
        
        # Build character list for prompt
        characters_text = ""
        if elements.get('characters'):
            for char in elements['characters']:
                name = char.get('name', 'Unknown')
                role = char.get('role', 'unknown role')
                desc = char.get('description', 'No description')
                characters_text += f"- {name} ({role}): {desc}\n"
        
        # Get themes and conflicts
        themes = ", ".join(elements.get('themes', []))
        conflicts = ", ".join(elements.get('conflicts', []))
        plot_points = "\n".join([f"- {p}" for p in elements.get('plot_points', [])])
        
        # Get arc generation prompts
        system_prompt = prompt_manager.get_prompt("brainstorm.story_arc", "system")
        user_prompt = prompt_manager.get_prompt(
            "brainstorm.story_arc", "user",
            structure_type=structure_type,
            title=elements.get('selectedTitle') or elements.get('suggested_titles', ['Untitled'])[0] if elements.get('suggested_titles') else "Untitled",
            genre=elements.get('genre', 'General Fiction'),
            tone=elements.get('tone', 'Balanced'),
            description=elements.get('description', ''),
            characters=characters_text or "No characters defined yet",
            scenario=elements.get('scenario', ''),
            themes=themes,
            conflicts=conflicts,
            plot_points=plot_points,
            world_setting=elements.get('world_setting', '')
        )
        
        try:
            # Call LLM to generate arc
            response = await self.llm_service.generate(
                prompt=user_prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt=system_prompt,
                max_tokens=self.user_settings.get('llm_settings', {}).get('max_tokens', 2048),
                temperature=0.7
            )
            
            # Parse JSON response
            response_clean = clean_llm_json(response)
            arc_data = json.loads(response_clean)
            
            # Ensure structure_type is set
            arc_data['structure_type'] = structure_type
            
            # Add timestamps
            arc_data['generated_at'] = datetime.utcnow().isoformat()
            arc_data['last_modified_at'] = datetime.utcnow().isoformat()
            
            # Save to session's extracted elements
            elements['story_arc'] = arc_data
            session.update_extracted_elements(elements)
            self.db.commit()
            
            logger.info(f"[BRAINSTORM] Generated {structure_type} story arc from session {session_id}")
            
            return {
                "session_id": session_id,
                "arc": arc_data
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"[BRAINSTORM] Failed to parse arc JSON: {str(e)}")
            logger.error(f"[BRAINSTORM] Raw response: {response}")
            raise ValueError("Failed to generate story arc - invalid response format")
        except Exception as e:
            logger.error(f"[BRAINSTORM] Error generating story arc from session: {str(e)}")
            raise

