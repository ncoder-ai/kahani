"""
Roleplay Context Builder

Builds cache-friendly multi-message prompts for roleplay sessions.
Follows the same stable-to-dynamic ordering as story prompts to maximize
LLM provider cache hits.

Message order:
1. System prompt (RP base + prose style + content filter)
2. ROLEPLAY SCENARIO (stable) — setting, scenario, tone
3. CHARACTER ROSTER (stable) — descriptions, voice styles, development state
4. CHARACTER RELATIONSHIPS (stable-ish) — loaded from dev stage + overrides
5. ROLEPLAY RULES (stable) — turn mode, narration, response length
   ---- cache break ----
6. CONVERSATION SUMMARY (if turn count > 30)
7. RECENT TURNS (changes every turn) — last N turns
8. RELEVANT PAST TURNS (semantic search for long RPs, turn count > 15)
→ TASK MESSAGE (appended by caller)
"""

import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func

from ...models.character import Character, StoryCharacter
from ...models.chapter import Chapter
from ...models.story import Story
from ...models.scene import Scene
from ...models.scene_variant import SceneVariant
from ...models.story_flow import StoryFlow
from ..llm.prompts import prompt_manager
from ..llm.service import UnifiedLLMService
from ..llm.context_formatter import format_character_voice_styles
from ...utils.content_filter import get_content_permission_prompt

logger = logging.getLogger(__name__)

# Shared LLM service instance (same as roleplay_service.py)
_llm_service = UnifiedLLMService()

# Token budget defaults
DEFAULT_MAX_CONTEXT_TOKENS = 8000
RECENT_TURNS_BUDGET_RATIO = 0.4  # 40% of budget for recent turns
CHARS_PER_TOKEN = 4  # Rough estimate

# Semantic memory thresholds
SEMANTIC_SEARCH_TURN_THRESHOLD = 15  # Enable semantic search after this many turns
SEMANTIC_SEARCH_BUDGET_CHARS = 1500  # Budget for past turn context

# Summarization thresholds
SUMMARY_TURN_THRESHOLD = 30  # Summarize when total turns exceed this
SUMMARY_INTERVAL = 20  # Re-summarize every N new turns
SUMMARY_BATCH_SIZE = 20  # How many turns to summarize at once
SUMMARY_BUDGET_CHARS = 800  # Budget for summary text


