"""
Entity State Service

Tracks and updates the state of characters, locations, and objects throughout a story.
Uses LLM to extract state changes from scenes and maintains authoritative truth.
"""

import logging
import json
import re
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from ..models import (
    Character, CharacterState, LocationState, ObjectState,
    Story, Scene, StoryCharacter, EntityStateBatch, StoryBranch,
    CharacterInteraction
)
from ..services.llm.service import UnifiedLLMService
from ..services.llm.extraction_service import ExtractionLLMService
from ..services.llm.prompts import prompt_manager
from ..config import settings

logger = logging.getLogger(__name__)


def clean_llm_json(json_str: str) -> str:
    """
    Clean common JSON errors from LLM responses.
    
    Common issues:
    - Unquoted values (e.g., location: above instead of location: "above")
    - Trailing commas
    - Comments
    """
    # Fix unquoted values in key-value pairs
    # Pattern: "key": value, or "key": value}
    # Replace with: "key": "value", or "key": "value"}
    # This regex finds: "key": <word_without_quotes>
    json_str = re.sub(
        r':\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*([,}\]])',
        r': "\1"\2',
        json_str
    )
    
    # Remove trailing commas before closing brackets
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    
    # Remove comments (// or /* */)
    json_str = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
    json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
    
    return json_str


def has_meaningful_character_state(char_update: Dict[str, Any]) -> bool:
    """
    Check if a character update has meaningful state data.
    A character update is meaningful if it has at least 2 of the 3 key state fields populated.

    Key fields: location, emotional_state, physical_condition
    These are the most important for story continuity.

    Args:
        char_update: Character update dictionary from extraction

    Returns:
        True if the character has meaningful state data (2+ key fields populated)
    """
    # Key fields that are most important for continuity (require 2 of 3)
    key_fields = ['location', 'emotional_state', 'physical_condition']
    # Secondary fields that also count
    secondary_fields = ['current_attire', 'current_position']

    key_field_count = 0
    secondary_field_count = 0

    def is_non_empty(value):
        """Check if a value is non-empty and meaningful."""
        if not value:
            return False
        if isinstance(value, str):
            stripped = value.strip().lower()
            return stripped and stripped not in ('null', 'none', 'n/a', 'unknown', 'unchanged', '')
        elif isinstance(value, (list, dict)):
            return len(value) > 0
        return False

    for field in key_fields:
        if is_non_empty(char_update.get(field)):
            key_field_count += 1

    for field in secondary_fields:
        if is_non_empty(char_update.get(field)):
            secondary_field_count += 1

    # Require at least 2 key fields, OR 1 key field + 2 secondary fields
    return key_field_count >= 2 or (key_field_count >= 1 and secondary_field_count >= 2)

    return False


def has_meaningful_character_state_in_db(char_state) -> bool:
    """
    Check if a CharacterState database object has meaningful data.

    Args:
        char_state: CharacterState model instance

    Returns:
        True if the character state has meaningful data
    """
    # Check text fields
    text_fields = ['current_location', 'emotional_state', 'physical_condition', 'appearance', 'current_goal']
    for field in text_fields:
        value = getattr(char_state, field, None)
        if value and isinstance(value, str) and value.strip():
            return True

    # Check list/dict fields
    list_fields = ['possessions', 'knowledge', 'secrets']
    for field in list_fields:
        value = getattr(char_state, field, None)
        if value and len(value) > 0:
            return True

    if char_state.relationships and len(char_state.relationships) > 0:
        return True

    return False


def update_extraction_quality_metrics(
    db: Session,
    story_id: int,
    extraction_result: Dict[str, Any],
    characters_expected: int
) -> None:
    """
    Update extraction quality metrics on the Story model.

    Tracks:
    - extraction_success_rate: % of extractions with meaningful data
    - extraction_empty_rate: % of extractions that returned empty/no data
    - extraction_total_count: total extractions performed

    Args:
        db: Database session
        story_id: Story ID
        extraction_result: Result from extract_and_update_states
        characters_expected: Number of characters expected in extraction
    """
    try:
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            return

        # Determine extraction quality
        is_successful = extraction_result.get('extraction_successful', False)
        chars_updated = extraction_result.get('characters_updated', 0)
        is_meaningful = chars_updated > 0 and chars_updated >= (characters_expected * 0.5)  # At least half

        # Initialize counters if needed
        total = story.extraction_total_count or 0
        success_count = int((story.extraction_success_rate or 0) * total / 100) if total > 0 else 0
        empty_count = int((story.extraction_empty_rate or 0) * total / 100) if total > 0 else 0

        # Update counters
        total += 1
        if is_successful and is_meaningful:
            success_count += 1
        if not is_successful or chars_updated == 0:
            empty_count += 1

        # Calculate new rates (as percentages 0-100)
        story.extraction_success_rate = int((success_count / total) * 100)
        story.extraction_empty_rate = int((empty_count / total) * 100)
        story.extraction_total_count = total
        story.last_extraction_quality_check = datetime.utcnow()

        db.commit()

        # Log warning if quality is degrading
        if total >= 5 and story.extraction_success_rate < 70:
            logger.warning(
                f"[EXTRACTION:QUALITY:LOW] story_id={story_id} success_rate={story.extraction_success_rate}% "
                f"empty_rate={story.extraction_empty_rate}% total={total}"
            )

    except Exception as e:
        logger.error(f"[EXTRACTION:METRICS:ERROR] story_id={story_id} error={e}")
        # Don't fail the main extraction flow


