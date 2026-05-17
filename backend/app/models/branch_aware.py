"""
Branch Aware Mixin and Cloning Registry

Provides automatic branch cloning registration for models that need to be
cloned when a story branch is forked. This eliminates the need to manually
update branch_service.py when adding new branch-aware models.

Usage:
    from .branch_aware import BranchCloneRegistry, branch_clone_config

    @branch_clone_config(
        priority=30,
        depends_on=['chapters'],
        fk_remappings={'chapter_id': 'chapter_id_map'},
        creates_mapping='scene_id_map',
        self_ref_fk='parent_scene_id',
        filter_func=lambda q, fork_seq, story_id, branch_id: q.filter(Scene.sequence_number <= fork_seq)
    )
    class Scene(Base):
        ...
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any, Type, Set
from functools import wraps
import logging

logger = logging.getLogger(__name__)


@dataclass
class BranchCloneConfig:
    """Configuration for how to clone a branch-aware model."""
    model_class: Type
    table_name: str

    # Cloning order - lower values are cloned first
    priority: int = 100

    # Dependencies: list of table names that must be cloned before this one
    depends_on: List[str] = field(default_factory=list)

    # FK remapping: {column_name: mapping_key}
    # e.g., {"chapter_id": "chapter_id_map"} means chapter_id should be
    # remapped using the chapter_id_map created when cloning chapters
    fk_remappings: Dict[str, str] = field(default_factory=dict)

    # Self-referential FK (e.g., Scene.parent_scene_id -> Scene)
    # This column will be remapped using the model's own ID mapping
    self_ref_fk: Optional[str] = None

    # Deferred FK remapping (for FKs that point to records not yet cloned)
    # e.g., SceneChoice.leads_to_scene_id which can point to any scene
    deferred_fk_remappings: Dict[str, str] = field(default_factory=dict)

    # Filter function: callable(query, fork_sequence, story_id, source_branch_id) -> query
    # Used to filter which records to clone (e.g., only scenes up to fork point)
    filter_func: Optional[Callable] = None

    # ID mapping key this table creates for others to use
    creates_mapping: Optional[str] = None

    # Special field handlers: {field_name: callable(old_value, new_branch_id) -> new_value}
    # For fields that need custom transformation (e.g., embedding_id)
    special_handlers: Dict[str, Callable] = field(default_factory=dict)

    # Fields to skip when copying (in addition to standard id, created_at, updated_at)
    skip_fields: List[str] = field(default_factory=list)

    # Nested models to clone within this model's loop
    # e.g., Scene clones SceneVariants and SceneChoices as nested
    nested_models: List[str] = field(default_factory=list)

    # For nested models: the FK field pointing to parent
    parent_fk_field: Optional[str] = None

    # Whether to clone all records (ignoring fork_sequence filter)
    # Used for StoryCharacter which needs full character list
    clone_all: bool = False

    # Whether to reset certain fields on clone
    reset_fields: Dict[str, Any] = field(default_factory=dict)

    # Whether the model has story_id column (some nested models don't)
    has_story_id: bool = True

    # Whether the model has branch_id column
    has_branch_id: bool = True

    # For models without story_id/branch_id that need to be cloned via FK mapping
    # e.g., ChapterSummaryBatch uses chapter_id to iterate via chapter_id_map
    iterate_via_mapping: Optional[str] = None  # mapping key to use
    iterate_fk_field: Optional[str] = None  # FK field to filter/update

    # Transform function applied to new_data dict before record creation
    # Signature: callable(new_data, fork_sequence, new_branch_id) -> new_data
    clone_transform: Optional[Callable] = None


class BranchCloneRegistry:
    """
    Registry of all branch-aware models and their cloning configurations.

    This class maintains a registry of models that need to be cloned when
    creating a new story branch. Models register themselves using the
    @branch_clone_config decorator.
    """

    _instance = None
    _registry: Dict[str, BranchCloneConfig] = {}
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, config: BranchCloneConfig) -> None:
        """Register a model's cloning configuration."""
        cls._registry[config.table_name] = config
        logger.debug(f"Registered branch-aware model: {config.table_name}")

    @classmethod
    def get(cls, table_name: str) -> Optional[BranchCloneConfig]:
        """Get configuration for a table."""
        return cls._registry.get(table_name)

    @classmethod
    def get_all(cls) -> Dict[str, BranchCloneConfig]:
        """Get all registered configurations."""
        return cls._registry.copy()

    @classmethod
    def get_clone_order(cls) -> List[str]:
        """
        Return table names in topological order for cloning.

        Respects both priority values and dependencies.
        """
        from graphlib import TopologicalSorter

        # Build dependency graph
        ts = TopologicalSorter()
        for table_name, config in cls._registry.items():
            # Filter dependencies to only include registered tables
            valid_deps = [d for d in config.depends_on if d in cls._registry]
            ts.add(table_name, *valid_deps)

        try:
            ordered = list(ts.static_order())
        except Exception as e:
            logger.error(f"Error computing clone order: {e}")
            # Fallback to priority-based order
            ordered = sorted(cls._registry.keys(),
                           key=lambda t: cls._registry[t].priority)

        # Sort by priority within each dependency level
        def sort_key(table_name):
            config = cls._registry.get(table_name)
            return config.priority if config else 100

        # Group by dependency level and sort within each group
        # For simplicity, just return topologically sorted with priority as tiebreaker
        return sorted(ordered, key=lambda t: (sort_key(t), ordered.index(t)))

    @classmethod
    def get_non_nested_tables(cls) -> List[str]:
        """Get tables that should be cloned in main loop (not as nested)."""
        return [
            name for name, config in cls._registry.items()
            if not config.parent_fk_field
        ]

    @classmethod
    def validate(cls) -> List[str]:
        """
        Validate that all tables with branch_id are registered.
        Returns list of unregistered tables (should be empty).
        """
        try:
            from sqlalchemy import inspect
            from ..database import engine

            inspector = inspect(engine)
            unregistered = []

            # Tables that don't need branch cloning
            excluded_tables = {
                'story_branches',  # The branch table itself
                'stories',         # Top-level, no branch_id
                'characters',      # Templates, no branch_id
                'users',           # Users, no branch_id
                'user_settings',   # Settings, no branch_id
                'system_settings', # System settings
                'prompt_templates', # Templates
                'writing_style_presets',
                'tts_settings',
                'tts_provider_configs',
                'brainstorm_sessions',
                'chapter_brainstorm_sessions',
                'worlds',
                'character_snapshots',  # Generated on-demand, not cloned
                'alembic_version',
            }

            for table_name in inspector.get_table_names():
                if table_name in excluded_tables:
                    continue

                columns = {col['name'] for col in inspector.get_columns(table_name)}
                if 'branch_id' in columns and table_name not in cls._registry:
                    unregistered.append(table_name)

            return unregistered
        except Exception as e:
            logger.error(f"Error validating registry: {e}")
            return []

    @classmethod
    def clear(cls) -> None:
        """Clear the registry (mainly for testing)."""
        cls._registry.clear()


