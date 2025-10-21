from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
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
    privacy_level = Column(Enum(PrivacyLevel), default=PrivacyLevel.PRIVATE)
    status = Column(Enum(StoryStatus), default=StoryStatus.DRAFT)
    story_mode = Column(Enum(StoryMode), default=StoryMode.DYNAMIC)  # New field
    
    # Story metadata
    genre = Column(String(50))
    tone = Column(String(50))
    target_length = Column(String(20))  # short, medium, long
    summary = Column(Text)  # AI-generated summary of the story
    
    # Story settings and context
    world_setting = Column(Text)
    initial_premise = Column(Text)
    story_context = Column(JSON, default={})  # Current story state, character states, etc.
    
    # Draft progress tracking
    creation_step = Column(Integer, default=0)  # Track which step of creation is complete (0-5)
    draft_data = Column(JSON, default={})  # Store intermediate creation data
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_scene_at = Column(DateTime(timezone=True))
    
    # Relationships
    owner = relationship("User", back_populates="stories")
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
    
    def __repr__(self):
        return f"<Story(id={self.id}, title='{self.title}', owner_id={self.owner_id})>"