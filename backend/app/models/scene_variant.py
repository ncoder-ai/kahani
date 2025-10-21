from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base

class SceneVariant(Base):
    """Multiple variations/regenerations of the same logical scene"""
    __tablename__ = "scene_variants"
    
    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)  # Parent logical scene
    
    # Variant information
    variant_number = Column(Integer, nullable=False, default=1)  # 1, 2, 3... for each regeneration
    is_original = Column(Boolean, default=False)  # First generated version
    
    # Content (moved from Scene model)
    content = Column(Text, nullable=False)
    title = Column(String(200))
    
    # Context and state
    characters_present = Column(JSON, default=[])
    location = Column(String(200))
    mood = Column(String(100))
    scene_context = Column(JSON, default={})
    
    # Generation metadata
    generation_prompt = Column(Text)  # Custom prompt used for this variant
    generation_method = Column(String(50), default="auto")  # "auto", "regenerate", "custom"
    
    # User editing tracking
    original_content = Column(Text)  # AI-generated content before user edits
    user_edited = Column(Boolean, default=False)
    edit_history = Column(JSON, default=[])
    
    # Quality/preference tracking
    user_rating = Column(Integer)  # 1-5 stars if user rates
    is_favorite = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    scene = relationship("Scene", back_populates="variants")
    choices = relationship("SceneChoice", back_populates="variant", cascade="all, delete-orphan")
    story_flows = relationship("StoryFlow", back_populates="scene_variant")
    
    def __repr__(self):
        return f"<SceneVariant(id={self.id}, scene_id={self.scene_id}, variant={self.variant_number})>"