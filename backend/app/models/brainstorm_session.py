"""
Brainstorm Session Model

Stores AI brainstorming sessions where users explore story ideas through
conversational interaction before creating a full story.
"""
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text
from sqlalchemy.orm import relationship, attributes
from datetime import datetime

from ..database import Base


class BrainstormSession(Base):
    """
    Represents a brainstorming session for story idea exploration.
    
    Users engage in conversational brainstorming with AI to develop:
    - Story concepts and themes
    - Character ideas
    - World settings
    - Plot hooks and conflicts
    
    Once refined, extracted elements can be used to pre-populate story creation.
    """
    __tablename__ = "brainstorm_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Session metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Chat history - array of message objects: [{role: 'user'|'assistant', content: str, timestamp: str}]
    messages = Column(JSON, default=list, nullable=False)
    
    # Extracted story elements - populated during refinement phase
    # Structure matches BrainstormExtractedElements interface:
    # {
    #   genre: str, tone: str, characters: [...], scenario: str,
    #   world_setting: str, suggested_titles: [...], description: str,
    #   plot_points: [...], themes: [...], conflicts: [...]
    # }
    extracted_elements = Column(JSON, default=dict, nullable=True)
    
    # Session status: 'exploring' (chat phase), 'refining' (editing extracted elements), 'completed' (used to create story)
    status = Column(String(100), default='exploring', nullable=False, index=True)
    
    # Optional link to created story (if user proceeded to create story from this session)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=True, index=True)
    
    # Relationships
    user = relationship("User", back_populates="brainstorm_sessions")
    story = relationship("Story", back_populates="brainstorm_session", uselist=False)

    def __repr__(self):
        return f"<BrainstormSession(id={self.id}, user_id={self.user_id}, status={self.status}, messages={len(self.messages or [])})>"
    
    def add_message(self, role: str, content: str):
        """Add a message to the conversation history."""
        if not self.messages:
            self.messages = []
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.messages.append(message)
        self.updated_at = datetime.utcnow()
        
        # Mark the JSON field as modified so SQLAlchemy knows to save it
        attributes.flag_modified(self, 'messages')
    
    def get_conversation_context(self, max_messages: int = None) -> list:
        """
        Get conversation history formatted for LLM context.
        
        Args:
            max_messages: Optional limit on number of messages to return (most recent)
            
        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        if not self.messages:
            return []
        
        messages = self.messages
        if max_messages:
            messages = messages[-max_messages:]
        
        return [{"role": msg["role"], "content": msg["content"]} for msg in messages]
    
    def update_extracted_elements(self, elements: dict):
        """Update the extracted story elements."""
        self.extracted_elements = elements
        self.updated_at = datetime.utcnow()

