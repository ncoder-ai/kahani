"""Recall agent orchestrator.

Wires together the agent framework + recall tools + prompts to find
relevant past scenes. Returns formatted text matching the signature
of search_and_format_multi_query() so the caller can't tell the difference.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from .recall_tools import create_recall_tools
from .runner import AgentRunner
from .trace_logger import AgentTraceLogger

logger = logging.getLogger(__name__)

# Re-use the robust JSON extractor from extraction_service
try:
    from ..llm.extraction_service import extract_json_robust
except ImportError:
    extract_json_robust = None


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

        # Post-agent validation: LLM cross-checks each scene against the query
        scene_sequences = await _validate_agent_scenes(
            extraction_service=extraction_service,
            db=db,
            story_id=story_id,
            branch_id=branch_id,
            user_intent=user_intent,
            scene_sequences=scene_sequences,
        )
        if not scene_sequences:
            logger.info("[RECALL AGENT] All scenes rejected by validation")
            return None

        # Expand scene list to include ±1 neighbors for contiguous narrative arcs
        scene_sequences = _expand_neighbors(scene_sequences)

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


async def _validate_agent_scenes(
    extraction_service,
    db,
    story_id: int,
    branch_id: Optional[int],
    user_intent: str,
    scene_sequences: List[int],
    snippet_chars: int = 500,
) -> List[int]:
    """Post-agent validation: LLM cross-checks each scene against the query.

    Fetches a short snippet of each scene, sends them all to the extraction LLM
    with the original intent, and asks for a per-scene relevant/not-relevant judgment.
    Returns only the scenes marked as relevant.
    """
    from ...models.scene import Scene
    from ...models.story_flow import StoryFlow
    from ..llm.prompts import prompt_manager

    if len(scene_sequences) <= 1:
        return scene_sequences  # Nothing to validate

    # 1. Fetch snippets
    snippets = {}
    for seq in scene_sequences:
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
        if flow and flow.scene_variant:
            content = (flow.scene_variant.content or "")[:snippet_chars]
            snippets[int(seq)] = content

    if not snippets:
        return scene_sequences  # Can't validate without content

    # 2. Build numbered scene list
    scene_list_parts = []
    for seq in sorted(snippets.keys()):
        scene_list_parts.append(f"{seq}. {snippets[seq]}")
    scene_list = "\n\n".join(scene_list_parts)

    # 3. Call extraction LLM with validation prompt
    try:
        prompt_template = prompt_manager.get_prompt("agent_recall_validate", "user")
        if not prompt_template:
            logger.warning("[RECALL VALIDATE] No prompt template found, skipping validation")
            return scene_sequences

        prompt_text = prompt_template.format(
            user_intent=user_intent,
            scene_list=scene_list,
        )
        messages = [{"role": "user", "content": prompt_text}]
        response = await extraction_service.generate_with_messages(messages, max_tokens=200)

        # 4. Parse indexed true/false response
        parsed = None
        if extract_json_robust:
            parsed = extract_json_robust(response)
        if not parsed:
            try:
                parsed = json.loads(response)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"[RECALL VALIDATE] Failed to parse response: {response[:200]}")
                return scene_sequences  # Can't parse → keep all

        if not isinstance(parsed, dict):
            logger.warning(f"[RECALL VALIDATE] Response is not a dict: {type(parsed)}")
            return scene_sequences

        # 5. Filter scenes
        validated = []
        rejected = []
        for seq in scene_sequences:
            # Check both int and string keys
            val = parsed.get(str(seq), parsed.get(seq, True))
            if val is True or val == "true" or val == 1:
                validated.append(seq)
            else:
                rejected.append(seq)

        if rejected:
            logger.info(f"[RECALL VALIDATE] Kept {validated}, rejected {rejected}")
        else:
            logger.info(f"[RECALL VALIDATE] All {len(validated)} scenes validated")

        return validated if validated else scene_sequences  # Never return empty — keep originals as fallback

    except Exception as e:
        logger.warning(f"[RECALL VALIDATE] Validation failed, keeping all scenes: {e}")
        return scene_sequences  # Validation is best-effort


def _expand_neighbors(scene_sequences: List[int], radius: int = 1) -> List[int]:
    """Expand scene list to include ±radius neighbors, sorted chronologically.

    Events span multiple consecutive scenes. If the agent finds scene 201,
    we also include 200 and 202 to give the main LLM the full narrative arc.
    The token budget in _format_agent_scenes handles overflow naturally.
    """
    expanded = set()
    for seq in scene_sequences:
        seq = int(seq)
        for offset in range(-radius, radius + 1):
            if seq + offset > 0:
                expanded.add(seq + offset)
    return sorted(expanded)


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
        # Truncate only if this scene exceeds remaining budget
        if len(content) > chars_remaining:
            content = content[:chars_remaining] + "..."

        parts.append(f"[Relevant from Scene {seq}]:\n{content}")
        chars_remaining -= len(content) + 50  # header overhead

    if not parts:
        return None, 0.0

    return "\n\n".join(parts), top_score
