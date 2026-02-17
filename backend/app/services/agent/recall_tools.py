"""Tool wrappers for the recall agent.

Each tool wraps an existing function, taking simple params (strings, ints)
and returning concise formatted strings. The factory function closes over
service references so tools don't need SQLAlchemy sessions as params.
"""

import logging
from typing import Any, Dict, List, Optional

from .tool import Tool, ToolParameter

logger = logging.getLogger(__name__)


def create_recall_tools(
    semantic_memory,
    context_manager,
    db,
    story_id: int,
    branch_id: Optional[int],
    exclude_sequences: Optional[List[int]] = None,
) -> List[Tool]:
    """Create the recall agent tools, closing over service references."""

    # --- Tool 1: search_scenes ---
    async def search_scenes(query: str, top_k: int = 8) -> str:
        """Semantic search for scenes by meaning."""
        try:
            top_k = min(int(top_k), 15)
            results_per_query = await semantic_memory.search_similar_scenes_batch(
                query_texts=[query],
                story_id=story_id,
                top_k=top_k,
                exclude_sequences=exclude_sequences,
            )
            results = results_per_query[0] if results_per_query else []
            if not results:
                return "No scenes found matching that query."

            lines = []
            for r in results:
                seq = r.get("sequence", "?")
                score = r.get("similarity_score", 0)
                chapter = r.get("chapter_id", "?")
                chars = r.get("characters", "")
                lines.append(f"  Scene {seq} (ch {chapter}, score {score:.2f}): characters={chars}")
            return f"Found {len(results)} scenes:\n" + "\n".join(lines)
        except Exception as e:
            logger.warning(f"[recall_tools] search_scenes error: {e}")
            return f"Error: {e}"

    # --- Tool 2: search_events ---
    async def search_events(queries: str = "", keywords: str = "", query: str = "") -> str:
        """Search the scene event index for specific actions/events."""
        try:
            # Accept "query" as alias for "queries" (LLMs sometimes use singular)
            if not queries and query:
                queries = query
            # Parse queries — accept comma-separated or JSON list
            if isinstance(queries, str):
                query_list = [q.strip() for q in queries.split(",") if q.strip()]
            else:
                query_list = list(queries)

            keyword_list = None
            if keywords:
                if isinstance(keywords, str):
                    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
                else:
                    keyword_list = list(keywords)

            # Auto-extract keywords from queries when agent doesn't provide them.
            # This ensures substring matching (Pass B) always fires, catching
            # multi-word terms like "stolen car" that word-split scoring misses.
            if not keyword_list:
                keyword_list = [q.strip() for q in query_list if len(q.strip()) >= 3]

            results = await context_manager._lookup_scene_events(
                sub_queries=query_list,
                story_id=story_id,
                branch_id=branch_id,
                db=db,
                llm_keywords=keyword_list,
            )
            if not results:
                return "No matching events found."

            lines = []
            for r in results:
                seq = r.get("scene_sequence", "?")
                text = r.get("event_text", "")
                score = r.get("score", 0)
                kw = " [keyword match]" if r.get("has_keyword_match") else ""
                lines.append(f"  Scene {seq} (score {score:.2f}{kw}): {text[:150]}")
            return f"Found {len(results)} events:\n" + "\n".join(lines)
        except Exception as e:
            logger.warning(f"[recall_tools] search_events error: {e}")
            return f"Error: {e}"

    # --- Tool 3: read_scene ---
    async def read_scene(sequence: int) -> str:
        """Read the full content of a scene by sequence number."""
        try:
            sequence = int(sequence)
            from ...models.scene import Scene
            from ...models.story_flow import StoryFlow

            scene = db.query(Scene).filter(
                Scene.story_id == story_id,
                Scene.sequence_number == sequence,
                Scene.is_deleted == False,
                *([Scene.branch_id == branch_id] if branch_id else [Scene.branch_id.is_(None)]),
            ).first()

            if not scene:
                return f"Scene {sequence} not found."

            flow = db.query(StoryFlow).filter(
                StoryFlow.scene_id == scene.id,
                StoryFlow.is_active == True,
            ).first()

            if not flow or not flow.scene_variant:
                return f"Scene {sequence} has no active variant."

            content = flow.scene_variant.content or ""
            chapter_id = scene.chapter_id or "?"
            title = flow.scene_variant.title or scene.title or ""

            header = f"Scene {sequence} (chapter {chapter_id})"
            if title:
                header += f" — {title}"

            # Truncate to prevent context overflow
            max_chars = 4000
            if len(content) > max_chars:
                content = content[:max_chars] + "\n... (truncated)"

            return f"{header}\n{content}"
        except Exception as e:
            logger.warning(f"[recall_tools] read_scene error: {e}")
            return f"Error: {e}"

    # --- Tool 4: read_scenes (batch) ---
    async def read_scenes(sequences: str) -> str:
        """Read multiple scenes at once. Returns shorter previews per scene to fit budget."""
        try:
            from ...models.scene import Scene
            from ...models.story_flow import StoryFlow

            # Parse sequences — accept comma-separated, space-separated, or JSON list
            if isinstance(sequences, str):
                seq_list = [s.strip().rstrip(",") for s in sequences.replace(",", " ").split() if s.strip()]
            elif isinstance(sequences, list):
                seq_list = sequences
            else:
                return "Error: sequences must be a comma-separated string or list of numbers"

            seq_ints = []
            for s in seq_list:
                try:
                    seq_ints.append(int(float(str(s).strip())))
                except (ValueError, TypeError):
                    continue
            if not seq_ints:
                return "Error: no valid sequence numbers provided"
            seq_ints = seq_ints[:8]  # Cap at 8

            # Budget per scene scales inversely with count
            chars_per_scene = max(800, 5000 // len(seq_ints))
            parts = []

            for seq in seq_ints:
                scene = db.query(Scene).filter(
                    Scene.story_id == story_id,
                    Scene.sequence_number == seq,
                    Scene.is_deleted == False,
                    *([Scene.branch_id == branch_id] if branch_id else [Scene.branch_id.is_(None)]),
                ).first()
                if not scene:
                    parts.append(f"[Scene {seq}]: not found")
                    continue

                flow = db.query(StoryFlow).filter(
                    StoryFlow.scene_id == scene.id,
                    StoryFlow.is_active == True,
                ).first()
                if not flow or not flow.scene_variant:
                    parts.append(f"[Scene {seq}]: no active variant")
                    continue

                content = flow.scene_variant.content or ""
                if len(content) > chars_per_scene:
                    content = content[:chars_per_scene] + "..."

                chapter_id = scene.chapter_id or "?"
                parts.append(f"[Scene {seq} (ch {chapter_id})]:\n{content}")

            return "\n\n".join(parts)
        except Exception as e:
            logger.warning(f"[recall_tools] read_scenes error: {e}")
            return f"Error: {e}"

    # --- Tool 5: get_nearby_scenes ---
    async def get_nearby_scenes(sequence: int, radius: int = 2) -> str:
        """Get short previews of scenes around a known-relevant scene."""
        try:
            sequence = int(sequence)
            radius = min(int(radius), 5)
            from ...models.scene import Scene
            from ...models.story_flow import StoryFlow

            start = max(1, sequence - radius)
            end = sequence + radius

            scenes = db.query(Scene).filter(
                Scene.story_id == story_id,
                Scene.sequence_number >= start,
                Scene.sequence_number <= end,
                Scene.is_deleted == False,
                *([Scene.branch_id == branch_id] if branch_id else [Scene.branch_id.is_(None)]),
            ).order_by(Scene.sequence_number).all()

            if not scenes:
                return f"No scenes found near sequence {sequence}."

            lines = []
            for scene in scenes:
                flow = db.query(StoryFlow).filter(
                    StoryFlow.scene_id == scene.id,
                    StoryFlow.is_active == True,
                ).first()

                content = ""
                if flow and flow.scene_variant:
                    content = (flow.scene_variant.content or "")[:300]
                    if len(flow.scene_variant.content or "") > 300:
                        content += "..."

                marker = " <<<" if scene.sequence_number == sequence else ""
                lines.append(f"  Scene {scene.sequence_number} (ch {scene.chapter_id or '?'}){marker}: {content}")

            return f"Scenes {start}-{end}:\n" + "\n".join(lines)
        except Exception as e:
            logger.warning(f"[recall_tools] get_nearby_scenes error: {e}")
            return f"Error: {e}"

    # --- Tool 5: list_chapter_scenes ---
    async def list_chapter_scenes(chapter_number: int) -> str:
        """List all scenes in a chapter with short previews."""
        try:
            chapter_number = int(chapter_number)
            from ...models.chapter import Chapter
            from ...models.scene import Scene
            from ...models.story_flow import StoryFlow

            chapter = db.query(Chapter).filter(
                Chapter.story_id == story_id,
                Chapter.chapter_number == chapter_number,
                *([Chapter.branch_id == branch_id] if branch_id else [Chapter.branch_id.is_(None)]),
            ).first()

            if not chapter:
                return f"Chapter {chapter_number} not found."

            scenes = db.query(Scene).filter(
                Scene.chapter_id == chapter.id,
                Scene.is_deleted == False,
            ).order_by(Scene.sequence_number).all()

            if not scenes:
                return f"Chapter {chapter_number} ('{chapter.title or ''}') has no scenes."

            lines = [f"Chapter {chapter_number}: '{chapter.title or ''}' ({len(scenes)} scenes)"]
            for scene in scenes:
                flow = db.query(StoryFlow).filter(
                    StoryFlow.scene_id == scene.id,
                    StoryFlow.is_active == True,
                ).first()

                preview = ""
                if flow and flow.scene_variant:
                    preview = (flow.scene_variant.content or "")[:150]
                    if len(flow.scene_variant.content or "") > 150:
                        preview += "..."

                lines.append(f"  Scene {scene.sequence_number}: {preview}")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"[recall_tools] list_chapter_scenes error: {e}")
            return f"Error: {e}"

    # Build Tool objects with descriptions and parameters
    return [
        Tool(
            name="search_scenes",
            description="Semantic search for scenes by meaning. Good for broad topic searches.",
            parameters=[
                ToolParameter("query", "string", "Natural language search query", required=True),
                ToolParameter("top_k", "int", "Number of results (max 15)", required=False, default=8),
            ],
            func=search_scenes,
        ),
        Tool(
            name="search_events",
            description="Search the event index for specific actions/events. Most precise tool — use this first for finding specific things that happened.",
            parameters=[
                ToolParameter("queries", "string", "Comma-separated search queries (e.g. 'kissed in kitchen, red dress')", required=True),
                ToolParameter("keywords", "string", "Comma-separated keywords/synonyms for better matching", required=False, default=""),
            ],
            func=search_events,
        ),
        Tool(
            name="read_scene",
            description="Read the full content of ONE scene. Use read_scenes (plural) to verify multiple candidates at once.",
            parameters=[
                ToolParameter("sequence", "int", "Scene sequence number", required=True),
            ],
            func=read_scene,
        ),
        Tool(
            name="read_scenes",
            description="Read multiple scenes at once (batch). Much faster than calling read_scene repeatedly. Returns shorter previews per scene.",
            parameters=[
                ToolParameter("sequences", "string", "Comma-separated scene sequence numbers (e.g. '138, 201, 288')", required=True),
            ],
            func=read_scenes,
        ),
        Tool(
            name="get_nearby_scenes",
            description="Get short previews of scenes around a known scene. Useful for finding context before/after an event.",
            parameters=[
                ToolParameter("sequence", "int", "Center scene sequence number", required=True),
                ToolParameter("radius", "int", "How many scenes before/after to include (max 5)", required=False, default=2),
            ],
            func=get_nearby_scenes,
        ),
        Tool(
            name="list_chapter_scenes",
            description="List all scenes in a chapter with short previews. Useful when you know roughly which chapter something happened in.",
            parameters=[
                ToolParameter("chapter_number", "int", "Chapter number (1-based)", required=True),
            ],
            func=list_chapter_scenes,
        ),
    ]
