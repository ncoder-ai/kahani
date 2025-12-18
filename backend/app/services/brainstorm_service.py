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
    
    def create_session(self) -> BrainstormSession:
        """Create a new brainstorming session."""
        session = BrainstormSession(
            user_id=self.user_id,
            messages=[],
            status='exploring'
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        
        logger.info(f"[BRAINSTORM] Created new session {session.id} for user {self.user_id}")
        return session
    
    def get_session(self, session_id: int) -> Optional[BrainstormSession]:
        """Get a brainstorming session by ID."""
        session = self.db.query(BrainstormSession).filter(
            BrainstormSession.id == session_id,
            BrainstormSession.user_id == self.user_id
        ).first()
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
        user_message: str
    ) -> Dict[str, Any]:
        """
        Send a user message and get AI response.
        
        Args:
            session_id: The brainstorming session ID
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
        self.db.refresh(session)  # Refresh to ensure we have latest messages
        
        try:
            # Get conversation context (includes all messages including the just-added user message)
            conversation_history = session.get_conversation_context()
            
            # Debug: Log conversation history
            logger.debug(f"[BRAINSTORM] Session {session_id} - Conversation history: {len(conversation_history)} messages")
            for i, msg in enumerate(conversation_history):
                logger.debug(f"[BRAINSTORM] Message {i}: {msg['role']} - {msg['content'][:50]}...")
            
            # Get prompts
            system_prompt = prompt_manager.get_prompt("brainstorm.chat", "system")
            
            # Get LLM client to check completion mode
            client = self.llm_service.get_user_client(self.user_id, self.user_settings)
            
            # For chat mode, use proper messages array for multi-turn conversation
            if client.completion_mode == "chat":
                # Build messages array for proper multi-turn conversation
                messages = []
                
                # Handle system prompt with NSFW filter if needed
                user_allow_nsfw = self.user_settings.get('allow_nsfw', False) if self.user_settings else False
                
                if system_prompt and system_prompt.strip():
                    final_system_prompt = system_prompt.strip()
                    # Inject NSFW filter if user doesn't have NSFW permissions
                    if should_inject_nsfw_filter(user_allow_nsfw):
                        final_system_prompt = final_system_prompt + "\n\n" + get_nsfw_prevention_prompt()
                    messages.append({"role": "system", "content": final_system_prompt})
                elif should_inject_nsfw_filter(user_allow_nsfw):
                    # No system prompt provided, but we need to inject NSFW filter
                    messages.append({"role": "system", "content": get_nsfw_prevention_prompt()})
                
                # Add all conversation history as proper message turns
                logger.debug(f"[BRAINSTORM] Building messages array from {len(conversation_history)} conversation messages")
                for msg in conversation_history:
                    # Map our roles to chat API roles
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role == "user":
                        messages.append({"role": "user", "content": content})
                    elif role == "assistant":
                        messages.append({"role": "assistant", "content": content})
                    else:
                        logger.warning(f"[BRAINSTORM] Unknown message role: {role}")
                
                logger.debug(f"[BRAINSTORM] Final messages array has {len(messages)} messages (including system)")
                logger.debug(f"[BRAINSTORM] Last 3 messages: {messages[-3:] if len(messages) >= 3 else messages}")
                
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
            else:
                # Text completion mode - build conversation as text (fallback)
                conversation_text = ""
                for msg in conversation_history[:-1]:  # Exclude the just-added user message
                    role_label = "User" if msg["role"] == "user" else "AI"
                    conversation_text += f"{role_label}: {msg['content']}\n\n"
                
                # Add current user message
                conversation_text += f"User: {user_message}\n\nAI:"
                
                # Generate AI response using standard method
                ai_response = await self.llm_service.generate(
                    prompt=conversation_text,
                    user_id=self.user_id,
                    user_settings=self.user_settings,
                    system_prompt=system_prompt,
                    max_tokens=self.user_settings.get('generation_preferences', {}).get('max_tokens', 1000),
                    temperature=0.8  # Higher temperature for creative brainstorming
                )
            
            # Add AI response to history
            session.add_message("assistant", ai_response)
            self.db.commit()
            
            logger.info(f"[BRAINSTORM] Session {session_id} - exchanged messages")
            
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
                max_tokens=2000,
                temperature=0.3  # Lower temperature for more structured extraction
            )
            
            # Parse JSON response
            response_clean = clean_llm_json(response)
            extracted_elements = json.loads(response_clean)
            
            # Validate and normalize extracted elements
            normalized_elements = self._normalize_extracted_elements(extracted_elements)
            
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
                normalized_characters.append({
                    "name": char.get("name", ""),
                    "role": char.get("role", "other"),
                    "description": char.get("description", ""),
                    "personality_traits": char.get("personality_traits", [])
                })
        normalized["characters"] = normalized_characters
        
        # Ensure lists are actually lists
        for list_field in ["characters", "suggested_titles", "plot_points", "themes", "conflicts"]:
            if not isinstance(normalized[list_field], list):
                normalized[list_field] = []
        
        return normalized

