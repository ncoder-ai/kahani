"""
Contradiction Model

Tracks detected continuity errors between scene extractions.
Used for:
- location_jump: Character moved without travel scene
- knowledge_leak: Character knows something they shouldn't
- state_regression: State reverted without explanation
- timeline_error: Event order inconsistency
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
from .branch_aware import branch_clone_config


def _contradiction_filter(query, fork_seq, story_id, branch_id):
    """Filter contradictions up to and including the fork point."""
    return query.filter(Contradiction.scene_sequence <= fork_seq)


@branch_clone_config(
    priority=58,  # After relationship summaries (57)
    filter_func=_contradiction_filter,
)
class Contradiction(Base):
    """
    Records detected continuity errors for review.

    Contradictions are logged but don't block scene generation.
    They can be reviewed and marked as resolved with an explanation.
    """
    __tablename__ = "contradictions"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)
    scene_sequence = Column(Integer, nullable=False)

    # Contradiction details
    contradiction_type = Column(String(50), nullable=False)  # location_jump, knowledge_leak, etc.
    character_name = Column(String(255), nullable=True)  # Which character is affected

    previous_value = Column(Text, nullable=True)  # Previous state value
    current_value = Column(Text, nullable=True)   # New contradicting value

    severity = Column(String(20), default="warning")  # info, warning, error
    resolved = Column(Boolean, default=False, index=True)
    resolution_note = Column(Text, nullable=True)  # Explanation when resolved

    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    story = relationship("Story", back_populates="contradictions")
    branch = relationship("StoryBranch", back_populates="contradictions")

    def to_dict(self):
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "story_id": self.story_id,
            "branch_id": self.branch_id,
            "scene_sequence": self.scene_sequence,
            "contradiction_type": self.contradiction_type,
            "character_name": self.character_name,
            "previous_value": self.previous_value,
            "current_value": self.current_value,
            "severity": self.severity,
            "resolved": self.resolved,
            "resolution_note": self.resolution_note,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None
        }

    def __repr__(self):
        return f"<Contradiction(id={self.id}, type={self.contradiction_type}, char={self.character_name}, resolved={self.resolved})>"
