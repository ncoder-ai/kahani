# Import Base from database first
from ..database import Base

# Import branch-aware infrastructure first (needed by model decorators)
from .branch_aware import (
    BranchCloneRegistry,
    BranchCloneConfig,
    branch_clone_config,
    embedding_id_handler,
)

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
from .scene_event import SceneEvent
from .generated_image import GeneratedImage
from .working_memory import WorkingMemory
from .contradiction import Contradiction
from .relationship import CharacterRelationship, RelationshipSummary
from .world import World
from .chronicle import CharacterChronicle, LocationLorebook, ChronicleEntryType, CharacterSnapshot

__all__ = [
    "Base",
    # Branch-aware infrastructure
    "BranchCloneRegistry", "BranchCloneConfig", "branch_clone_config", "embedding_id_handler",
    # Models
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
    "CharacterInteraction",
    "SceneEvent",
    "GeneratedImage",
    "WorkingMemory",
    "Contradiction",
    "CharacterRelationship",
    "RelationshipSummary",
    "World",
    "CharacterChronicle",
    "LocationLorebook",
    "ChronicleEntryType",
    "CharacterSnapshot",
]