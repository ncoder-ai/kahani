"""
Writing Style Preset Model

Stores user-customizable writing style presets that control how the AI writes stories.
Only the system prompts are customizable - user prompts remain locked for app stability.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class WritingStylePreset(Base):
    """
    User's writing style preset for AI story generation.
    
    Attributes:
        id: Primary key
        user_id: Foreign key to users table
        name: User-friendly name for the preset (e.g., "Epic Fantasy", "Cozy Romance")
        description: Optional description of the writing style
        system_prompt: The main system prompt that controls writing style, tone, NSFW settings
        summary_system_prompt: Optional override for story summary generation
        is_active: Whether this preset is currently active for the user (only one can be active)
        created_at: Timestamp when preset was created
        updated_at: Timestamp when preset was last modified
    """
    __tablename__ = "writing_style_presets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=False)
    summary_system_prompt = Column(Text, nullable=True)
    pov = Column(String(20), nullable=True)  # 'first', 'second', 'third', or None for default
    prose_style = Column(String(100), nullable=True, default='balanced')  # Writing style: balanced, dialogue_forward, etc.
    is_active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    user = relationship("User", back_populates="writing_style_presets")

    # Indexes
    __table_args__ = (
        Index('idx_writing_presets_user_active', 'user_id', 'is_active'),
    )

    def __repr__(self):
        return f"<WritingStylePreset(id={self.id}, user_id={self.user_id}, name='{self.name}', active={self.is_active})>"

    def to_dict(self):
        """Convert preset to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "summary_system_prompt": self.summary_system_prompt,
            "pov": self.pov,
            "prose_style": self.prose_style,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

