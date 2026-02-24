"""
Scene Event Model

Tracks significant events extracted from each scene for keyword-based retrieval.
Provides an unconstrained event index for finding specific past events during
recall queries — complementing embedding-based semantic search with exact keyword matching.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
from .branch_aware import branch_clone_config


def _scene_event_filter(query, fork_seq, story_id, branch_id):
    """Filter scene events that occurred before the fork point."""
    return query.filter(SceneEvent.scene_sequence <= fork_seq)


@branch_clone_config(
    priority=86,
    depends_on=['scenes'],
    fk_remappings={'scene_id': 'scene_id_map'},
    filter_func=_scene_event_filter,
)
class SceneEvent(Base):
    """
    Tracks significant events extracted from story scenes.

    Each scene produces 2-6 events describing what HAPPENED — actions, discoveries,
    arrivals, departures, gifts, injuries, etc. Events are searched via keyword
    matching (not embeddings) to pin relevant scenes during multi-query retrieval.

    characters_involved uses name strings (not FK IDs) to handle NPCs
    that aren't in the characters table.
    """
    __tablename__ = "scene_events"

    id = Column(Integer, primary_key=True, index=True)

    # Story and branch context
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)
    world_id = Column(Integer, ForeignKey("worlds.id", ondelete="CASCADE"), nullable=True, index=True)  # For cross-story world-scope search
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_sequence = Column(Integer, nullable=False, index=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True)

    # Event data
    event_text = Column(String(500), nullable=False)
    characters_involved = Column(JSON, nullable=True)  # List of name strings, e.g. ["Mira", "Samir"]

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    story = relationship("Story", back_populates="scene_events")
    branch = relationship("StoryBranch", back_populates="scene_events")
    scene = relationship("Scene", back_populates="scene_events")

    # Composite indexes for efficient lookups
    __table_args__ = (
        Index('ix_scene_events_story_sequence', 'story_id', 'scene_sequence'),
        Index('ix_scene_events_story_branch', 'story_id', 'branch_id'),
        Index('ix_scene_events_scene', 'scene_id'),
    )

    def __repr__(self):
        chars = self.characters_involved or []
        return f"<SceneEvent(id={self.id}, scene_seq={self.scene_sequence}, chars={chars}, text='{self.event_text[:50]}...')>"

    def to_dict(self):
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "story_id": self.story_id,
            "branch_id": self.branch_id,
            "scene_id": self.scene_id,
            "scene_sequence": self.scene_sequence,
            "chapter_id": self.chapter_id,
            "event_text": self.event_text,
            "characters_involved": self.characters_involved or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
