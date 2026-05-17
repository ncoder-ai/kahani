"""
Relationship Graph Models

Tracks character relationships as a queryable graph with history and trajectory.
- CharacterRelationship: Event log of every relationship change
- RelationshipSummary: Current state for fast lookup in context building
"""

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
from .branch_aware import branch_clone_config


def _relationship_filter(query, fork_seq, story_id, branch_id):
    """Filter relationships created before or at the fork point."""
    return query.filter(CharacterRelationship.scene_sequence <= fork_seq)


def _relationship_summary_filter(query, fork_seq, story_id, branch_id):
    """Filter relationship summaries updated before or at the fork point."""
    return query.filter(RelationshipSummary.last_scene_sequence <= fork_seq)


@branch_clone_config(
    priority=56,  # After working memory (55)
    filter_func=_relationship_filter,
)
class CharacterRelationship(Base):
    """
    Event log tracking relationship changes between two characters over time.

    Each row represents a single interaction/change in a specific scene.
    Characters are stored in alphabetical order for consistent querying.
    """
    __tablename__ = "character_relationships"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)

    # Characters involved (stored alphabetically for consistent querying)
    character_a = Column(String(255), nullable=False)
    character_b = Column(String(255), nullable=False)

    # Relationship type and strength
    # Types: stranger, acquaintance, friend, close_friend, romantic, family, professional, rival, enemy
    relationship_type = Column(String(50))
    # Strength: -1.0 (hostile) to 1.0 (intimate)
    strength = Column(Float, default=0.0)

    # Scene tracking
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    scene_sequence = Column(Integer, nullable=False)

    # What changed
    change_description = Column(Text)  # "First meeting", "Shared a secret", "Had argument"
    change_sentiment = Column(String(20))  # positive, negative, neutral

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes for efficient queries
    __table_args__ = (
        Index('idx_relationship_story_chars', 'story_id', 'character_a', 'character_b'),
        Index('idx_relationship_story_branch', 'story_id', 'branch_id'),
        Index('idx_relationship_scene_seq', 'story_id', 'scene_sequence'),
    )

    # Relationships
    story = relationship("Story", back_populates="character_relationships")
    branch = relationship("StoryBranch", back_populates="character_relationships")
    scene = relationship("Scene", back_populates="character_relationships")

    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "character_a": self.character_a,
            "character_b": self.character_b,
            "type": self.relationship_type,
            "strength": self.strength,
            "scene_sequence": self.scene_sequence,
            "change": self.change_description,
            "sentiment": self.change_sentiment,
        }

    def __repr__(self):
        return f"<CharacterRelationship({self.character_a} <-> {self.character_b}, {self.relationship_type}, scene={self.scene_sequence})>"


@branch_clone_config(
    priority=57,  # After CharacterRelationship (56)
    filter_func=_relationship_summary_filter,
)
class RelationshipSummary(Base):
    """
    Current state summary of a relationship (computed from history).

    One row per character pair per story/branch.
    Used for fast lookup during context building.
    """
    __tablename__ = "relationship_summaries"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)

    # Characters (stored alphabetically)
    character_a = Column(String(255), nullable=False)
    character_b = Column(String(255), nullable=False)

    # Current state (latest)
    current_type = Column(String(50))
    current_strength = Column(Float, default=0.0)

    # Arc tracking
    initial_type = Column(String(50))      # How they started
    initial_strength = Column(Float)
    trajectory = Column(String(20))         # warming, cooling, stable, volatile
    total_interactions = Column(Integer, default=0)

    # Last interaction
    last_scene_sequence = Column(Integer)
    last_change = Column(Text)

    # Computed arc summary
    arc_summary = Column(Text)  # "strangers -> acquaintances -> friends (warming over 8 scenes)"

    # Metadata
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Unique constraint on story + branch + character pair
    __table_args__ = (
        Index('idx_relsummary_story_chars', 'story_id', 'branch_id', 'character_a', 'character_b', unique=True),
        Index('idx_relsummary_story_branch', 'story_id', 'branch_id'),
    )

    # Relationships
    story = relationship("Story", back_populates="relationship_summaries")
    branch = relationship("StoryBranch", back_populates="relationship_summaries")

    def to_dict(self):
        """Convert to dictionary for context building."""
        return {
            "characters": [self.character_a, self.character_b],
            "type": self.current_type,
            "strength": self.current_strength,
            "trajectory": self.trajectory,
            "arc": self.arc_summary,
            "last_change": self.last_change,
            "interactions": self.total_interactions,
            "last_scene": self.last_scene_sequence,
        }

    def __repr__(self):
        return f"<RelationshipSummary({self.character_a} <-> {self.character_b}, {self.current_type}, strength={self.current_strength})>"
