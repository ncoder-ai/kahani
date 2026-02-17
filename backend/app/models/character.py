from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
from .branch_aware import branch_clone_config

class Character(Base):
    __tablename__ = "characters"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    gender = Column(String(20), nullable=True)  # "male", "female", "non-binary", etc.

    # Character details
    personality_traits = Column(JSON, default=[])  # List of traits
    background = Column(Text)
    goals = Column(Text)
    fears = Column(Text)
    appearance = Column(Text)
    
    # Voice/Speech Style - defines how the character speaks
    # JSON structure: {
    #   "preset": "standard_neutral" | "indian_english" | "british_rp" | ... | "custom",
    #   "formality": "formal" | "casual" | "streetwise" | "archaic",
    #   "vocabulary": "simple" | "average" | "sophisticated" | "technical",
    #   "tone": "cheerful" | "sarcastic" | "gruff" | "nervous" | "calm" | "dramatic" | "deadpan",
    #   "profanity": "none" | "mild" | "moderate" | "heavy",
    #   "speech_quirks": "free text for catchphrases, verbal tics",
    #   "secondary_language": "hindi" | "spanish" | "mandarin" | "japanese" | null,
    #   "language_mixing": "none" | "light" | "moderate" | "heavy"
    # }
    voice_style = Column(JSON, nullable=True)  # Character's default speaking style
    
    # Portrait image (generated or uploaded)
    portrait_image_id = Column(Integer, ForeignKey("generated_images.id", ondelete="SET NULL"), nullable=True)

    # Meta information
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_template = Column(Boolean, default=False)  # Can be reused across stories
    is_public = Column(Boolean, default=False)  # Available to other users
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    creator = relationship("User", back_populates="characters")
    story_characters = relationship("StoryCharacter", back_populates="character", cascade="all, delete-orphan")
    memories = relationship("CharacterMemory", back_populates="character", cascade="all, delete-orphan")
    state = relationship("CharacterState", back_populates="character", uselist=False, cascade="all, delete-orphan")
    portrait_image = relationship("GeneratedImage", foreign_keys=[portrait_image_id])
    
    def __repr__(self):
        return f"<Character(id={self.id}, name='{self.name}')>"

@branch_clone_config(
    priority=20,
    creates_mapping='story_character_id_map',
    clone_all=True,  # Clone all characters, not filtered by fork_sequence
)
class StoryCharacter(Base):
    """Association table for characters in specific stories with story-specific state"""
    __tablename__ = "story_characters"
    
    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("story_branches.id", ondelete="CASCADE"), nullable=True, index=True)  # Story branch
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False)
    
    # Story-specific character properties
    role = Column(String(100))  # Role in this specific story (protagonist, antagonist, etc.)
    
    # Story-specific voice style override
    # If set, overrides the character's default voice_style for this story
    # Same JSON structure as Character.voice_style
    voice_style_override = Column(JSON, nullable=True)
    
    # Story-specific character state
    current_location = Column(String(200))
    current_emotional_state = Column(String(100))
    current_goals = Column(Text)
    knowledge_state = Column(JSON, default={})  # What they know in this story
    relationships = Column(JSON, default={})  # Relationships with other characters
    
    # Character arc tracking
    character_development = Column(JSON, default=[])  # List of development events
    is_active = Column(Boolean, default=True)  # Currently available in story
    
    # Timestamps
    introduced_at = Column(DateTime(timezone=True), server_default=func.now())
    last_appearance = Column(DateTime(timezone=True))
    
    # Relationships
    story = relationship("Story", back_populates="story_characters")
    branch = relationship("StoryBranch", back_populates="story_characters")
    character = relationship("Character", back_populates="story_characters")
    
    def __repr__(self):
        return f"<StoryCharacter(story_id={self.story_id}, branch_id={self.branch_id}, character_id={self.character_id})>"