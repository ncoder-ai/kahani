"""
Chapter Brainstorm Session Model

Stores AI-assisted chapter planning sessions with conversation history
and extracted plot elements.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship, attributes
from sqlalchemy.sql import func
from ..database import Base


class ChapterBrainstormSession(Base):
    """
    Stores chapter brainstorming sessions for AI-assisted chapter planning.
    
    Each session tracks:
    - Conversation with AI about chapter direction
    - Structured elements confirmed by user during brainstorming
    - Extracted plot elements (summary, key events, climax, etc.)
    - Link to story arc phase
    - Status of the brainstorming process
    """
    __tablename__ = "chapter_brainstorm_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Conversation history (list of {role, content, timestamp} dicts)
    messages = Column(JSON, default=list)
    
    # Structured elements confirmed by user during brainstorming
    # Structure: {overview: str, characters: [...], tone: str, key_events: [...], ending: str}
    structured_elements = Column(JSON, default=dict)
    
    # Extracted chapter plot from conversation
    extracted_plot = Column(JSON, nullable=True)
    
    # Link to story arc phase this chapter targets
    arc_phase_id = Column(String(100), nullable=True)
    
    # User-provided summary of the prior/current chapter for context
    # This helps the AI understand what just happened before brainstorming the next chapter
    prior_chapter_summary = Column(Text, nullable=True)
    
    # Session status: 'brainstorming', 'extracted', 'applied'
    status = Column(String(50), default='brainstorming')
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    story = relationship("Story", backref="chapter_brainstorm_sessions")
    chapter = relationship("Chapter", backref="brainstorm_session", foreign_keys=[chapter_id])
    user = relationship("User", backref="chapter_brainstorm_sessions")
    
    def add_message(self, role: str, content: str):
        """Add a message to the conversation history."""
        from datetime import datetime
        if self.messages is None:
            self.messages = []
        
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
        # Mark the JSON field as modified so SQLAlchemy detects the change
        attributes.flag_modified(self, 'messages')
    
    def get_conversation_context(self):
        """Get messages formatted for LLM context."""
        return self.messages or []
    
    def update_extracted_plot(self, plot_data: dict):
        """Update the extracted plot data."""
        if self.extracted_plot is None:
            self.extracted_plot = {}
        self.extracted_plot.update(plot_data)
        attributes.flag_modified(self, 'extracted_plot')
    
    def update_structured_element(self, element_type: str, value):
        """
        Update a single structured element.
        
        Args:
            element_type: One of 'overview', 'characters', 'tone', 'key_events', 'ending'
            value: The value to set (string for most, list for characters/key_events)
        """
        if self.structured_elements is None:
            self.structured_elements = {}
        self.structured_elements[element_type] = value
        attributes.flag_modified(self, 'structured_elements')
    
    def get_structured_elements(self) -> dict:
        """Get all structured elements with defaults for missing ones."""
        defaults = {
            'overview': '',
            'characters': [],
            'tone': '',
            'key_events': [],
            'ending': ''
        }
        if self.structured_elements:
            defaults.update(self.structured_elements)
        return defaults
    
    def __repr__(self):
        return f"<ChapterBrainstormSession(id={self.id}, story_id={self.story_id}, status='{self.status}')>"

