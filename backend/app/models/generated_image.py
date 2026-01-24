from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
from .branch_aware import branch_clone_config


@branch_clone_config(
    priority=15,  # Before story_characters (20) since characters may reference images
    creates_mapping='generated_image_id_map',
    clone_all=True,
)
class GeneratedImage(Base):
    """Model for storing generated images from ComfyUI or other providers"""
    __tablename__ = "generated_images"

    id = Column(Integer, primary_key=True, index=True)

    # Story association (optional - NULL for default character portraits)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)

    # Optional associations - one of these typically set
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="SET NULL"), nullable=True, index=True)

    # Image type for filtering
    image_type = Column(String(50), nullable=False)  # "scene", "character_portrait"

    # File storage
    file_path = Column(String(500), nullable=False)  # Relative path in storage
    thumbnail_path = Column(String(500), nullable=True)  # Thumbnail for quick loading

    # Generation details for reproducibility
    prompt = Column(Text, nullable=True)  # The generation prompt used
    negative_prompt = Column(Text, nullable=True)
    generation_params = Column(JSON, nullable=True)  # seed, steps, cfg, checkpoint, etc.

    # Image metadata
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)

    # Provider info
    provider = Column(String(50), default="comfyui")  # "comfyui", etc.

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    story = relationship("Story", back_populates="generated_images")
    branch = relationship("StoryBranch", back_populates="generated_images")
    scene = relationship("Scene", back_populates="generated_images")
    # Note: character relationship is handled through portrait_image on Character model

    def __repr__(self):
        return f"<GeneratedImage(id={self.id}, type='{self.image_type}', story_id={self.story_id})>"

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "story_id": self.story_id,
            "branch_id": self.branch_id,
            "scene_id": self.scene_id,
            "character_id": self.character_id,
            "image_type": self.image_type,
            "file_path": self.file_path,
            "thumbnail_path": self.thumbnail_path,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "generation_params": self.generation_params,
            "width": self.width,
            "height": self.height,
            "provider": self.provider,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
