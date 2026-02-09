"""
Working Memory Model

Tracks scene-to-scene continuity details (micro-level focus).
Unlike PlotEvent (major story threads), this tracks:
- Recent narrative focus
- Pending micro-items (objects picked up, interrupted actions)
- Characters needing narrative attention
"""

from sqlalchemy import Column, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
from .branch_aware import branch_clone_config


def _working_memory_filter(query, fork_seq, story_id, branch_id):
    """Filter working memory updated before or at the fork point."""
    return query.filter(WorkingMemory.last_scene_sequence <= fork_seq)


@branch_clone_config(
    priority=55,  # After character states (50)
    filter_func=_working_memory_filter,
)
class WorkingMemory(Base):
    """
    Tracks scene-to-scene narrative focus for micro-level continuity.

    NOTE: active_threads are NOT stored here - they are derived from
    PlotEvent.is_resolved=False to avoid duplication.

    This model tracks:
    - recent_focus: What was important in last few scenes
    - pending_items: Concrete items mentioned but not acted on
    - character_spotlight: Characters needing narrative attention
    """
    __tablename__ = "working_memory"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)

    # Recent focus (what was emotionally/narratively important in last few scenes)
    # Example: ["Character A's inner conflict", "The confrontation with rival"]
    recent_focus = Column(JSON, nullable=True, default=list)

    # Pending micro-items (mentioned but not acted on - needs follow-up)
    # Example: ["The letter was picked up but not read", "Phone rang but wasn't answered"]
    pending_items = Column(JSON, nullable=True, default=list)

    # Character spotlight (who needs narrative attention next)
    # Example: {"Alice": "hasn't spoken in 2 scenes", "Bob": "just had revelation"}
    character_spotlight = Column(JSON, nullable=True, default=dict)

    # Tracking
    last_scene_sequence = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    story = relationship("Story", back_populates="working_memory")
    branch = relationship("StoryBranch", back_populates="working_memory")
    chapter = relationship("Chapter", back_populates="working_memory")

    def to_dict(self):
        """Convert to dictionary for context building."""
        return {
            "recent_focus": self.recent_focus or [],
            "pending_items": self.pending_items or [],
            "character_spotlight": self.character_spotlight or {},
            "last_scene_sequence": self.last_scene_sequence
        }

    def __repr__(self):
        return f"<WorkingMemory(story_id={self.story_id}, branch_id={self.branch_id}, last_scene={self.last_scene_sequence})>"
