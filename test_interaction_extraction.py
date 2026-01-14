#!/usr/bin/env python3
"""
Test script for retroactive interaction extraction.

Usage:
    python test_interaction_extraction.py <story_id> [--extract] [--view]

Examples:
    # View current interactions for story 5
    python test_interaction_extraction.py 5 --view
    
    # Run extraction for story 5
    python test_interaction_extraction.py 5 --extract
    
    # Both extract and view
    python test_interaction_extraction.py 5 --extract --view
"""

import sys
import os
import asyncio

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def get_db_url():
    """Get database URL from environment or default."""
    return os.environ.get(
        'DATABASE_URL',
        'postgresql://kahani:kahani@localhost:5432/kahani'
    )


def view_interactions(story_id: int):
    """View current interaction history for a story."""
    from app.models import Story, CharacterInteraction, Character
    
    engine = create_engine(get_db_url())
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            print(f"Story {story_id} not found")
            return
        
        print(f"\n{'='*60}")
        print(f"Story: {story.title} (ID: {story_id})")
        print(f"{'='*60}")
        
        print(f"\nConfigured Interaction Types:")
        for t in (story.interaction_types or []):
            print(f"  - {t}")
        
        # Get interactions
        interactions = db.query(CharacterInteraction).filter(
            CharacterInteraction.story_id == story_id
        ).order_by(CharacterInteraction.first_occurrence_scene).all()
        
        if not interactions:
            print(f"\nNo interactions recorded yet.")
        else:
            # Get character names
            char_ids = set()
            for i in interactions:
                char_ids.add(i.character_a_id)
                char_ids.add(i.character_b_id)
            
            characters = db.query(Character).filter(Character.id.in_(char_ids)).all()
            char_map = {c.id: c.name for c in characters}
            
            print(f"\nRecorded Interactions ({len(interactions)}):")
            for i in interactions:
                char_a = char_map.get(i.character_a_id, "Unknown")
                char_b = char_map.get(i.character_b_id, "Unknown")
                print(f"  Scene {i.first_occurrence_scene}: {i.interaction_type}")
                print(f"    {char_a} & {char_b}")
                if i.description:
                    print(f"    \"{i.description}\"")
        
        # Show what hasn't occurred
        configured = set(story.interaction_types or [])
        occurred = {i.interaction_type for i in interactions}
        not_occurred = configured - occurred
        
        if not_occurred:
            print(f"\nInteractions NOT YET occurred:")
            for t in sorted(not_occurred):
                print(f"  - {t}")
        
    finally:
        db.close()


