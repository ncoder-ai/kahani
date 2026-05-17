from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
from ..config import settings

class SystemSettings(Base):
    """
    System-wide settings configured by admin.
    This is a singleton table - only one record should exist.
    """
    __tablename__ = "system_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Default permissions for new users - NO DEFAULTS, must come from config.yaml
    default_allow_nsfw = Column(Boolean, nullable=True)
    default_can_change_llm_provider = Column(Boolean, nullable=True)
    default_can_change_tts_settings = Column(Boolean, nullable=True)
    default_can_use_stt = Column(Boolean, nullable=True)
    default_can_use_image_generation = Column(Boolean, nullable=True)
    default_can_export_stories = Column(Boolean, nullable=True)
    default_can_import_stories = Column(Boolean, nullable=True)
    
    # Default resource limits for new users
    default_max_stories = Column(Integer, nullable=True)  # None = unlimited
    default_max_images_per_story = Column(Integer, nullable=True)
    default_max_stt_minutes_per_month = Column(Integer, nullable=True)
    
    # Default LLM configuration (applied to new users)
    default_llm_api_url = Column(String(500), nullable=True)
    default_llm_api_key = Column(String(500), nullable=True)
    default_llm_model_name = Column(String(200), nullable=True)
    default_llm_temperature = Column(Float, nullable=True)
    
    # Registration settings
    registration_requires_approval = Column(Boolean, nullable=True)
    
    # Metadata
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationship to track who last updated settings
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    
    def __repr__(self):
        return f"<SystemSettings(id={self.id}, registration_requires_approval={self.registration_requires_approval})>"

