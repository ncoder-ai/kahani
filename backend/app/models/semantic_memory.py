"""
Database models for semantic memory tracking

These models store references to embeddings and track character/plot information
that supplements the vector database.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from ..database import Base
from .branch_aware import branch_clone_config, embedding_id_handler
import enum


class MomentType(str, enum.Enum):
    """Types of character moments"""
    ACTION = "action"
    DIALOGUE = "dialogue"
    DEVELOPMENT = "development"
    RELATIONSHIP = "relationship"


class EventType(str, enum.Enum):
    """Types of plot events"""
    INTRODUCTION = "introduction"
    COMPLICATION = "complication"
    REVELATION = "revelation"
    RESOLUTION = "resolution"


def _character_memory_filter(query, fork_seq, story_id, branch_id):
    """Filter character memories up to the fork point."""
    return query.filter(CharacterMemory.sequence_order <= fork_seq)


@branch_clone_config(
    priority=70,
    depends_on=['scenes', 'chapters'],
    fk_remappings={
        'scene_id': 'scene_id_map',
        'chapter_id': 'chapter_id_map',
    },
    special_handlers={'embedding_id': embedding_id_handler},
    filter_func=_character_memory_filter,
)
class CharacterMemory(Base):
    """
    Tracks character moments across the story

    Stores metadata about character-specific moments that are embedded
    in the semantic memory system for retrieval and analysis.
    """
    __tablename__ = "character_memories"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # References
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)  # Story branch
    
    # Moment details
    moment_type = Column(SQLEnum(MomentType), nullable=False, index=True)
    content = Column(Text, nullable=False)  # The actual moment text
    embedding_id = Column(String(200), nullable=False, unique=True, index=True)  # Unique identifier
    embedding = Column(Vector(768), nullable=True)  # pgvector embedding

    # Context
    sequence_order = Column(Integer, nullable=False, index=True)  # Scene sequence number
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)

    # Metadata
    extracted_automatically = Column(Boolean, default=True)  # True if extracted by LLM, False if manual
    confidence_score = Column(Integer, default=0)  # 0-100, for auto-extracted moments

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    character = relationship("Character")
    scene = relationship("Scene")
    story = relationship("Story")
    branch = relationship("StoryBranch", back_populates="character_memories")
    chapter = relationship("Chapter")

    def __repr__(self):
        return f"<CharacterMemory(id={self.id}, character_id={self.character_id}, branch_id={self.branch_id}, moment_type={self.moment_type})>"


def _plot_event_filter(query, fork_seq, story_id, branch_id):
    """Filter plot events up to the fork point."""
    return query.filter(PlotEvent.sequence_order <= fork_seq)


@branch_clone_config(
    priority=70,
    depends_on=['scenes', 'chapters'],
    fk_remappings={
        'scene_id': 'scene_id_map',
        'chapter_id': 'chapter_id_map',
        'resolution_scene_id': 'scene_id_map',
    },
    special_handlers={'embedding_id': embedding_id_handler},
    filter_func=_plot_event_filter,
)
class PlotEvent(Base):
    """
    Tracks plot events and story threads

    Stores metadata about key plot events that are embedded for
    semantic retrieval and thread tracking.
    """
    __tablename__ = "plot_events"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # References
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)  # Story branch
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Event details
    event_type = Column(SQLEnum(EventType), nullable=False, index=True)
    description = Column(Text, nullable=False)  # Human-readable event description
    embedding_id = Column(String(200), nullable=False, unique=True, index=True)  # Unique identifier
    embedding = Column(Vector(768), nullable=True)  # pgvector embedding

    # Thread tracking
    thread_id = Column(String(100), nullable=True, index=True)  # Groups related events
    is_resolved = Column(Boolean, default=False, index=True)  # Whether the thread is resolved
    resolution_scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    
    # Context
    sequence_order = Column(Integer, nullable=False, index=True)  # Scene sequence number
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    involved_characters = Column(JSON, default=list)  # List of character IDs involved
    
    # Metadata
    extracted_automatically = Column(Boolean, default=True)
    confidence_score = Column(Integer, default=0)  # 0-100, for auto-extracted events
    importance_score = Column(Integer, default=50)  # 0-100, plot significance
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    story = relationship("Story")
    branch = relationship("StoryBranch", back_populates="plot_events")
    scene = relationship("Scene", foreign_keys=[scene_id])
    resolution_scene = relationship("Scene", foreign_keys=[resolution_scene_id])
    chapter = relationship("Chapter")
    
    def __repr__(self):
        return f"<PlotEvent(id={self.id}, branch_id={self.branch_id}, event_type={self.event_type}, resolved={self.is_resolved})>"


def _scene_embedding_filter(query, fork_seq, story_id, branch_id):
    """Filter scene embeddings up to the fork point."""
    return query.filter(SceneEmbedding.sequence_order <= fork_seq)


@branch_clone_config(
    priority=75,
    depends_on=['scenes', 'scene_variants', 'chapters'],
    fk_remappings={
        'scene_id': 'scene_id_map',
        'variant_id': 'scene_variant_id_map',
        'chapter_id': 'chapter_id_map',
    },
    special_handlers={'embedding_id': embedding_id_handler},
    filter_func=_scene_embedding_filter,
)
class SceneEmbedding(Base):
    """
    Tracks scene embeddings in the vector database

    Stores metadata about scene embeddings for tracking and management.
    """
    __tablename__ = "scene_embeddings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # References
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)  # Story branch
    world_id = Column(Integer, ForeignKey("worlds.id", ondelete="CASCADE"), nullable=True, index=True)  # For cross-story world-scope search
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("scene_variants.id", ondelete="CASCADE"), nullable=False, index=True)

    # Embedding details
    embedding_id = Column(String(200), nullable=False, unique=True, index=True)  # Unique identifier
    embedding = Column(Vector(768), nullable=True)  # pgvector embedding
    content_hash = Column(String(64), nullable=True)  # SHA256 hash of content for change detection
    
    # Context
    sequence_order = Column(Integer, nullable=False, index=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    
    # Metadata
    embedding_version = Column(String(20), default="v1")  # Track embedding model version
    content_length = Column(Integer, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    story = relationship("Story")
    branch = relationship("StoryBranch", back_populates="scene_embeddings")
    scene = relationship("Scene")
    variant = relationship("SceneVariant")
    chapter = relationship("Chapter")
    
    def __repr__(self):
        return f"<SceneEmbedding(id={self.id}, branch_id={self.branch_id}, scene_id={self.scene_id}, variant_id={self.variant_id})>"

