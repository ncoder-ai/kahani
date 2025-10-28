from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(50), unique=True, index=True, nullable=False)
    display_name = Column(String(100))
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # User preferences
    preferences = Column(JSON, default={})
    
    # Admin approval system
    is_approved = Column(Boolean, default=False, nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Content permissions
    allow_nsfw = Column(Boolean, default=False, nullable=False)
    
    # Feature permissions
    can_change_llm_provider = Column(Boolean, default=True, nullable=False)
    can_change_tts_settings = Column(Boolean, default=True, nullable=False)
    can_use_stt = Column(Boolean, default=True, nullable=False)  # Future: Speech-to-Text
    can_use_image_generation = Column(Boolean, default=True, nullable=False)  # Future: Image generation
    can_export_stories = Column(Boolean, default=True, nullable=False)
    can_import_stories = Column(Boolean, default=True, nullable=False)
    
    # Resource limits
    max_stories = Column(Integer, nullable=True)  # None = unlimited
    max_images_per_story = Column(Integer, nullable=True)  # Future: Image generation limit
    max_stt_minutes_per_month = Column(Integer, nullable=True)  # Future: STT usage limit
    
    # Relationships
    stories = relationship("Story", back_populates="owner", cascade="all, delete-orphan")
    characters = relationship("Character", back_populates="creator", cascade="all, delete-orphan")
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    tts_settings = relationship("TTSSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    prompt_templates = relationship("PromptTemplate", back_populates="user", cascade="all, delete-orphan")
    writing_style_presets = relationship("WritingStylePreset", back_populates="user", cascade="all, delete-orphan")
    
    # Self-referential relationship for approval tracking
    approved_by = relationship("User", remote_side=[id], foreign_keys=[approved_by_id])
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"