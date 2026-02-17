from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
from .branch_aware import branch_clone_config


@branch_clone_config(
    priority=31,
    parent_fk_field='scene_id',  # Nested under Scene
    creates_mapping='scene_variant_id_map',
    has_story_id=False,
    has_branch_id=False,
)
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

    # Entity states snapshot for cache consistency during variant regeneration
    # Stores the entity states text (~1-2KB) at the time this variant was generated
    # Used to ensure identical LLM prompts when regenerating variants
    entity_states_snapshot = Column(Text)

    # Full context snapshot (JSON) for complete cache consistency
    # Stores entity_states_text, story_focus, relationship_context as JSON
    # Used to ensure 100% identical prompts when regenerating variants
    context_snapshot = Column(Text)  # JSON string
    
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