"""
Branch Service

Manages story branches including creation, switching, forking (deep cloning),
and deletion. Implements the "fork and clone" model where each branch is
a fully independent copy of story data.
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from ..models import (
    StoryBranch, Story, Scene, SceneVariant, SceneChoice, Chapter, 
    StoryCharacter, StoryFlow, CharacterState, LocationState, ObjectState,
    EntityStateBatch, NPCMention, NPCTracking, NPCTrackingSnapshot,
    CharacterMemory, PlotEvent, SceneEmbedding, ChapterSummaryBatch
)

logger = logging.getLogger(__name__)


class BranchService:
    """
    Service for managing story branches.
    
    Provides methods for:
    - Getting/setting the active branch
    - Creating new branches (forking)
    - Deleting branches
    - Listing branches
    """
    
    def get_active_branch(self, db: Session, story_id: int) -> Optional[StoryBranch]:
        """
        Get the currently active branch for a story.
        
        Args:
            db: Database session
            story_id: Story ID
            
        Returns:
            The active StoryBranch or None if no active branch exists
        """
        return db.query(StoryBranch).filter(
            and_(
                StoryBranch.story_id == story_id,
                StoryBranch.is_active == True
            )
        ).first()
    
    def get_active_branch_id(self, db: Session, story_id: int) -> Optional[int]:
        """
        Get the ID of the currently active branch for a story.
        
        Args:
            db: Database session
            story_id: Story ID
            
        Returns:
            The active branch ID or None
        """
        branch = self.get_active_branch(db, story_id)
        return branch.id if branch else None
    
    def set_active_branch(self, db: Session, story_id: int, branch_id: int) -> bool:
        """
        Set a branch as the active branch for a story.
        
        Args:
            db: Database session
            story_id: Story ID
            branch_id: Branch ID to activate
            
        Returns:
            True if successful, False otherwise
        """
        from ..models import Story
        
        # Verify the branch exists and belongs to this story
        branch = db.query(StoryBranch).filter(
            and_(
                StoryBranch.id == branch_id,
                StoryBranch.story_id == story_id
            )
        ).first()
        
        if not branch:
            logger.warning(f"Branch {branch_id} not found for story {story_id}")
            return False
        
        # Deactivate all other branches for this story
        db.query(StoryBranch).filter(
            StoryBranch.story_id == story_id
        ).update({"is_active": False})
        
        # Activate the target branch
        branch.is_active = True
        
        # Update story's current_branch_id to point to the new active branch
        story = db.query(Story).filter(Story.id == story_id).first()
        if story:
            story.current_branch_id = branch_id
        
        db.commit()
        
        logger.info(f"Activated branch {branch_id} ('{branch.name}') for story {story_id}")
        return True
    
    def list_branches(self, db: Session, story_id: int) -> List[StoryBranch]:
        """
        List all branches for a story.
        
        Args:
            db: Database session
            story_id: Story ID
            
        Returns:
            List of StoryBranch objects
        """
        return db.query(StoryBranch).filter(
            StoryBranch.story_id == story_id
        ).order_by(StoryBranch.created_at).all()
    
    def get_branch(self, db: Session, branch_id: int) -> Optional[StoryBranch]:
        """
        Get a branch by ID.
        
        Args:
            db: Database session
            branch_id: Branch ID
            
        Returns:
            StoryBranch or None
        """
        return db.query(StoryBranch).filter(StoryBranch.id == branch_id).first()
    
    def get_branch_stats(self, db: Session, branch_id: int) -> Dict[str, Any]:
        """
        Get statistics for a branch.
        
        Args:
            db: Database session
            branch_id: Branch ID
            
        Returns:
            Dictionary with branch statistics
        """
        scene_count = db.query(Scene).filter(Scene.branch_id == branch_id).count()
        chapter_count = db.query(Chapter).filter(Chapter.branch_id == branch_id).count()
        character_count = db.query(StoryCharacter).filter(StoryCharacter.branch_id == branch_id).count()
        
        # Get latest scene sequence
        latest_scene = db.query(Scene).filter(
            Scene.branch_id == branch_id
        ).order_by(Scene.sequence_number.desc()).first()
        
        return {
            "scene_count": scene_count,
            "chapter_count": chapter_count,
            "character_count": character_count,
            "latest_scene_sequence": latest_scene.sequence_number if latest_scene else 0
        }
    
    def create_branch(
        self,
        db: Session,
        story_id: int,
        name: str,
        fork_from_scene_sequence: int,
        description: Optional[str] = None,
        activate: bool = True
    ) -> Tuple[StoryBranch, Dict[str, Any]]:
        """
        Create a new branch by forking from a specific scene.
        
        This performs a deep clone of all story data up to and including
        the specified scene sequence number.
        
        Args:
            db: Database session
            story_id: Story ID
            name: Name for the new branch
            fork_from_scene_sequence: Scene sequence number to fork from
            description: Optional description for the branch
            activate: Whether to activate the new branch immediately
            
        Returns:
            Tuple of (new StoryBranch, stats dict with clone counts)
        """
        logger.info(f"Creating branch '{name}' for story {story_id} from scene {fork_from_scene_sequence}")
        
        # Get the current active branch (source branch)
        source_branch = self.get_active_branch(db, story_id)
        if not source_branch:
            raise ValueError(f"No active branch found for story {story_id}")
        
        # Create the new branch record
        new_branch = StoryBranch(
            story_id=story_id,
            name=name,
            description=description,
            is_main=False,
            is_active=False,  # Will be activated later if requested
            forked_from_branch_id=source_branch.id,
            forked_at_scene_sequence=fork_from_scene_sequence
        )
        db.add(new_branch)
        db.flush()  # Get the new branch ID
        
        new_branch_id = new_branch.id
        source_branch_id = source_branch.id
        
        # ID mapping dictionaries for foreign key remapping
        scene_id_map: Dict[int, int] = {}
        chapter_id_map: Dict[int, int] = {}
        story_character_id_map: Dict[int, int] = {}
        scene_variant_id_map: Dict[int, int] = {}
        scene_choice_id_map: Dict[int, int] = {}
        
        stats = {
            "scenes": 0,
            "scene_variants": 0,
            "scene_choices": 0,
            "chapters": 0,
            "story_characters": 0,
            "story_flows": 0,
            "character_states": 0,
            "location_states": 0,
            "object_states": 0,
            "entity_state_batches": 0,
            "npc_mentions": 0,
            "npc_tracking": 0,
            "npc_tracking_snapshots": 0,
            "character_memories": 0,
            "plot_events": 0,
            "scene_embeddings": 0,
            "chapter_summary_batches": 0
        }
        
        # 1. Clone Chapters (need to do first for scene FK)
        chapters = db.query(Chapter).filter(
            Chapter.branch_id == source_branch_id
        ).order_by(Chapter.chapter_number).all()
        
        for chapter in chapters:
            # Check if this chapter has any scenes up to the fork point
            has_scenes_before_fork = db.query(Scene).filter(
                and_(
                    Scene.chapter_id == chapter.id,
                    Scene.branch_id == source_branch_id,
                    Scene.sequence_number <= fork_from_scene_sequence
                )
            ).count() > 0
            
            if has_scenes_before_fork or chapter.chapter_number == 1:
                new_chapter = Chapter(
                    story_id=story_id,
                    branch_id=new_branch_id,
                    chapter_number=chapter.chapter_number,
                    title=chapter.title,
                    description=chapter.description,
                    plot_point=chapter.plot_point,
                    plot_point_index=chapter.plot_point_index,
                    story_so_far=chapter.story_so_far,
                    auto_summary=chapter.auto_summary,
                    last_summary_scene_count=chapter.last_summary_scene_count,
                    last_extraction_scene_count=chapter.last_extraction_scene_count,
                    location_name=chapter.location_name,
                    time_period=chapter.time_period,
                    scenario=chapter.scenario,
                    continues_from_previous=chapter.continues_from_previous,
                    status=chapter.status,
                    context_tokens_used=chapter.context_tokens_used,
                    scenes_count=0  # Will be updated after cloning scenes
                )
                db.add(new_chapter)
                db.flush()
                chapter_id_map[chapter.id] = new_chapter.id
                stats["chapters"] += 1
        
        # 2. Clone StoryCharacters (all of them)
        story_characters = db.query(StoryCharacter).filter(
            StoryCharacter.branch_id == source_branch_id
        ).all()
        
        for sc in story_characters:
            new_sc = StoryCharacter(
                story_id=story_id,
                branch_id=new_branch_id,
                character_id=sc.character_id,
                role=sc.role,
                current_location=sc.current_location,
                current_emotional_state=sc.current_emotional_state,
                current_goals=sc.current_goals,
                knowledge_state=sc.knowledge_state,
                relationships=sc.relationships,
                character_development=sc.character_development,
                is_active=sc.is_active
            )
            db.add(new_sc)
            db.flush()
            story_character_id_map[sc.id] = new_sc.id
            stats["story_characters"] += 1
        
        # 3. Clone Scenes up to fork point
        scenes = db.query(Scene).filter(
            and_(
                Scene.branch_id == source_branch_id,
                Scene.sequence_number <= fork_from_scene_sequence
            )
        ).order_by(Scene.sequence_number).all()
        
        for scene in scenes:
            new_chapter_id = chapter_id_map.get(scene.chapter_id) if scene.chapter_id else None
            new_parent_scene_id = scene_id_map.get(scene.parent_scene_id) if scene.parent_scene_id else None
            
            new_scene = Scene(
                story_id=story_id,
                branch_id=new_branch_id,
                chapter_id=new_chapter_id,
                sequence_number=scene.sequence_number,
                parent_scene_id=new_parent_scene_id,
                branch_choice=scene.branch_choice,
                title=scene.title,
                scene_type=scene.scene_type,
                is_deleted=scene.is_deleted,
                deletion_point=scene.deletion_point
            )
            db.add(new_scene)
            db.flush()
            scene_id_map[scene.id] = new_scene.id
            stats["scenes"] += 1
            
            # Clone SceneVariants for this scene
            variants = db.query(SceneVariant).filter(
                SceneVariant.scene_id == scene.id
            ).all()
            
            for variant in variants:
                new_variant = SceneVariant(
                    scene_id=new_scene.id,
                    variant_number=variant.variant_number,
                    is_original=variant.is_original,
                    content=variant.content,
                    title=variant.title,
                    characters_present=variant.characters_present,
                    location=variant.location,
                    mood=variant.mood,
                    scene_context=variant.scene_context,
                    generation_prompt=variant.generation_prompt,
                    generation_method=variant.generation_method,
                    original_content=variant.original_content,
                    user_edited=variant.user_edited,
                    edit_history=variant.edit_history,
                    user_rating=variant.user_rating,
                    is_favorite=variant.is_favorite
                )
                db.add(new_variant)
                db.flush()
                scene_variant_id_map[variant.id] = new_variant.id
                stats["scene_variants"] += 1
            
            # Clone SceneChoices for this scene
            choices = db.query(SceneChoice).filter(
                SceneChoice.scene_id == scene.id
            ).all()
            
            for choice in choices:
                new_variant_id = scene_variant_id_map.get(choice.scene_variant_id) if choice.scene_variant_id else None
                
                new_choice = SceneChoice(
                    scene_id=new_scene.id,
                    scene_variant_id=new_variant_id,
                    choice_text=choice.choice_text,
                    choice_description=choice.choice_description,
                    choice_order=choice.choice_order,
                    is_user_created=choice.is_user_created,
                    predicted_outcomes=choice.predicted_outcomes,
                    character_reactions=choice.character_reactions,
                    times_selected=0,  # Reset for new branch
                    leads_to_scene_id=None  # Will be updated after all scenes are cloned
                )
                db.add(new_choice)
                db.flush()
                scene_choice_id_map[choice.id] = new_choice.id
                stats["scene_choices"] += 1
        
        # Update leads_to_scene_id for choices (now that all scenes are cloned)
        for old_choice_id, new_choice_id in scene_choice_id_map.items():
            old_choice = db.query(SceneChoice).filter(SceneChoice.id == old_choice_id).first()
            if old_choice and old_choice.leads_to_scene_id:
                new_leads_to = scene_id_map.get(old_choice.leads_to_scene_id)
                if new_leads_to:
                    new_choice = db.query(SceneChoice).filter(SceneChoice.id == new_choice_id).first()
                    new_choice.leads_to_scene_id = new_leads_to
        
        # 4. Clone StoryFlow entries
        flows = db.query(StoryFlow).filter(
            and_(
                StoryFlow.branch_id == source_branch_id,
                StoryFlow.sequence_number <= fork_from_scene_sequence
            )
        ).all()
        
        for flow in flows:
            new_scene_id = scene_id_map.get(flow.scene_id)
            new_variant_id = scene_variant_id_map.get(flow.scene_variant_id)
            new_choice_id = scene_choice_id_map.get(flow.from_choice_id) if flow.from_choice_id else None
            
            if new_scene_id and new_variant_id:
                new_flow = StoryFlow(
                    story_id=story_id,
                    branch_id=new_branch_id,
                    sequence_number=flow.sequence_number,
                    scene_id=new_scene_id,
                    scene_variant_id=new_variant_id,
                    from_choice_id=new_choice_id,
                    choice_text=flow.choice_text,
                    is_active=flow.is_active,
                    flow_name=flow.flow_name
                )
                db.add(new_flow)
                stats["story_flows"] += 1
        
        # 5. Clone Entity States (latest values only)
        # Character States
        char_states = db.query(CharacterState).filter(
            and_(
                CharacterState.branch_id == source_branch_id,
                CharacterState.last_updated_scene <= fork_from_scene_sequence
            )
        ).all()
        
        for state in char_states:
            new_state = CharacterState(
                character_id=state.character_id,
                story_id=story_id,
                branch_id=new_branch_id,
                last_updated_scene=state.last_updated_scene,
                current_location=state.current_location,
                physical_condition=state.physical_condition,
                appearance=state.appearance,
                possessions=state.possessions,
                emotional_state=state.emotional_state,
                current_goal=state.current_goal,
                active_conflicts=state.active_conflicts,
                knowledge=state.knowledge,
                secrets=state.secrets,
                relationships=state.relationships,
                arc_stage=state.arc_stage,
                arc_progress=state.arc_progress,
                recent_decisions=state.recent_decisions,
                recent_actions=state.recent_actions,
                full_state=state.full_state
            )
            db.add(new_state)
            stats["character_states"] += 1
        
        # Location States
        loc_states = db.query(LocationState).filter(
            and_(
                LocationState.branch_id == source_branch_id,
                LocationState.last_updated_scene <= fork_from_scene_sequence
            )
        ).all()
        
        for state in loc_states:
            new_state = LocationState(
                story_id=story_id,
                branch_id=new_branch_id,
                location_name=state.location_name,
                last_updated_scene=state.last_updated_scene,
                condition=state.condition,
                atmosphere=state.atmosphere,
                notable_features=state.notable_features,
                current_occupants=state.current_occupants,
                significant_events=state.significant_events,
                time_of_day=state.time_of_day,
                weather=state.weather,
                full_state=state.full_state
            )
            db.add(new_state)
            stats["location_states"] += 1
        
        # Object States
        obj_states = db.query(ObjectState).filter(
            and_(
                ObjectState.branch_id == source_branch_id,
                ObjectState.last_updated_scene <= fork_from_scene_sequence
            )
        ).all()
        
        for state in obj_states:
            new_state = ObjectState(
                story_id=story_id,
                branch_id=new_branch_id,
                object_name=state.object_name,
                last_updated_scene=state.last_updated_scene,
                condition=state.condition,
                current_location=state.current_location,
                current_owner_id=state.current_owner_id,
                significance=state.significance,
                object_type=state.object_type,
                powers=state.powers,
                limitations=state.limitations,
                origin=state.origin,
                previous_owners=state.previous_owners,
                recent_events=state.recent_events,
                full_state=state.full_state
            )
            db.add(new_state)
            stats["object_states"] += 1
        
        # Entity State Batches
        batches = db.query(EntityStateBatch).filter(
            and_(
                EntityStateBatch.branch_id == source_branch_id,
                EntityStateBatch.end_scene_sequence <= fork_from_scene_sequence
            )
        ).all()
        
        for batch in batches:
            new_batch = EntityStateBatch(
                story_id=story_id,
                branch_id=new_branch_id,
                start_scene_sequence=batch.start_scene_sequence,
                end_scene_sequence=batch.end_scene_sequence,
                character_states_snapshot=batch.character_states_snapshot,
                location_states_snapshot=batch.location_states_snapshot,
                object_states_snapshot=batch.object_states_snapshot
            )
            db.add(new_batch)
            stats["entity_state_batches"] += 1
        
        # 6. Clone NPC Tracking
        # NPC Mentions
        mentions = db.query(NPCMention).filter(
            and_(
                NPCMention.branch_id == source_branch_id,
                NPCMention.sequence_number <= fork_from_scene_sequence
            )
        ).all()
        
        for mention in mentions:
            new_scene_id = scene_id_map.get(mention.scene_id)
            if new_scene_id:
                new_mention = NPCMention(
                    story_id=story_id,
                    branch_id=new_branch_id,
                    scene_id=new_scene_id,
                    character_name=mention.character_name,
                    sequence_number=mention.sequence_number,
                    mention_count=mention.mention_count,
                    has_dialogue=mention.has_dialogue,
                    has_actions=mention.has_actions,
                    has_relationships=mention.has_relationships,
                    context_snippets=mention.context_snippets,
                    extracted_properties=mention.extracted_properties
                )
                db.add(new_mention)
                stats["npc_mentions"] += 1
        
        # NPC Tracking (aggregated)
        tracking_records = db.query(NPCTracking).filter(
            NPCTracking.branch_id == source_branch_id
        ).all()
        
        for tracking in tracking_records:
            # Only clone if NPC appeared before fork point
            if tracking.first_appearance_scene and tracking.first_appearance_scene <= fork_from_scene_sequence:
                new_tracking = NPCTracking(
                    story_id=story_id,
                    branch_id=new_branch_id,
                    character_name=tracking.character_name,
                    entity_type=tracking.entity_type,
                    total_mentions=tracking.total_mentions,
                    scene_count=tracking.scene_count,
                    first_appearance_scene=tracking.first_appearance_scene,
                    last_appearance_scene=min(tracking.last_appearance_scene or fork_from_scene_sequence, fork_from_scene_sequence),
                    has_dialogue_count=tracking.has_dialogue_count,
                    has_actions_count=tracking.has_actions_count,
                    significance_score=tracking.significance_score,
                    importance_score=tracking.importance_score,
                    frequency_score=tracking.frequency_score,
                    extracted_profile=tracking.extracted_profile,
                    crossed_threshold=tracking.crossed_threshold,
                    user_prompted=tracking.user_prompted,
                    profile_extracted=tracking.profile_extracted,
                    converted_to_character=tracking.converted_to_character
                )
                db.add(new_tracking)
                stats["npc_tracking"] += 1
        
        # NPC Tracking Snapshots
        snapshots = db.query(NPCTrackingSnapshot).filter(
            and_(
                NPCTrackingSnapshot.branch_id == source_branch_id,
                NPCTrackingSnapshot.scene_sequence <= fork_from_scene_sequence
            )
        ).all()
        
        for snapshot in snapshots:
            new_scene_id = scene_id_map.get(snapshot.scene_id)
            if new_scene_id:
                new_snapshot = NPCTrackingSnapshot(
                    scene_id=new_scene_id,
                    scene_sequence=snapshot.scene_sequence,
                    story_id=story_id,
                    branch_id=new_branch_id,
                    snapshot_data=snapshot.snapshot_data
                )
                db.add(new_snapshot)
                stats["npc_tracking_snapshots"] += 1
        
        # 7. Clone Semantic Memory
        # Character Memories
        memories = db.query(CharacterMemory).filter(
            and_(
                CharacterMemory.branch_id == source_branch_id,
                CharacterMemory.sequence_order <= fork_from_scene_sequence
            )
        ).all()
        
        for memory in memories:
            new_scene_id = scene_id_map.get(memory.scene_id)
            new_chapter_id = chapter_id_map.get(memory.chapter_id) if memory.chapter_id else None
            
            if new_scene_id:
                # Generate new embedding_id for the clone
                new_embedding_id = f"{memory.embedding_id}_branch_{new_branch_id}"
                
                new_memory = CharacterMemory(
                    character_id=memory.character_id,
                    scene_id=new_scene_id,
                    story_id=story_id,
                    branch_id=new_branch_id,
                    moment_type=memory.moment_type,
                    content=memory.content,
                    embedding_id=new_embedding_id,
                    sequence_order=memory.sequence_order,
                    chapter_id=new_chapter_id,
                    extracted_automatically=memory.extracted_automatically,
                    confidence_score=memory.confidence_score
                )
                db.add(new_memory)
                stats["character_memories"] += 1
        
        # Plot Events
        events = db.query(PlotEvent).filter(
            and_(
                PlotEvent.branch_id == source_branch_id,
                PlotEvent.sequence_order <= fork_from_scene_sequence
            )
        ).all()
        
        for event in events:
            new_scene_id = scene_id_map.get(event.scene_id)
            new_chapter_id = chapter_id_map.get(event.chapter_id) if event.chapter_id else None
            new_resolution_scene_id = scene_id_map.get(event.resolution_scene_id) if event.resolution_scene_id else None
            
            if new_scene_id:
                # Generate new embedding_id for the clone
                new_embedding_id = f"{event.embedding_id}_branch_{new_branch_id}"
                
                new_event = PlotEvent(
                    story_id=story_id,
                    branch_id=new_branch_id,
                    scene_id=new_scene_id,
                    event_type=event.event_type,
                    description=event.description,
                    embedding_id=new_embedding_id,
                    thread_id=event.thread_id,
                    is_resolved=event.is_resolved,
                    resolution_scene_id=new_resolution_scene_id,
                    sequence_order=event.sequence_order,
                    chapter_id=new_chapter_id,
                    involved_characters=event.involved_characters,
                    extracted_automatically=event.extracted_automatically,
                    confidence_score=event.confidence_score,
                    importance_score=event.importance_score,
                    resolved_at=event.resolved_at
                )
                db.add(new_event)
                stats["plot_events"] += 1
        
        # Scene Embeddings
        embeddings = db.query(SceneEmbedding).filter(
            and_(
                SceneEmbedding.branch_id == source_branch_id,
                SceneEmbedding.sequence_order <= fork_from_scene_sequence
            )
        ).all()
        
        for embedding in embeddings:
            new_scene_id = scene_id_map.get(embedding.scene_id)
            new_variant_id = scene_variant_id_map.get(embedding.variant_id)
            new_chapter_id = chapter_id_map.get(embedding.chapter_id) if embedding.chapter_id else None
            
            if new_scene_id and new_variant_id:
                # Generate new embedding_id for the clone
                new_embedding_id = f"{embedding.embedding_id}_branch_{new_branch_id}"
                
                new_embedding = SceneEmbedding(
                    story_id=story_id,
                    branch_id=new_branch_id,
                    scene_id=new_scene_id,
                    variant_id=new_variant_id,
                    embedding_id=new_embedding_id,
                    content_hash=embedding.content_hash,
                    sequence_order=embedding.sequence_order,
                    chapter_id=new_chapter_id,
                    embedding_version=embedding.embedding_version,
                    content_length=embedding.content_length
                )
                db.add(new_embedding)
                stats["scene_embeddings"] += 1
        
        # 8. Clone ChapterSummaryBatches
        for old_chapter_id, new_chapter_id in chapter_id_map.items():
            batches = db.query(ChapterSummaryBatch).filter(
                and_(
                    ChapterSummaryBatch.chapter_id == old_chapter_id,
                    ChapterSummaryBatch.end_scene_sequence <= fork_from_scene_sequence
                )
            ).all()
            
            for batch in batches:
                new_batch = ChapterSummaryBatch(
                    chapter_id=new_chapter_id,
                    start_scene_sequence=batch.start_scene_sequence,
                    end_scene_sequence=batch.end_scene_sequence,
                    summary=batch.summary
                )
                db.add(new_batch)
                stats["chapter_summary_batches"] += 1
        
        # Update chapter scene counts
        for old_chapter_id, new_chapter_id in chapter_id_map.items():
            scene_count = db.query(Scene).filter(Scene.chapter_id == new_chapter_id).count()
            chapter = db.query(Chapter).filter(Chapter.id == new_chapter_id).first()
            if chapter:
                chapter.scenes_count = scene_count
        
        # Commit all changes
        db.commit()
        
        # Activate the new branch if requested
        if activate:
            self.set_active_branch(db, story_id, new_branch_id)
        
        logger.info(f"Created branch '{name}' (id={new_branch_id}) with stats: {stats}")
        
        return new_branch, stats
    
    def delete_branch(self, db: Session, branch_id: int) -> bool:
        """
        Delete a branch.
        
        Cannot delete the main branch or the only remaining branch.
        If deleting the active branch, switches to another branch first.
        
        Args:
            db: Database session
            branch_id: Branch ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        branch = db.query(StoryBranch).filter(StoryBranch.id == branch_id).first()
        
        if not branch:
            logger.warning(f"Branch {branch_id} not found")
            return False
        
        # Cannot delete main branch
        if branch.is_main:
            logger.warning(f"Cannot delete main branch {branch_id}")
            return False
        
        story_id = branch.story_id
        
        # Check if this is the only branch
        branch_count = db.query(StoryBranch).filter(
            StoryBranch.story_id == story_id
        ).count()
        
        if branch_count <= 1:
            logger.warning(f"Cannot delete the only remaining branch {branch_id}")
            return False
        
        # If this is the active branch, switch to main branch
        if branch.is_active:
            main_branch = db.query(StoryBranch).filter(
                and_(
                    StoryBranch.story_id == story_id,
                    StoryBranch.is_main == True
                )
            ).first()
            
            if main_branch:
                self.set_active_branch(db, story_id, main_branch.id)
        
        # Delete the branch (cascades will handle related records)
        db.delete(branch)
        db.commit()
        
        logger.info(f"Deleted branch {branch_id} from story {story_id}")
        return True
    
    def rename_branch(self, db: Session, branch_id: int, new_name: str, new_description: Optional[str] = None) -> bool:
        """
        Rename a branch.
        
        Args:
            db: Database session
            branch_id: Branch ID
            new_name: New name for the branch
            new_description: Optional new description
            
        Returns:
            True if successful, False otherwise
        """
        branch = db.query(StoryBranch).filter(StoryBranch.id == branch_id).first()
        
        if not branch:
            logger.warning(f"Branch {branch_id} not found")
            return False
        
        branch.name = new_name
        if new_description is not None:
            branch.description = new_description
        
        db.commit()
        
        logger.info(f"Renamed branch {branch_id} to '{new_name}'")
        return True
    
    def ensure_main_branch(self, db: Session, story_id: int) -> StoryBranch:
        """
        Ensure a story has a main branch. Creates one if it doesn't exist.
        
        This is useful for stories created before the branching feature.
        
        Args:
            db: Database session
            story_id: Story ID
            
        Returns:
            The main StoryBranch
        """
        main_branch = db.query(StoryBranch).filter(
            and_(
                StoryBranch.story_id == story_id,
                StoryBranch.is_main == True
            )
        ).first()
        
        if main_branch:
            return main_branch
        
        # Create main branch
        main_branch = StoryBranch(
            story_id=story_id,
            name="Main",
            is_main=True,
            is_active=True
        )
        db.add(main_branch)
        db.flush()
        
        # Update all existing records to use this branch
        branch_id = main_branch.id
        
        # Update all story-related tables
        db.query(Scene).filter(
            and_(Scene.story_id == story_id, Scene.branch_id == None)
        ).update({"branch_id": branch_id})
        
        db.query(Chapter).filter(
            and_(Chapter.story_id == story_id, Chapter.branch_id == None)
        ).update({"branch_id": branch_id})
        
        db.query(StoryCharacter).filter(
            and_(StoryCharacter.story_id == story_id, StoryCharacter.branch_id == None)
        ).update({"branch_id": branch_id})
        
        db.query(StoryFlow).filter(
            and_(StoryFlow.story_id == story_id, StoryFlow.branch_id == None)
        ).update({"branch_id": branch_id})
        
        db.query(CharacterState).filter(
            and_(CharacterState.story_id == story_id, CharacterState.branch_id == None)
        ).update({"branch_id": branch_id})
        
        db.query(LocationState).filter(
            and_(LocationState.story_id == story_id, LocationState.branch_id == None)
        ).update({"branch_id": branch_id})
        
        db.query(ObjectState).filter(
            and_(ObjectState.story_id == story_id, ObjectState.branch_id == None)
        ).update({"branch_id": branch_id})
        
        db.query(EntityStateBatch).filter(
            and_(EntityStateBatch.story_id == story_id, EntityStateBatch.branch_id == None)
        ).update({"branch_id": branch_id})
        
        db.query(NPCMention).filter(
            and_(NPCMention.story_id == story_id, NPCMention.branch_id == None)
        ).update({"branch_id": branch_id})
        
        db.query(NPCTracking).filter(
            and_(NPCTracking.story_id == story_id, NPCTracking.branch_id == None)
        ).update({"branch_id": branch_id})
        
        db.query(NPCTrackingSnapshot).filter(
            and_(NPCTrackingSnapshot.story_id == story_id, NPCTrackingSnapshot.branch_id == None)
        ).update({"branch_id": branch_id})
        
        db.query(CharacterMemory).filter(
            and_(CharacterMemory.story_id == story_id, CharacterMemory.branch_id == None)
        ).update({"branch_id": branch_id})
        
        db.query(PlotEvent).filter(
            and_(PlotEvent.story_id == story_id, PlotEvent.branch_id == None)
        ).update({"branch_id": branch_id})
        
        db.query(SceneEmbedding).filter(
            and_(SceneEmbedding.story_id == story_id, SceneEmbedding.branch_id == None)
        ).update({"branch_id": branch_id})
        
        db.commit()
        
        logger.info(f"Created main branch for story {story_id}")
        return main_branch


# Singleton instance
branch_service = BranchService()


def get_branch_service() -> BranchService:
    """Get the branch service singleton."""
    return branch_service

