"""Recall agent orchestrator.

Wires together the agent framework + recall tools + prompts to find
relevant past scenes. Returns formatted text matching the signature
of search_and_format_multi_query() so the caller can't tell the difference.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from .recall_tools import create_recall_tools
from .runner import AgentRunner
from .trace_logger import AgentTraceLogger

logger = logging.getLogger(__name__)


async def run_recall_agent(
    extraction_service,
    semantic_memory,
    context_manager,
    db,
    story_id: int,
    branch_id: Optional[int],
    user_intent: str,
    char_context: str,
    exclude_sequences: Optional[List[int]] = None,
    token_budget: int = 2000,
    prompt_debug: bool = False,
) -> Optional[Tuple[str, float]]:
    """Run the recall agent to find relevant past scenes.

    Returns:
        (formatted_text, score) matching search_and_format_multi_query() signature,
        or None if agent fails (caller should fall back to deterministic pipeline).
    """
    try:
        # 0. Read config
        from ...config import settings
        agent_config = settings.service_defaults.get("recall_agent", {})
        if not agent_config.get("enabled", False):
            logger.debug("[RECALL AGENT] Disabled in config")
            return None
        quality_score = agent_config.get("quality_score", 0.85)
        max_turns = agent_config.get("max_turns", 8)
        agent_timeout = agent_config.get("timeout", 45)

        # 1. Create tools
        tools = create_recall_tools(
            semantic_memory=semantic_memory,
            context_manager=context_manager,
            db=db,
            story_id=story_id,
            branch_id=branch_id,
            exclude_sequences=exclude_sequences,
        )

        # 2. Load prompts from prompts.yml (hot-reloadable)
        from ..llm.prompts import prompt_manager
        system_prompt = prompt_manager.get_prompt("agent_recall", "system")
        user_template = prompt_manager.get_prompt("agent_recall", "user")

        if not system_prompt:
            logger.warning("[RECALL AGENT] No system prompt found for agent_recall")
            return None

        # Format user message with context
        user_message = user_template.format(
            char_context=char_context,
            user_intent=user_intent,
        ) if user_template else f"Find scenes relevant to: {user_intent}"

        # 3. Create runner
        trace_logger = AgentTraceLogger("recall_agent", enabled=prompt_debug)
        runner = AgentRunner(
            extraction_service=extraction_service,
            tools=tools,
            system_prompt=system_prompt,
            max_turns=max_turns,
            timeout=float(agent_timeout),
            agent_name="recall_agent",
            trace_logger=trace_logger,
        )

        # 4. Run the agent
        logger.info(f"[RECALL AGENT] Starting for intent: '{user_intent[:100]}'")
        result = await runner.run(user_message)

        if not result["success"]:
            logger.info(f"[RECALL AGENT] Failed: {result['error']} (turns: {result['turns']})")
            return None

        # 5. Parse final answer → format as scene text
        answer = result["answer"]
        if isinstance(answer, dict):
            scene_sequences = answer.get("relevant_scenes", [])
        elif isinstance(answer, list):
            # Some LLMs return a flat list of scene numbers instead of a dict
            scene_sequences = [s for s in answer if isinstance(s, (int, float))]
            logger.info(f"[RECALL AGENT] Final answer was a list, extracted {len(scene_sequences)} scene numbers")
        else:
            logger.info(f"[RECALL AGENT] Final answer is not a dict or list: {type(answer)}")
            return None
        if not scene_sequences:
            logger.info("[RECALL AGENT] No relevant scenes in final answer")
            return None

        # Fetch and format scene content, same style as search_and_format_multi_query
        formatted_text, top_score = await _format_agent_scenes(
            db=db,
            story_id=story_id,
            branch_id=branch_id,
            scene_sequences=scene_sequences,
            token_budget=token_budget,
            quality_score=quality_score,
        )

        if formatted_text:
            logger.info(f"[RECALL AGENT] Completed in {result['turns']} turns, "
                       f"found {len(scene_sequences)} scenes, score={top_score:.2f}")
        return (formatted_text, top_score) if formatted_text else None

    except Exception as e:
        logger.error(f"[RECALL AGENT] Unexpected error: {e}", exc_info=True)
        return None


async def _format_agent_scenes(
    db,
    story_id: int,
    branch_id: Optional[int],
    scene_sequences: List[int],
    token_budget: int,
    quality_score: float = 0.85,
) -> Tuple[Optional[str], float]:
    """Fetch scene content and format like search_and_format_multi_query output."""
    from ...models.scene import Scene
    from ...models.story_flow import StoryFlow

    parts = []
    chars_remaining = token_budget * 4  # rough chars-per-token estimate
    top_score = quality_score

    for seq in scene_sequences:
        if chars_remaining <= 0:
            break

        scene = db.query(Scene).filter(
            Scene.story_id == story_id,
            Scene.sequence_number == int(seq),
            Scene.is_deleted == False,
            *([Scene.branch_id == branch_id] if branch_id else [Scene.branch_id.is_(None)]),
        ).first()
        if not scene:
            continue

        flow = db.query(StoryFlow).filter(
            StoryFlow.scene_id == scene.id,
            StoryFlow.is_active == True,
        ).first()
        if not flow or not flow.scene_variant:
            continue

        content = flow.scene_variant.content or ""
        # Truncate per-scene content to fit budget
        max_per_scene = min(2000, chars_remaining)
        if len(content) > max_per_scene:
            content = content[:max_per_scene] + "..."

        parts.append(f"[Relevant from Scene {seq}]:\n{content}")
        chars_remaining -= len(content) + 50  # header overhead

    if not parts:
        return None, 0.0

    return "\n\n".join(parts), top_score