def branch_clone_config(
    priority: int = 100,
    depends_on: Optional[List[str]] = None,
    fk_remappings: Optional[Dict[str, str]] = None,
    self_ref_fk: Optional[str] = None,
    deferred_fk_remappings: Optional[Dict[str, str]] = None,
    filter_func: Optional[Callable] = None,
    creates_mapping: Optional[str] = None,
    special_handlers: Optional[Dict[str, Callable]] = None,
    skip_fields: Optional[List[str]] = None,
    nested_models: Optional[List[str]] = None,
    parent_fk_field: Optional[str] = None,
    clone_all: bool = False,
    reset_fields: Optional[Dict[str, Any]] = None,
    has_story_id: bool = True,
    has_branch_id: bool = True,
    iterate_via_mapping: Optional[str] = None,
    iterate_fk_field: Optional[str] = None,
    clone_transform: Optional[Callable] = None,
):
    """
    Decorator to register a model for branch cloning.

    Args:
        priority: Clone order priority (lower = earlier). Default 100.
        depends_on: List of table names that must be cloned first.
        fk_remappings: Dict mapping column names to ID mapping keys.
        self_ref_fk: Column name for self-referential FK.
        deferred_fk_remappings: Dict of FKs to remap after all records cloned.
        filter_func: Function to filter records to clone.
        creates_mapping: Key name for ID mapping this table creates.
        special_handlers: Dict of field handlers for custom transformations.
        skip_fields: Additional fields to skip copying.
        nested_models: Table names of models to clone as nested.
        parent_fk_field: FK field pointing to parent (for nested models).
        clone_all: Whether to clone all records regardless of fork_sequence.
        reset_fields: Dict of field names to reset values.
        has_story_id: Whether model has story_id column.
        has_branch_id: Whether model has branch_id column.
        iterate_via_mapping: For models without story_id/branch_id, iterate via this mapping.
        iterate_fk_field: FK field to filter/update when using iterate_via_mapping.
        clone_transform: Function to transform new_data before record creation.
                        Signature: callable(new_data, fork_sequence, new_branch_id) -> new_data

    Example:
        @branch_clone_config(
            priority=30,
            depends_on=['chapters'],
            fk_remappings={'chapter_id': 'chapter_id_map'},
            creates_mapping='scene_id_map',
            self_ref_fk='parent_scene_id',
            filter_func=lambda q, fork_seq, story_id, branch_id: q.filter(Scene.sequence_number <= fork_seq)
        )
        class Scene(Base):
            __tablename__ = 'scenes'
            ...
    """
    def decorator(model_class):
        if not hasattr(model_class, '__tablename__'):
            raise ValueError(f"Model {model_class.__name__} must have __tablename__")

        config = BranchCloneConfig(
            model_class=model_class,
            table_name=model_class.__tablename__,
            priority=priority,
            depends_on=depends_on or [],
            fk_remappings=fk_remappings or {},
            self_ref_fk=self_ref_fk,
            deferred_fk_remappings=deferred_fk_remappings or {},
            filter_func=filter_func,
            creates_mapping=creates_mapping,
            special_handlers=special_handlers or {},
            skip_fields=skip_fields or [],
            nested_models=nested_models or [],
            parent_fk_field=parent_fk_field,
            clone_all=clone_all,
            reset_fields=reset_fields or {},
            has_story_id=has_story_id,
            has_branch_id=has_branch_id,
            iterate_via_mapping=iterate_via_mapping,
            iterate_fk_field=iterate_fk_field,
            clone_transform=clone_transform,
        )

        BranchCloneRegistry.register(config)
        return model_class

    return decorator


def embedding_id_handler(old_value: Optional[str], new_branch_id: int) -> Optional[str]:
    """Special handler for embedding_id fields - appends branch suffix."""
    if old_value is None:
        return None
    return f"{old_value}_branch_{new_branch_id}"


def clamp_to_fork_sequence(field_name: str, fork_sequence: int):
    """
    Create a handler that clamps a field value to the fork sequence.

    Used for fields like last_appearance_scene that should not exceed
    the fork point.
    """
    def handler(old_value: Optional[int], new_branch_id: int) -> Optional[int]:
        if old_value is None:
            return None
        return min(old_value, fork_sequence)
    return handler


# Standard skip fields for all models
STANDARD_SKIP_FIELDS = ['id', 'created_at', 'updated_at']


def get_model_columns(model_class: Type) -> List[str]:
    """Get list of column names for a model."""
    from sqlalchemy import inspect
    mapper = inspect(model_class)
    return [col.name for col in mapper.columns]
