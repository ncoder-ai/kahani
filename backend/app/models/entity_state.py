"""
Entity State Models

Tracks the current state of characters, locations, and objects throughout the story.
Provides authoritative, up-to-date information for maintaining consistency.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
from .branch_aware import branch_clone_config


def _character_state_filter(query, fork_seq, story_id, branch_id):
    """Filter character states updated before or at the fork point."""
    return query.filter(CharacterState.last_updated_scene <= fork_seq)


@branch_clone_config(
    priority=50,
    filter_func=_character_state_filter,
)
class CharacterState(Base):
    """
    Tracks the current state of a character in a story.
    
    Updated after each scene to maintain an authoritative snapshot of:
    - Physical state (location, condition, appearance)
    - Emotional state (feelings, goals, conflicts)
    - Relationships (with other characters)
    - Knowledge (what they know)
    - Possessions (items they carry)
    - Character arc progress
    """
    __tablename__ = "character_states"
    
    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)  # Story branch
    last_updated_scene = Column(Integer, nullable=True)  # Scene sequence number
    
    # Physical State
    current_location = Column(Text, nullable=True)
    current_position = Column(Text, nullable=True)  # Sub-room position: "sitting on the couch", "standing by counter"
    items_in_hand = Column(JSON, nullable=True)  # Array of items currently held: ["coffee mug"]
    physical_condition = Column(Text, nullable=True)  # "healthy", "wounded", "exhausted"
    appearance = Column(Text, nullable=True)  # Current appearance description
    possessions = Column(JSON, nullable=True)  # Array of items
    
    # Emotional/Mental State
    emotional_state = Column(Text, nullable=True)  # "angry", "sad", "determined"
    current_goal = Column(Text, nullable=True)  # Main objective
    active_conflicts = Column(JSON, nullable=True)  # Array of internal/external conflicts
    knowledge = Column(JSON, nullable=True)  # Array of known facts
    secrets = Column(JSON, nullable=True)  # Array of secrets character holds
    
    # Relationships (JSON object: character_name -> relationship_data)
    relationships = Column(JSON, nullable=True)
    
    # Character Arc
    arc_stage = Column(Text, nullable=True)  # "ordinary_world", "call_to_adventure", "climax", etc.
    arc_progress = Column(Float, default=0.0)  # 0.0 to 1.0
    recent_decisions = Column(JSON, nullable=True)  # Array of key decisions
    
    # Recent Activity
    recent_actions = Column(JSON, nullable=True)  # Last N actions

    # Full State Snapshot (for flexibility)
    full_state = Column(JSON, nullable=True)

    # Track manually edited fields (JSON array of field names)
    # These fields will not be overwritten by automatic extraction
    manually_edited_fields = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    character = relationship("Character", back_populates="state")
    story = relationship("Story", back_populates="character_states")
    branch = relationship("StoryBranch", back_populates="character_states")
    
    def to_dict(self):
        """Convert to dictionary for easy serialization"""
        return {
            "id": self.id,
            "character_id": self.character_id,
            "story_id": self.story_id,
            "branch_id": self.branch_id,  # Include branch_id for proper snapshot/restore
            "last_updated_scene": self.last_updated_scene,
            "current_location": self.current_location,
            "current_position": self.current_position,
            "items_in_hand": self.items_in_hand or [],
            "physical_condition": self.physical_condition,
            "appearance": self.appearance,
            "possessions": self.possessions or [],
            "emotional_state": self.emotional_state,
            "current_goal": self.current_goal,
            "active_conflicts": self.active_conflicts or [],
            "knowledge": self.knowledge or [],
            "secrets": self.secrets or [],
            "relationships": self.relationships or {},
            "arc_stage": self.arc_stage,
            "arc_progress": self.arc_progress,
            "recent_decisions": self.recent_decisions or [],
            "recent_actions": self.recent_actions or [],
            "full_state": self.full_state or {},
            "manually_edited_fields": self.manually_edited_fields or [],
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


def _location_state_filter(query, fork_seq, story_id, branch_id):
    """Filter location states updated before or at the fork point."""
    return query.filter(LocationState.last_updated_scene <= fork_seq)


@branch_clone_config(
    priority=50,
    filter_func=_location_state_filter,
)
class LocationState(Base):
    """
    Tracks the current state of a location in a story.

    Maintains:
    - Physical condition (damaged, pristine, etc.)
    - Atmosphere and mood
    - Current occupants
    - Recent events at this location
    - Notable features
    """
    __tablename__ = "location_states"
    
    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)  # Story branch
    location_name = Column(String(255), nullable=False)
    last_updated_scene = Column(Integer, nullable=True)
    
    # Physical State
    condition = Column(Text, nullable=True)  # "pristine", "damaged", "destroyed"
    atmosphere = Column(Text, nullable=True)  # "tense", "peaceful", "ominous"
    notable_features = Column(JSON, nullable=True)  # Array of features
    
    # Occupancy
    current_occupants = Column(JSON, nullable=True)  # Array of character names
    
    # History
    significant_events = Column(JSON, nullable=True)  # Array of important events
    
    # Environment
    time_of_day = Column(String(50), nullable=True)  # "dawn", "noon", "dusk", "night"
    weather = Column(String(255), nullable=True)  # If applicable
    
    # Full State Snapshot
    full_state = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    story = relationship("Story", back_populates="location_states")
    branch = relationship("StoryBranch", back_populates="location_states")
    
    def to_dict(self):
        """Convert to dictionary for easy serialization"""
        return {
            "id": self.id,
            "story_id": self.story_id,
            "branch_id": self.branch_id,  # Include branch_id for proper snapshot/restore
            "location_name": self.location_name,
            "last_updated_scene": self.last_updated_scene,
            "condition": self.condition,
            "atmosphere": self.atmosphere,
            "notable_features": self.notable_features or [],
            "current_occupants": self.current_occupants or [],
            "significant_events": self.significant_events or [],
            "time_of_day": self.time_of_day,
            "weather": self.weather,
            "full_state": self.full_state or {},
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


def _object_state_filter(query, fork_seq, story_id, branch_id):
    """Filter object states updated before or at the fork point."""
    return query.filter(ObjectState.last_updated_scene <= fork_seq)


@branch_clone_config(
    priority=50,
    filter_func=_object_state_filter,
)
class ObjectState(Base):
    """
    Tracks the current state of an important object in a story.

    Maintains:
    - Physical condition
    - Current location
    - Current owner
    - Significance and capabilities
    - History
    """
    __tablename__ = "object_states"
    
    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)  # Story branch
    object_name = Column(String(255), nullable=False)
    last_updated_scene = Column(Integer, nullable=True)
    
    # Physical State
    condition = Column(Text, nullable=True)  # "pristine", "damaged", "glowing"
    current_location = Column(Text, nullable=True)  # Where it is now
    current_owner_id = Column(Integer, ForeignKey("characters.id"), nullable=True)
    
    # Metadata
    significance = Column(Text, nullable=True)  # Why it matters
    object_type = Column(String(100), nullable=True)  # "weapon", "artifact", "document", "item"
    
    # Capabilities (for magical/special items)
    powers = Column(JSON, nullable=True)  # Array of powers/abilities
    limitations = Column(JSON, nullable=True)  # Array of limitations
    
    # History
    origin = Column(Text, nullable=True)  # Where it came from
    previous_owners = Column(JSON, nullable=True)  # Array of previous owners
    recent_events = Column(JSON, nullable=True)  # Array of recent events involving it
    
    # Full State Snapshot
    full_state = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    story = relationship("Story", back_populates="object_states")
    branch = relationship("StoryBranch", back_populates="object_states")
    current_owner = relationship("Character", foreign_keys=[current_owner_id])
    
    def to_dict(self):
        """Convert to dictionary for easy serialization"""
        return {
            "id": self.id,
            "story_id": self.story_id,
            "branch_id": self.branch_id,  # Include branch_id for proper snapshot/restore
            "object_name": self.object_name,
            "last_updated_scene": self.last_updated_scene,
            "condition": self.condition,
            "current_location": self.current_location,
            "current_owner_id": self.current_owner_id,
            "significance": self.significance,
            "object_type": self.object_type,
            "powers": self.powers or [],
            "limitations": self.limitations or [],
            "origin": self.origin,
            "previous_owners": self.previous_owners or [],
            "recent_events": self.recent_events or [],
            "full_state": self.full_state or {},
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


def _entity_state_batch_filter(query, fork_seq, story_id, branch_id):
    """Filter entity state batches that end before or at the fork point."""
    return query.filter(EntityStateBatch.end_scene_sequence <= fork_seq)


@branch_clone_config(
    priority=55,
    filter_func=_entity_state_batch_filter,
)
class EntityStateBatch(Base):
    """Stores entity state snapshots in batches to enable partial regeneration"""
    __tablename__ = "entity_state_batches"
    
    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)  # Story branch
    
    # Scene range this batch covers
    start_scene_sequence = Column(Integer, nullable=False)  # First scene in batch
    end_scene_sequence = Column(Integer, nullable=False)     # Last scene in batch
    
    # Entity state snapshots (JSON)
    character_states_snapshot = Column(JSON, nullable=False)  # Array of CharacterState dicts
    location_states_snapshot = Column(JSON, nullable=False)   # Array of LocationState dicts
    object_states_snapshot = Column(JSON, nullable=False)     # Array of ObjectState dicts
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship
    story = relationship("Story", back_populates="entity_state_batches")
    branch = relationship("StoryBranch", back_populates="entity_state_batches")
    
    def __repr__(self):
        return f"<EntityStateBatch(id={self.id}, story_id={self.story_id}, branch_id={self.branch_id}, scenes={self.start_scene_sequence}-{self.end_scene_sequence})>"

