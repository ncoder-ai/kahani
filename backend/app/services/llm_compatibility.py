"""
Backward Compatibility Wrapper for LLM Service

This module provides backward compatibility for existing code that uses the old LLM service interfaces.
It wraps the new unified LLM service to maintain existing API contracts.
"""

from typing import Dict, Any, List, AsyncGenerator
from .llm import unified_llm_service
import logging

logger = logging.getLogger(__name__)

# High-level functions for backward compatibility
async def generate_scenario(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
    """Generate a story scenario based on characters and context"""
    return await unified_llm_service.generate_scenario(context, user_id, user_settings)

async def generate_titles(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> List[str]:
    """Generate creative story titles based on story content"""
    return await unified_llm_service.generate_story_title(context, user_id, user_settings)

async def generate_complete_plot(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> List[str]:
    """Generate a complete 5-point plot structure based on characters and scenario"""
    return await unified_llm_service.generate_plot_points(context, user_id, user_settings, "complete")

async def generate_single_plot_point(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
    """Generate a single plot point based on characters and scenario"""
    plot_points = await unified_llm_service.generate_plot_points(context, user_id, user_settings, "single")
    return plot_points[0] if plot_points else ""

async def generate_scene(prompt: str, user_id: int, user_settings: Dict[str, Any], system_prompt: str = "", max_tokens: int = 2048) -> str:
    """Generate a story scene using streaming (workaround for TabbyAPI non-streaming 422 issue)"""
    # This is a legacy function that takes a prompt directly
    # We'll need to create a context from the prompt
    context = {"prompt": prompt}
    return await unified_llm_service.generate_scene(context, user_id, user_settings)

async def generate_scene_streaming(prompt: str, user_id: int, user_settings: Dict[str, Any], system_prompt: str = "", max_tokens: int = 2048):
    """Generate a story scene with streaming"""
    context = {"prompt": prompt}
    async for chunk in unified_llm_service.generate_scene_streaming(context, user_id, user_settings):
        yield chunk

async def generate_choices(scene_content: str, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> List[str]:
    """Generate choices for a scene"""
    return await unified_llm_service.generate_choices(scene_content, context, user_id, user_settings)

async def generate_scene_continuation(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
    """Generate a scene continuation based on context"""
    return await unified_llm_service.generate_scene_continuation(context, user_id, user_settings)

async def generate_scene_continuation_streaming(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]):
    """Generate a scene continuation with streaming response"""
    async for chunk in unified_llm_service.generate_scene_continuation_streaming(context, user_id, user_settings):
        yield chunk

def invalidate_user_llm_cache(user_id: int):
    """Call this when user updates their LLM settings"""
    unified_llm_service.invalidate_user_client(user_id)
    logger.info(f"Invalidated LLM cache for user {user_id}")

