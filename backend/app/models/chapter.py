from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum, Table, JSON, and_
from sqlalchemy.orm import relationship, attributes
from sqlalchemy.sql import func
from ..database import Base
from .branch_aware import branch_clone_config
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
    # Named constraints are handled in migration
)

def _chapter_filter(query, fork_seq, story_id, branch_id):
    """Filter chapters that have scenes up to the fork point."""
    from .scene import Scene
    from sqlalchemy.orm import Session

    # Get the database session from the query
    db = query.session

    # Get chapter IDs that have scenes within the fork point
    chapters_with_scenes = db.query(Scene.chapter_id).filter(
        and_(
            Scene.branch_id == branch_id,
            Scene.sequence_number <= fork_seq
        )
    ).distinct().subquery()

    # Include chapters that have scenes before fork point OR chapter 1
    return query.filter(
        (Chapter.id.in_(chapters_with_scenes)) | (Chapter.chapter_number == 1)
    )


@branch_clone_config(
    priority=10,
    creates_mapping='chapter_id_map',
    filter_func=_chapter_filter,
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
    last_chronicle_scene_count = Column(Integer, default=0)  # Track when we last ran chronicle extraction
    
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
    creation_step = Column(Integer, nullable=True, default=None)  # None=fully created, 4=story_so_far pending
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
    working_memory = relationship("WorkingMemory", back_populates="chapter", uselist=False)

    def __repr__(self):
        return f"<Chapter(id={self.id}, story_id={self.story_id}, number={self.chapter_number}, title='{self.title}')>"


def _chapter_summary_batch_filter(query, fork_seq, story_id, branch_id):
    """Filter chapter summary batches that end before or at the fork point."""
    return query.filter(ChapterSummaryBatch.end_scene_sequence <= fork_seq)


@branch_clone_config(
    priority=80,
    depends_on=['chapters'],
    iterate_via_mapping='chapter_id_map',
    iterate_fk_field='chapter_id',
    filter_func=_chapter_summary_batch_filter,
    has_story_id=False,
    has_branch_id=False,
)
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


def _chapter_plot_progress_batch_filter(query, fork_seq, story_id, branch_id):
    """Filter chapter plot progress batches that end before or at the fork point."""
    return query.filter(ChapterPlotProgressBatch.end_scene_sequence <= fork_seq)


@branch_clone_config(
    priority=80,
    depends_on=['chapters'],
    iterate_via_mapping='chapter_id_map',
    iterate_fk_field='chapter_id',
    filter_func=_chapter_plot_progress_batch_filter,
    has_story_id=False,
    has_branch_id=False,
)
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
