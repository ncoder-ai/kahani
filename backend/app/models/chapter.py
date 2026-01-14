from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum, Table, JSON
from sqlalchemy.orm import relationship, attributes
from sqlalchemy.sql import func
from ..database import Base
import enum

class ChapterStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"

# Association table for chapter-character many-to-many relationship
chapter_characters = Table(
    'chapter_characters',
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('chapter_id', Integer, ForeignKey('chapters.id', ondelete='CASCADE'), nullable=False),
    Column('story_character_id', Integer, ForeignKey('story_characters.id', ondelete='CASCADE'), nullable=False),
    Column('perspective', String(50), nullable=True),  # For future use (POV, main, supporting)
    # Unique constraint to prevent duplicate associations
    # Note: SQLite doesn't support named constraints in Table(), so we'll handle this in migration
)

class Chapter(Base):
    """Story chapters for organizing narrative into manageable segments"""
    __tablename__ = "chapters"
    
    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)  # Story branch
    chapter_number = Column(Integer, nullable=False)
    
    # Basic info
    title = Column(String(200), nullable=True)  # Auto-generated or user-defined
    description = Column(Text, nullable=True)
    
    # For structured mode - links to plot point
    plot_point = Column(Text, nullable=True)  # The plot point this chapter represents
    plot_point_index = Column(Integer, nullable=True)  # Order in original plot
    
    # Story context for this chapter
    story_so_far = Column(Text, nullable=True)  # Editable summary/background for this chapter
    auto_summary = Column(Text, nullable=True)  # Auto-generated summary (based on user's context_summary_threshold setting)
    last_summary_scene_count = Column(Integer, default=0)  # Track when we last generated summary
    last_extraction_scene_count = Column(Integer, default=0)  # Track when we last ran character/NPC extraction
    last_plot_extraction_scene_count = Column(Integer, default=0)  # Track when we last ran plot event extraction
    
    # Chapter metadata
    location_name = Column(String(255), nullable=True)  # Primary location for this chapter
    time_period = Column(String(100), nullable=True)  # Time of day, era, etc.
    scenario = Column(Text, nullable=True)  # Chapter-specific scenario
    continues_from_previous = Column(Boolean, default=True)  # Whether chapter directly follows previous chapter
    
    # Chapter plot guidance (from brainstorming)
    chapter_plot = Column(JSON, nullable=True)  # Structured plot: summary, key_events, climax, resolution
    arc_phase_id = Column(String(100), nullable=True)  # Links to story arc phase
    brainstorm_session_id = Column(Integer, ForeignKey("chapter_brainstorm_sessions.id", ondelete="SET NULL"), nullable=True)
    
    # Plot progress tracking
    plot_progress = Column(JSON, nullable=True)  # {"completed_events": [...], "scene_count": N, "last_updated": "..."}
    
    # Status and metrics
    status = Column(Enum(ChapterStatus), default=ChapterStatus.ACTIVE)
    context_tokens_used = Column(Integer, default=0)
    scenes_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    story = relationship("Story", back_populates="chapters")
    branch = relationship("StoryBranch", back_populates="chapters")
    scenes = relationship("Scene", back_populates="chapter", cascade="all, delete-orphan", order_by="Scene.sequence_number")
    # Many-to-many relationship with StoryCharacter via chapter_characters association table
    characters = relationship(
        "StoryCharacter",
        secondary=chapter_characters,
        backref="chapters",
        lazy="dynamic"
    )
    summary_batches = relationship("ChapterSummaryBatch", back_populates="chapter", cascade="all, delete-orphan", order_by="ChapterSummaryBatch.start_scene_sequence")
    plot_progress_batches = relationship("ChapterPlotProgressBatch", back_populates="chapter", cascade="all, delete-orphan", order_by="ChapterPlotProgressBatch.start_scene_sequence")
    
    def __repr__(self):
        return f"<Chapter(id={self.id}, story_id={self.story_id}, number={self.chapter_number}, title='{self.title}')>"


class ChapterSummaryBatch(Base):
    """Stores summary batches for chapters to enable partial regeneration"""
    __tablename__ = "chapter_summary_batches"
    
    id = Column(Integer, primary_key=True, index=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    
    # Scene range this batch covers
    start_scene_sequence = Column(Integer, nullable=False)  # First scene in batch
    end_scene_sequence = Column(Integer, nullable=False)     # Last scene in batch
    
    # Batch summary content
    summary = Column(Text, nullable=False)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship
    chapter = relationship("Chapter", back_populates="summary_batches")
    
    def __repr__(self):
        return f"<ChapterSummaryBatch(id={self.id}, chapter_id={self.chapter_id}, scenes={self.start_scene_sequence}-{self.end_scene_sequence})>"


class ChapterPlotProgressBatch(Base):
    """Stores plot progress batches for chapters to enable rollback on deletion"""
    __tablename__ = "chapter_plot_progress_batches"
    
    id = Column(Integer, primary_key=True, index=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    
    # Scene range this batch covers
    start_scene_sequence = Column(Integer, nullable=False)
    end_scene_sequence = Column(Integer, nullable=False)
    
    # Events completed in this batch (cumulative up to this point)
    completed_events = Column(JSON, nullable=False, default=list)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship
    chapter = relationship("Chapter", back_populates="plot_progress_batches")
    
    def __repr__(self):
        return f"<ChapterPlotProgressBatch(id={self.id}, chapter_id={self.chapter_id}, scenes={self.start_scene_sequence}-{self.end_scene_sequence}, events={len(self.completed_events or [])})>"
