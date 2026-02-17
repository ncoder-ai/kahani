"""
Story Branch Model

Represents a branch/fork of a story, enabling users to explore
different narrative paths from any point in the story.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class StoryBranch(Base):
    """
    Represents a branch of a story.
    
    Each story has at least one branch (the "Main" branch).
    Users can create new branches by forking from any scene,
    which creates a deep copy of all story data up to that point.
    """
    __tablename__ = "story_branches"
    
    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Branch identification
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    
    # Branch type flags
    is_main = Column(Boolean, default=False, nullable=False, index=True)  # True for the original/main branch
    is_active = Column(Boolean, default=False, nullable=False, index=True)  # True for the currently selected branch
    
    # Fork information (null for main branch)
    forked_from_branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="SET NULL"), nullable=True)
    forked_at_scene_sequence = Column(Integer, nullable=True)  # The scene sequence number where the fork was created
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    story = relationship("Story", back_populates="branches", foreign_keys=[story_id])
    forked_from_branch = relationship("StoryBranch", remote_side=[id], backref="child_branches")
    
    # Reverse relationships to branch-aware models
    scenes = relationship("Scene", back_populates="branch", cascade="all, delete-orphan")
    chapters = relationship("Chapter", back_populates="branch", cascade="all, delete-orphan")
    story_characters = relationship("StoryCharacter", back_populates="branch", cascade="all, delete-orphan")
    story_flows = relationship("StoryFlow", back_populates="branch", cascade="all, delete-orphan")
    
    # Entity states
    character_states = relationship("CharacterState", back_populates="branch", cascade="all, delete-orphan")
    location_states = relationship("LocationState", back_populates="branch", cascade="all, delete-orphan")
    object_states = relationship("ObjectState", back_populates="branch", cascade="all, delete-orphan")
    entity_state_batches = relationship("EntityStateBatch", back_populates="branch", cascade="all, delete-orphan")
    
    # NPC tracking
    npc_mentions = relationship("NPCMention", back_populates="branch", cascade="all, delete-orphan")
    npc_tracking = relationship("NPCTracking", back_populates="branch", cascade="all, delete-orphan")
    npc_tracking_snapshots = relationship("NPCTrackingSnapshot", back_populates="branch", cascade="all, delete-orphan")
    
    # Semantic memory
    character_memories = relationship("CharacterMemory", back_populates="branch", cascade="all, delete-orphan")
    plot_events = relationship("PlotEvent", back_populates="branch", cascade="all, delete-orphan")
    scene_embeddings = relationship("SceneEmbedding", back_populates="branch", cascade="all, delete-orphan")
    
    # Character interactions
    character_interactions = relationship("CharacterInteraction", back_populates="branch", cascade="all, delete-orphan")

    # Scene events
    scene_events = relationship("SceneEvent", back_populates="branch", cascade="all, delete-orphan")

    # Generated images
    generated_images = relationship("GeneratedImage", back_populates="branch", cascade="all, delete-orphan")

    # Working memory (scene-to-scene continuity)
    working_memory = relationship("WorkingMemory", back_populates="branch", uselist=False, cascade="all, delete-orphan")

    # Contradictions (continuity error tracking)
    contradictions = relationship("Contradiction", back_populates="branch", cascade="all, delete-orphan")

    # Relationship Graph (character relationship tracking)
    character_relationships = relationship("CharacterRelationship", back_populates="branch", cascade="all, delete-orphan")
    relationship_summaries = relationship("RelationshipSummary", back_populates="branch", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<StoryBranch(id={self.id}, story_id={self.story_id}, name='{self.name}', is_main={self.is_main}, is_active={self.is_active})>"

