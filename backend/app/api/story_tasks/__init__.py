"""
Stories API module.

This module contains the stories router and related background tasks.
"""
from .generation_tracker import (
    GenerationState,
    register_generation,
    get_generation,
    remove_generation,
    cleanup_stale_generations,
)

from .background_tasks import (
    # Progress stores
    extraction_progress_store,
    scene_event_extraction_progress_store,

    # Lock getters
    get_chapter_extraction_lock,
    get_story_entity_extraction_lock,
    get_story_deletion_lock,
    get_scene_variant_lock,
    get_variant_edit_lock,
    get_scene_generation_lock,
    mark_scene_generation_start,
    mark_scene_generation_end,
    force_release_scene_generation_lock,

    # Background tasks
    run_interaction_extraction_background,
    run_extractions_in_background,
    recalculate_entities_in_background,
    run_plot_extraction_in_background,
    restore_npc_tracking_in_background,
    cleanup_semantic_data_in_background,
    restore_entity_states_in_background,
    update_working_memory_in_background,
    initialize_branch_entity_states_in_background,
    run_inline_entity_extraction_background,
    run_chapter_summary_background,
    rollback_plot_progress_in_background,
    rollback_working_memory_and_relationships_in_background,
    run_scene_event_extraction_background,
    run_chronicle_extraction_in_background,
)

__all__ = [
    # Generation tracker
    'GenerationState',
    'register_generation',
    'get_generation',
    'remove_generation',
    'cleanup_stale_generations',

    # Progress stores
    'extraction_progress_store',
    'scene_event_extraction_progress_store',

    # Lock getters
    'get_chapter_extraction_lock',
    'get_story_entity_extraction_lock',
    'get_story_deletion_lock',
    'get_scene_variant_lock',
    'get_variant_edit_lock',
    'get_scene_generation_lock',
    'mark_scene_generation_start',
    'mark_scene_generation_end',
    'force_release_scene_generation_lock',

    # Background tasks
    'run_interaction_extraction_background',
    'run_extractions_in_background',
    'recalculate_entities_in_background',
    'run_plot_extraction_in_background',
    'restore_npc_tracking_in_background',
    'cleanup_semantic_data_in_background',
    'restore_entity_states_in_background',
    'update_working_memory_in_background',
    'initialize_branch_entity_states_in_background',
    'run_inline_entity_extraction_background',
    'run_chapter_summary_background',
    'rollback_plot_progress_in_background',
    'rollback_working_memory_and_relationships_in_background',
    'run_scene_event_extraction_background',
    'run_chronicle_extraction_in_background',
]
