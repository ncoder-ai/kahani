"""
Branch Service

Manages story branches including creation, switching, forking (deep cloning),
and deletion. Implements the "fork and clone" model where each branch is
a fully independent copy of story data.

Uses the BranchCloneRegistry and BranchCloner for automatic cloning of all
branch-aware data. See models/branch_aware.py for the registry configuration.
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
    CharacterMemory, PlotEvent, SceneEmbedding, ChapterSummaryBatch,
    CharacterInteraction, ChapterPlotProgressBatch
)
from .branch_cloner import BranchCloner

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

        # Use automatic branch cloner for all data cloning
        cloner = BranchCloner(
            db=db,
            story_id=story_id,
            source_branch_id=source_branch_id,
            new_branch_id=new_branch_id,
            fork_sequence=fork_from_scene_sequence
        )

        stats = cloner.clone_all()

        # Update chapter scene counts
        chapter_id_map = cloner.id_maps.get('chapter_id_map', {})
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

