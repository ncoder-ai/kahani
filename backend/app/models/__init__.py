# Import Base from database first
from ..database import Base

# Import all models to ensure they're registered with SQLAlchemy
from .user import User
from .user_settings import UserSettings
from .system_settings import SystemSettings
from .story import Story, StoryStatus, PrivacyLevel, StoryMode
from .story_branch import StoryBranch
from .character import Character, StoryCharacter
from .chapter import Chapter, ChapterStatus, chapter_characters, ChapterSummaryBatch, ChapterPlotProgressBatch
from .scene import Scene, SceneChoice, SceneType
from .scene_variant import SceneVariant
from .story_flow import StoryFlow
from .prompt_template import PromptTemplate
from .writing_style_preset import WritingStylePreset
from .tts_settings import TTSSettings, SceneAudio
from .semantic_memory import CharacterMemory, PlotEvent, SceneEmbedding, MomentType, EventType
from .entity_state import CharacterState, LocationState, ObjectState, EntityStateBatch
from .npc_tracking import NPCMention, NPCTracking, NPCTrackingSnapshot
from .brainstorm_session import BrainstormSession
from .chapter_brainstorm_session import ChapterBrainstormSession
from .character_interaction import CharacterInteraction

__all__ = [
    "Base",
    "User", "UserSettings", "SystemSettings",
    "Story", "StoryStatus", "PrivacyLevel", "StoryMode",
    "StoryBranch",
    "Chapter", "ChapterStatus", "chapter_characters", "ChapterSummaryBatch", "ChapterPlotProgressBatch",
    "Character", "StoryCharacter", 
    "Scene", "SceneChoice", "SceneType",
    "SceneVariant", "StoryFlow", "PromptTemplate",
    "WritingStylePreset",
    "TTSSettings", "SceneAudio",
    "CharacterMemory", "PlotEvent", "SceneEmbedding", "MomentType", "EventType",
    "CharacterState", "LocationState", "ObjectState", "EntityStateBatch",
    "NPCMention", "NPCTracking", "NPCTrackingSnapshot",
    "BrainstormSession",
    "ChapterBrainstormSession",
    "CharacterInteraction"
]