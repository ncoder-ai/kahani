"""
NPC Tracking Models

Tracks NPCs (Non-Player Characters) mentioned in scenes that aren't explicitly added as characters.
Calculates importance scores and automatically includes them in context when they cross a threshold.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, JSON, Boolean, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
from .branch_aware import branch_clone_config


def _npc_mention_filter(query, fork_seq, story_id, branch_id):
    """Filter NPC mentions up to the fork point."""
    return query.filter(NPCMention.sequence_number <= fork_seq)


@branch_clone_config(
    priority=60,
    depends_on=['scenes'],
    fk_remappings={'scene_id': 'scene_id_map'},
    filter_func=_npc_mention_filter,
)
class NPCMention(Base):
    """
    Tracks individual mentions of NPCs in scenes.
    
    Stores per-scene data about NPC appearances:
    - How many times mentioned
    - Whether they have dialogue, actions, relationships
    - Context snippets from the scene
    """
    __tablename__ = "npc_mentions"
    
    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)  # Story branch
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    character_name = Column(String(255), nullable=False, index=True)
    sequence_number = Column(Integer, nullable=False)  # Scene sequence number
    
    # Mention metrics
    mention_count = Column(Integer, default=1)  # How many times mentioned in this scene
    has_dialogue = Column(Boolean, default=False)  # NPC has dialogue in this scene
    has_actions = Column(Boolean, default=False)  # NPC performs actions in this scene
    has_relationships = Column(Boolean, default=False)  # NPC has relationship interactions
    
    # Context data
    context_snippets = Column(JSON, nullable=True)  # Array of text snippets mentioning the NPC
    extracted_properties = Column(JSON, nullable=True)  # Extracted properties: role, description, etc.
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    story = relationship("Story", back_populates="npc_mentions")
    branch = relationship("StoryBranch", back_populates="npc_mentions")
    scene = relationship("Scene", back_populates="npc_mentions")
    
    # Index for efficient queries
    __table_args__ = (
        Index('idx_npc_mentions_story_name', 'story_id', 'character_name'),
        Index('idx_npc_mentions_story_scene', 'story_id', 'scene_id'),
        Index('idx_npc_mentions_branch', 'branch_id', 'character_name'),
    )
    
    def __repr__(self):
        return f"<NPCMention(story_id={self.story_id}, branch_id={self.branch_id}, character_name='{self.character_name}', scene_id={self.scene_id})>"


def _npc_tracking_filter(query, fork_seq, story_id, branch_id):
    """Filter NPC tracking records that first appeared before the fork point."""
    return query.filter(NPCTracking.first_appearance_scene <= fork_seq)


def _npc_tracking_transform(new_data, fork_seq, new_branch_id):
    """Transform NPCTracking data to clamp last_appearance_scene to fork point."""
    if new_data.get('last_appearance_scene') is not None:
        new_data['last_appearance_scene'] = min(
            new_data['last_appearance_scene'],
            fork_seq
        )
    return new_data


@branch_clone_config(
    priority=60,
    filter_func=_npc_tracking_filter,
    clone_transform=_npc_tracking_transform,
)
class NPCTracking(Base):
    """
    Aggregated tracking of NPCs across a story.

    Maintains:
    - Total mentions and scene appearances
    - Importance score (frequency + significance)
    - Extracted full character profile
    - Threshold crossing status
    """
    __tablename__ = "npc_tracking"
    
    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)  # Story branch
    character_name = Column(String(255), nullable=False, index=True)
    entity_type = Column(String(50), default="CHARACTER", nullable=True)  # CHARACTER or ENTITY
    
    # Frequency metrics
    total_mentions = Column(Integer, default=0)  # Total mentions across all scenes
    scene_count = Column(Integer, default=0)  # Number of scenes where NPC appears
    first_appearance_scene = Column(Integer, nullable=True)  # First scene sequence number
    last_appearance_scene = Column(Integer, nullable=True)  # Last scene sequence number
    
    # Significance metrics
    has_dialogue_count = Column(Integer, default=0)  # Scenes with dialogue
    has_actions_count = Column(Integer, default=0)  # Scenes with actions
    significance_score = Column(Float, default=0.0)  # Calculated significance
    
    # Importance score
    importance_score = Column(Float, default=0.0, index=True)  # Combined frequency + significance
    frequency_score = Column(Float, default=0.0)  # Frequency component
    
    # Profile data
    extracted_profile = Column(JSON, nullable=True)  # Full character profile extracted from scenes
    # Profile structure:
    # {
    #   "name": "Batman",
    #   "role": "superhero ally",
    #   "description": "...",
    #   "personality": ["determined", "vigilant"],
    #   "background": "...",
    #   "goals": "...",
    #   "relationships": {...},
    #   "appearance": "..."
    # }
    
    # Status flags
    crossed_threshold = Column(Boolean, default=False, index=True)  # Has crossed importance threshold
    user_prompted = Column(Boolean, default=False)  # User has been prompted to add as character
    profile_extracted = Column(Boolean, default=False)  # Full profile has been extracted
    converted_to_character = Column(Boolean, default=False, index=True)  # NPC has been converted to explicit character
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_calculated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    story = relationship("Story", back_populates="npc_tracking")
    branch = relationship("StoryBranch", back_populates="npc_tracking")
    
    # Index for efficient queries
    __table_args__ = (
        Index('idx_npc_tracking_story_name', 'story_id', 'character_name'),
        Index('idx_npc_tracking_branch_name', 'branch_id', 'character_name', unique=True),
        Index('idx_npc_tracking_threshold', 'story_id', 'crossed_threshold'),
    )
    
    def to_dict(self):
        """Convert to dictionary for easy serialization"""
        return {
            "id": self.id,
            "story_id": self.story_id,
            "character_name": self.character_name,
            "entity_type": self.entity_type or "CHARACTER",
            "total_mentions": self.total_mentions,
            "scene_count": self.scene_count,
            "first_appearance_scene": self.first_appearance_scene,
            "last_appearance_scene": self.last_appearance_scene,
            "has_dialogue_count": self.has_dialogue_count,
            "has_actions_count": self.has_actions_count,
            "significance_score": self.significance_score,
            "importance_score": self.importance_score,
            "frequency_score": self.frequency_score,
            "extracted_profile": self.extracted_profile or {},
            "crossed_threshold": self.crossed_threshold,
            "user_prompted": self.user_prompted,
            "profile_extracted": self.profile_extracted,
            "converted_to_character": self.converted_to_character,
            "last_calculated": self.last_calculated.isoformat() if self.last_calculated else None
        }
    
    def __repr__(self):
        return f"<NPCTracking(story_id={self.story_id}, character_name='{self.character_name}', importance_score={self.importance_score:.2f})>"


def _npc_tracking_snapshot_filter(query, fork_seq, story_id, branch_id):
    """Filter NPC tracking snapshots up to the fork point."""
    return query.filter(NPCTrackingSnapshot.scene_sequence <= fork_seq)


@branch_clone_config(
    priority=65,
    depends_on=['scenes'],
    fk_remappings={'scene_id': 'scene_id_map'},
    filter_func=_npc_tracking_snapshot_filter,
)
class NPCTrackingSnapshot(Base):
    """
    Stores per-scene snapshots of NPC tracking aggregated data.

    This enables fast rollback on scene deletion without recalculation.
    Each snapshot contains the aggregated state of all NPCs up to that scene.
    """
    __tablename__ = "npc_tracking_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_sequence = Column(Integer, nullable=False, index=True)  # For quick lookup by sequence
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)  # Story branch
    
    # Snapshot data: JSON object mapping character_name to aggregated values
    # Structure: {
    #   "character_name": {
    #     "total_mentions": int,
    #     "scene_count": int,
    #     "importance_score": float,
    #     "frequency_score": float,
    #     "significance_score": float,
    #     "first_appearance_scene": int,
    #     "last_appearance_scene": int,
    #     "has_dialogue_count": int,
    #     "has_actions_count": int,
    #     "crossed_threshold": bool,
    #     "entity_type": str,
    #     ...
    #   }
    # }
    snapshot_data = Column(JSON, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    scene = relationship("Scene", back_populates="npc_tracking_snapshots")
    story = relationship("Story", back_populates="npc_tracking_snapshots")
    branch = relationship("StoryBranch", back_populates="npc_tracking_snapshots")
    
    # Index for efficient queries
    __table_args__ = (
        Index('idx_npc_snapshot_story_sequence', 'story_id', 'scene_sequence'),
        Index('idx_npc_snapshot_branch_sequence', 'branch_id', 'scene_sequence'),
        Index('idx_npc_snapshot_scene', 'scene_id'),
    )
    
    def __repr__(self):
        npc_count = len(self.snapshot_data) if self.snapshot_data else 0
        return f"<NPCTrackingSnapshot(scene_id={self.scene_id}, branch_id={self.branch_id}, scene_sequence={self.scene_sequence}, npcs={npc_count})>"

