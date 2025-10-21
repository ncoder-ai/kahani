from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
import enum

class ChapterStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"

class Chapter(Base):
    """Story chapters for organizing narrative into manageable segments"""
    __tablename__ = "chapters"
    
    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
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
    scenes = relationship("Scene", back_populates="chapter", cascade="all, delete-orphan", order_by="Scene.sequence_number")
    
    def __repr__(self):
        return f"<Chapter(id={self.id}, story_id={self.story_id}, number={self.chapter_number}, title='{self.title}')>"
