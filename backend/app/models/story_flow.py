from sqlalchemy import Column, Integer, ForeignKey, DateTime, Boolean, String, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base

class StoryFlow(Base):
    """Tracks the active path through scene variants for each story"""
    __tablename__ = "story_flows"
    
    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=False)
    
    # Flow path definition
    sequence_number = Column(Integer, nullable=False)  # Order in story (1, 2, 3...)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)  # Logical scene
    scene_variant_id = Column(Integer, ForeignKey("scene_variants.id"), nullable=False)  # Active variant
    
    # Choice that led here (from previous scene)
    from_choice_id = Column(Integer, ForeignKey("scene_choices.id"))
    choice_text = Column(String(500))  # Cache of choice text for quick access
    
    # Flow metadata
    is_active = Column(Boolean, default=True)  # Is this the current active path?
    flow_name = Column(String(100))  # Optional name for saved paths
    
    # User session tracking
    created_by_session = Column(String(100))  # Session ID that created this flow
    last_accessed = Column(DateTime(timezone=True), server_default=func.now())
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    story = relationship("Story", back_populates="story_flows")
    scene = relationship("Scene")
    scene_variant = relationship("SceneVariant", back_populates="story_flows")
    from_choice = relationship("SceneChoice", foreign_keys=[from_choice_id])
    
    # Unique constraint: one active flow per story per sequence
    __table_args__ = (
        # Each story should have exactly one active variant per sequence
        # But can have multiple saved/inactive flows
    )
    
    def __repr__(self):
        return f"<StoryFlow(id={self.id}, story_id={self.story_id}, seq={self.sequence_number}, variant_id={self.scene_variant_id})>"