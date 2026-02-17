"""
Character Interaction Model

Tracks significant interactions between character pairs throughout a story.
Used to maintain factual history of what has and hasn't occurred between characters.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
from .branch_aware import branch_clone_config


def _character_interaction_filter(query, fork_seq, story_id, branch_id):
    """Filter character interactions that first occurred before the fork point."""
    return query.filter(CharacterInteraction.first_occurrence_scene <= fork_seq)


@branch_clone_config(
    priority=85,
    filter_func=_character_interaction_filter,
)
class CharacterInteraction(Base):
    """
    Tracks significant interactions between character pairs.
    
    This provides an authoritative record of specific interactions that have occurred,
    enabling the LLM to know exactly what has happened (and by omission, what has NOT).
    
    The interaction_type values are user-defined per story via the story's
    interaction_types configuration, allowing genre-appropriate tracking.
    """
    __tablename__ = "character_interactions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Story and branch context
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # The two characters involved (order doesn't matter - we normalize to lower ID first)
    character_a_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    character_b_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # The type of interaction (user-defined via story settings)
    interaction_type = Column(String(100), nullable=False, index=True)
    
    # When this interaction first occurred
    first_occurrence_scene = Column(Integer, nullable=False)
    
    # Brief factual description of the interaction
    description = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    story = relationship("Story", back_populates="character_interactions")
    branch = relationship("StoryBranch", back_populates="character_interactions")
    character_a = relationship("Character", foreign_keys=[character_a_id])
    character_b = relationship("Character", foreign_keys=[character_b_id])
    
    # Composite index for efficient lookups
    __table_args__ = (
        Index('ix_character_interactions_story_chars', 'story_id', 'character_a_id', 'character_b_id'),
        Index('ix_character_interactions_story_type', 'story_id', 'interaction_type'),
    )
    
    def __repr__(self):
        return f"<CharacterInteraction(id={self.id}, story_id={self.story_id}, type='{self.interaction_type}', chars={self.character_a_id}-{self.character_b_id})>"
    
    def to_dict(self):
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "story_id": self.story_id,
            "branch_id": self.branch_id,
            "character_a_id": self.character_a_id,
            "character_b_id": self.character_b_id,
            "interaction_type": self.interaction_type,
            "first_occurrence_scene": self.first_occurrence_scene,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }



