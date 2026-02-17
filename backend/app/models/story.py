from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship, attributes
from sqlalchemy.sql import func
from ..database import Base
import enum

class StoryStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"

class PrivacyLevel(str, enum.Enum):
    PRIVATE = "private"
    FRIENDS = "friends"
    UNLISTED = "unlisted"
    PUBLIC = "public"

class StoryMode(str, enum.Enum):
    DYNAMIC = "dynamic"        # Freeform with auto chapter management
    STRUCTURED = "structured"  # Plot-driven with predefined chapters

class Story(Base):
    __tablename__ = "stories"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    
    # Ownership and access
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=True)
    privacy_level = Column(Enum(PrivacyLevel), default=PrivacyLevel.PRIVATE)
    status = Column(Enum(StoryStatus), default=StoryStatus.DRAFT)
    story_mode = Column(Enum(StoryMode), default=StoryMode.DYNAMIC)  # New field
    
    # Story metadata
    genre = Column(String(200))
    tone = Column(String(200))
    target_length = Column(String(20))  # short, medium, long
    summary = Column(Text)  # AI-generated summary of the story
    
    # Story settings and context
    world_setting = Column(Text)
    initial_premise = Column(Text)
    scenario = Column(Text)  # Scenario created during story setup
    story_context = Column(JSON, default={})  # Current story state, character states, etc.
    
    # Draft progress tracking
    creation_step = Column(Integer, default=0)  # Track which step of creation is complete (0-5)
    draft_data = Column(JSON, default={})  # Store intermediate creation data
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_scene_at = Column(DateTime(timezone=True))
    
    # Active branch tracking
    current_branch_id = Column(Integer, ForeignKey("story_branches.id"), nullable=True)
    
    # Relationships
    owner = relationship("User", back_populates="stories")
    world = relationship("World", back_populates="stories")
    scenes = relationship("Scene", back_populates="story", cascade="all, delete-orphan", order_by="Scene.sequence_number")
    chapters = relationship("Chapter", back_populates="story", cascade="all, delete-orphan", order_by="Chapter.chapter_number")
    story_characters = relationship("StoryCharacter", back_populates="story", cascade="all, delete-orphan")
    story_flows = relationship("StoryFlow", back_populates="story", cascade="all, delete-orphan")
    
    # Semantic Memory Relationships
    character_memories = relationship("CharacterMemory", back_populates="story", cascade="all, delete-orphan")
    plot_events = relationship("PlotEvent", back_populates="story", cascade="all, delete-orphan")
    scene_embeddings = relationship("SceneEmbedding", back_populates="story", cascade="all, delete-orphan")
    
    # Entity State Relationships
    character_states = relationship("CharacterState", back_populates="story", cascade="all, delete-orphan")
    location_states = relationship("LocationState", back_populates="story", cascade="all, delete-orphan")
    object_states = relationship("ObjectState", back_populates="story", cascade="all, delete-orphan")
    
    # NPC Tracking Relationships
    npc_mentions = relationship("NPCMention", back_populates="story", cascade="all, delete-orphan")
    npc_tracking = relationship("NPCTracking", back_populates="story", cascade="all, delete-orphan")
    npc_tracking_snapshots = relationship("NPCTrackingSnapshot", back_populates="story", cascade="all, delete-orphan")
    
    # Entity State Batch Relationships
    entity_state_batches = relationship("EntityStateBatch", back_populates="story", cascade="all, delete-orphan", order_by="EntityStateBatch.start_scene_sequence")
    
    # Character Interaction Relationships
    character_interactions = relationship("CharacterInteraction", back_populates="story", cascade="all, delete-orphan")

    # Scene Event Index
    scene_events = relationship("SceneEvent", back_populates="story", cascade="all, delete-orphan")
    
    # Story Branches
    branches = relationship("StoryBranch", back_populates="story", cascade="all, delete-orphan", order_by="StoryBranch.created_at", foreign_keys="StoryBranch.story_id")
    current_branch = relationship("StoryBranch", foreign_keys=[current_branch_id], post_update=True)
    
    # Brainstorm Session (if story was created from brainstorm)
    brainstorm_session = relationship("BrainstormSession", back_populates="story", uselist=False)

    # Generated Images
    generated_images = relationship("GeneratedImage", back_populates="story", cascade="all, delete-orphan")

    # Working Memory (scene-to-scene continuity tracking)
    working_memory = relationship("WorkingMemory", back_populates="story", uselist=False, cascade="all, delete-orphan")

    # Contradictions (continuity error tracking)
    contradictions = relationship("Contradiction", back_populates="story", cascade="all, delete-orphan")

    # Relationship Graph (character relationship tracking)
    character_relationships = relationship("CharacterRelationship", back_populates="story", cascade="all, delete-orphan")
    relationship_summaries = relationship("RelationshipSummary", back_populates="story", cascade="all, delete-orphan")

    # Story Arc - AI-generated narrative structure
    story_arc = Column(JSON, nullable=True)
    
    # Content Rating - controls NSFW filter per story
    # "sfw" = Safe for Work (family friendly, filters applied)
    # "nsfw" = Not Safe for Work (mature content allowed if user permits)
    content_rating = Column(String(10), default="sfw")
    
    # Interaction Types - user-defined list of interaction types to track for this story
    # Example: ["first meeting", "first kiss", "first conflict", "reconciliation"]
    # These are used by the entity extraction service to track character interactions
    interaction_types = Column(JSON, nullable=True, default=list)

    # Plot event checking mode - how many events to send for LLM detection
    # "1" = next event only (strict), "3" = next 3 events, "all" = all remaining
    plot_check_mode = Column(String(10), nullable=True)

    # Timeline order within a world (author-defined chronological position)
    # Null means unordered (treated as last). Used for character snapshot scoping.
    timeline_order = Column(Integer, nullable=True)

    # Extraction Quality Metrics - track how well entity extraction is working
    # success_rate: ratio of extractions with meaningful data (2+ non-empty fields per character)
    # empty_rate: ratio of extractions that returned empty or no character data
    extraction_success_rate = Column(Integer, nullable=True)  # 0-100 percentage
    extraction_empty_rate = Column(Integer, nullable=True)    # 0-100 percentage
    extraction_total_count = Column(Integer, default=0)       # total extractions performed
    last_extraction_quality_check = Column(DateTime(timezone=True), nullable=True)

    def update_story_arc(self, arc_data: dict):
        """Update the story arc data."""
        if self.story_arc is None:
            self.story_arc = {}
        self.story_arc.update(arc_data)
        attributes.flag_modified(self, 'story_arc')
    
    def get_arc_phase(self, phase_id: str) -> dict:
        """Get a specific arc phase by ID."""
        if not self.story_arc or 'phases' not in self.story_arc:
            return None
        for phase in self.story_arc.get('phases', []):
            if phase.get('id') == phase_id:
                return phase
        return None
    
    def __repr__(self):
        return f"<Story(id={self.id}, title='{self.title}', owner_id={self.owner_id})>"