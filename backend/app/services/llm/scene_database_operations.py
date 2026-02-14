"""
Scene Database Operations Service

Extracted from UnifiedLLMService to handle all scene-related database operations
including creation, variant management, story flow, and deletion.
"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from collections import defaultdict
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SceneDatabaseOperations:
    """
    Handles database operations for scenes, variants, and story flow.

    This class is used by UnifiedLLMService to separate database operations
    from LLM generation logic.
    """

    def get_active_branch_id(self, db: Session, story_id: int) -> Optional[int]:
        """Get the active branch ID for a story."""
        from ...models import StoryBranch
        active_branch = db.query(StoryBranch).filter(
            and_(
                StoryBranch.story_id == story_id,
                StoryBranch.is_active == True
            )
        ).first()
        return active_branch.id if active_branch else None

    def create_scene_with_variant(
        self,
        db: Session,
        story_id: int,
        sequence_number: int,
        content: str,
        title: str = None,
        custom_prompt: str = None,
        choices: List[Dict[str, Any]] = None,
        generation_method: str = "auto",
        branch_id: int = None,
        chapter_id: int = None,
        entity_states_snapshot: str = None,
        context_snapshot: str = None
    ) -> Tuple[Any, Any]:
        """Create a new scene with its first variant

        Args:
            entity_states_snapshot: Entity states text at generation time for cache consistency (legacy)
            context_snapshot: Full context snapshot JSON for complete cache consistency
        """
        from ...models import Scene, SceneVariant, SceneChoice, StoryFlow

        # Get active branch if not specified
        if branch_id is None:
            branch_id = self.get_active_branch_id(db, story_id)

        # Check if a scene already exists for this sequence in this story/branch
        existing_flow_query = db.query(StoryFlow).filter(
            StoryFlow.story_id == story_id,
            StoryFlow.sequence_number == sequence_number
        )
        if branch_id:
            existing_flow_query = existing_flow_query.filter(StoryFlow.branch_id == branch_id)
        existing_flow = existing_flow_query.first()

        if existing_flow:
            # Return the existing scene and variant instead of creating duplicates
            existing_scene = db.query(Scene).filter(Scene.id == existing_flow.scene_id).first()
            existing_variant = db.query(SceneVariant).filter(SceneVariant.id == existing_flow.scene_variant_id).first()
            logger.warning(f"Scene already exists for story {story_id} sequence {sequence_number} (branch {branch_id}), returning existing scene {existing_scene.id}")
            return existing_scene, existing_variant

        # Create the logical scene
        scene = Scene(
            story_id=story_id,
            branch_id=branch_id,
            chapter_id=chapter_id,
            sequence_number=sequence_number,
            title=title or f"Scene {sequence_number}",
        )
        db.add(scene)
        db.flush()  # Get the scene ID

        # Create the first variant
        variant = SceneVariant(
            scene_id=scene.id,
            variant_number=1,
            is_original=True,
            content=content,
            title=title,
            original_content=content,
            generation_prompt=custom_prompt,
            generation_method=generation_method,
            entity_states_snapshot=entity_states_snapshot,
            context_snapshot=context_snapshot
        )
        db.add(variant)
        db.flush()  # Get the variant ID

        # Create choices if provided
        if choices:
            for choice_data in choices:
                choice = SceneChoice(
                    scene_id=scene.id,
                    scene_variant_id=variant.id,
                    choice_text=choice_data.get('text', ''),
                    choice_order=choice_data.get('order', 0),
                    choice_description=choice_data.get('description')
                )
                db.add(choice)

        # Update story flow
        self.update_story_flow(db, story_id, sequence_number, scene.id, variant.id, branch_id=branch_id)

        db.commit()
        logger.info(f"Successfully created scene {scene.id} with variant {variant.id} at sequence {sequence_number} (branch {branch_id})")
        return scene, variant

    def switch_to_variant(self, db: Session, story_id: int, scene_id: int, variant_id: int, branch_id: int = None) -> bool:
        """Switch the active variant for a scene in the story flow"""
        from ...models import StoryFlow, SceneVariant

        # Verify the variant exists
        variant = db.query(SceneVariant).filter(SceneVariant.id == variant_id).first()
        if not variant or variant.scene_id != scene_id:
            return False

        # Get active branch if not specified
        if branch_id is None:
            branch_id = self.get_active_branch_id(db, story_id)

        # Update story flow to use this variant (filtered by branch)
        flow_query = db.query(StoryFlow).filter(
            StoryFlow.story_id == story_id,
            StoryFlow.scene_id == scene_id
        )
        if branch_id:
            flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)
        flow_entry = flow_query.first()

        if flow_entry:
            flow_entry.scene_variant_id = variant_id
            db.commit()
            logger.info(f"Switched to variant {variant_id} for scene {scene_id} in story {story_id} (branch {branch_id})")
            return True

        return False

    def get_scene_variants(self, db: Session, scene_id: int) -> List[Any]:
        """Get all variants for a scene"""
        from ...models import SceneVariant

        return db.query(SceneVariant)\
            .filter(SceneVariant.scene_id == scene_id)\
            .order_by(SceneVariant.variant_number)\
            .all()

    def get_active_scene_count(self, db: Session, story_id: int, chapter_id: Optional[int] = None, branch_id: int = None) -> int:
        """
        Get count of active scenes from StoryFlow.

        Args:
            db: Database session
            story_id: Story ID
            chapter_id: Optional chapter ID to filter scenes by chapter
            branch_id: Optional branch ID for filtering

        Returns:
            Count of active scenes in the story flow
        """
        from ...models import StoryFlow, Scene

        # Get active branch if not specified
        if branch_id is None:
            branch_id = self.get_active_branch_id(db, story_id)

        query = db.query(StoryFlow).filter(
            StoryFlow.story_id == story_id,
            StoryFlow.is_active == True
        )

        if branch_id:
            query = query.filter(StoryFlow.branch_id == branch_id)

        if chapter_id:
            # Join with Scene to filter by chapter
            query = query.join(Scene).filter(Scene.chapter_id == chapter_id)

        return query.count()

    def get_active_story_flow(self, db: Session, story_id: int, branch_id: int = None, chapter_id: int = None) -> List[Dict[str, Any]]:
        """Get the active story flow with scene variants.

        Optimized to use batch loading instead of N+1 queries.
        Previous: 4 queries per scene (scene, variant, choices, variant_count)
        Now: 5 queries total regardless of scene count

        Args:
            chapter_id: If provided, only return scenes for this chapter
        """
        from ...models import StoryFlow, Scene, SceneVariant, SceneChoice

        # Get active branch if not specified
        if branch_id is None:
            branch_id = self.get_active_branch_id(db, story_id)

        # 1. Get the story flow ordered by sequence (1 query)
        flow_query = db.query(StoryFlow).filter(StoryFlow.story_id == story_id)
        if branch_id:
            flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)
        if chapter_id:
            # Join with Scene to filter by chapter
            flow_query = flow_query.join(Scene, StoryFlow.scene_id == Scene.id).filter(Scene.chapter_id == chapter_id)
        flow_entries = flow_query.order_by(StoryFlow.sequence_number).all()

        if not flow_entries:
            return []

        # Extract IDs for batch loading
        scene_ids = [fe.scene_id for fe in flow_entries]
        variant_ids = [fe.scene_variant_id for fe in flow_entries]

        # 2. Batch load all scenes (1 query)
        scenes = db.query(Scene).filter(Scene.id.in_(scene_ids)).all()
        scene_map = {s.id: s for s in scenes}

        # 3. Batch load all active variants (1 query)
        variants = db.query(SceneVariant).filter(SceneVariant.id.in_(variant_ids)).all()
        variant_map = {v.id: v for v in variants}

        # 4. Batch load all choices for these variants (1 query)
        choices = db.query(SceneChoice)\
            .filter(SceneChoice.scene_variant_id.in_(variant_ids))\
            .order_by(SceneChoice.scene_variant_id, SceneChoice.choice_order)\
            .all()
        choices_by_variant = defaultdict(list)
        for choice in choices:
            choices_by_variant[choice.scene_variant_id].append(choice)

        # 5. Batch get variant counts per scene (1 query)
        variant_counts = db.query(
            SceneVariant.scene_id,
            func.count(SceneVariant.id)
        ).filter(
            SceneVariant.scene_id.in_(scene_ids)
        ).group_by(SceneVariant.scene_id).all()
        count_map = {scene_id: count for scene_id, count in variant_counts}

        # Build result with O(1) lookups - no queries in loop
        result = []
        for flow_entry in flow_entries:
            scene = scene_map.get(flow_entry.scene_id)
            if not scene:
                continue

            variant = variant_map.get(flow_entry.scene_variant_id)
            if not variant:
                continue

            scene_choices = choices_by_variant.get(variant.id, [])
            variant_count = count_map.get(scene.id, 1)

            result.append({
                'scene_id': scene.id,
                'chapter_id': scene.chapter_id,
                'sequence_number': flow_entry.sequence_number,
                'title': variant.title or scene.title,
                'content': variant.content,
                'location': variant.location or '',
                'characters_present': [],
                'variant': {
                    'id': variant.id,
                    'variant_number': variant.variant_number,
                    'is_original': variant.is_original,
                    'content': variant.content,
                    'title': variant.title,
                    'generation_method': variant.generation_method
                },
                'variant_id': variant.id,
                'variant_number': variant.variant_number,
                'is_original': variant.is_original,
                'has_multiple_variants': variant_count > 1,
                'choices': [
                    {
                        'id': choice.id,
                        'text': choice.choice_text,
                        'description': choice.choice_description,
                        'order': choice.choice_order
                    } for choice in scene_choices
                ]
            })

        return result

    def update_story_flow(self, db: Session, story_id: int, sequence_number: int, scene_id: int, variant_id: int, branch_id: int = None):
        """Update or create story flow entry"""
        from ...models import StoryFlow

        # Get active branch if not specified
        if branch_id is None:
            branch_id = self.get_active_branch_id(db, story_id)

        # Check if flow entry already exists for this sequence (filtered by branch)
        existing_flow_query = db.query(StoryFlow).filter(
            StoryFlow.story_id == story_id,
            StoryFlow.sequence_number == sequence_number
        )
        if branch_id:
            existing_flow_query = existing_flow_query.filter(StoryFlow.branch_id == branch_id)
        existing_flow = existing_flow_query.first()

        if existing_flow:
            # Update existing entry
            existing_flow.scene_id = scene_id
            existing_flow.scene_variant_id = variant_id
        else:
            # Create new flow entry
            flow_entry = StoryFlow(
                story_id=story_id,
                branch_id=branch_id,
                sequence_number=sequence_number,
                scene_id=scene_id,
                scene_variant_id=variant_id
            )
            db.add(flow_entry)

    async def delete_scenes_from_sequence(self, db: Session, story_id: int, sequence_number: int, skip_restoration: bool = False, branch_id: int = None) -> bool:
        """Delete all scenes from a given sequence number onwards"""
        start_time = time.perf_counter()
        trace_id = f"scene-del-{uuid.uuid4()}"
        status = "error"
        story_flows_deleted = 0
        scenes_deleted = 0
        try:
            from ...models import StoryFlow, Scene

            # Get active branch if not specified
            phase_start = time.perf_counter()
            if branch_id is None:
                branch_id = self.get_active_branch_id(db, story_id)
            logger.info(f"[DELETE:START] trace_id={trace_id} story_id={story_id} sequence_start={sequence_number} branch_id={branch_id} skip_restoration={skip_restoration}")

            # Phase 1: Delete all StoryFlow entries for this story with sequence_number >= sequence_number (filtered by branch)
            phase_start = time.perf_counter()
            flow_delete_query = db.query(StoryFlow).filter(
                StoryFlow.story_id == story_id,
                StoryFlow.sequence_number >= sequence_number
            )
            if branch_id:
                flow_delete_query = flow_delete_query.filter(StoryFlow.branch_id == branch_id)
            story_flows_deleted = flow_delete_query.delete()
            logger.info(f"[DELETE:PHASE] trace_id={trace_id} phase=delete_story_flows duration_ms={(time.perf_counter()-phase_start)*1000:.2f} flows_deleted={story_flows_deleted}")

            # Phase 2: Get scenes to delete (don't use bulk delete to ensure cascades work) - filtered by branch
            phase_start = time.perf_counter()
            scene_query = db.query(Scene).filter(
                Scene.story_id == story_id,
                Scene.sequence_number >= sequence_number
            )
            if branch_id:
                scene_query = scene_query.filter(Scene.branch_id == branch_id)
            scenes_to_delete = scene_query.all()
            logger.info(f"[DELETE:PHASE] trace_id={trace_id} phase=query_scenes duration_ms={(time.perf_counter()-phase_start)*1000:.2f} scenes_found={len(scenes_to_delete)}")

            # NOTE: Semantic cleanup (embeddings, character moments, plot events) is now handled
            # as a background task by the API endpoint to avoid blocking the response.
            # This method only handles fast database deletions.
            logger.info(f"[DELETE:CONTEXT] trace_id={trace_id} scenes_to_delete={len(scenes_to_delete)} sequence_start={sequence_number} scene_ids={[s.id for s in scenes_to_delete[:5]]}{'...' if len(scenes_to_delete) > 5 else ''}")

            # Restore NPCTracking from snapshot after scene deletion (skip if doing in background)
            if not skip_restoration:
                self._restore_npc_tracking_from_snapshot(
                    db, story_id, sequence_number, branch_id, trace_id
                )

            # Get min and max deleted sequence numbers for batch invalidation (before deleting scenes)
            if scenes_to_delete:
                min_deleted_seq = min(scene.sequence_number for scene in scenes_to_delete)
                max_deleted_seq = max(scene.sequence_number for scene in scenes_to_delete)
            else:
                min_deleted_seq = sequence_number
                max_deleted_seq = sequence_number

            # Get affected chapter IDs before deleting scenes
            affected_chapter_ids = set()
            for scene in scenes_to_delete:
                if scene.chapter_id:
                    affected_chapter_ids.add(scene.chapter_id)
            logger.info(f"[DELETE:CONTEXT] trace_id={trace_id} affected_chapters={list(affected_chapter_ids)}")

            # Phase 2.5: Clear leads_to_scene_id references in SceneChoice before deleting scenes
            # This prevents foreign key constraint violations
            if scenes_to_delete:
                from ...models import SceneChoice
                scene_ids_to_delete = [s.id for s in scenes_to_delete]
                phase_start = time.perf_counter()
                leads_to_cleared = db.query(SceneChoice).filter(
                    SceneChoice.leads_to_scene_id.in_(scene_ids_to_delete)
                ).update({SceneChoice.leads_to_scene_id: None}, synchronize_session='fetch')
                logger.info(f"[DELETE:PHASE] trace_id={trace_id} phase=clear_leads_to_refs duration_ms={(time.perf_counter()-phase_start)*1000:.2f} refs_cleared={leads_to_cleared}")

            # Phase 3: Delete each scene individually to trigger cascade relationships
            phase_start = time.perf_counter()
            scenes_deleted = 0
            total_scenes = len(scenes_to_delete)
            batch_log_interval = max(1, total_scenes // 10) if total_scenes > 10 else 1  # Log every 10% or every scene if < 10

            logger.info(f"[DELETE:SCENE_LOOP:START] trace_id={trace_id} total_scenes={total_scenes}")
            for i, scene in enumerate(scenes_to_delete):
                scene_start = time.perf_counter()
                db.delete(scene)
                scenes_deleted += 1
                scene_duration = (time.perf_counter() - scene_start) * 1000

                # Log progress every batch_log_interval scenes or if a single delete takes > 100ms
                if (i + 1) % batch_log_interval == 0 or scene_duration > 100:
                    elapsed_ms = (time.perf_counter() - phase_start) * 1000
                    logger.info(f"[DELETE:PROGRESS] trace_id={trace_id} progress={i+1}/{total_scenes} ({((i+1)/total_scenes*100):.1f}%) elapsed_ms={elapsed_ms:.2f} last_scene_ms={scene_duration:.2f} scene_id={scene.id}")

            loop_duration = (time.perf_counter() - phase_start) * 1000
            logger.info(f"[DELETE:SCENE_LOOP:END] trace_id={trace_id} scenes_deleted={scenes_deleted} duration_ms={loop_duration:.2f} avg_per_scene_ms={loop_duration/max(1,scenes_deleted):.2f}")

            # Phase 4: Recalculate scenes_count and invalidate affected batches for affected chapters
            self._update_affected_chapters(
                db, story_id, branch_id, affected_chapter_ids,
                min_deleted_seq, max_deleted_seq, trace_id
            )

            # Invalidate and restore entity states using batch system (skip if doing in background)
            if not skip_restoration:
                await self._restore_entity_states(
                    db, story_id, sequence_number, branch_id,
                    min_deleted_seq, max_deleted_seq, trace_id
                )

            # Phase 5: Commit the transaction
            phase_start = time.perf_counter()
            logger.info(f"[DELETE:COMMIT:START] trace_id={trace_id} story_id={story_id}")
            db.commit()
            commit_duration = (time.perf_counter() - phase_start) * 1000
            logger.info(f"[DELETE:COMMIT:END] trace_id={trace_id} commit_duration_ms={commit_duration:.2f}")
            status = "success"

            total_duration = (time.perf_counter() - start_time) * 1000
            logger.info(f"[DELETE:END] trace_id={trace_id} story_id={story_id} sequence_start={sequence_number} flows_deleted={story_flows_deleted} scenes_deleted={scenes_deleted} total_duration_ms={total_duration:.2f}")
            return True

        except Exception as e:
            logger.error(f"[DELETE:ERROR] trace_id={trace_id} story_id={story_id} sequence_start={sequence_number} error={e}")
            db.rollback()
            return False
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            if duration_ms > 15000:
                logger.error(f"[DELETE:SLOW] trace_id={trace_id} duration_ms={duration_ms:.2f} status={status} story_id={story_id}")
            elif duration_ms > 5000:
                logger.warning(f"[DELETE:SLOW] trace_id={trace_id} duration_ms={duration_ms:.2f} status={status} story_id={story_id}")
            else:
                logger.info(f"[DELETE:DONE] trace_id={trace_id} duration_ms={duration_ms:.2f} status={status} story_id={story_id}")

    def _restore_npc_tracking_from_snapshot(
        self, db: Session, story_id: int, sequence_number: int,
        branch_id: int, trace_id: str
    ) -> None:
        """Restore NPC tracking from the last available snapshot."""
        try:
            from ...models import Scene, NPCTracking, NPCTrackingSnapshot

            # Find the last remaining scene's sequence number (filtered by branch)
            last_remaining_query = db.query(Scene).filter(
                Scene.story_id == story_id,
                Scene.sequence_number < sequence_number
            )
            if branch_id:
                last_remaining_query = last_remaining_query.filter(Scene.branch_id == branch_id)
            last_remaining_scene = last_remaining_query.order_by(Scene.sequence_number.desc()).first()

            if last_remaining_scene:
                # Get snapshot for the last remaining scene (filtered by branch)
                snapshot_query = db.query(NPCTrackingSnapshot).filter(
                    NPCTrackingSnapshot.story_id == story_id,
                    NPCTrackingSnapshot.scene_sequence == last_remaining_scene.sequence_number
                )
                if branch_id:
                    snapshot_query = snapshot_query.filter(NPCTrackingSnapshot.branch_id == branch_id)
                snapshot = snapshot_query.first()

                if snapshot:
                    # Restore NPCTracking from snapshot
                    snapshot_data = snapshot.snapshot_data or {}

                    # Delete existing NPC tracking records for this story and branch
                    npc_delete_query = db.query(NPCTracking).filter(
                        NPCTracking.story_id == story_id
                    )
                    if branch_id:
                        npc_delete_query = npc_delete_query.filter(NPCTracking.branch_id == branch_id)
                    npc_delete_query.delete()

                    # Restore from snapshot
                    for character_name, npc_data in snapshot_data.items():
                        tracking = NPCTracking(
                            story_id=story_id,
                            branch_id=branch_id,
                            character_name=character_name,
                            entity_type=npc_data.get("entity_type", "CHARACTER"),
                            total_mentions=npc_data.get("total_mentions", 0),
                            scene_count=npc_data.get("scene_count", 0),
                            importance_score=npc_data.get("importance_score", 0.0),
                            frequency_score=npc_data.get("frequency_score", 0.0),
                            significance_score=npc_data.get("significance_score", 0.0),
                            first_appearance_scene=npc_data.get("first_appearance_scene"),
                            last_appearance_scene=npc_data.get("last_appearance_scene"),
                            has_dialogue_count=npc_data.get("has_dialogue_count", 0),
                            has_actions_count=npc_data.get("has_actions_count", 0),
                            crossed_threshold=npc_data.get("crossed_threshold", False),
                            user_prompted=npc_data.get("user_prompted", False),
                            profile_extracted=npc_data.get("profile_extracted", False),
                            converted_to_character=npc_data.get("converted_to_character", False),
                            extracted_profile=npc_data.get("extracted_profile", {})
                        )
                        db.add(tracking)

                    logger.info(f"[DELETE] Restored NPC tracking from snapshot for scene {last_remaining_scene.sequence_number} (story {story_id} branch {branch_id})")
                else:
                    logger.warning(f"[DELETE] No snapshot found for last remaining scene {last_remaining_scene.sequence_number} (branch {branch_id}), NPC tracking may be inconsistent")
            else:
                # No remaining scenes - delete NPC tracking for this branch
                npc_delete_query = db.query(NPCTracking).filter(
                    NPCTracking.story_id == story_id
                )
                if branch_id:
                    npc_delete_query = npc_delete_query.filter(NPCTracking.branch_id == branch_id)
                npc_delete_query.delete()
                logger.info(f"[DELETE] No remaining scenes, deleted NPC tracking for story {story_id} branch {branch_id}")

        except Exception as e:
            # Don't fail scene deletion if NPC tracking restoration fails
            logger.warning(f"[DELETE] Failed to restore NPC tracking from snapshot after scene deletion: {e}")
            import traceback
            logger.warning(f"[DELETE] Traceback: {traceback.format_exc()}")

    def _update_affected_chapters(
        self, db: Session, story_id: int, branch_id: int,
        affected_chapter_ids: set, min_deleted_seq: int, max_deleted_seq: int,
        trace_id: str
    ) -> None:
        """Update affected chapters after scene deletion."""
        phase_start = time.perf_counter()
        from ...models import Chapter, ChapterSummaryBatch, Scene
        from ..chapter_summary_service import update_chapter_summary_from_batches

        logger.info(f"[DELETE:CHAPTER_UPDATE:START] trace_id={trace_id} chapters_to_update={len(affected_chapter_ids)}")
        for chapter_idx, chapter_id in enumerate(affected_chapter_ids):
            chapter_start = time.perf_counter()
            chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
            if chapter:
                chapter.scenes_count = self.get_active_scene_count(db, story_id, chapter_id, branch_id=chapter.branch_id)
                logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} new_scenes_count={chapter.scenes_count}")

                # Invalidate summary batches that overlap with deleted scenes
                affected_batches = db.query(ChapterSummaryBatch).filter(
                    ChapterSummaryBatch.chapter_id == chapter_id,
                    ChapterSummaryBatch.start_scene_sequence <= max_deleted_seq,
                    ChapterSummaryBatch.end_scene_sequence >= min_deleted_seq
                ).all()

                if affected_batches:
                    for batch in affected_batches:
                        db.delete(batch)
                    logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} summary_batches_invalidated={len(affected_batches)}")

                    # Recalculate summary from remaining batches
                    summary_start = time.perf_counter()
                    update_chapter_summary_from_batches(chapter_id, db)
                    logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} summary_recalc_ms={(time.perf_counter()-summary_start)*1000:.2f}")

                # Invalidate plot progress batches that overlap with deleted scenes
                from ...models import ChapterPlotProgressBatch
                affected_plot_batches = db.query(ChapterPlotProgressBatch).filter(
                    ChapterPlotProgressBatch.chapter_id == chapter_id,
                    ChapterPlotProgressBatch.start_scene_sequence <= max_deleted_seq,
                    ChapterPlotProgressBatch.end_scene_sequence >= min_deleted_seq
                ).all()

                if affected_plot_batches:
                    for batch in affected_plot_batches:
                        db.delete(batch)
                    logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} plot_batches_invalidated={len(affected_plot_batches)}")

                    # Rollback plot progress to last valid batch (before deleted scenes)
                    from ..chapter_progress_service import ChapterProgressService
                    progress_service = ChapterProgressService(db)
                    progress_service.restore_from_last_valid_batch(chapter_id, min_deleted_seq)
                    logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} plot_progress_rolled_back")

                # Update last_extraction_scene_count and last_summary_scene_count to max remaining sequence
                # This prevents extraction/summary from being skipped due to negative scene counts
                remaining_scenes_query = db.query(Scene).filter(
                    Scene.story_id == story_id,
                    Scene.chapter_id == chapter_id,
                    Scene.is_deleted == False
                )
                if branch_id:
                    remaining_scenes_query = remaining_scenes_query.filter(Scene.branch_id == branch_id)
                remaining_scenes = remaining_scenes_query.all()

                if remaining_scenes:
                    max_remaining_seq = max(s.sequence_number for s in remaining_scenes)
                    # Only lower them, never raise them (scenes were deleted, not added)
                    if chapter.last_extraction_scene_count and chapter.last_extraction_scene_count > max_remaining_seq:
                        chapter.last_extraction_scene_count = max_remaining_seq
                        logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} extraction_count_updated_to={max_remaining_seq}")
                    if chapter.last_summary_scene_count and chapter.last_summary_scene_count > max_remaining_seq:
                        chapter.last_summary_scene_count = max_remaining_seq
                        logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} summary_count_updated_to={max_remaining_seq}")
                    if chapter.last_plot_extraction_scene_count and chapter.last_plot_extraction_scene_count > max_remaining_seq:
                        chapter.last_plot_extraction_scene_count = max_remaining_seq
                        logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} plot_extraction_count_updated_to={max_remaining_seq}")
                    if chapter.last_chronicle_scene_count and chapter.last_chronicle_scene_count > max_remaining_seq:
                        chapter.last_chronicle_scene_count = max_remaining_seq
                        logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} chronicle_count_updated_to={max_remaining_seq}")
                    # Restore plot_progress from batches instead of resetting to None
                    # This preserves events from earlier batches that are still valid
                    from ..chapter_progress_service import ChapterProgressService
                    progress_service = ChapterProgressService(db)
                    progress_service.update_plot_progress_from_batches(chapter.id)
                    logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} plot_progress_restored_from_batches")
                else:
                    chapter.last_extraction_scene_count = 0
                    chapter.last_summary_scene_count = 0
                    chapter.last_plot_extraction_scene_count = 0
                    chapter.last_chronicle_scene_count = 0
                    # No remaining scenes, so restore from batches (will set to None if no batches)
                    from ..chapter_progress_service import ChapterProgressService
                    progress_service = ChapterProgressService(db)
                    progress_service.update_plot_progress_from_batches(chapter.id)
                    logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} extraction_summary_plot_count_reset_to=0")

                chapter_duration = (time.perf_counter() - chapter_start) * 1000
                logger.info(f"[DELETE:CHAPTER] trace_id={trace_id} chapter_id={chapter_id} chapter_update_ms={chapter_duration:.2f}")

        chapter_phase_duration = (time.perf_counter() - phase_start) * 1000
        logger.info(f"[DELETE:CHAPTER_UPDATE:END] trace_id={trace_id} chapters_updated={len(affected_chapter_ids)} duration_ms={chapter_phase_duration:.2f}")

    async def _restore_entity_states(
        self, db: Session, story_id: int, sequence_number: int, branch_id: int,
        min_deleted_seq: int, max_deleted_seq: int, trace_id: str
    ) -> None:
        """Restore entity states after scene deletion."""
        try:
            from ...models import Story, UserSettings, Scene
            from ..entity_state_service import EntityStateService

            # Get story to find owner_id
            story = db.query(Story).filter(Story.id == story_id).first()
            if story:
                # Get user settings
                user_settings_obj = db.query(UserSettings).filter(
                    UserSettings.user_id == story.owner_id
                ).first()

                if user_settings_obj:
                    user_settings = user_settings_obj.to_dict()
                    entity_service = EntityStateService(
                        user_id=story.owner_id,
                        user_settings=user_settings
                    )

                    # Invalidate batches that overlap with deleted scenes
                    entity_service.invalidate_entity_batches_for_scenes(
                        db, story_id, min_deleted_seq, max_deleted_seq
                    )

                    # Check if remaining scenes form a complete batch (filtered by branch)
                    remaining_scene_query = db.query(Scene).filter(
                        Scene.story_id == story_id,
                        Scene.sequence_number < sequence_number
                    )
                    if branch_id:
                        remaining_scene_query = remaining_scene_query.filter(Scene.branch_id == branch_id)
                    last_remaining_scene = remaining_scene_query.order_by(Scene.sequence_number.desc()).first()

                    if last_remaining_scene:
                        batch_threshold = user_settings.get("context_summary_threshold", 5)
                        last_sequence = last_remaining_scene.sequence_number
                        is_complete_batch = (last_sequence % batch_threshold) == 0

                        if is_complete_batch:
                            # Complete batch - recalculate (will re-extract)
                            await entity_service.recalculate_entity_states_from_batches(
                                db, story_id, story.owner_id, user_settings, max_deleted_seq, branch_id=branch_id
                            )
                            logger.info(f"[DELETE] Recalculated entity states (complete batch) for story {story_id} branch {branch_id}")
                        else:
                            # Incomplete batch - only restore, don't re-extract
                            entity_service.restore_from_last_complete_batch(
                                db, story_id, max_deleted_seq, branch_id=branch_id
                            )
                            logger.info(f"[DELETE] Restored entity states from last complete batch (incomplete batch remains, waiting for threshold) for story {story_id} branch {branch_id}")
                    else:
                        # No remaining scenes on this branch - clear entity states for this branch only
                        from ...models import CharacterState, LocationState, ObjectState
                        char_del_query = db.query(CharacterState).filter(CharacterState.story_id == story_id)
                        loc_del_query = db.query(LocationState).filter(LocationState.story_id == story_id)
                        obj_del_query = db.query(ObjectState).filter(ObjectState.story_id == story_id)
                        if branch_id:
                            char_del_query = char_del_query.filter(CharacterState.branch_id == branch_id)
                            loc_del_query = loc_del_query.filter(LocationState.branch_id == branch_id)
                            obj_del_query = obj_del_query.filter(ObjectState.branch_id == branch_id)
                        char_del_query.delete()
                        loc_del_query.delete()
                        obj_del_query.delete()
                        logger.info(f"[DELETE] No remaining scenes, cleared entity states for story {story_id} branch {branch_id}")
                else:
                    logger.warning(f"[DELETE] No user settings found for story owner {story.owner_id}, skipping entity state restoration")
            else:
                logger.warning(f"[DELETE] Story {story_id} not found, skipping entity state restoration")
        except Exception as e:
            # Don't fail scene deletion if entity state restoration fails
            logger.warning(f"[DELETE] Failed to restore entity states after scene deletion: {e}")
            import traceback
            logger.warning(f"[DELETE] Traceback: {traceback.format_exc()}")


# Module-level singleton instance for convenience
_scene_db_ops_instance: Optional[SceneDatabaseOperations] = None


def get_scene_database_operations() -> SceneDatabaseOperations:
    """Get or create the singleton SceneDatabaseOperations instance."""
    global _scene_db_ops_instance
    if _scene_db_ops_instance is None:
        _scene_db_ops_instance = SceneDatabaseOperations()
    return _scene_db_ops_instance
