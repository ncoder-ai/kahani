# Import Base from database first
from ..database import Base

# Import all models to ensure they're registered with SQLAlchemy
from .user import User
from .user_settings import UserSettings
from .story import Story, StoryStatus, PrivacyLevel, StoryMode
from .character import Character, StoryCharacter
from .chapter import Chapter, ChapterStatus
from .scene import Scene, SceneChoice, SceneType
from .scene_variant import SceneVariant
from .story_flow import StoryFlow
from .prompt_template import PromptTemplate
from .writing_style_preset import WritingStylePreset
from .tts_settings import TTSSettings, SceneAudio
from .semantic_memory import CharacterMemory, PlotEvent, SceneEmbedding, MomentType, EventType

__all__ = [
    "Base",
    "User", "UserSettings",
    "Story", "StoryStatus", "PrivacyLevel", "StoryMode",
    "Chapter", "ChapterStatus",
    "Character", "StoryCharacter", 
    "Scene", "SceneChoice", "SceneType",
    "SceneVariant", "StoryFlow", "PromptTemplate",
    "WritingStylePreset",
    "TTSSettings", "SceneAudio",
    "CharacterMemory", "PlotEvent", "SceneEmbedding", "MomentType", "EventType"
]