class EntityStateService:
    """
    Service for managing entity states (characters, locations, objects).
    
    Responsibilities:
    - Extract state changes from scenes using LLM
    - Update entity state database records
    - Provide current state for context assembly
    - Track relationships, possessions, locations
    """
    
    def __init__(self, user_id: int, user_settings: Dict[str, Any]):
        self.user_id = user_id
        self.user_settings = user_settings
        self.llm_service = UnifiedLLMService()
        self.extraction_service = None  # Will be initialized conditionally
    
    def _get_active_branch_id(self, db: Session, story_id: int) -> int:
        """Get the active branch ID for a story."""
        active_branch = db.query(StoryBranch).filter(
            and_(
                StoryBranch.story_id == story_id,
                StoryBranch.is_active == True
            )
        ).first()
        return active_branch.id if active_branch else None
    
    async def extract_and_update_states(
        self,
        db: Session,
        story_id: int,
        scene_id: int,
        scene_sequence: int,
        scene_content: str,
        branch_id: int = None,
        chapter_location: str = None,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Extract state changes from a scene and update all entity states.
        Uses cache-friendly multi-message structure matching scene generation.

        Args:
            db: Database session
            story_id: Story ID
            scene_id: Scene ID
            scene_sequence: Scene sequence number
            scene_content: Scene content text
            branch_id: Optional branch ID (if not provided, uses active branch)
            chapter_location: Optional chapter location for hierarchical context
            context: Optional scene generation context for cache-friendly extraction

        Returns:
            Dictionary with extraction results
        """
        op_start = time.perf_counter()
        trace_id = f"entity-extract-{uuid.uuid4()}"
        results = {
            "characters_updated": 0,
            "locations_updated": 0,
            "objects_updated": 0,
            "interactions_recorded": 0,
            "extraction_successful": False
        }
        status = "error"

        # Verify scene exists before processing (prevents foreign key violations)
        scene_exists = db.query(Scene).filter(Scene.id == scene_id).first()
        if not scene_exists:
            logger.warning(f"[ENTITY:SKIP] trace_id={trace_id} scene_id={scene_id} story_id={story_id} reason=scene_missing")
            return results

        # Get active branch if not specified
        if branch_id is None:
            branch_id = self._get_active_branch_id(db, story_id)
        logger.info(f"[ENTITY:START] trace_id={trace_id} story_id={story_id} scene_id={scene_id} sequence={scene_sequence} branch_id={branch_id}")

        try:
            # Get story for interaction types
            story = db.query(Story).filter(Story.id == story_id).first()
            interaction_types = story.interaction_types if story else []

            # Get story characters for context (filtered by branch)
            char_query = db.query(StoryCharacter).filter(StoryCharacter.story_id == story_id)
            if branch_id:
                char_query = char_query.filter(StoryCharacter.branch_id == branch_id)
            story_characters = char_query.all()

            # Build character name to ID mapping
            character_name_to_id = {}
            character_names = []
            for sc in story_characters:
                char = db.query(Character).filter(Character.id == sc.character_id).first()
                if char:
                    character_names.append(char.name)
                    character_name_to_id[char.name.lower()] = char.id

            # Query previous character states for carry-forward in extraction prompt
            previous_states_text = ""
            try:
                previous_attire = {}
                for sc in story_characters:
                    char = db.query(Character).filter(Character.id == sc.character_id).first()
                    if not char:
                        continue
                    state_q = db.query(CharacterState).filter(
                        CharacterState.character_id == sc.character_id,
                        CharacterState.story_id == story_id
                    )
                    if branch_id:
                        state_q = state_q.filter(CharacterState.branch_id == branch_id)
                    cs = state_q.first()
                    if cs and cs.appearance and cs.appearance.strip().lower() not in ('null', 'none', ''):
                        previous_attire[char.name] = cs.appearance
                if previous_attire:
                    lines = [f"- {name}: attire={attire}" for name, attire in previous_attire.items()]
                    previous_states_text = "PREVIOUS KNOWN STATES (carry forward if scene doesn't change them):\n" + "\n".join(lines)
                    logger.debug(f"[ENTITY:PREVIOUS_STATES] trace_id={trace_id} Passing {len(previous_attire)} previous attire states to extraction")
            except Exception as prev_err:
                logger.warning(f"[ENTITY:PREVIOUS_STATES:FAIL] trace_id={trace_id} Failed to query previous states: {prev_err}")

            # Build context if not provided (for cache-friendly extraction)
            if context is None:
                try:
                    from .context_manager import ContextManager
                    context_manager = ContextManager(self.user_id, self.user_settings)
                    # Get chapter_id from scene
                    chapter_id = scene_exists.chapter_id
                    context = await context_manager.build_scene_generation_context(
                        story_id=story_id,
                        db=db,
                        chapter_id=chapter_id,
                        branch_id=branch_id
                    )
                    logger.debug(f"[ENTITY:CONTEXT] trace_id={trace_id} Built context for cache-friendly extraction")
                except Exception as ctx_err:
                    logger.warning(f"[ENTITY:CONTEXT:FAIL] trace_id={trace_id} Failed to build context: {ctx_err}, using fallback")
                    context = None

            # Use cache-friendly extraction if we have context
            if context is not None:
                try:
                    raw_response = await self.llm_service.extract_entity_states_cache_friendly(
                        scene_content=scene_content,
                        character_names=character_names,
                        chapter_location=chapter_location or "unspecified location",
                        context=context,
                        user_id=self.user_id,
                        user_settings=self.user_settings,
                        db=db,
                        previous_states=previous_states_text
                    )
                    logger.debug(f"[ENTITY:CACHE_FRIENDLY] trace_id={trace_id} Used cache-friendly extraction")

                    # Parse the response
                    response_clean = raw_response.strip()
                    if response_clean.startswith("```json"):
                        response_clean = response_clean[7:]
                    if response_clean.startswith("```"):
                        response_clean = response_clean[3:]
                    if response_clean.endswith("```"):
                        response_clean = response_clean[:-3]
                    response_clean = response_clean.strip()
                    response_clean = clean_llm_json(response_clean)

                    state_changes = json.loads(response_clean)
                    state_changes = self._validate_state_changes(state_changes)
                except Exception as cache_err:
                    logger.warning(f"[ENTITY:CACHE_FRIENDLY:FAIL] trace_id={trace_id} Cache-friendly extraction failed: {cache_err}, using fallback")
                    state_changes = None
            else:
                state_changes = None

            # Fallback to old extraction if cache-friendly failed or no context
            if state_changes is None:
                state_changes = await self._extract_state_changes(
                    scene_content,
                    scene_sequence,
                    character_names,
                    chapter_location=chapter_location,
                    trace_id=trace_id,
                    interaction_types=interaction_types,
                    previous_states=previous_states_text
                )

            # Check if extraction returned meaningful data
            has_meaningful_chars = False
            if state_changes and state_changes.get("characters"):
                for char in state_changes["characters"]:
                    if has_meaningful_character_state(char):
                        has_meaningful_chars = True
                        break

            # Retry once if extraction returned empty or all characters have empty state data
            if not state_changes or (state_changes.get("characters") and not has_meaningful_chars):
                logger.warning(
                    f"[ENTITY:RETRY] trace_id={trace_id} scene_id={scene_id} story_id={story_id} "
                    f"sequence={scene_sequence} reason={'empty_response' if not state_changes else 'empty_states'} "
                    "Retrying extraction once..."
                )
                # Wait briefly before retry
                import asyncio
                await asyncio.sleep(0.5)

                state_changes = await self._extract_state_changes(
                    scene_content,
                    scene_sequence,
                    character_names,
                    chapter_location=chapter_location,
                    trace_id=f"{trace_id}-retry",
                    interaction_types=interaction_types,
                    previous_states=previous_states_text
                )

                # Check retry result
                if state_changes and state_changes.get("characters"):
                    retry_has_meaningful = any(has_meaningful_character_state(c) for c in state_changes["characters"])
                    if retry_has_meaningful:
                        logger.info(
                            f"[ENTITY:RETRY:SUCCESS] trace_id={trace_id} scene_id={scene_id} "
                            "Retry extraction returned meaningful character data."
                        )
                    else:
                        logger.warning(
                            f"[ENTITY:RETRY:STILL_EMPTY] trace_id={trace_id} scene_id={scene_id} "
                            "Retry extraction still returned empty character states."
                        )

            if not state_changes:
                logger.warning(f"[ENTITY:EMPTY] trace_id={trace_id} scene_id={scene_id} story_id={story_id} sequence={scene_sequence}")
                return results

            # Check for contradictions before updating states (if enabled)
            context_settings = self.user_settings.get('context_settings', {})
            contradiction_enabled = context_settings.get('enable_contradiction_detection', True)
            severity_threshold = context_settings.get('contradiction_severity_threshold', 'info')

            if contradiction_enabled:
                try:
                    from .contradiction_service import ContradictionService
                    contradiction_service = ContradictionService(db)
                    contradictions = await contradiction_service.check_extraction(
                        story_id=story_id,
                        branch_id=branch_id,
                        scene_sequence=scene_sequence,
                        new_states=state_changes,
                        chapter_location=chapter_location
                    )

                    # Filter by severity threshold
                    severity_order = {'info': 0, 'warning': 1, 'error': 2}
                    threshold_level = severity_order.get(severity_threshold, 0)
                    filtered_contradictions = [
                        c for c in contradictions
                        if severity_order.get(c.severity, 0) >= threshold_level
                    ]

                    # Log and save filtered contradictions (non-blocking)
                    for c in filtered_contradictions:
                        logger.info(
                            f"[CONTRADICTION] trace_id={trace_id} type={c.contradiction_type} "
                            f"char={c.character_name} prev='{c.previous_value}' curr='{c.current_value}'"
                        )
                        db.add(c)

                    if filtered_contradictions:
                        results["contradictions_found"] = len(filtered_contradictions)
                except Exception as e:
                    logger.warning(f"[CONTRADICTION:ERROR] trace_id={trace_id} error={e}")

            # Update character states
            if "characters" in state_changes:
                for char_update in state_changes["characters"]:
                    await self._update_character_state(
                        db, story_id, scene_sequence, char_update, branch_id=branch_id, trace_id=trace_id
                    )
                    results["characters_updated"] += 1
            
            # Update location states
            if "locations" in state_changes:
                for loc_update in state_changes["locations"]:
                    await self._update_location_state(
                        db, story_id, scene_sequence, loc_update, branch_id=branch_id, trace_id=trace_id
                    )
                    results["locations_updated"] += 1
            
            # Update object states
            if "objects" in state_changes:
                for obj_update in state_changes["objects"]:
                    await self._update_object_state(
                        db, story_id, scene_sequence, obj_update, branch_id=branch_id, trace_id=trace_id,
                        scene_content=scene_content
                    )
                    results["objects_updated"] += 1
            
            # Record character interactions
            if "interactions" in state_changes and interaction_types:
                for interaction in state_changes["interactions"]:
                    recorded = await self._record_character_interaction(
                        db, story_id, scene_sequence, interaction,
                        character_name_to_id, branch_id=branch_id, trace_id=trace_id
                    )
                    if recorded:
                        results["interactions_recorded"] += 1
            
            results["extraction_successful"] = True
            status = "success"
            logger.info(f"[ENTITY:UPDATED] trace_id={trace_id} scene_id={scene_id} story_id={story_id} sequence={scene_sequence} counts={results}")

            # Update extraction quality metrics
            update_extraction_quality_metrics(
                db=db,
                story_id=story_id,
                extraction_result=results,
                characters_expected=len(character_names)
            )

            # Create batch snapshot every scene (attire changes per-scene, rollback needs latest state)
            try:
                self.create_entity_state_batch_snapshot(
                    db, story_id, scene_sequence, scene_sequence, branch_id=branch_id
                )
            except Exception as e:
                # Don't fail extraction if batch creation fails
                logger.warning(f"[ENTITY:BATCH:ERROR] trace_id={trace_id} story_id={story_id} scene={scene_sequence} error={e}")
            
        except Exception as e:
            logger.error(f"[ENTITY:ERROR] trace_id={trace_id} story_id={story_id} scene_id={scene_id} error={e}")
        finally:
            duration_ms = (time.perf_counter() - op_start) * 1000
            if duration_ms > 15000:
                logger.error(f"[ENTITY:SLOW] trace_id={trace_id} duration_ms={duration_ms:.2f} status={status} story_id={story_id}")
            elif duration_ms > 5000:
                logger.warning(f"[ENTITY:SLOW] trace_id={trace_id} duration_ms={duration_ms:.2f} status={status} story_id={story_id}")
            else:
                logger.info(f"[ENTITY:DONE] trace_id={trace_id} duration_ms={duration_ms:.2f} status={status} story_id={story_id}")
        
        return results

    async def update_working_memory(
        self,
        db: Session,
        story_id: int,
        branch_id: int,
        chapter_id: Optional[int],
        scene_sequence: int,
        scene_content: str,
        scene_generation_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Update working memory after scene generation.

        Tracks scene-to-scene narrative continuity:
        - recent_focus: What was narratively emphasized
        - character_spotlight: Who needs attention next

        Note: Unresolved plot threads are tracked separately via PlotEvents.
        """
        from ..models import WorkingMemory

        trace_id = f"working-memory-{uuid.uuid4()}"
        logger.debug(f"[WORKING_MEMORY:START] trace_id={trace_id} story_id={story_id} scene={scene_sequence}")

        try:
            # Get or create working memory for this story/branch
            memory = db.query(WorkingMemory).filter(
                WorkingMemory.story_id == story_id,
                WorkingMemory.branch_id == branch_id
            ).first()

            if not memory:
                memory = WorkingMemory(
                    story_id=story_id,
                    branch_id=branch_id,
                    recent_focus=[],
                    character_spotlight={}
                )
                db.add(memory)

            # Get current state for context
            current_focus = memory.recent_focus or []

            # Extract updates using LLM
            updates = await self._extract_working_memory_updates(
                scene_content=scene_content,
                current_focus=current_focus,
                scene_generation_context=scene_generation_context,
                db=db
            )

            if updates:
                # Apply updates
                memory.recent_focus = updates.get('recent_focus', [])[:3]  # Limit to 3
                memory.character_spotlight = updates.get('character_spotlight', {})
                memory.chapter_id = chapter_id
                memory.last_scene_sequence = scene_sequence

                db.commit()
                logger.info(f"[WORKING_MEMORY:UPDATED] trace_id={trace_id} story_id={story_id} "
                           f"focus={len(memory.recent_focus)} spotlight={len(memory.character_spotlight)}")

                return memory.to_dict()
            else:
                logger.warning(f"[WORKING_MEMORY:EMPTY] trace_id={trace_id} story_id={story_id} No updates extracted")
                return memory.to_dict() if memory.id else {}

        except Exception as e:
            logger.error(f"[WORKING_MEMORY:ERROR] trace_id={trace_id} story_id={story_id} error={e}")
            return {}

    async def _extract_working_memory_updates(
        self,
        scene_content: str,
        current_focus: List[str],
        scene_generation_context: Optional[Dict[str, Any]] = None,
        db: Optional[Session] = None
    ) -> Optional[Dict[str, Any]]:
        """Extract working memory updates from scene content.

        If scene_generation_context is provided, uses cache-friendly unified extraction
        that matches the scene generation message structure for cache hits.
        """
        current_focus_str = ', '.join(current_focus[:3]) if current_focus else 'None'

        # === CACHE-FRIENDLY PATH: Use unified service method ===
        if scene_generation_context is not None:
            logger.debug("[WORKING_MEMORY] Using cache-friendly extraction with scene generation context")
            llm_service = UnifiedLLMService()
            return await llm_service.extract_working_memory_cache_friendly(
                scene_content=scene_content,
                current_focus=current_focus_str,
                context=scene_generation_context,
                user_id=self.user_id,
                user_settings=self.user_settings,
                db=db
            )

        # === FALLBACK PATH: Original 2-message structure ===
        logger.debug("[WORKING_MEMORY] Using fallback extraction (no scene context - cache may miss)")
        extraction_service = self._get_extraction_service()

        template_vars = {
            'scene_content': scene_content[:3000],  # Limit content length
            'current_focus': current_focus_str
        }

        try:
            # Get system and user prompts from template
            system_prompt = prompt_manager.get_prompt(
                "working_memory_update", "system", **template_vars
            )
            user_prompt = prompt_manager.get_prompt(
                "working_memory_update", "user", **template_vars
            )

            if extraction_service:
                # Use extraction LLM with generate method
                response = await extraction_service.generate(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    max_tokens=512
                )
            else:
                # Fall back to main LLM
                llm_service = UnifiedLLMService()
                llm_client = llm_service._create_client(self.user_id, self.user_settings)

                if not llm_client:
                    logger.warning("[WORKING_MEMORY] No LLM client available")
                    return None

                response = await llm_client.complete_non_streaming(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=512
                )

            if not response:
                return None

            # Parse JSON response
            response_text = response.strip()

            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    # Try cleaning common issues
                    cleaned = clean_llm_json(json_match.group())
                    return json.loads(cleaned)

            return None

        except Exception as e:
            logger.error(f"[WORKING_MEMORY:EXTRACT:ERROR] error={e}")
            return None

    # =========================================================================
    # RELATIONSHIP GRAPH TRACKING
    # =========================================================================

    def _get_canonical_character_names(self, db: Session, story_id: int) -> List[str]:
        """Fetch canonical character names from the story's character list."""
        from ..models.character import Character, StoryCharacter

        results = db.query(Character.name).join(
            StoryCharacter, StoryCharacter.character_id == Character.id
        ).filter(StoryCharacter.story_id == story_id).all()

        return [r[0] for r in results]

    def _normalize_character_name(self, name: str, canonical_names: List[str]) -> str:
        """Normalize an extracted character name to match a canonical name.

        Uses exact match first, then case-insensitive, then substring matching.
        """
        if not name or not canonical_names:
            return name

        name_stripped = name.strip()

        # Exact match
        for cn in canonical_names:
            if cn == name_stripped:
                return cn

        # Case-insensitive match
        name_lower = name_stripped.lower()
        for cn in canonical_names:
            if cn.lower() == name_lower:
                return cn

        # Substring match: extracted name is part of canonical name (e.g. "Ali" -> "Ali Malik")
        # or canonical name is part of extracted name (e.g. "Ali Malik" -> "Ali")
        for cn in canonical_names:
            cn_lower = cn.lower()
            if name_lower in cn_lower or cn_lower in name_lower:
                return cn

        # First-name match: compare first word
        name_first = name_lower.split()[0] if name_lower.split() else name_lower
        for cn in canonical_names:
            cn_first = cn.lower().split()[0] if cn.lower().split() else cn.lower()
            if name_first == cn_first:
                return cn

        return name_stripped  # Return as-is if no match

    def _deduplicate_extractions(self, updates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate extractions: keep one entry per character pair (highest strength)."""
        seen = {}
        for rel in updates:
            char_a = rel.get('character_a', '')
            char_b = rel.get('character_b', '')
            if not char_a or not char_b:
                continue
            pair = tuple(sorted([char_a, char_b]))
            strength = abs(float(rel.get('strength', 0)))
            if pair not in seen or strength > abs(float(seen[pair].get('strength', 0))):
                seen[pair] = rel
        return list(seen.values())

    async def update_relationship_graph(
        self,
        db: Session,
        story_id: int,
        branch_id: int,
        scene_id: int,
        scene_sequence: int,
        scene_content: str,
        characters: List[str],
        scene_generation_context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract and update character relationships from a scene.

        Tracks:
        - Relationship events (every change logged)
        - Relationship summaries (current state for context)
        """
        from ..models import CharacterRelationship, RelationshipSummary

        if not characters or len(characters) < 2:
            logger.debug(f"[RELATIONSHIP:SKIP] story_id={story_id} scene={scene_sequence} - less than 2 characters")
            return []

        trace_id = f"relationship-{uuid.uuid4()}"
        logger.debug(f"[RELATIONSHIP:START] trace_id={trace_id} story_id={story_id} scene={scene_sequence} characters={characters}")

        try:
            # Fetch canonical character names for normalization
            canonical_names = self._get_canonical_character_names(db, story_id)

            # Get previous relationship states for context
            previous_rels = self._get_previous_relationships(db, story_id, branch_id, characters)

            # Extract relationship updates using LLM
            updates = await self._extract_relationship_updates(
                scene_content=scene_content,
                characters=characters,
                previous_relationships=previous_rels,
                canonical_names=canonical_names,
                scene_generation_context=scene_generation_context,
                db=db
            )

            # Post-process: normalize names and deduplicate
            if updates and canonical_names:
                for rel in updates:
                    rel['character_a'] = self._normalize_character_name(
                        rel.get('character_a', ''), canonical_names
                    )
                    rel['character_b'] = self._normalize_character_name(
                        rel.get('character_b', ''), canonical_names
                    )
                updates = self._deduplicate_extractions(updates)

            if not updates:
                logger.info(f"[RELATIONSHIP:NONE] trace_id={trace_id} story_id={story_id} - no relationship changes")
                return []

            # Store relationship events and update summaries
            stored_events = []
            for rel in updates:
                event = self._store_relationship_event(
                    db=db,
                    story_id=story_id,
                    branch_id=branch_id,
                    scene_id=scene_id,
                    scene_sequence=scene_sequence,
                    relationship=rel
                )
                if event:
                    stored_events.append(event.to_dict())

                self._update_relationship_summary(
                    db=db,
                    story_id=story_id,
                    branch_id=branch_id,
                    scene_sequence=scene_sequence,
                    relationship=rel
                )

            db.commit()
            logger.info(f"[RELATIONSHIP:DONE] trace_id={trace_id} story_id={story_id} events={len(stored_events)}")
            return stored_events

        except Exception as e:
            logger.error(f"[RELATIONSHIP:ERROR] trace_id={trace_id} story_id={story_id} error={e}")
            db.rollback()
            return []

    def _get_previous_relationships(
        self,
        db: Session,
        story_id: int,
        branch_id: int,
        characters: List[str]
    ) -> str:
        """Get previous relationship states for context."""
        from ..models import RelationshipSummary

        summaries = db.query(RelationshipSummary).filter(
            RelationshipSummary.story_id == story_id,
            RelationshipSummary.branch_id == branch_id
        ).all()

        if not summaries:
            return "No previous relationships established."

        # Filter to summaries involving the characters in this scene
        relevant = []
        char_set = set(characters)
        for s in summaries:
            if s.character_a in char_set or s.character_b in char_set:
                relevant.append(f"{s.character_a} <-> {s.character_b}: {s.current_type} (strength: {s.current_strength:.1f})")

        if not relevant:
            return "No previous relationships between these characters."

        return "\n".join(relevant)

    async def _extract_relationship_updates(
        self,
        scene_content: str,
        characters: List[str],
        previous_relationships: str,
        canonical_names: List[str] = None,
        scene_generation_context: Optional[Dict[str, Any]] = None,
        db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """Extract relationship updates from scene content using LLM.

        If scene_generation_context is provided, uses cache-friendly unified extraction
        that matches the scene generation message structure for cache hits.
        """
        # Build canonical name list for the prompt
        name_list = canonical_names if canonical_names else characters
        character_names_list = [name for name in name_list]

        # === CACHE-FRIENDLY PATH: Use unified service method ===
        if scene_generation_context is not None:
            logger.debug("[RELATIONSHIP] Using cache-friendly extraction with scene generation context")
            llm_service = UnifiedLLMService()
            return await llm_service.extract_relationship_cache_friendly(
                scene_content=scene_content,
                character_names=character_names_list,
                characters_in_scene=characters,
                previous_relationships=previous_relationships,
                context=scene_generation_context,
                user_id=self.user_id,
                user_settings=self.user_settings,
                db=db
            )

        # === FALLBACK PATH: No scene generation context available ===
        # Cache-friendly path requires scene_generation_context. Without it,
        # relationship extraction is skipped (no standalone prompt template exists).
        logger.debug("[RELATIONSHIP] No scene generation context available, skipping relationship extraction")
        return []

    def _store_relationship_event(
        self,
        db: Session,
        story_id: int,
        branch_id: int,
        scene_id: int,
        scene_sequence: int,
        relationship: Dict[str, Any]
    ):
        """Store a single relationship change event."""
        from ..models import CharacterRelationship

        # Normalize character order (alphabetical) for consistent querying
        char_a = relationship.get('character_a', '')
        char_b = relationship.get('character_b', '')
        if not char_a or not char_b:
            return None

        char_a, char_b = sorted([char_a, char_b])

        event = CharacterRelationship(
            story_id=story_id,
            branch_id=branch_id,
            character_a=char_a,
            character_b=char_b,
            relationship_type=relationship.get('type', 'acquaintance'),
            strength=float(relationship.get('strength', 0.0)),
            scene_id=scene_id,
            scene_sequence=scene_sequence,
            change_description=relationship.get('change', ''),
            change_sentiment=relationship.get('sentiment', 'neutral')
        )
        db.add(event)
        db.flush()

        logger.debug(f"[RELATIONSHIP:EVENT] {char_a} <-> {char_b}: {event.relationship_type} ({event.strength})")
        return event

    def _update_relationship_summary(
        self,
        db: Session,
        story_id: int,
        branch_id: int,
        scene_sequence: int,
        relationship: Dict[str, Any]
    ):
        """Update or create relationship summary."""
        from ..models import RelationshipSummary

        char_a = relationship.get('character_a', '')
        char_b = relationship.get('character_b', '')
        if not char_a or not char_b:
            return

        # Normalize order
        char_a, char_b = sorted([char_a, char_b])

        # Find or create summary
        summary = db.query(RelationshipSummary).filter(
            RelationshipSummary.story_id == story_id,
            RelationshipSummary.branch_id == branch_id,
            RelationshipSummary.character_a == char_a,
            RelationshipSummary.character_b == char_b
        ).first()

        rel_type = relationship.get('type', 'acquaintance')
        strength = float(relationship.get('strength', 0.0))

        if not summary:
            summary = RelationshipSummary(
                story_id=story_id,
                branch_id=branch_id,
                character_a=char_a,
                character_b=char_b,
                initial_type=rel_type,
                initial_strength=strength,
                current_type=rel_type,
                current_strength=strength,
                total_interactions=1,
                last_scene_sequence=scene_sequence,
                last_change=relationship.get('change', ''),
                trajectory='developing'
            )
            summary.arc_summary = f"{rel_type} (first interaction)"
            db.add(summary)
        else:
            # Update existing summary
            old_strength = summary.current_strength or 0.0

            summary.current_type = rel_type
            summary.current_strength = strength
            summary.total_interactions = (summary.total_interactions or 0) + 1
            summary.last_scene_sequence = scene_sequence
            summary.last_change = relationship.get('change', '')

            # Calculate trajectory
            initial_strength = summary.initial_strength or 0.0
            strength_delta = strength - initial_strength
            if abs(strength_delta) < 0.15:
                summary.trajectory = 'stable'
            elif strength_delta > 0.3:
                summary.trajectory = 'warming'
            elif strength_delta < -0.3:
                summary.trajectory = 'cooling'
            else:
                summary.trajectory = 'developing'

            # Generate arc summary
            if summary.initial_type == summary.current_type:
                summary.arc_summary = f"{summary.current_type} ({summary.trajectory}, {summary.total_interactions} interactions)"
            else:
                summary.arc_summary = f"{summary.initial_type} -> {summary.current_type} ({summary.trajectory} over {summary.total_interactions} scenes)"

        db.flush()

    def _get_extraction_service(self) -> Optional[ExtractionLLMService]:
        """
        Get or create extraction service if enabled in user settings
        
        Returns:
            ExtractionLLMService instance or None if not enabled
        """
        return ExtractionLLMService.from_settings(self.user_settings)
    
    async def _extract_state_changes(
        self,
        scene_content: str,
        scene_sequence: int,
        character_names: List[str],
        chapter_location: str = None,
        trace_id: Optional[str] = None,
        interaction_types: List[str] = None,
        previous_states: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to extract state changes from a scene.
        Tries extraction model first, falls back to main LLM if enabled.
        
        Args:
            scene_content: Scene text to analyze
            scene_sequence: Scene sequence number
            character_names: List of known character names
            chapter_location: Chapter-level location for hierarchical context
            trace_id: Optional trace ID for logging
            interaction_types: List of interaction types to look for
        
        Returns JSON with character, location, object updates, and interactions.
        """
        trace_id = trace_id or f"entity-extract-{uuid.uuid4()}"
        op_start = time.perf_counter()
        interaction_types = interaction_types or []
        
        # Try extraction model first if enabled
        extraction_service = self._get_extraction_service()
        if extraction_service:
            try:
                logger.debug(f"[ENTITY:LLM:START] trace_id={trace_id} mode=extraction_model user={self.user_id} scene_sequence={scene_sequence}")
                state_changes = await extraction_service.extract_entity_states(
                    scene_content=scene_content,
                    scene_sequence=scene_sequence,
                    character_names=character_names,
                    chapter_location=chapter_location,
                    interaction_types=interaction_types  # Pass interaction types for extraction
                )

                # Validate state changes
                validated = self._validate_state_changes(state_changes)
                if validated:
                    duration_ms = (time.perf_counter() - op_start) * 1000
                    logger.debug(f"[ENTITY:LLM:END] trace_id={trace_id} mode=extraction_model status=success duration_ms={duration_ms:.2f}")
                    return validated
                else:
                    logger.warning(f"[ENTITY:LLM:EMPTY] trace_id={trace_id} mode=extraction_model duration_ms={(time.perf_counter() - op_start) * 1000:.2f} fallback=main")
            except Exception as e:
                logger.warning(f"[ENTITY:LLM:ERROR] trace_id={trace_id} mode=extraction_model error={e}, fallback=main")
                # Continue to fallback
        
        # Fallback to main LLM
        fallback_enabled = self.user_settings.get('extraction_model_settings', {}).get('fallback_to_main', True)
        if not fallback_enabled and extraction_service:
            logger.warning(f"[ENTITY:LLM:DISABLED] trace_id={trace_id} fallback_disabled=True returning_empty=True")
            return {'characters': [], 'locations': [], 'objects': [], 'interactions': []}
        
        try:
            llm_start = time.perf_counter()
            logger.debug(f"[ENTITY:LLM:START] trace_id={trace_id} mode=main_llm user={self.user_id} scene_sequence={scene_sequence}")
            
            # Build interaction types section for prompt
            interaction_section = ""
            if interaction_types:
                interaction_section = f"""
      
      INTERACTION TYPES TO DETECT:
      The story is tracking these specific interaction types: {json.dumps(interaction_types)}
      
      If ANY of these interactions occur for the FIRST TIME between two characters in this scene,
      include them in the "interactions" array. Only report interactions that are EXPLICITLY shown
      happening in this scene, not referenced or remembered.
      
      For interactions, return:
      {{
        "interaction_type": "the exact type from the list above",
        "character_a": "first character name",
        "character_b": "second character name", 
        "description": "brief factual description of what happened"
      }}"""
            
            # Get prompts from centralized prompts.yml
            system_prompt = prompt_manager.get_prompt("entity_state_extraction.single", "system")
            user_prompt = prompt_manager.get_prompt(
                "entity_state_extraction.single", "user",
                scene_sequence=scene_sequence,
                scene_content=scene_content,
                character_names=', '.join(character_names),
                chapter_location=chapter_location or "Unknown",
                previous_states=previous_states or ""
            )
            
            # Append interaction extraction instructions if needed
            if interaction_types:
                user_prompt += interaction_section
                user_prompt += '\n\nInclude "interactions": [] in your JSON response (empty array if no tracked interactions detected).'

            response = await self.llm_service.generate(
                prompt=user_prompt,
                user_id=self.user_id,
                user_settings=self.user_settings,
                system_prompt=system_prompt,
                max_tokens=self.user_settings.get('llm_settings', {}).get('max_tokens', 2048)
            )
            llm_duration_ms = (time.perf_counter() - llm_start) * 1000
            
            
            # Parse JSON response
            # Clean up response (remove markdown code blocks if present)
            response_clean = response.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            if response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            response_clean = response_clean.strip()
            
            # Clean common JSON errors from LLM
            response_clean = clean_llm_json(response_clean)
            
            state_changes = json.loads(response_clean)
            validated = self._validate_state_changes(state_changes)
            if validated:
                logger.debug(f"[ENTITY:LLM:END] trace_id={trace_id} mode=main_llm status=success duration_ms={llm_duration_ms:.2f}")
            else:
                logger.warning(f"[ENTITY:LLM:EMPTY] trace_id={trace_id} mode=main_llm duration_ms={llm_duration_ms:.2f}")
            return validated
            
        except json.JSONDecodeError as e:
            logger.error(f"[ENTITY:LLM:PARSE_ERROR] trace_id={trace_id} error={e}")
            logger.debug(f"Original response was: {response}")
            logger.debug(f"Cleaned response was: {response_clean}")
            return None
        except Exception as e:
            logger.error(f"[ENTITY:LLM:ERROR] trace_id={trace_id} mode=main_llm error={e}")
            return None
    
    def _validate_state_changes(self, state_changes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and normalize state changes dictionary.
        Also checks for meaningful state data and logs warnings if extraction returned empty states.

        Args:
            state_changes: Raw state changes dictionary

        Returns:
            Validated state changes dictionary
        """
        if not isinstance(state_changes, dict):
            return {'characters': [], 'locations': [], 'objects': [], 'interactions': []}

        validated = {
            'characters': [],
            'locations': [],
            'objects': [],
            'interactions': []
        }

        # Validate characters and check for meaningful state data
        characters = state_changes.get('characters', [])
        empty_state_chars = []
        meaningful_state_chars = []
        if isinstance(characters, list):
            for char in characters:
                if isinstance(char, dict) and char.get('name'):
                    validated['characters'].append(char)
                    # Check if this character has meaningful state data
                    if has_meaningful_character_state(char):
                        meaningful_state_chars.append(char.get('name'))
                    else:
                        empty_state_chars.append(char.get('name'))

        # Log warning if extraction returned characters but with empty states
        if empty_state_chars:
            logger.warning(
                f"[ENTITY:VALIDATION:EMPTY_STATES] Characters with no meaningful state data: {empty_state_chars}. "
                f"Characters with data: {meaningful_state_chars}. "
                "This may indicate an issue with the LLM extraction prompt or response parsing."
            )

        # Log alert if ALL characters have empty states
        if validated['characters'] and not meaningful_state_chars:
            logger.error(
                f"[ENTITY:VALIDATION:ALL_EMPTY] ALL {len(validated['characters'])} extracted characters have empty state data! "
                f"Characters: {[c.get('name') for c in validated['characters']]}. "
                "This is a critical issue - extraction is not populating character states."
            )

        # Validate locations
        locations = state_changes.get('locations', [])
        if isinstance(locations, list):
            for loc in locations:
                if isinstance(loc, dict) and loc.get('name'):
                    validated['locations'].append(loc)

        # Validate objects
        objects = state_changes.get('objects', [])
        if isinstance(objects, list):
            for obj in objects:
                if isinstance(obj, dict) and obj.get('name'):
                    validated['objects'].append(obj)

        # Validate interactions
        interactions = state_changes.get('interactions', [])
        if isinstance(interactions, list):
            for interaction in interactions:
                if isinstance(interaction, dict) and interaction.get('interaction_type') and interaction.get('character_a') and interaction.get('character_b'):
                    validated['interactions'].append(interaction)
        
        return validated
    
    async def _update_character_state(
        self,
        db: Session,
        story_id: int,
        scene_sequence: int,
        char_update: Dict[str, Any],
        branch_id: int = None,
        trace_id: Optional[str] = None
    ):
        """Update or create character state from extracted changes"""
        try:
            trace_suffix = f" trace_id={trace_id}" if trace_id else ""
            char_name = char_update.get("name")
            if not char_name:
                return
            
            # Find character by name in this story (filtered by branch)
            base_char_query = db.query(StoryCharacter).join(Character).filter(
                StoryCharacter.story_id == story_id
            )
            if branch_id:
                base_char_query = base_char_query.filter(StoryCharacter.branch_id == branch_id)

            # Try exact match first
            story_char = base_char_query.filter(Character.name == char_name).first()

            # Fallback: starts-with match (e.g., "Radhika" matches "Radhika Sharma")
            if not story_char:
                story_char = base_char_query.filter(Character.name.ilike(f"{char_name}%")).first()
                if story_char:
                    matched_char = db.query(Character).filter(Character.id == story_char.character_id).first()
                    logger.debug(f"Character '{char_name}' fuzzy-matched to '{matched_char.name}' in story {story_id}{trace_suffix}")

            if not story_char:
                logger.warning(f"Character '{char_name}' not found in story {story_id} (branch {branch_id}){trace_suffix}")
                return
            
            # Get or create character state (include branch_id=None to avoid duplicates)
            state_query = db.query(CharacterState).filter(
                CharacterState.character_id == story_char.character_id,
                CharacterState.story_id == story_id
            )
            if branch_id:
                state_query = state_query.filter(CharacterState.branch_id == branch_id)
            char_state = state_query.first()
            
            if not char_state:
                char_state = CharacterState(
                    character_id=story_char.character_id,
                    story_id=story_id,
                    branch_id=branch_id,
                    possessions=[],
                    knowledge=[],
                    secrets=[],
                    relationships={},
                    recent_actions=[],
                    recent_decisions=[],
                    full_state={}
                )
                db.add(char_state)
                try:
                    db.flush()  # Flush to catch constraint violations immediately
                except IntegrityError as ie:
                    db.rollback()
                    error_msg = str(ie).lower()
                    if "duplicate" in error_msg or "unique constraint" in error_msg:
                        logger.debug(f"Character state already exists (race condition), reloading: {char_name}{trace_suffix}")
                        # Reload the state that was created by another process
                        state_query = db.query(CharacterState).filter(
                            CharacterState.character_id == story_char.character_id,
                            CharacterState.story_id == story_id
                        )
                        if branch_id:
                            state_query = state_query.filter(CharacterState.branch_id == branch_id)
                        char_state = state_query.first()
                        if not char_state:
                            logger.error(f"Failed to reload character state after race condition: {char_name}{trace_suffix}")
                            return
                    else:
                        # Re-raise if it's a different integrity error
                        raise

            # Update fields
            char_state.last_updated_scene = scene_sequence
            
            if char_update.get("location"):
                val = char_update["location"]
                char_state.current_location = None if isinstance(val, str) and val.lower() == "null" else val

            if char_update.get("current_position"):
                val = char_update["current_position"]
                char_state.current_position = None if isinstance(val, str) and val.lower() == "null" else val

            if char_update.get("items_in_hand") is not None:
                # items_in_hand is an array - can be empty []
                val = char_update["items_in_hand"]
                if isinstance(val, list):
                    char_state.items_in_hand = val
                elif val and isinstance(val, str) and val.lower() != "null":
                    # Handle case where LLM returns a string instead of array
                    char_state.items_in_hand = [val]
                else:
                    char_state.items_in_hand = []

            if char_update.get("emotional_state"):
                val = char_update["emotional_state"]
                char_state.emotional_state = None if isinstance(val, str) and val.lower() == "null" else val

            if char_update.get("physical_condition"):
                val = char_update["physical_condition"]
                char_state.physical_condition = None if isinstance(val, str) and val.lower() == "null" else val

            if char_update.get("current_attire"):
                val = char_update["current_attire"]
                char_state.appearance = None if isinstance(val, str) and val.lower() == "null" else val
            
            # Update possessions
            if char_update.get("possessions_gained"):
                current_poss = char_state.possessions or []
                char_state.possessions = list(set(current_poss + char_update["possessions_gained"]))
            
            if char_update.get("possessions_lost"):
                current_poss = char_state.possessions or []
                char_state.possessions = [p for p in current_poss if p not in char_update["possessions_lost"]]
            
            # Update knowledge
            if char_update.get("knowledge_gained"):
                current_knowledge = char_state.knowledge or []
                char_state.knowledge = list(set(current_knowledge + char_update["knowledge_gained"]))
            
            # Update relationships
            if char_update.get("relationship_changes"):
                current_relationships = char_state.relationships or {}
                current_relationships.update(char_update["relationship_changes"])
                char_state.relationships = current_relationships
            
            try:
                db.commit()
                logger.debug(f"Updated character state for {char_name}{trace_suffix}")
            except IntegrityError as ie:
                db.rollback()
                logger.warning(f"Failed to commit character state update for {char_name}: {ie}{trace_suffix}")
                # Don't re-raise - allow processing to continue
            
        except Exception as e:
            logger.error(f"Failed to update character state: {e}{trace_suffix}")
            db.rollback()
    
    async def _record_character_interaction(
        self,
        db: Session,
        story_id: int,
        scene_sequence: int,
        interaction: Dict[str, Any],
        character_name_to_id: Dict[str, int],
        branch_id: int = None,
        trace_id: Optional[str] = None
    ) -> bool:
        """
        Record a character interaction if it's the first occurrence.
        
        Args:
            db: Database session
            story_id: Story ID
            scene_sequence: Scene sequence number
            interaction: Interaction data from LLM extraction
            character_name_to_id: Mapping of character names to IDs
            branch_id: Optional branch ID
            trace_id: Optional trace ID for logging
            
        Returns:
            True if interaction was recorded, False if it already existed
        """
        try:
            trace_suffix = f" trace_id={trace_id}" if trace_id else ""
            
            interaction_type = interaction.get("interaction_type", "").strip().lower()
            char_a_name = interaction.get("character_a", "").strip().lower()
            char_b_name = interaction.get("character_b", "").strip().lower()
            description = interaction.get("description", "")
            
            if not interaction_type or not char_a_name or not char_b_name:
                return False
            
            # Get character IDs
            char_a_id = character_name_to_id.get(char_a_name)
            char_b_id = character_name_to_id.get(char_b_name)
            
            if not char_a_id or not char_b_id:
                logger.warning(f"[INTERACTION:SKIP] Unknown character(s): {char_a_name}, {char_b_name}{trace_suffix}")
                return False
            
            # Normalize order (lower ID first) for consistent lookups
            if char_a_id > char_b_id:
                char_a_id, char_b_id = char_b_id, char_a_id
            
            # Check if this interaction already exists
            existing = db.query(CharacterInteraction).filter(
                CharacterInteraction.story_id == story_id,
                CharacterInteraction.character_a_id == char_a_id,
                CharacterInteraction.character_b_id == char_b_id,
                CharacterInteraction.interaction_type == interaction_type
            )
            if branch_id:
                existing = existing.filter(CharacterInteraction.branch_id == branch_id)
            
            if existing.first():
                logger.debug(f"[INTERACTION:EXISTS] {interaction_type} between {char_a_name} and {char_b_name}{trace_suffix}")
                return False
            
            # Create new interaction record
            new_interaction = CharacterInteraction(
                story_id=story_id,
                branch_id=branch_id,
                character_a_id=char_a_id,
                character_b_id=char_b_id,
                interaction_type=interaction_type,
                first_occurrence_scene=scene_sequence,
                description=description
            )
            
            db.add(new_interaction)
            try:
                db.flush()
                logger.debug(f"[INTERACTION:RECORDED] {interaction_type} between {char_a_name} and {char_b_name} at scene {scene_sequence}{trace_suffix}")
                return True
            except IntegrityError:
                db.rollback()
                logger.debug(f"[INTERACTION:RACE] Already exists (race condition): {interaction_type}{trace_suffix}")
                return False
                
        except Exception as e:
            logger.error(f"[INTERACTION:ERROR] Failed to record interaction: {e}{trace_suffix}")
            db.rollback()
            return False
    
    async def _update_location_state(
        self,
        db: Session,
        story_id: int,
        scene_sequence: int,
        loc_update: Dict[str, Any],
        branch_id: int = None,
        trace_id: Optional[str] = None
    ):
        """Update or create location state from extracted changes"""
        try:
            trace_suffix = f" trace_id={trace_id}" if trace_id else ""
            loc_name = loc_update.get("name")
            if not loc_name:
                return
            
            # Get or create location state (filtered by branch)
            state_query = db.query(LocationState).filter(
                LocationState.story_id == story_id,
                LocationState.location_name == loc_name
            )
            if branch_id:
                state_query = state_query.filter(LocationState.branch_id == branch_id)
            loc_state = state_query.first()
            
            if not loc_state:
                loc_state = LocationState(
                    story_id=story_id,
                    branch_id=branch_id,
                    location_name=loc_name,
                    notable_features=[],
                    current_occupants=[],
                    significant_events=[],
                    full_state={}
                )
                db.add(loc_state)
                try:
                    db.flush()  # Flush to catch constraint violations immediately
                except IntegrityError as ie:
                    db.rollback()
                    error_msg = str(ie).lower()
                    if "duplicate" in error_msg or "unique constraint" in error_msg:
                        logger.debug(f"Location state already exists (race condition), reloading: {loc_name}{trace_suffix}")
                        # Reload the state that was created by another process
                        state_query = db.query(LocationState).filter(
                            LocationState.story_id == story_id,
                            LocationState.location_name == loc_name
                        )
                        if branch_id:
                            state_query = state_query.filter(LocationState.branch_id == branch_id)
                        loc_state = state_query.first()
                        if not loc_state:
                            logger.error(f"Failed to reload location state after race condition: {loc_name}{trace_suffix}")
                            return
                    else:
                        # Re-raise if it's a different integrity error
                        raise
            
            # Update fields
            loc_state.last_updated_scene = scene_sequence
            
            if loc_update.get("condition"):
                val = loc_update["condition"]
                loc_state.condition = None if isinstance(val, str) and val.lower() == "null" else val

            if loc_update.get("atmosphere"):
                val = loc_update["atmosphere"]
                loc_state.atmosphere = None if isinstance(val, str) and val.lower() == "null" else val
            
            if loc_update.get("occupants"):
                # Validate occupants are actual characters in the story
                valid_occupants = []
                raw_occupants = loc_update["occupants"]
                if isinstance(raw_occupants, list):
                    # Get valid character names for this story
                    story_chars = db.query(Character.name).join(StoryCharacter).filter(
                        StoryCharacter.story_id == story_id
                    ).all()
                    valid_char_names = {c.name.lower() for c in story_chars}
                    
                    for occupant in raw_occupants:
                        if isinstance(occupant, str) and occupant.lower() in valid_char_names:
                            valid_occupants.append(occupant)
                        else:
                            logger.warning(f"Ignoring invalid occupant '{occupant}' - not a character in story {story_id}{trace_suffix}")
                    
                    if valid_occupants:
                        loc_state.current_occupants = valid_occupants
                    # If no valid occupants, don't update (keep existing)
            
            try:
                db.commit()
                logger.debug(f"Updated location state for {loc_name}{trace_suffix}")
            except IntegrityError as ie:
                db.rollback()
                logger.warning(f"Failed to commit location state update for {loc_name}: {ie}{trace_suffix}")
                # Don't re-raise - allow processing to continue
            
        except Exception as e:
            logger.error(f"Failed to update location state: {e}{trace_suffix}")
            db.rollback()
    
    async def _update_object_state(
        self,
        db: Session,
        story_id: int,
        scene_sequence: int,
        obj_update: Dict[str, Any],
        branch_id: int = None,
        trace_id: Optional[str] = None,
        scene_content: str = None
    ):
        """Update or create object state from extracted changes"""
        try:
            trace_suffix = f" trace_id={trace_id}" if trace_id else ""
            obj_name = obj_update.get("name")
            if not obj_name:
                return
            
            # Skip common hallucinated objects that are unlikely to be real story objects
            hallucinated_objects = {'pistol', 'gun', 'knife', 'weapon', 'sword', 'dagger'}
            if obj_name.lower() in hallucinated_objects:
                # Only create if object actually appears in scene content
                if scene_content and obj_name.lower() not in scene_content.lower():
                    logger.warning(f"Ignoring likely hallucinated object '{obj_name}' - not found in scene content{trace_suffix}")
                    return
            
            # Get or create object state (filtered by branch)
            state_query = db.query(ObjectState).filter(
                ObjectState.story_id == story_id,
                ObjectState.object_name == obj_name
            )
            if branch_id:
                state_query = state_query.filter(ObjectState.branch_id == branch_id)
            obj_state = state_query.first()
            
            if not obj_state:
                obj_state = ObjectState(
                    story_id=story_id,
                    branch_id=branch_id,
                    object_name=obj_name,
                    powers=[],
                    limitations=[],
                    previous_owners=[],
                    recent_events=[],
                    full_state={}
                )
                db.add(obj_state)
                try:
                    db.flush()  # Flush to catch constraint violations immediately
                except IntegrityError as ie:
                    db.rollback()
                    error_msg = str(ie).lower()
                    if "duplicate" in error_msg or "unique constraint" in error_msg:
                        logger.debug(f"Object state already exists (race condition), reloading: {obj_name}{trace_suffix}")
                        # Reload the state that was created by another process
                        state_query = db.query(ObjectState).filter(
                            ObjectState.story_id == story_id,
                            ObjectState.object_name == obj_name
                        )
                        if branch_id:
                            state_query = state_query.filter(ObjectState.branch_id == branch_id)
                        obj_state = state_query.first()
                        if not obj_state:
                            logger.error(f"Failed to reload object state after race condition: {obj_name}{trace_suffix}")
                            return
                    else:
                        # Re-raise if it's a different integrity error
                        raise
            
            # Update fields
            obj_state.last_updated_scene = scene_sequence
            
            if obj_update.get("location"):
                val = obj_update["location"]
                obj_state.current_location = None if isinstance(val, str) and val.lower() == "null" else val

            if obj_update.get("condition"):
                val = obj_update["condition"]
                obj_state.condition = None if isinstance(val, str) and val.lower() == "null" else val

            if obj_update.get("significance"):
                val = obj_update["significance"]
                obj_state.significance = None if isinstance(val, str) and val.lower() == "null" else val
            
            # Update owner if specified
            if obj_update.get("owner"):
                owner_name = obj_update["owner"]
                # Find character ID by name (filtered by branch)
                story_char_query = db.query(StoryCharacter).join(Character).filter(
                    StoryCharacter.story_id == story_id,
                    Character.name == owner_name
                )
                if branch_id:
                    story_char_query = story_char_query.filter(StoryCharacter.branch_id == branch_id)
                story_char = story_char_query.first()
                if story_char:
                    obj_state.current_owner_id = story_char.character_id
            
            try:
                db.commit()
                logger.debug(f"Updated object state for {obj_name}{trace_suffix}")
            except IntegrityError as ie:
                db.rollback()
                logger.warning(f"Failed to commit object state update for {obj_name}: {ie}{trace_suffix}")
                # Don't re-raise - allow processing to continue
            
        except Exception as e:
            logger.error(f"Failed to update object state: {e}{trace_suffix}")
            db.rollback()

    async def process_entity_states(
        self,
        db: Session,
        story_id: int,
        branch_id: int,
        scene_id: int,
        scene_sequence: int,
        entity_states: Dict[str, Any],
        scene_content: str = ""
    ) -> int:
        """
        Process entity states from extraction results.
        Updates character, location, and object states.

        Args:
            db: Database session
            story_id: Story ID
            branch_id: Branch ID for branch isolation
            scene_id: Scene ID
            scene_sequence: Scene sequence number
            entity_states: Dict with 'characters', 'locations', 'objects' keys
            scene_content: Optional scene content for validation

        Returns:
            Number of states processed
        """
        total_processed = 0

        try:
            # Process character states
            if entity_states.get('characters'):
                for char_update in entity_states['characters']:
                    try:
                        # Track if this character has meaningful state data
                        if has_meaningful_character_state(char_update):
                            logger.debug(f"Processing meaningful character state: {char_update.get('name')}")
                        else:
                            logger.debug(f"Character state has no meaningful data: {char_update.get('name')}")

                        await self._update_character_state(
                            db, story_id, scene_sequence, char_update, branch_id=branch_id
                        )
                        total_processed += 1
                    except Exception as e:
                        logger.warning(f"Failed to update character state for {char_update.get('name', 'unknown')}: {e}")
                        continue

            # Process location states
            if entity_states.get('locations'):
                for loc_update in entity_states['locations']:
                    try:
                        await self._update_location_state(
                            db, story_id, scene_sequence, loc_update, branch_id=branch_id
                        )
                        total_processed += 1
                    except Exception as e:
                        logger.warning(f"Failed to update location state for {loc_update.get('name', 'unknown')}: {e}")
                        continue

            # Process object states
            if entity_states.get('objects'):
                for obj_update in entity_states['objects']:
                    try:
                        await self._update_object_state(
                            db, story_id, scene_sequence, obj_update, branch_id=branch_id,
                            scene_content=scene_content
                        )
                        total_processed += 1
                    except Exception as e:
                        logger.warning(f"Failed to update object state for {obj_update.get('name', 'unknown')}: {e}")
                        continue

            db.commit()
            logger.info(f"[ENTITY:PROCESS] Processed {total_processed} entity states for scene {scene_sequence}")

        except Exception as e:
            logger.error(f"Failed to process entity states: {e}")
            db.rollback()

        return total_processed

    def get_character_state(
        self,
        db: Session,
        character_id: int,
        story_id: int,
        branch_id: int = None
    ) -> Optional[CharacterState]:
        """Get current character state (optionally filtered by branch)"""
        query = db.query(CharacterState).filter(
            CharacterState.character_id == character_id,
            CharacterState.story_id == story_id
        )
        if branch_id:
            query = query.filter(CharacterState.branch_id == branch_id)
        return query.first()

    def get_character_state_at_scene(
        self,
        db: Session,
        character_id: int,
        story_id: int,
        branch_id: int,
        scene_sequence: int
    ) -> Optional[Dict[str, Any]]:
        """Get character state from the batch snapshot covering a specific scene.

        Looks up EntityStateBatch where start_scene_sequence <= scene_sequence <= end_scene_sequence.
        If no exact match, falls back to the nearest batch before the scene.
        Returns the character dict from the snapshot, or None if no batch found.
        """
        # Try exact batch covering this scene
        batch = db.query(EntityStateBatch).filter(
            EntityStateBatch.story_id == story_id,
            EntityStateBatch.branch_id == branch_id if branch_id else EntityStateBatch.branch_id.is_(None),
            EntityStateBatch.start_scene_sequence <= scene_sequence,
            EntityStateBatch.end_scene_sequence >= scene_sequence,
        ).first()

        # Fall back to nearest batch before the scene
        if not batch:
            batch = db.query(EntityStateBatch).filter(
                EntityStateBatch.story_id == story_id,
                EntityStateBatch.branch_id == branch_id if branch_id else EntityStateBatch.branch_id.is_(None),
                EntityStateBatch.end_scene_sequence < scene_sequence,
            ).order_by(EntityStateBatch.end_scene_sequence.desc()).first()

        if not batch or not batch.character_states_snapshot:
            return None

        for char_dict in batch.character_states_snapshot:
            if char_dict.get("character_id") == character_id:
                return char_dict

        return None

    def get_all_character_states(
        self,
        db: Session,
        story_id: int,
        branch_id: int = None
    ) -> List[CharacterState]:
        """Get all character states for a story (optionally filtered by branch)"""
        query = db.query(CharacterState).filter(
            CharacterState.story_id == story_id
        )
        if branch_id:
            query = query.filter(CharacterState.branch_id == branch_id)
        return query.all()
    
    def get_all_character_interactions(
        self,
        db: Session,
        story_id: int,
        branch_id: int = None
    ) -> List[CharacterInteraction]:
        """Get all character interactions for a story (optionally filtered by branch)"""
        query = db.query(CharacterInteraction).filter(
            CharacterInteraction.story_id == story_id
        )
        if branch_id:
            query = query.filter(CharacterInteraction.branch_id == branch_id)
        return query.order_by(CharacterInteraction.first_occurrence_scene).all()
    
    def get_location_state(
        self,
        db: Session,
        story_id: int,
        location_name: str,
        branch_id: int = None
    ) -> Optional[LocationState]:
        """Get current location state (optionally filtered by branch)"""
        query = db.query(LocationState).filter(
            LocationState.story_id == story_id,
            LocationState.location_name == location_name
        )
        if branch_id:
            query = query.filter(LocationState.branch_id == branch_id)
        return query.first()
    
    def get_all_location_states(
        self,
        db: Session,
        story_id: int,
        branch_id: int = None
    ) -> List[LocationState]:
        """Get all location states for a story (optionally filtered by branch)"""
        query = db.query(LocationState).filter(
            LocationState.story_id == story_id
        )
        if branch_id:
            query = query.filter(LocationState.branch_id == branch_id)
        return query.all()
    
    def get_object_state(
        self,
        db: Session,
        story_id: int,
        object_name: str,
        branch_id: int = None
    ) -> Optional[ObjectState]:
        """Get current object state (optionally filtered by branch)"""
        query = db.query(ObjectState).filter(
            ObjectState.story_id == story_id,
            ObjectState.object_name == object_name
        )
        if branch_id:
            query = query.filter(ObjectState.branch_id == branch_id)
        return query.first()
    
    def get_all_object_states(
        self,
        db: Session,
        story_id: int,
        branch_id: int = None
    ) -> List[ObjectState]:
        """Get all object states for a story (optionally filtered by branch)"""
        query = db.query(ObjectState).filter(
            ObjectState.story_id == story_id
        )
        if branch_id:
            query = query.filter(ObjectState.branch_id == branch_id)
        return query.all()
    
    def create_entity_state_batch_snapshot(
        self,
        db: Session,
        story_id: int,
        start_scene_sequence: int,
        end_scene_sequence: int,
        branch_id: int = None
    ) -> Optional[EntityStateBatch]:
        """
        Create a snapshot of current entity states as a batch.
        
        Args:
            db: Database session
            story_id: Story ID
            start_scene_sequence: First scene sequence in batch
            end_scene_sequence: Last scene sequence in batch
            branch_id: Optional branch ID for filtering
            
        Returns:
            Created EntityStateBatch or None if no states exist
        """
        try:
            # Get all current entity states for this branch
            char_query = db.query(CharacterState).filter(CharacterState.story_id == story_id)
            if branch_id:
                char_query = char_query.filter(CharacterState.branch_id == branch_id)
            character_states = char_query.all()

            loc_query = db.query(LocationState).filter(LocationState.story_id == story_id)
            if branch_id:
                loc_query = loc_query.filter(LocationState.branch_id == branch_id)
            location_states = loc_query.all()

            obj_query = db.query(ObjectState).filter(ObjectState.story_id == story_id)
            if branch_id:
                obj_query = obj_query.filter(ObjectState.branch_id == branch_id)
            object_states = obj_query.all()
            
            # Convert to JSON snapshots
            character_snapshot = [state.to_dict() for state in character_states]
            location_snapshot = [state.to_dict() for state in location_states]
            object_snapshot = [state.to_dict() for state in object_states]
            
            # Only create batch if there are states to snapshot
            if not (character_snapshot or location_snapshot or object_snapshot):
                logger.debug(f"No entity states to snapshot for story {story_id} (branch {branch_id})")
                return None

            # Check if character states have meaningful data
            chars_with_data = []
            chars_without_data = []
            for char_state in character_states:
                if has_meaningful_character_state_in_db(char_state):
                    chars_with_data.append(char_state.character_id)
                else:
                    chars_without_data.append(char_state.character_id)

            # Log warning if batch would contain empty character states
            if chars_without_data:
                logger.warning(
                    f"[ENTITY:BATCH:EMPTY_STATES] Creating batch for story {story_id} scenes {start_scene_sequence}-{end_scene_sequence} "
                    f"with {len(chars_without_data)} characters having no meaningful state data (IDs: {chars_without_data}). "
                    f"Characters with data: {len(chars_with_data)}."
                )

            # CRITICAL: If ALL character states have empty data, this is a serious issue
            if character_states and not chars_with_data:
                logger.error(
                    f"[ENTITY:BATCH:ALL_EMPTY] CRITICAL - Batch for story {story_id} scenes {start_scene_sequence}-{end_scene_sequence} "
                    f"would contain ALL {len(character_states)} characters with EMPTY state data! "
                    "This may indicate extraction failure. Consider not creating this batch or investigating the cause."
                )
                # Still create the batch for now, but the warning should be investigated

            # Check if batch already exists for this scene range (upsert logic)
            existing_batch = db.query(EntityStateBatch).filter(
                EntityStateBatch.story_id == story_id,
                EntityStateBatch.branch_id == branch_id if branch_id else EntityStateBatch.branch_id.is_(None),
                EntityStateBatch.start_scene_sequence == start_scene_sequence,
                EntityStateBatch.end_scene_sequence == end_scene_sequence
            ).first()

            if existing_batch:
                # Update existing batch
                existing_batch.character_states_snapshot = character_snapshot
                existing_batch.location_states_snapshot = location_snapshot
                existing_batch.object_states_snapshot = object_snapshot
                db.flush()
                logger.info(f"[ENTITY:BATCH] Updated existing batch for story {story_id} (branch {branch_id}): scenes {start_scene_sequence}-{end_scene_sequence}")
                return existing_batch

            # Create new batch snapshot
            batch = EntityStateBatch(
                story_id=story_id,
                branch_id=branch_id,
                start_scene_sequence=start_scene_sequence,
                end_scene_sequence=end_scene_sequence,
                character_states_snapshot=character_snapshot,
                location_states_snapshot=location_snapshot,
                object_states_snapshot=object_snapshot
            )

            db.add(batch)
            db.flush()

            logger.info(f"[ENTITY:BATCH] Created new batch for story {story_id} (branch {branch_id}): scenes {start_scene_sequence}-{end_scene_sequence} ({len(character_snapshot)} characters, {len(location_snapshot)} locations, {len(object_snapshot)} objects)")
            
            return batch
            
        except Exception as e:
            logger.error(f"Failed to create entity state batch snapshot: {e}")
            return None
    
    def get_last_valid_batch(
        self,
        db: Session,
        story_id: int,
        max_scene_sequence: int,
        branch_id: int = None,
        require_meaningful_data: bool = True
    ) -> Optional[EntityStateBatch]:
        """
        Find the last valid batch that doesn't overlap with deleted scenes.
        Optionally checks that the batch has meaningful character state data.

        Args:
            db: Database session
            story_id: Story ID
            max_scene_sequence: Maximum scene sequence to consider (scenes after this are deleted)
            branch_id: Optional branch ID to filter by
            require_meaningful_data: If True, skip batches where all characters have empty states

        Returns:
            Last valid EntityStateBatch or None
        """
        # Find all batches where end_scene_sequence < max_scene_sequence, ordered by most recent first
        batch_query = db.query(EntityStateBatch).filter(
            EntityStateBatch.story_id == story_id,
            EntityStateBatch.end_scene_sequence < max_scene_sequence
        )
        if branch_id is not None:
            batch_query = batch_query.filter(EntityStateBatch.branch_id == branch_id)
        batches = batch_query.order_by(EntityStateBatch.end_scene_sequence.desc()).limit(10).all()

        for batch in batches:
            if not require_meaningful_data:
                return batch

            # Check if this batch has at least one character with meaningful data
            has_meaningful = False
            for char_dict in batch.character_states_snapshot or []:
                # Check if any key state fields have non-null values
                state_fields = ['current_location', 'emotional_state', 'physical_condition', 'appearance']
                for field in state_fields:
                    value = char_dict.get(field)
                    if value and isinstance(value, str) and value.strip() and value.lower() not in ('null', 'none'):
                        has_meaningful = True
                        break
                # Also check knowledge and relationships
                if char_dict.get('knowledge') and len(char_dict.get('knowledge', [])) > 0:
                    has_meaningful = True
                if char_dict.get('relationships') and len(char_dict.get('relationships', {})) > 0:
                    has_meaningful = True
                if has_meaningful:
                    break

            if has_meaningful:
                if batch != batches[0]:
                    logger.warning(
                        f"[ENTITY:BATCH:SKIP_EMPTY] Skipped {batches.index(batch)} empty batch(es) to find batch {batch.id} "
                        f"(scenes {batch.start_scene_sequence}-{batch.end_scene_sequence}) with meaningful character data."
                    )
                return batch
            else:
                logger.warning(
                    f"[ENTITY:BATCH:EMPTY] Batch {batch.id} (scenes {batch.start_scene_sequence}-{batch.end_scene_sequence}) "
                    f"has no meaningful character state data, checking older batches..."
                )

        # No batch with meaningful data found
        if batches:
            logger.error(
                f"[ENTITY:BATCH:ALL_EMPTY] All {len(batches)} recent batches for story {story_id} have empty character states! "
                "Falling back to most recent batch anyway."
            )
            return batches[0] if batches else None

        return None
    
    def restore_entity_states_from_batch(
        self,
        db: Session,
        batch: EntityStateBatch
    ) -> Dict[str, int]:
        """
        Restore entity states from a batch snapshot.

        Args:
            db: Database session
            batch: EntityStateBatch to restore from

        Returns:
            Dictionary with counts of restored states
        """
        try:
            # Note: Caller (restore_from_last_complete_batch) is responsible for deleting
            # existing entity states before calling this method.

            # Restore character states (always use batch's branch_id for proper branch isolation)
            char_count = 0
            char_errors = 0
            for idx, char_dict in enumerate(batch.character_states_snapshot or []):
                try:
                    state_data = {k: v for k, v in char_dict.items() if k != 'id' and k != 'updated_at'}
                    # Always use batch's branch_id (snapshot may have parent branch's ID after cloning)
                    state_data['branch_id'] = batch.branch_id
                    char_state = CharacterState(**state_data)
                    db.add(char_state)
                    char_count += 1
                except Exception as char_err:
                    char_errors += 1
                    char_name = char_dict.get('name', 'unknown')
                    logger.error(f"[ENTITY:RESTORE:CHAR_ERROR] batch={batch.id} idx={idx} name={char_name} error={char_err} keys={list(char_dict.keys())}")

            # Restore location states (always use batch's branch_id for proper branch isolation)
            loc_count = 0
            loc_errors = 0
            for idx, loc_dict in enumerate(batch.location_states_snapshot or []):
                try:
                    state_data = {k: v for k, v in loc_dict.items() if k != 'id' and k != 'updated_at'}
                    # Always use batch's branch_id (snapshot may have parent branch's ID after cloning)
                    state_data['branch_id'] = batch.branch_id
                    loc_state = LocationState(**state_data)
                    db.add(loc_state)
                    loc_count += 1
                except Exception as loc_err:
                    loc_errors += 1
                    loc_name = loc_dict.get('name', 'unknown')
                    logger.error(f"[ENTITY:RESTORE:LOC_ERROR] batch={batch.id} idx={idx} name={loc_name} error={loc_err} keys={list(loc_dict.keys())}")

            # Restore object states (always use batch's branch_id for proper branch isolation)
            obj_count = 0
            obj_errors = 0
            for idx, obj_dict in enumerate(batch.object_states_snapshot or []):
                try:
                    state_data = {k: v for k, v in obj_dict.items() if k != 'id' and k != 'updated_at'}
                    # Always use batch's branch_id (snapshot may have parent branch's ID after cloning)
                    state_data['branch_id'] = batch.branch_id
                    obj_state = ObjectState(**state_data)
                    db.add(obj_state)
                    obj_count += 1
                except Exception as obj_err:
                    obj_errors += 1
                    obj_name = obj_dict.get('name', 'unknown')
                    logger.error(f"[ENTITY:RESTORE:OBJ_ERROR] batch={batch.id} idx={idx} name={obj_name} error={obj_err} keys={list(obj_dict.keys())}")
            
            db.flush()

            total_errors = char_errors + loc_errors + obj_errors
            if total_errors > 0:
                logger.warning(f"[ENTITY:RESTORE:PARTIAL] batch={batch.id} restored chars={char_count} locs={loc_count} objs={obj_count} errors={total_errors}")
            else:
                logger.info(f"Restored entity states from batch {batch.id}: {char_count} characters, {loc_count} locations, {obj_count} objects")

            return {
                "characters_restored": char_count,
                "locations_restored": loc_count,
                "objects_restored": obj_count,
                "errors": total_errors
            }

        except Exception as e:
            import traceback
            logger.error(f"[ENTITY:RESTORE:FATAL] Failed to restore entity states from batch {batch.id}: {e}")
            logger.error(f"[ENTITY:RESTORE:TRACEBACK] {traceback.format_exc()}")
            db.rollback()
            raise  # Re-raise so caller knows restoration failed
    
    def invalidate_entity_batches_for_scenes(
        self,
        db: Session,
        story_id: int,
        min_seq: int,
        max_seq: int,
        branch_id: int = None
    ) -> int:
        """
        Delete entity state batches and character interactions that overlap with deleted scenes.
        
        Args:
            db: Database session
            story_id: Story ID
            min_seq: Minimum scene sequence deleted
            max_seq: Maximum scene sequence deleted
            branch_id: Optional branch ID to filter by
            
        Returns:
            Number of batches deleted
        """
        # Delete entity state batches that overlap with deleted scenes
        affected_batches_query = db.query(EntityStateBatch).filter(
            EntityStateBatch.story_id == story_id,
            EntityStateBatch.start_scene_sequence <= max_seq,
            EntityStateBatch.end_scene_sequence >= min_seq
        )
        if branch_id is not None:
            affected_batches_query = affected_batches_query.filter(EntityStateBatch.branch_id == branch_id)
        affected_batches = affected_batches_query.all()
        
        batch_count = 0
        if affected_batches:
            batch_count = len(affected_batches)
            for batch in affected_batches:
                db.delete(batch)
            logger.info(f"Invalidated {batch_count} entity state batch(es) for story {story_id} (scenes {min_seq}-{max_seq})")
        
        # Delete character interactions that were first detected in deleted scenes
        # This ensures interactions can be re-detected if scenes are regenerated
        interaction_query = db.query(CharacterInteraction).filter(
            CharacterInteraction.story_id == story_id,
            CharacterInteraction.first_occurrence_scene >= min_seq,
            CharacterInteraction.first_occurrence_scene <= max_seq
        )
        if branch_id is not None:
            interaction_query = interaction_query.filter(CharacterInteraction.branch_id == branch_id)
        
        interaction_count = interaction_query.delete(synchronize_session='fetch')
        if interaction_count > 0:
            logger.info(f"Invalidated {interaction_count} character interaction(s) for story {story_id} (scenes {min_seq}-{max_seq})")
        
        return batch_count

    def rollback_entity_states_for_edit(
        self,
        db: Session,
        story_id: int,
        edited_scene_sequence: int,
        branch_id: int = None
    ) -> Dict[str, Any]:
        """
        Rollback entity states when a scene is edited.

        This method:
        1. Deletes entity states where last_updated_scene >= edited_scene_sequence
        2. Deletes batches where end_scene_sequence >= edited_scene_sequence
        3. Finds prior valid batch (end_scene_sequence < edited_scene_sequence)
        4. Restores from that batch if it exists

        Args:
            db: Database session
            story_id: Story ID
            edited_scene_sequence: The sequence number of the edited scene
            branch_id: Optional branch ID to filter by

        Returns:
            Dictionary with rollback results including whether re-extraction is needed
        """
        try:
            # Step 1: Delete all entity states for this branch (will be restored from batch)
            char_delete_query = db.query(CharacterState).filter(
                CharacterState.story_id == story_id
            )
            loc_delete_query = db.query(LocationState).filter(
                LocationState.story_id == story_id
            )
            obj_delete_query = db.query(ObjectState).filter(
                ObjectState.story_id == story_id
            )

            if branch_id is not None:
                char_delete_query = char_delete_query.filter(CharacterState.branch_id == branch_id)
                loc_delete_query = loc_delete_query.filter(LocationState.branch_id == branch_id)
                obj_delete_query = obj_delete_query.filter(ObjectState.branch_id == branch_id)

            chars_deleted = char_delete_query.delete()
            locs_deleted = loc_delete_query.delete()
            objs_deleted = obj_delete_query.delete()

            logger.info(f"[EDIT ROLLBACK] Deleted entity states for story {story_id} branch={branch_id}: "
                       f"chars={chars_deleted}, locs={locs_deleted}, objs={objs_deleted}")

            # Step 2: Delete batches that include or are after the edited scene
            batch_delete_query = db.query(EntityStateBatch).filter(
                EntityStateBatch.story_id == story_id,
                EntityStateBatch.end_scene_sequence >= edited_scene_sequence
            )
            if branch_id is not None:
                batch_delete_query = batch_delete_query.filter(EntityStateBatch.branch_id == branch_id)

            batches_deleted = batch_delete_query.delete(synchronize_session='fetch')
            logger.info(f"[EDIT ROLLBACK] Deleted {batches_deleted} batch(es) for story {story_id} ending at scene>={edited_scene_sequence}")

            # Step 3: Find prior valid batch (end_scene_sequence < edited_scene_sequence)
            prior_batch = self.get_last_valid_batch(
                db, story_id, edited_scene_sequence, branch_id=branch_id, require_meaningful_data=False
            )

            # Step 4: Restore from prior batch if exists
            restore_results = {"characters_restored": 0, "locations_restored": 0, "objects_restored": 0}
            if prior_batch:
                restore_results = self.restore_entity_states_from_batch(db, prior_batch)
                logger.info(f"[EDIT ROLLBACK] Restored from batch {prior_batch.id} (scenes {prior_batch.start_scene_sequence}-{prior_batch.end_scene_sequence})")
            else:
                logger.info(f"[EDIT ROLLBACK] No prior batch found for story {story_id} before scene {edited_scene_sequence}")

            db.commit()

            return {
                "chars_deleted": chars_deleted,
                "locs_deleted": locs_deleted,
                "objs_deleted": objs_deleted,
                "batches_deleted": batches_deleted,
                "prior_batch_id": prior_batch.id if prior_batch else None,
                "prior_batch_end_scene": prior_batch.end_scene_sequence if prior_batch else None,
                **restore_results,
                "needs_reextraction": True,
                "reextraction_start_scene": prior_batch.end_scene_sequence + 1 if prior_batch else 1
            }

        except Exception as e:
            logger.error(f"[EDIT ROLLBACK] Failed for story {story_id} scene {edited_scene_sequence}: {e}")
            db.rollback()
            return {
                "chars_deleted": 0,
                "locs_deleted": 0,
                "objs_deleted": 0,
                "batches_deleted": 0,
                "prior_batch_id": None,
                "prior_batch_end_scene": None,
                "characters_restored": 0,
                "locations_restored": 0,
                "objects_restored": 0,
                "needs_reextraction": False,
                "reextraction_start_scene": None,
                "error": str(e)
            }

    def restore_from_last_complete_batch(
        self,
        db: Session,
        story_id: int,
        max_deleted_sequence: int,
        branch_id: int = None
    ) -> Dict[str, Any]:
        """
        Restore entity states from last complete batch without re-extraction.
        Used when deletion leaves an incomplete batch - we restore and wait for threshold.
        
        Args:
            db: Database session
            story_id: Story ID
            max_deleted_sequence: Maximum scene sequence that was deleted
            branch_id: Optional branch ID to filter by
            
        Returns:
            Dictionary with restoration results
        """
        try:
            # Find last valid batch before deleted scenes
            last_valid_batch = self.get_last_valid_batch(db, story_id, max_deleted_sequence, branch_id=branch_id)
            
            # Delete all existing entity states for this branch
            char_delete_query = db.query(CharacterState).filter(CharacterState.story_id == story_id)
            loc_delete_query = db.query(LocationState).filter(LocationState.story_id == story_id)
            obj_delete_query = db.query(ObjectState).filter(ObjectState.story_id == story_id)
            if branch_id is not None:
                char_delete_query = char_delete_query.filter(CharacterState.branch_id == branch_id)
                loc_delete_query = loc_delete_query.filter(LocationState.branch_id == branch_id)
                obj_delete_query = obj_delete_query.filter(ObjectState.branch_id == branch_id)
            char_deleted = char_delete_query.delete()
            loc_deleted = loc_delete_query.delete()
            obj_deleted = obj_delete_query.delete()
            logger.info(f"[DELETE] Deleted entity states: chars={char_deleted}, locs={loc_deleted}, objs={obj_deleted}")

            # Restore from last valid batch if exists
            if last_valid_batch:
                restore_results = self.restore_entity_states_from_batch(db, last_valid_batch)
                db.commit()
                logger.info(f"[DELETE] Restored entity states from batch {last_valid_batch.id} (scenes 1-{last_valid_batch.end_scene_sequence})")
                return {
                    **restore_results,
                    "restoration_successful": True
                }
            else:
                # No batch to restore from - just commit the deletions
                db.commit()
                logger.info(f"[DELETE] No valid batch found, entity states cleared")
                return {
                    "characters_restored": 0,
                    "locations_restored": 0,
                    "objects_restored": 0,
                    "restoration_successful": True
                }
            
        except Exception as e:
            import traceback
            logger.error(f"[DELETE:RESTORE:FATAL] Failed to restore entity states from last complete batch: {e}")
            logger.error(f"[DELETE:RESTORE:TRACEBACK] {traceback.format_exc()}")
            db.rollback()
            raise  # Re-raise so caller can log and handle appropriately

    async def recalculate_entity_states_from_batches(
        self,
        db: Session,
        story_id: int,
        user_id: int,
        user_settings: Dict[str, Any],
        max_deleted_sequence: int,
        branch_id: int = None,
        force_extraction: bool = False
    ) -> Dict[str, Any]:
        """
        Recalculate entity states using batch system after scene deletion/edit.
        Only re-extracts if remaining scenes form a complete batch, unless force_extraction=True.

        Args:
            db: Database session
            story_id: Story ID
            user_id: User ID
            user_settings: User settings
            max_deleted_sequence: Maximum scene sequence that was deleted/edited
            branch_id: Optional branch ID to filter by
            force_extraction: If True, extract regardless of batch threshold (for edits)

        Returns:
            Dictionary with recalculation results
        """
        try:
            # Find last valid batch before deleted scenes
            last_valid_batch = self.get_last_valid_batch(db, story_id, max_deleted_sequence, branch_id=branch_id)

            # Delete all existing entity states for this branch
            char_delete_query = db.query(CharacterState).filter(CharacterState.story_id == story_id)
            loc_delete_query = db.query(LocationState).filter(LocationState.story_id == story_id)
            obj_delete_query = db.query(ObjectState).filter(ObjectState.story_id == story_id)
            if branch_id is not None:
                char_delete_query = char_delete_query.filter(CharacterState.branch_id == branch_id)
                loc_delete_query = loc_delete_query.filter(LocationState.branch_id == branch_id)
                obj_delete_query = obj_delete_query.filter(ObjectState.branch_id == branch_id)
            char_delete_query.delete()
            loc_delete_query.delete()
            obj_delete_query.delete()

            # Restore from last valid batch if exists
            if last_valid_batch:
                restore_results = self.restore_entity_states_from_batch(db, last_valid_batch)
                start_sequence = last_valid_batch.end_scene_sequence + 1
                logger.info(f"Restored entity states from batch {last_valid_batch.id} (scenes 1-{last_valid_batch.end_scene_sequence})")
            else:
                restore_results = {"characters_restored": 0, "locations_restored": 0, "objects_restored": 0}
                start_sequence = 1
                logger.info(f"No valid batch found, starting from scene 1")
            
            # Get all remaining scenes after the last valid batch (filtered by branch)
            from ..models import Scene, StoryFlow
            remaining_scenes_query = db.query(Scene).filter(
                Scene.story_id == story_id,
                Scene.sequence_number >= start_sequence
            )
            if branch_id is not None:
                remaining_scenes_query = remaining_scenes_query.filter(Scene.branch_id == branch_id)
            remaining_scenes = remaining_scenes_query.order_by(Scene.sequence_number).all()
            
            if not remaining_scenes:
                logger.info(f"No remaining scenes to process after batch restoration")
                db.commit()
                return {
                    **restore_results,
                    "scenes_processed": 0,
                    "recalculation_successful": True
                }
            
            # Check if remaining scenes form a complete batch
            batch_threshold = self.user_settings.get("context_summary_threshold", 5)
            last_remaining_sequence = remaining_scenes[-1].sequence_number

            # Check if we have a complete batch (last scene sequence is a multiple of threshold)
            is_complete_batch = (last_remaining_sequence % batch_threshold) == 0

            if not is_complete_batch and not force_extraction:
                # Incomplete batch - only restore, don't re-extract (unless forced for edits)
                logger.info(f"[DELETE] Incomplete batch remaining (last scene: {last_remaining_sequence}, threshold: {batch_threshold}). Restored from batch, waiting for threshold.")
                db.commit()
                return {
                    **restore_results,
                    "scenes_processed": 0,
                    "recalculation_successful": True,
                    "incomplete_batch": True
                }

            if force_extraction and not is_complete_batch:
                logger.info(f"[EDIT] Force extraction enabled - processing {len(remaining_scenes)} scenes despite incomplete batch")
            
            # Complete batch - re-extract entity states for remaining scenes
            from ..models import Chapter
            scenes_processed = 0
            for scene in remaining_scenes:
                # Get active variant content
                flow = db.query(StoryFlow).filter(
                    StoryFlow.scene_id == scene.id,
                    StoryFlow.is_active == True
                ).first()
                
                if flow and flow.scene_variant:
                    scene_content = flow.scene_variant.content
                    
                    # Get chapter location for hierarchical context
                    chapter_location = None
                    if scene.chapter_id:
                        chapter = db.query(Chapter).filter(Chapter.id == scene.chapter_id).first()
                        if chapter and chapter.location_name:
                            chapter_location = chapter.location_name
                    
                    await self.extract_and_update_states(
                        db=db,
                        story_id=story_id,
                        scene_id=scene.id,
                        scene_sequence=scene.sequence_number,
                        scene_content=scene_content,
                        chapter_location=chapter_location
                    )
                    scenes_processed += 1
            
            db.commit()
            
            logger.info(f"Recalculated entity states: restored from batch, then processed {scenes_processed} remaining scenes")
            
            return {
                **restore_results,
                "scenes_processed": scenes_processed,
                "recalculation_successful": True
            }
            
        except Exception as e:
            logger.error(f"Failed to recalculate entity states from batches: {e}")
            db.rollback()
            return {
                "characters_restored": 0,
                "locations_restored": 0,
                "objects_restored": 0,
                "scenes_processed": 0,
                "recalculation_successful": False
            }

