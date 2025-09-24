"""
Service for managing scene variants and story flows
"""

from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from ..models import Scene, SceneVariant, StoryFlow, SceneChoice, Story
from ..services.llm_service import llm_service
from ..services.context_manager import ContextManager
import logging

logger = logging.getLogger(__name__)

class SceneVariantService:
    """Service for managing scene variants and regenerations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_scene_with_variant(
        self, 
        story_id: int, 
        sequence_number: int, 
        content: str,
        title: str = None,
        custom_prompt: str = None,
        choices: List[Dict[str, Any]] = None
    ) -> Tuple[Scene, SceneVariant]:
        """Create a new scene with its first variant"""
        
        # Create the logical scene
        scene = Scene(
            story_id=story_id,
            sequence_number=sequence_number,
            title=title or f"Scene {sequence_number}",
        )
        self.db.add(scene)
        self.db.flush()  # Get the scene ID
        
        # Create the first variant
        variant = SceneVariant(
            scene_id=scene.id,
            variant_number=1,
            is_original=True,
            content=content,
            title=title,
            original_content=content,
            generation_prompt=custom_prompt,
            generation_method="auto"
        )
        self.db.add(variant)
        self.db.flush()  # Get the variant ID
        
        # Create choices for this variant
        if choices:
            for i, choice_data in enumerate(choices):
                # Handle both string and dict formats for backward compatibility
                if isinstance(choice_data, str):
                    choice_text = choice_data
                    choice_description = None
                    predicted_outcomes = {}
                else:
                    choice_text = choice_data.get('text', '')
                    choice_description = choice_data.get('description')
                    predicted_outcomes = choice_data.get('outcomes', {})
                
                choice = SceneChoice(
                    scene_id=scene.id,
                    scene_variant_id=variant.id,
                    choice_text=choice_text,
                    choice_order=i + 1,
                    choice_description=choice_description,
                    predicted_outcomes=predicted_outcomes,
                )
                self.db.add(choice)
        
        # Create or update the story flow
        self._update_story_flow(story_id, sequence_number, scene.id, variant.id)
        
        self.db.commit()
        logger.info(f"Successfully created scene {scene.id} with variant {variant.id} at sequence {sequence_number}")
        return scene, variant
    
    async def regenerate_scene_variant(
        self, 
        scene_id: int, 
        custom_prompt: str = None,
        user_settings: dict = None
    ) -> SceneVariant:
        """Create a new variant for an existing scene"""
        
        scene = self.db.query(Scene).filter(Scene.id == scene_id).first()
        if not scene:
            raise ValueError(f"Scene {scene_id} not found")
        
        # Get the next variant number
        max_variant = self.db.query(SceneVariant.variant_number)\
            .filter(SceneVariant.scene_id == scene_id)\
            .order_by(desc(SceneVariant.variant_number))\
            .first()
        
        next_variant_number = (max_variant[0] if max_variant else 0) + 1
        
        # Generate new content using LLM
        context_manager = ContextManager(user_settings=user_settings)
        scene_context = await context_manager.build_scene_generation_context(
            scene.story_id, self.db, custom_prompt or ""
        )
        
        new_content = await llm_service.generate_scene_with_context_management(
            scene_context, user_settings
        )
        
        # Create the new variant
        new_variant = SceneVariant(
            scene_id=scene_id,
            variant_number=next_variant_number,
            is_original=False,
            content=new_content,
            title=scene.title,
            original_content=new_content,
            generation_prompt=custom_prompt,
            generation_method="regenerate" if not custom_prompt else "custom"
        )
        self.db.add(new_variant)
        self.db.flush()
        
        # Generate choices for the new variant
        choices_context = await context_manager.build_choice_generation_context(
            scene.story_id, self.db
        )
        choices_raw = await llm_service.generate_choices(choices_context, user_settings)
        
        # Handle different choice formats from LLM service
        if isinstance(choices_raw, list):
            # Direct list of strings
            choices_list = choices_raw
        elif isinstance(choices_raw, dict) and 'choices' in choices_raw:
            # Dictionary with 'choices' key
            choices_list = choices_raw['choices']
        else:
            choices_list = []
        
        # Create choices for the new variant
        for i, choice_data in enumerate(choices_list):
            # Handle both string and dict formats
            if isinstance(choice_data, str):
                choice_text = choice_data
                choice_description = None
                predicted_outcomes = {}
            else:
                choice_text = choice_data.get('text', '')
                choice_description = choice_data.get('description')
                predicted_outcomes = choice_data.get('outcomes', {})
            
            choice = SceneChoice(
                scene_id=scene_id,
                scene_variant_id=new_variant.id,
                choice_text=choice_text,
                choice_order=i + 1,
                choice_description=choice_description,
                predicted_outcomes=predicted_outcomes,
            )
            self.db.add(choice)
        
        # Update story flow to use the new variant
        self._update_story_flow(scene.story_id, scene.sequence_number, scene_id, new_variant.id)
        
        self.db.commit()
        return new_variant
    
    def switch_to_variant(self, story_id: int, scene_id: int, variant_id: int) -> bool:
        """Switch the active story flow to use a different variant"""
        
        scene = self.db.query(Scene).filter(Scene.id == scene_id).first()
        variant = self.db.query(SceneVariant).filter(SceneVariant.id == variant_id).first()
        
        if not scene or not variant or variant.scene_id != scene_id:
            return False
        
        # Update the story flow
        self._update_story_flow(story_id, scene.sequence_number, scene_id, variant_id)
        self.db.commit()
        return True
    
    def get_scene_variants(self, scene_id: int) -> List[SceneVariant]:
        """Get all variants for a scene"""
        return self.db.query(SceneVariant)\
            .filter(SceneVariant.scene_id == scene_id)\
            .order_by(SceneVariant.variant_number)\
            .all()
    
    def get_active_story_flow(self, story_id: int) -> List[Dict[str, Any]]:
        """Get the current active flow through scene variants"""
        flows = self.db.query(StoryFlow)\
            .filter(and_(StoryFlow.story_id == story_id, StoryFlow.is_active == True))\
            .order_by(StoryFlow.sequence_number)\
            .all()
        
        result = []
        for flow in flows:
            variant = self.db.query(SceneVariant)\
                .filter(SceneVariant.id == flow.scene_variant_id)\
                .first()
            
            choices = self.db.query(SceneChoice)\
                .filter(SceneChoice.scene_variant_id == variant.id)\
                .order_by(SceneChoice.choice_order)\
                .all()
            
            result.append({
                'flow_id': flow.id,
                'scene_id': flow.scene_id,
                'sequence_number': flow.sequence_number,
                'variant': {
                    'id': variant.id,
                    'variant_number': variant.variant_number,
                    'content': variant.content,
                    'title': variant.title,
                    'is_original': variant.is_original,
                    'generation_method': variant.generation_method,
                    'user_rating': variant.user_rating,
                    'is_favorite': variant.is_favorite,
                },
                'choices': [
                    {
                        'id': choice.id,
                        'text': choice.choice_text,
                        'description': choice.choice_description,
                        'order': choice.choice_order,
                    }
                    for choice in choices
                ],
                'all_variants_count': self.db.query(SceneVariant)
                    .filter(SceneVariant.scene_id == flow.scene_id)
                    .count()
            })
        
        return result
    
    def delete_scenes_from_sequence(self, story_id: int, from_sequence: int) -> bool:
        """Delete all scenes from a given sequence number onwards"""
        
        # Mark scenes as deleted (soft delete)
        scenes_to_delete = self.db.query(Scene)\
            .filter(and_(
                Scene.story_id == story_id,
                Scene.sequence_number >= from_sequence
            ))\
            .all()
        
        for scene in scenes_to_delete:
            scene.is_deleted = True
        
        # Remove from active story flow
        self.db.query(StoryFlow)\
            .filter(and_(
                StoryFlow.story_id == story_id,
                StoryFlow.sequence_number >= from_sequence,
                StoryFlow.is_active == True
            ))\
            .update({'is_active': False})
        
        self.db.commit()
        return True
    
    def _update_story_flow(self, story_id: int, sequence_number: int, scene_id: int, variant_id: int):
        """Update or create story flow entry"""
        
        # Deactivate any existing flow for this sequence
        updated_count = self.db.query(StoryFlow)\
            .filter(and_(
                StoryFlow.story_id == story_id,
                StoryFlow.sequence_number == sequence_number,
                StoryFlow.is_active == True
            ))\
            .update({'is_active': False})
        
        logger.info(f"Deactivated {updated_count} existing flows for story {story_id}, sequence {sequence_number}")
        
        # Create new active flow entry
        flow = StoryFlow(
            story_id=story_id,
            sequence_number=sequence_number,
            scene_id=scene_id,
            scene_variant_id=variant_id,
            is_active=True
        )
        self.db.add(flow)
        self.db.flush()  # Get the flow ID
        logger.info(f"Created new story flow {flow.id}: story {story_id}, sequence {sequence_number}, scene {scene_id}, variant {variant_id}")

    def get_active_variant(self, scene_id: int) -> Optional[SceneVariant]:
        """Get the currently active variant for a scene"""
        # Find the active story flow for this scene
        active_flow = self.db.query(StoryFlow)\
            .filter(and_(
                StoryFlow.scene_id == scene_id,
                StoryFlow.is_active == True
            ))\
            .first()
        
        if active_flow:
            # Return the variant specified in the flow
            return self.db.query(SceneVariant)\
                .filter(SceneVariant.id == active_flow.scene_variant_id)\
                .first()
        else:
            # Fallback to the original variant if no flow is found
            return self.db.query(SceneVariant)\
                .filter(and_(
                    SceneVariant.scene_id == scene_id,
                    SceneVariant.is_original == True
                ))\
                .first()


# Async wrapper for the service
async def get_scene_variant_service(db: Session) -> SceneVariantService:
    """Get an instance of the scene variant service"""
    return SceneVariantService(db)