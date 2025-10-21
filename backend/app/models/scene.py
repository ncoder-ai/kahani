from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
import enum

class SceneType(str, enum.Enum):
    NARRATIVE = "narrative"
    DIALOGUE = "dialogue"
    ACTION = "action"
    DESCRIPTION = "description"

class Scene(Base):
    """Logical scene container - holds multiple variants/regenerations"""
    __tablename__ = "scenes"
    
    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=False)
    chapter_id = Column(Integer, ForeignKey("chapters.id"), nullable=True)  # New: Link to chapter
    
    # Scene ordering and structure
    sequence_number = Column(Integer, nullable=False)  # Order in story
    parent_scene_id = Column(Integer, ForeignKey("scenes.id"))  # For branching
    branch_choice = Column(Text)  # The choice that led to this scene
    
    # Scene metadata (content now in SceneVariant)
    title = Column(String(200))  # Default title, variants can override
    scene_type = Column(Enum(SceneType), default=SceneType.NARRATIVE)
    
    # Scene state
    is_deleted = Column(Boolean, default=False)  # Soft delete
    deletion_point = Column(Boolean, default=False)  # Mark as deletion boundary
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    story = relationship("Story", back_populates="scenes")
    chapter = relationship("Chapter", back_populates="scenes")
    parent_scene = relationship("Scene", remote_side=[id], backref="child_scenes")
    variants = relationship("SceneVariant", back_populates="scene", cascade="all, delete-orphan")
    story_flows = relationship("StoryFlow", back_populates="scene")
    
    # Legacy relationship (will be deprecated)
    choices = relationship("SceneChoice", back_populates="scene", foreign_keys="SceneChoice.scene_id", cascade="all, delete-orphan")
    
    @property
    def active_variant(self):
        """Get the currently active variant for this scene"""
        # This will be determined by StoryFlow
        return None  # To be implemented
    
    @property 
    def content(self):
        """Legacy property for backward compatibility"""
        active = self.active_variant
        return active.content if active else ""
    
    def __repr__(self):
        return f"<Scene(id={self.id}, story_id={self.story_id}, sequence={self.sequence_number})>"

class SceneChoice(Base):
    """Choices available at the end of each scene variant"""
    __tablename__ = "scene_choices"
    
    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)  # Legacy - logical scene
    scene_variant_id = Column(Integer, ForeignKey("scene_variants.id"))  # New - specific variant
    
    # Choice content
    choice_text = Column(Text, nullable=False)
    choice_description = Column(Text)  # Additional context about consequences
    
    # Choice metadata
    choice_order = Column(Integer, default=0)  # Display order (1-4 typically)
    is_user_created = Column(Boolean, default=False)  # User-added vs AI-generated
    
    # Consequences and outcomes
    predicted_outcomes = Column(JSON, default={})  # What might happen
    character_reactions = Column(JSON, default={})  # How characters might react
    
    # Usage tracking
    times_selected = Column(Integer, default=0)
    leads_to_scene_id = Column(Integer, ForeignKey("scenes.id"))  # If choice was taken
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    scene = relationship("Scene", back_populates="choices", foreign_keys=[scene_id])
    variant = relationship("SceneVariant", back_populates="choices")
    leads_to_scene = relationship("Scene", foreign_keys=[leads_to_scene_id], post_update=True)
    
    def __repr__(self):
        return f"<SceneChoice(id={self.id}, variant_id={self.scene_variant_id}, order={self.choice_order})>"