class RoleplayContextBuilder:
    """Builds context for roleplay LLM calls."""

    @staticmethod
    async def build_context(
        db: Session,
        story: Story,
        user_settings: dict,
    ) -> dict:
        """
        Build the full roleplay context dict.

        Returns a dict with all data needed by build_message_prefix() and
        build_task_message() to construct the final prompt.
        """
        rp_settings = (story.story_context or {}).get("roleplay_settings", {})
        talkativeness = (story.story_context or {}).get("character_talkativeness", {})

        # Load all active story characters with their base character data
        story_characters = (
            db.query(StoryCharacter)
            .filter(
                StoryCharacter.story_id == story.id,
                StoryCharacter.is_active == True,
            )
            .all()
        )

        # Build character info dicts
        characters = []
        player_character = None
        for sc in story_characters:
            char = db.query(Character).filter(Character.id == sc.character_id).first()
            if not char:
                continue

            char_info = {
                "story_character_id": sc.id,
                "character_id": char.id,
                "name": char.name,
                "description": char.description or "",
                "gender": char.gender,
                "personality_traits": char.personality_traits or [],
                "background": char.background or "",
                "goals": sc.current_goals or char.goals or "",
                "fears": char.fears or "",
                "appearance": char.appearance or "",
                "role": sc.role or "participant",
                "voice_style": sc.voice_style_override or char.voice_style,
                "emotional_state": sc.current_emotional_state,
                "development": sc.character_development or [],
                "relationships": sc.relationships or {},
                "talkativeness": talkativeness.get(str(sc.id), 0.5),
                "is_player": sc.is_player_character,
            }
            characters.append(char_info)
            if sc.is_player_character:
                player_character = char_info

        # Get total turn count
        max_tokens = user_settings.get("context_max_tokens", DEFAULT_MAX_CONTEXT_TOKENS)
        turn_count = (
            db.query(sql_func.count(StoryFlow.id))
            .filter(
                StoryFlow.story_id == story.id,
                StoryFlow.is_active == True,
            )
            .scalar()
        ) or 0

        # Get or generate summary for long sessions
        summary = None
        if turn_count > SUMMARY_TURN_THRESHOLD:
            summary = await RoleplayContextBuilder._get_or_generate_summary(
                db, story, user_settings
            )

        # Load recent turns (scenes)
        recent_turns = await RoleplayContextBuilder._load_recent_turns(
            db, story, max_tokens, summary_exists=summary is not None
        )

        # Semantic search for relevant past turns
        relevant_past = None
        if turn_count > SEMANTIC_SEARCH_TURN_THRESHOLD:
            relevant_past = await RoleplayContextBuilder._search_relevant_past_turns(
                db, story, recent_turns
            )

        return {
            "story": story,
            "characters": characters,
            "player_character": player_character,
            "recent_turns": recent_turns,
            "summary": summary,
            "relevant_past": relevant_past,
            "rp_settings": rp_settings,
            "talkativeness": talkativeness,
            "max_tokens": max_tokens,
            "allow_nsfw": user_settings.get("allow_nsfw", False),
        }

    @staticmethod
    def build_message_prefix(
        context: dict,
        user_settings: dict,
    ) -> list[dict]:
        """
        Build the cache-friendly multi-message prefix for roleplay.

        Returns list of {role, content} message dicts.
        Everything up to the cache break is stable between turns.
        """
        story = context["story"]
        characters = context["characters"]
        player_character = context["player_character"]
        rp_settings = context["rp_settings"]
        allow_nsfw = context["allow_nsfw"]
        recent_turns = context["recent_turns"]
        summary = context.get("summary")
        relevant_past = context.get("relevant_past")

        messages = []

        # --- Message 1: System prompt ---
        system_prompt = RoleplayContextBuilder._build_system_prompt(
            rp_settings, user_settings, allow_nsfw
        )
        messages.append({"role": "system", "content": system_prompt})

        # --- Message 2: ROLEPLAY SCENARIO (stable) ---
        scenario_parts = ["=== ROLEPLAY SCENARIO ==="]
        if story.tone:
            scenario_parts.append(f"Tone: {story.tone}")
        if story.scenario:
            scenario_parts.append(f"Scenario: {story.scenario}")
        if story.world_setting:
            scenario_parts.append(f"Setting: {story.world_setting}")
        if story.content_rating:
            scenario_parts.append(f"Content Rating: {story.content_rating.upper()}")

        player_name = player_character["name"] if player_character else "the user"
        player_mode = rp_settings.get("player_mode", "character")
        if player_mode == "character":
            scenario_parts.append(f"\nThe player is roleplaying as {player_name}.")
        elif player_mode == "narrator":
            scenario_parts.append("\nThe player acts as Narrator, describing events without being a character.")
        elif player_mode == "director":
            scenario_parts.append("\nThe player acts as Director, giving meta-instructions to guide the scene.")

        messages.append({"role": "user", "content": "\n".join(scenario_parts)})

        # --- Message 3: CHARACTER ROSTER (stable) ---
        roster_text = RoleplayContextBuilder._build_character_roster(characters)
        if roster_text:
            messages.append({"role": "user", "content": roster_text})

        # --- Message 4: CHARACTER DIALOGUE STYLES (stable) ---
        voice_text = format_character_voice_styles(
            [c for c in characters if not c["is_player"]]
        )
        if voice_text:
            header = prompt_manager.get_raw_prompt("roleplay.dialogue_styles_header")
            if not header:
                header = "=== CHARACTER DIALOGUE STYLES ===\n"
            messages.append({"role": "user", "content": header + voice_text})

        # --- Message 5: CHARACTER RELATIONSHIPS (stable-ish) ---
        rel_text = RoleplayContextBuilder._build_relationship_context(characters)
        if rel_text:
            messages.append({"role": "user", "content": rel_text})

        # --- Message 6: ROLEPLAY RULES (stable) ---
        rules_text = RoleplayContextBuilder._build_rules_message(rp_settings, player_character, characters)
        messages.append({"role": "user", "content": rules_text})

        # ---- CACHE BREAK POINT ----

        # --- Message 7: CONVERSATION SUMMARY (if long session) ---
        if summary:
            messages.append({"role": "user", "content": f"=== CONVERSATION SO FAR ===\n{summary}"})

        # --- Message 8: RECENT TURNS (changes every turn) ---
        if recent_turns:
            turns_text = "=== RECENT CONVERSATION ===\n" + recent_turns
            messages.append({"role": "user", "content": turns_text})

        # --- Message 9: RELEVANT PAST TURNS (semantic search) ---
        if relevant_past:
            messages.append({"role": "user", "content": f"=== RELEVANT PAST TURNS ===\n{relevant_past}"})

        return messages

    @staticmethod
    def build_task_message(
        user_input: str,
        input_mode: str,
        active_character_names: list[str],
        player_name: str,
        rp_settings: dict,
    ) -> str:
        """
        Build the final task message appended after the prefix.

        Args:
            user_input: What the user typed
            input_mode: "character", "narration", or "direction"
            active_character_names: Which AI characters should respond
            player_name: Name of the player's character
            rp_settings: Roleplay settings dict
        """
        response_length = rp_settings.get("response_length", "concise")
        length_key = "roleplay.length_concise" if response_length == "concise" else "roleplay.length_detailed"
        length_instruction = prompt_manager.get_raw_prompt(length_key) or "Keep responses concise (150-300 words)."

        narration_style = rp_settings.get("narration_style", "moderate")
        narration_key = f"roleplay.narration_{narration_style}"
        narration_instruction = prompt_manager.get_raw_prompt(narration_key) or ""

        active_list = ", ".join(active_character_names)

        if input_mode == "direction":
            template_key = "roleplay.task_direction"
        elif input_mode == "narration":
            template_key = "roleplay.task_narration"
        else:
            template_key = "roleplay.task_character"

        result = prompt_manager.get_raw_prompt(
            template_key,
            active_list=active_list,
            user_input=user_input,
            player_name=player_name,
            length_instruction=length_instruction,
            narration_instruction=narration_instruction,
        )
        if result:
            return result

        # Fallback if template not found
        return (
            f"ACTIVE CHARACTERS THIS TURN: {active_list}\n\n"
            f">>> {user_input} <<<\n\n"
            f"Write responses for the active characters.\n"
            f"{length_instruction}\n{narration_instruction}"
        )

    @staticmethod
    def build_auto_continue_task(
        active_character_names: list[str],
        player_name: str,
        rp_settings: dict,
    ) -> str:
        """Build task message for auto-continue (characters talking without user input)."""
        response_length = rp_settings.get("response_length", "concise")
        length_key = "roleplay.length_concise_auto" if response_length == "concise" else "roleplay.length_detailed_auto"
        length_instruction = prompt_manager.get_raw_prompt(length_key) or "Keep responses concise (150-300 words)."

        active_list = ", ".join(active_character_names)

        result = prompt_manager.get_raw_prompt(
            "roleplay.task_auto_continue",
            active_list=active_list,
            player_name=player_name,
            length_instruction=length_instruction,
        )
        if result:
            return result

        return (
            f"ACTIVE CHARACTERS THIS TURN: {active_list}\n\n"
            f"Continue the conversation between the AI characters.\n"
            f"{length_instruction}"
        )

    @staticmethod
    def build_auto_player_task(
        player_name: str,
        rp_settings: dict,
    ) -> str:
        """Build task message for auto-generating the player character's turn."""
        response_length = rp_settings.get("response_length", "concise")
        length_key = "roleplay.length_concise" if response_length == "concise" else "roleplay.length_detailed"
        length_instruction = prompt_manager.get_raw_prompt(length_key) or "Keep responses concise (150-300 words)."

        narration_style = rp_settings.get("narration_style", "moderate")
        narration_key = f"roleplay.narration_{narration_style}"
        narration_instruction = prompt_manager.get_raw_prompt(narration_key) or ""

        result = prompt_manager.get_raw_prompt(
            "roleplay.task_auto_player",
            player_name=player_name,
            length_instruction=length_instruction,
            narration_instruction=narration_instruction,
        )
        if result:
            return result

        return (
            f"Write {player_name}'s next response in this conversation.\n"
            f"Write ONLY {player_name} — no other characters.\n"
            f"{length_instruction}\n{narration_instruction}"
        )

    @staticmethod
    def build_opening_task(
        character_names: list[str],
        player_name: str,
        scenario: str,
        rp_settings: dict,
    ) -> str:
        """Build task message for generating the opening scene."""
        response_length = rp_settings.get("response_length", "concise")
        length_key = "roleplay.length_concise_opening" if response_length == "concise" else "roleplay.length_detailed_opening"
        length_instruction = prompt_manager.get_raw_prompt(length_key) or "Keep the opening concise (200-400 words)."

        char_list = ", ".join(character_names)

        result = prompt_manager.get_raw_prompt(
            "roleplay.task_opening",
            char_list=char_list,
            scenario=scenario,
            player_name=player_name,
            length_instruction=length_instruction,
        )
        if result:
            return result

        return (
            f"Generate the opening scene for this roleplay.\n\n"
            f"Characters present: {char_list}\n"
            f"Scenario: {scenario}\n\n"
            f"Establish the setting and show the characters' initial behavior.\n"
            f"{length_instruction}"
        )

    # --- Private helpers ---

    @staticmethod
    def _build_system_prompt(
        rp_settings: dict,
        user_settings: dict,
        allow_nsfw: bool,
    ) -> str:
        """Build the system prompt for roleplay."""
        # Try to load from prompts.yml, fall back to inline
        system_text = prompt_manager.get_prompt("roleplay", "system")
        if not system_text:
            system_text = (
                "You are a roleplay facilitator embodying multiple characters in an interactive scene.\n\n"
                "YOUR ROLE:\n"
                "- Write ONLY the AI characters' dialogue, actions, and reactions\n"
                "- NEVER write the player character's actions, dialogue, or internal thoughts\n"
                "- Each character must speak/act consistently with their personality and development\n"
                "- Respond naturally to the player's actions — acknowledge, react, create consequences\n\n"
                "RESPONSE FORMAT:\n"
                "- Use **Character Name** before each character's section\n"
                "- Dialogue in quotes, actions in asterisks\n"
                "- Characters who have nothing relevant to say should stay silent\n"
                "- End at a natural point where the player can respond\n"
            )

        # Append content filter
        content_prompt = get_content_permission_prompt(allow_nsfw)
        system_text += "\n\n" + content_prompt

        return system_text

    @staticmethod
    def _build_character_roster(characters: list[dict]) -> str:
        """Build the CHARACTER ROSTER message with all character details."""
        if not characters:
            return ""

        parts = ["=== CHARACTER ROSTER ==="]

        for char in characters:
            if char["is_player"]:
                parts.append(f"\n**{char['name']}** (PLAYER CHARACTER — do not write for this character)")
                parts.append(f"  Role: {char['role']}")
                if char.get("description"):
                    parts.append(f"  Description: {char['description'][:300]}")
                continue

            parts.append(f"\n**{char['name']}** (AI Character)")
            parts.append(f"  Role: {char['role']}")
            if char.get("description"):
                parts.append(f"  Description: {char['description'][:500]}")
            if char.get("personality_traits"):
                traits = ", ".join(char["personality_traits"][:8])
                parts.append(f"  Personality: {traits}")
            if char.get("goals"):
                parts.append(f"  Current Goals: {char['goals'][:200]}")
            if char.get("emotional_state"):
                parts.append(f"  Current Emotional State: {char['emotional_state']}")
            if char.get("appearance"):
                parts.append(f"  Appearance: {char['appearance'][:300]}")
            if char.get("background"):
                parts.append(f"  Background: {char['background'][:300]}")

            # Development entries (from loaded story stage)
            dev = char.get("development", [])
            if dev:
                defining = [e for e in dev if e.get("is_defining")]
                recent = [e for e in dev if not e.get("is_defining")][-5:]  # Last 5
                if defining:
                    parts.append("  Key Development:")
                    for entry in defining[:5]:
                        parts.append(f"    - [{entry['entry_type']}] {entry['description'][:150]}")
                if recent:
                    parts.append("  Recent Development:")
                    for entry in recent:
                        parts.append(f"    - [{entry['entry_type']}] {entry['description'][:150]}")

        return "\n".join(parts)

    @staticmethod
    def _build_relationship_context(characters: list[dict]) -> str:
        """Build CHARACTER RELATIONSHIPS message from loaded relationship data."""
        all_relationships = []
        seen_pairs = set()

        for char in characters:
            for other_name, rel_data in (char.get("relationships") or {}).items():
                pair = tuple(sorted([char["name"], other_name]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                rel_type = rel_data.get("type", "unknown")
                strength = rel_data.get("strength", 0)
                arc = rel_data.get("arc_summary", "")
                line = f"  {pair[0]} <-> {pair[1]}: {rel_type} (strength: {strength:.1f})"
                if arc:
                    line += f" — {arc[:100]}"
                all_relationships.append(line)

        if not all_relationships:
            return ""

        header = "=== CHARACTER RELATIONSHIPS ==="
        return header + "\n" + "\n".join(all_relationships)

    @staticmethod
    def _build_rules_message(
        rp_settings: dict,
        player_character: Optional[dict],
        characters: list[dict],
    ) -> str:
        """Build the ROLEPLAY RULES message."""
        rules = ["=== ROLEPLAY RULES ==="]

        ai_count = sum(1 for c in characters if not c.get("is_player", False))
        is_group = ai_count > 1

        turn_mode = rp_settings.get("turn_mode", "natural")
        if turn_mode == "natural":
            rules.append("- Characters respond when addressed or when the situation is relevant to them")
            rules.append("- Not every character needs to respond every turn — stay silent if natural")
        elif turn_mode == "round_robin":
            rules.append("- All listed active characters should respond in order")

        if is_group:
            rules.append("- ONLY characters listed as ACTIVE in the task message should speak or act")
            rules.append("- Characters NOT listed as active must stay completely silent this turn")
            rules.append("- Use **Character Name** headers to clearly separate each character's section")
            rules.append("- Characters may react to each other, not just to the player")

        rules.append("- Each character has a distinct personality — maintain their unique voice")
        rules.append("- React to what just happened — acknowledge, respond, create consequences")
        rules.append("- End at a natural pause where the player can respond")

        if player_character:
            rules.append(f"- NEVER write {player_character['name']}'s dialogue, actions, or thoughts")

        return "\n".join(rules)

    @staticmethod
    async def _load_recent_turns(
        db: Session,
        story: Story,
        max_tokens: int,
        summary_exists: bool = False,
    ) -> str:
        """Load recent turns (scenes) formatted for the prompt, respecting token budget."""
        budget_chars = int(max_tokens * RECENT_TURNS_BUDGET_RATIO * CHARS_PER_TOKEN)

        # When summary exists, load fewer turns (summary covers earlier ones)
        turn_limit = 20 if summary_exists else 50

        # Get recent scenes via StoryFlow (active path)
        flows = (
            db.query(StoryFlow)
            .filter(
                StoryFlow.story_id == story.id,
                StoryFlow.is_active == True,
            )
            .order_by(StoryFlow.sequence_number.desc())
            .limit(turn_limit)
            .all()
        )

        if not flows:
            return ""

        # Reverse to chronological order
        flows.reverse()

        # Load variant content for each flow entry
        turns = []
        total_chars = 0
        for flow in flows:
            variant = db.query(SceneVariant).filter(
                SceneVariant.id == flow.scene_variant_id
            ).first()
            if not variant or not variant.content:
                continue

            content = variant.content.strip()
            method = variant.generation_method or "auto"

            # Format turn label
            if method in ("user_written", "auto_player"):
                label = f"[Player Turn {flow.sequence_number}]"
            elif method == "direction":
                label = f"[Direction {flow.sequence_number}]"
            else:
                label = f"[Turn {flow.sequence_number}]"

            turn_text = f"{label}\n{content}"

            # Check budget
            if total_chars + len(turn_text) > budget_chars:
                # If we haven't added any turns yet, add at least the last one truncated
                if not turns:
                    turns.append(turn_text[:budget_chars])
                break

            turns.append(turn_text)
            total_chars += len(turn_text)

        return "\n\n".join(turns)

    @staticmethod
    async def _search_relevant_past_turns(
        db: Session,
        story: Story,
        recent_turns_text: str,
    ) -> Optional[str]:
        """
        Search for relevant past turns using semantic memory.
        Only activates when turn count > SEMANTIC_SEARCH_TURN_THRESHOLD.
        Uses the last user turn as the query.
        """
        try:
            from ..semantic_memory import SemanticMemoryService

            semantic_memory = SemanticMemoryService()

            # Build query from the last few turns (most recent context)
            query = recent_turns_text[-500:] if recent_turns_text else ""
            if not query.strip():
                return None

            # Get recent sequence numbers to exclude
            recent_flows = (
                db.query(StoryFlow.sequence_number)
                .filter(
                    StoryFlow.story_id == story.id,
                    StoryFlow.is_active == True,
                )
                .order_by(StoryFlow.sequence_number.desc())
                .limit(10)
                .all()
            )
            exclude_seqs = [f.sequence_number for f in recent_flows]

            results = await semantic_memory.search_similar_scenes(
                query_text=query,
                story_id=story.id,
                top_k=5,
                exclude_sequences=exclude_seqs,
                branch_id=story.current_branch_id,
            )

            if not results:
                return None

            # Format results within budget
            parts = []
            total_chars = 0
            for result in results:
                content = result.get("content", "")
                seq = result.get("sequence_number", "?")
                text = f"[Recalled Turn {seq}]\n{content}"
                if total_chars + len(text) > SEMANTIC_SEARCH_BUDGET_CHARS:
                    break
                parts.append(text)
                total_chars += len(text)

            return "\n\n".join(parts) if parts else None

        except Exception as e:
            logger.warning(f"Semantic search failed for RP {story.id}: {e}")
            return None

    @staticmethod
    async def improve_semantic_search(
        context: dict,
        messages: list[dict],
        user_input: str,
        user_settings: dict,
        user_id: int,
        db: Session,
    ) -> bool:
        """
        Run multi-query decomposition + RRF search to improve semantic recall.

        Mirrors _maybe_improve_semantic_scenes() in service.py but uses a
        lightweight ContextManager instance for the search pipeline.

        Replaces or inserts the RELEVANT PAST TURNS message in-place.
        Returns True if messages were updated.
        """
        try:
            story = context["story"]
            characters = context["characters"]

            # Build char_context for pronoun resolution in decomposition
            char_labels = []
            for c in characters:
                name = c.get("name", "")
                if not name:
                    continue
                parts = [name]
                gender = (c.get("gender") or "").strip().lower()
                if gender:
                    parts.append(gender)
                role = c.get("role", "")
                if role:
                    parts.append(role)
                char_labels.append(f"{parts[0]} ({', '.join(parts[1:])})" if len(parts) > 1 else name)
            char_context = f"Characters: {', '.join(char_labels)}\n\n" if char_labels else ""

            # Get decomposition prompt
            decompose_task = prompt_manager.get_prompt("semantic_decompose", "user", user_intent=user_input)
            if not decompose_task:
                logger.info("[RP SEMANTIC] No decompose prompt found, skipping")
                return False

            # Route to extraction LLM (preferred) or main LLM
            ext_settings = user_settings.get('extraction_model_settings', {})
            use_extraction = ext_settings.get('enabled', False)
            extraction_service = _llm_service._get_extraction_service(user_settings) if use_extraction else None

            if extraction_service:
                allow_thinking = ext_settings.get('thinking_enabled_memory', True)
                decompose_messages = [{"role": "user", "content": char_context + decompose_task}]
                response = await extraction_service.generate_with_messages(
                    messages=decompose_messages,
                    max_tokens=300,
                    allow_thinking=allow_thinking,
                )
            else:
                import copy
                decompose_messages = copy.deepcopy(messages)
                decompose_messages.append({"role": "user", "content": char_context + decompose_task})
                decompose_settings = copy.deepcopy(user_settings)
                decompose_settings.setdefault('llm_settings', {})['temperature'] = 0.3
                decompose_settings['llm_settings']['reasoning_effort'] = 'disabled'
                response = await _llm_service._generate_with_messages(
                    messages=decompose_messages,
                    user_id=user_id,
                    user_settings=decompose_settings,
                    max_tokens=300,
                    skip_nsfw_filter=True,
                )

            if not response or not response.strip():
                logger.info("[RP SEMANTIC] Empty decomposition response")
                return False

            parsed = _llm_service._parse_decomposition_response(response)
            if not parsed:
                logger.info("[RP SEMANTIC] Failed to parse decomposition response")
                return False

            intent_type, temporal_type, sub_queries, keywords = parsed

            # Direct intent needs no semantic improvement
            if intent_type == "direct":
                logger.info("[RP SEMANTIC] Direct intent — no improvement needed")
                return False

            # Fallback keywords for recall without LLM-provided keywords
            if intent_type == "recall" and not keywords:
                _stop = {"the", "a", "an", "on", "in", "of", "to", "by", "with", "and", "or",
                         "is", "was", "her", "his", "him", "she", "he", "not", "had", "has",
                         "did", "does", "that", "this", "from", "for", "about", "over", "into"}
                for sq in sub_queries:
                    for w in sq.lower().split():
                        if len(w) >= 4 and w not in _stop:
                            keywords.append(w)
                if keywords:
                    keywords = list(dict.fromkeys(keywords))

            logger.info(f"[RP SEMANTIC] Intent: {intent_type or 'unknown'}, "
                       f"Sub-queries: {sub_queries}"
                       + (f", Keywords: {keywords}" if keywords else ""))

            # Build lightweight ContextManager + search state
            from ..context_manager import ContextManager

            ctx_mgr = ContextManager(user_settings=user_settings, user_id=user_id)
            if not ctx_mgr.semantic_memory:
                logger.info("[RP SEMANTIC] No semantic memory available")
                return False

            # Get recent sequence numbers to exclude
            recent_flows = (
                db.query(StoryFlow.sequence_number)
                .filter(
                    StoryFlow.story_id == story.id,
                    StoryFlow.is_active == True,
                )
                .order_by(StoryFlow.sequence_number.desc())
                .limit(10)
                .all()
            )
            exclude_seqs = [f.sequence_number for f in recent_flows]

            chapter_id = story.chapters[0].id if story.chapters else None

            # Build context dict with _semantic_search_state for search_and_format_multi_query
            search_context = {
                "_semantic_search_state": {
                    "user_intent": user_input,
                    "story_id": story.id,
                    "branch_id": story.current_branch_id,
                    "chapter_id": chapter_id,
                    "exclude_sequences": exclude_seqs,
                    "exclude_scene_ids": set(),
                    "token_budget": SEMANTIC_SEARCH_BUDGET_CHARS,
                    "intent_result": None,
                    "world_scope": None,
                },
            }

            # Try recall agent for recall intents
            improved_text, mq_top_score = None, 0.0

            if intent_type == "recall":
                from ..agent.recall_agent import run_recall_agent
                from ...config import settings

                # Wrap LLM for agent
                _allow_thinking = ext_settings.get('thinking_enabled_memory', True)
                class _AgentLLM:
                    async def generate_with_messages(self, messages, max_tokens=None, **kwargs):
                        return await _llm_service.generate_for_task(
                            messages=messages,
                            user_id=user_id,
                            user_settings=user_settings,
                            max_tokens=max_tokens,
                            task_type="agent",
                            allow_thinking=_allow_thinking,
                        )

                agent_result = await run_recall_agent(
                    extraction_service=_AgentLLM(),
                    semantic_memory=ctx_mgr.semantic_memory,
                    context_manager=ctx_mgr,
                    db=db,
                    story_id=story.id,
                    branch_id=story.current_branch_id,
                    user_intent=user_input,
                    char_context=char_context,
                    exclude_sequences=exclude_seqs,
                    token_budget=SEMANTIC_SEARCH_BUDGET_CHARS,
                    prompt_debug=settings.prompt_debug,
                )
                if agent_result:
                    improved_text, mq_top_score = agent_result
                    logger.info("[RP SEMANTIC] Recall agent succeeded")

            # Deterministic pipeline fallback
            if not improved_text:
                improved_text, mq_top_score = await ctx_mgr.search_and_format_multi_query(
                    sub_queries=sub_queries,
                    context=search_context,
                    db=db,
                    intent_type=intent_type,
                    temporal_type=temporal_type,
                    user_intent=user_input,
                    keywords=keywords,
                )

            if not improved_text:
                logger.info("[RP SEMANTIC] Multi-query search returned no results")
                return False

            # Quality gate
            min_quality = 0.60
            if mq_top_score < min_quality:
                logger.info(f"[RP SEMANTIC] Top score {mq_top_score:.3f} < {min_quality} — keeping baseline")
                return False

            # Replace or insert RELEVANT PAST TURNS message
            header = (
                "=== RELEVANT PAST TURNS ===\n"
                "The following turns from earlier in the conversation are directly relevant. "
                "Use these details — DO NOT invent or contradict what's described here:\n\n"
            )
            replaced = False
            for i, msg in enumerate(messages):
                if msg.get("role") == "user" and "=== RELEVANT PAST TURNS ===" in msg.get("content", ""):
                    messages[i]["content"] = header + improved_text
                    replaced = True
                    break

            if not replaced:
                # Insert before the last message (task message)
                new_msg = {"role": "user", "content": header + improved_text}
                if len(messages) > 1:
                    messages.insert(-1, new_msg)
                else:
                    messages.append(new_msg)

            logger.info(f"[RP SEMANTIC] Improved with {len(sub_queries)} sub-queries "
                       f"(replaced={replaced}, top_score={mq_top_score:.3f})")
            return True

        except Exception as e:
            logger.warning(f"[RP SEMANTIC] Failed (keeping baseline): {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False

    @staticmethod
    async def _get_or_generate_summary(
        db: Session,
        story: Story,
        user_settings: dict,
    ) -> Optional[str]:
        """
        Get or generate a conversation summary for long roleplay sessions.
        Uses the chapter's auto_summary field to cache summaries.
        Re-generates when enough new turns accumulate.
        """
        chapter = story.chapters[0] if story.chapters else None
        if not chapter:
            return None

        # Check if existing summary is recent enough
        ctx = story.story_context or {}
        last_summary_count = ctx.get("last_rp_summary_turn_count", 0)
        total_turns = (
            db.query(sql_func.count(StoryFlow.id))
            .filter(
                StoryFlow.story_id == story.id,
                StoryFlow.is_active == True,
            )
            .scalar()
        ) or 0

        # Use existing summary if it's recent enough
        if chapter.auto_summary and (total_turns - last_summary_count) < SUMMARY_INTERVAL:
            return chapter.auto_summary[:SUMMARY_BUDGET_CHARS]

        # Need to generate/update summary
        # Load turns to summarize (everything except last 15 which go in RECENT TURNS)
        flows = (
            db.query(StoryFlow)
            .filter(
                StoryFlow.story_id == story.id,
                StoryFlow.is_active == True,
            )
            .order_by(StoryFlow.sequence_number)
            .limit(total_turns - 15)  # Summarize everything except last 15
            .all()
        )

        if len(flows) < SUMMARY_TURN_THRESHOLD:
            return chapter.auto_summary[:SUMMARY_BUDGET_CHARS] if chapter.auto_summary else None

        # Build text to summarize
        turn_texts = []
        for flow in flows:
            variant = db.query(SceneVariant).filter(
                SceneVariant.id == flow.scene_variant_id
            ).first()
            if variant and variant.content:
                method = variant.generation_method or "auto"
                label = "Player" if method in ("user_written", "auto_player") else "AI"
                turn_texts.append(f"[{label}] {variant.content[:300]}")

        text_to_summarize = "\n\n".join(turn_texts)

        # Use extraction LLM for summarization
        try:
            from ..llm.service import UnifiedLLMService

            llm = UnifiedLLMService()
            extraction_service = llm._get_extraction_service(user_settings)

            summary_system = prompt_manager.get_raw_prompt("roleplay.summary_system") or "You are a concise summarizer. Output only the summary, no preamble."
            summary_prompt = prompt_manager.get_raw_prompt(
                "roleplay.summary_prompt",
                conversation_text=text_to_summarize[:6000],
            )
            if not summary_prompt:
                summary_prompt = (
                    "Summarize this roleplay conversation concisely. "
                    "Focus on: key events, relationship developments, current situation, "
                    "and emotional state of characters. Write in present tense.\n\n"
                    f"{text_to_summarize[:6000]}"
                )

            messages = [
                {"role": "system", "content": summary_system},
                {"role": "user", "content": summary_prompt},
            ]

            if extraction_service:
                summary = await extraction_service.generate_with_messages(messages, max_tokens=400)
            else:
                # Fallback: collect from streaming main LLM
                chunks = []
                async for chunk in llm._generate_stream_with_messages(
                    messages=messages,
                    user_id=story.owner_id,
                    user_settings=user_settings,
                    max_tokens=400,
                    skip_nsfw_filter=True,
                ):
                    if not chunk.startswith("__THINKING__:"):
                        chunks.append(chunk)
                summary = "".join(chunks)

            if summary and summary.strip():
                summary = summary.strip()[:SUMMARY_BUDGET_CHARS]
                chapter.auto_summary = summary
                ctx["last_rp_summary_turn_count"] = total_turns
                story.story_context = ctx
                from sqlalchemy.orm import attributes
                attributes.flag_modified(story, "story_context")
                db.flush()
                return summary

        except Exception as e:
            logger.warning(f"Summary generation failed for RP {story.id}: {e}")

        # Fall back to existing summary if generation failed
        return chapter.auto_summary[:SUMMARY_BUDGET_CHARS] if chapter.auto_summary else None