async def run_extraction(story_id: int):
    """Run retroactive interaction extraction."""
    from app.models import Story, Scene, StoryFlow, Character, StoryCharacter, CharacterInteraction, StoryBranch
    from app.services.llm.service import UnifiedLLMService
    from sqlalchemy import or_
    import json
    
    engine = create_engine(get_db_url())
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            print(f"Story {story_id} not found")
            return
        
        if not story.interaction_types:
            print(f"No interaction types configured for story {story_id}")
            print("Configure them in Story Settings first.")
            return
        
        print(f"\n{'='*60}")
        print(f"Extracting interactions for: {story.title}")
        print(f"Interaction types: {story.interaction_types}")
        print(f"{'='*60}\n")
        
        # Get active branch
        active_branch = db.query(StoryBranch).filter(
            StoryBranch.story_id == story_id,
            StoryBranch.is_active == True
        ).first()
        branch_id = active_branch.id if active_branch else None
        
        # Get scenes
        scene_query = db.query(Scene).filter(Scene.story_id == story_id)
        if branch_id:
            scene_query = scene_query.filter(Scene.branch_id == branch_id)
        scenes = scene_query.order_by(Scene.sequence_number).all()
        
        print(f"Found {len(scenes)} scenes to process")
        
        # Build character mapping
        char_query = db.query(StoryCharacter).filter(StoryCharacter.story_id == story_id)
        if branch_id:
            char_query = char_query.filter(or_(
                StoryCharacter.branch_id == branch_id,
                StoryCharacter.branch_id.is_(None)
            ))
        story_characters = char_query.all()
        
        character_name_to_id = {}
        character_names = []
        for sc in story_characters:
            char = db.query(Character).filter(Character.id == sc.character_id).first()
            if char:
                character_names.append(char.name)
                character_name_to_id[char.name.lower()] = char.id
        
        print(f"Characters: {', '.join(character_names)}")
        
        # Initialize LLM
        llm = UnifiedLLMService()
        
        # Get user settings from database (use user 1 as default)
        from app.models import UserSettings
        user_settings_record = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
        if user_settings_record:
            user_settings = user_settings_record.to_dict()
            print(f"Using LLM settings from user 1")
        else:
            user_settings = {
                'llm_settings': {
                    'max_tokens': 1024
                }
            }
            print("WARNING: No user settings found, using defaults")
        
        interactions_found = 0
        
        for scene in scenes:
            # Get scene content
            flow = db.query(StoryFlow).filter(
                StoryFlow.scene_id == scene.id,
                StoryFlow.is_active == True
            ).first()
            
            scene_content = flow.scene_variant.content if flow and flow.scene_variant else scene.content
            
            if not scene_content:
                continue
            
            print(f"\nProcessing scene {scene.sequence_number}...", end=" ", flush=True)
            
            # Build prompt
            prompt = f"""Analyze this scene and identify if ANY of these specific interactions occur for the FIRST TIME between characters.

INTERACTION TYPES TO DETECT: {json.dumps(story.interaction_types)}

CHARACTERS IN STORY: {', '.join(character_names)}

SCENE {scene.sequence_number}:
{scene_content[:2000]}{'...' if len(scene_content) > 2000 else ''}

If any of the listed interaction types occur EXPLICITLY in this scene (not just referenced or remembered), return them in this JSON format:
{{
  "interactions": [
    {{
      "interaction_type": "exact type from the list",
      "character_a": "first character name",
      "character_b": "second character name",
      "description": "brief factual description"
    }}
  ]
}}

If no tracked interactions occur, return: {{"interactions": []}}

IMPORTANT: Only report interactions that are SHOWN happening in this scene, not referenced from the past."""

            try:
                response = await llm.generate(
                    prompt=prompt,
                    user_id=1,
                    user_settings=user_settings,
                    system_prompt="You are a story analyst. Extract specific character interactions from scenes. Be precise and factual.",
                    max_tokens=1024
                )
                
                # Parse response
                response_clean = response.strip()
                if response_clean.startswith("```json"):
                    response_clean = response_clean[7:]
                if response_clean.startswith("```"):
                    response_clean = response_clean[3:]
                if response_clean.endswith("```"):
                    response_clean = response_clean[:-3]
                response_clean = response_clean.strip()
                
                result = json.loads(response_clean)
                
                scene_interactions = result.get("interactions", [])
                if not scene_interactions:
                    print("no interactions")
                    continue
                
                for interaction in scene_interactions:
                    interaction_type = interaction.get("interaction_type", "").strip().lower()
                    char_a_name = interaction.get("character_a", "").strip().lower()
                    char_b_name = interaction.get("character_b", "").strip().lower()
                    description = interaction.get("description", "")
                    
                    if not interaction_type or not char_a_name or not char_b_name:
                        continue
                    
                    char_a_id = character_name_to_id.get(char_a_name)
                    char_b_id = character_name_to_id.get(char_b_name)
                    
                    if not char_a_id or not char_b_id:
                        print(f"unknown chars: {char_a_name}, {char_b_name}")
                        continue
                    
                    # Normalize order
                    if char_a_id > char_b_id:
                        char_a_id, char_b_id = char_b_id, char_a_id
                    
                    # Check if exists
                    existing = db.query(CharacterInteraction).filter(
                        CharacterInteraction.story_id == story_id,
                        CharacterInteraction.character_a_id == char_a_id,
                        CharacterInteraction.character_b_id == char_b_id,
                        CharacterInteraction.interaction_type == interaction_type
                    ).first()
                    
                    if existing:
                        print(f"already recorded: {interaction_type}")
                    else:
                        new_interaction = CharacterInteraction(
                            story_id=story_id,
                            branch_id=branch_id,
                            character_a_id=char_a_id,
                            character_b_id=char_b_id,
                            interaction_type=interaction_type,
                            first_occurrence_scene=scene.sequence_number,
                            description=description
                        )
                        db.add(new_interaction)
                        db.flush()
                        interactions_found += 1
                        print(f"FOUND: {interaction_type}")
                
            except json.JSONDecodeError as e:
                print(f"parse error: {e}")
            except Exception as e:
                print(f"error: {e}")
        
        db.commit()
        print(f"\n{'='*60}")
        print(f"Extraction complete! Found {interactions_found} new interactions.")
        print(f"{'='*60}")
        
    finally:
        db.close()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Test interaction extraction')
    parser.add_argument('story_id', type=int, help='Story ID to process')
    parser.add_argument('--extract', action='store_true', help='Run extraction')
    parser.add_argument('--view', action='store_true', help='View current interactions')
    
    args = parser.parse_args()
    
    if not args.extract and not args.view:
        args.view = True  # Default to view
    
    if args.extract:
        asyncio.run(run_extraction(args.story_id))
    
    if args.view:
        view_interactions(args.story_id)


if __name__ == '__main__':
    main()

