#!/usr/bin/env python3
"""
Test script for branch cloning verification.

Tests both the registry configuration and the actual cloning functionality.

Usage:
    cd backend
    python scripts/test_branch_cloning.py
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models import (
    Story, StoryBranch, Chapter, Scene, SceneVariant, SceneChoice, StoryFlow,
    Character, StoryCharacter, CharacterState, LocationState, ObjectState,
    EntityStateBatch, NPCMention, NPCTracking, NPCTrackingSnapshot,
    CharacterMemory, PlotEvent, SceneEmbedding, CharacterInteraction,
    ChapterSummaryBatch, ChapterPlotProgressBatch, BranchCloneRegistry,
    User
)
from app.services.branch_service import BranchService
import json
from datetime import datetime
import uuid


def test_registry_configuration():
    """Test that all branch-aware models are registered in the registry."""
    print("\n" + "=" * 60)
    print("TEST 1: Registry Configuration")
    print("=" * 60)

    registry = BranchCloneRegistry.get_all()
    print(f"\nRegistered tables: {len(registry)}")

    for table_name, config in sorted(registry.items(), key=lambda x: x[1].priority):
        print(f"  {config.priority:3d} - {table_name}")
        if config.depends_on:
            print(f"        depends_on: {config.depends_on}")
        if config.fk_remappings:
            print(f"        fk_remappings: {config.fk_remappings}")
        if config.creates_mapping:
            print(f"        creates_mapping: {config.creates_mapping}")
        if config.nested_models:
            print(f"        nested_models: {config.nested_models}")
        if config.iterate_via_mapping:
            print(f"        iterate_via_mapping: {config.iterate_via_mapping}")

    # Test clone order
    print("\nClone order:")
    clone_order = BranchCloneRegistry.get_clone_order()
    for i, table in enumerate(clone_order, 1):
        config = registry.get(table)
        priority = config.priority if config else "N/A"
        print(f"  {i:2d}. {table} (priority={priority})")

    # Validate registry
    print("\nValidating registry...")
    unregistered = BranchCloneRegistry.validate()
    if unregistered:
        print(f"WARNING: Unregistered tables with branch_id: {unregistered}")
        return False
    else:
        print("All branch_id tables are registered!")
        return True


def create_test_user(db: Session) -> User:
    """Create or get a test user."""
    user = db.query(User).filter(User.email == "test@example.com").first()
    if not user:
        user = User(
            email="test@example.com",
            hashed_password="test",
            username="test_user",
            is_active=True
        )
        db.add(user)
        db.flush()
    return user


def create_test_story(db: Session, user_id: int) -> dict:
    """Create a comprehensive test story with all entity types."""
    print("\nCreating test story with all entity types...")

    # 1. Create Story
    story = Story(
        title=f"Branch Clone Test Story - {datetime.now().strftime('%Y%m%d_%H%M%S')}",
        description="Test story for branch cloning verification",
        genre="Fantasy",
        tone="Adventure",
        world_setting="A magical kingdom with dragons",
        initial_premise="A young mage discovers a hidden power",
        story_mode="dynamic",
        status="active",
        owner_id=user_id
    )
    db.add(story)
    db.flush()
    print(f"  Created story: {story.id}")

    # 2. Create Main Branch
    main_branch = StoryBranch(
        story_id=story.id,
        name="Main Branch",
        is_main=True,
        is_active=True
    )
    db.add(main_branch)
    db.flush()
    story.current_branch_id = main_branch.id
    print(f"  Created main branch: {main_branch.id}")

    # 3. Create Characters
    characters = []
    char_names = ["Elena (Protagonist)", "Marcus (Mentor)", "Shadow Dragon"]
    for name in char_names:
        char = Character(
            name=name,
            description=f"Test character: {name}",
            personality_traits=["brave", "curious"],
            background="Born in the magical realm",
            is_template=True,
            creator_id=user_id
        )
        db.add(char)
        db.flush()
        characters.append(char)
    print(f"  Created {len(characters)} characters")

    # 4. Create StoryCharacters
    story_characters = []
    for char in characters:
        sc = StoryCharacter(
            story_id=story.id,
            character_id=char.id,
            branch_id=main_branch.id,
            role="main" if "Protagonist" in char.name else "supporting"
        )
        db.add(sc)
        db.flush()
        story_characters.append(sc)
    print(f"  Created {len(story_characters)} story characters")

    # 5. Create Chapter
    chapter = Chapter(
        story_id=story.id,
        branch_id=main_branch.id,
        chapter_number=1,
        title="The Awakening",
        status="active",
        scenes_count=5
    )
    db.add(chapter)
    db.flush()
    print(f"  Created chapter: {chapter.id}")

    # 6. Create 5 Scenes with Variants and Choices
    scenes = []
    scene_variants = []
    scene_choices_list = []

    scene_contents = [
        "Elena stood at the edge of the ancient forest, her heart racing...",
        "Marcus appeared from the shadows, his staff glowing with blue light...",
        "Deep within the cave, they found the dragon's lair...",
        "The Shadow Dragon awakened, its eyes burning with ancient fire...",
        "Elena raised her hand, feeling the magic surge through her veins..."
    ]

    for seq, content in enumerate(scene_contents, 1):
        scene = Scene(
            story_id=story.id,
            branch_id=main_branch.id,
            chapter_id=chapter.id,
            sequence_number=seq,
            title=f"Scene {seq}",
            scene_type="narrative",
            parent_scene_id=scenes[-1].id if scenes else None
        )
        db.add(scene)
        db.flush()
        scenes.append(scene)

        # Create variant
        variant = SceneVariant(
            scene_id=scene.id,
            content=content,
            variant_number=1,
            is_original=True,
        )
        db.add(variant)
        db.flush()
        scene_variants.append(variant)

        # Create choices
        for choice_num in range(1, 3):
            choice = SceneChoice(
                scene_id=scene.id,
                branch_id=main_branch.id,
                scene_variant_id=variant.id,
                choice_text=f"Choice {choice_num} for scene {seq}",
                choice_order=choice_num,
                leads_to_scene_id=scenes[-2].id if len(scenes) > 1 and choice_num == 2 else None
            )
            db.add(choice)
            db.flush()
            scene_choices_list.append(choice)

    print(f"  Created {len(scenes)} scenes, {len(scene_variants)} variants, {len(scene_choices_list)} choices")

    # 7. Create StoryFlow entries
    for scene, variant in zip(scenes, scene_variants):
        flow = StoryFlow(
            story_id=story.id,
            branch_id=main_branch.id,
            sequence_number=scene.sequence_number,
            scene_id=scene.id,
            scene_variant_id=variant.id,
            is_active=True
        )
        db.add(flow)
    db.flush()
    print(f"  Created {len(scenes)} story flows")

    # 8. Create CharacterStates
    for sc in story_characters:
        state = CharacterState(
            story_id=story.id,
            branch_id=main_branch.id,
            character_id=sc.character_id,
            current_location="Ancient Forest",
            emotional_state="determined",
            knowledge=json.dumps(["magic exists", "dragons are real"]),
            last_updated_scene=3
        )
        db.add(state)
    db.flush()
    print(f"  Created {len(story_characters)} character states")

    # 9. Create LocationStates
    locations = ["Ancient Forest", "Dragon's Cave", "Mountain Peak"]
    for loc in locations:
        loc_state = LocationState(
            story_id=story.id,
            branch_id=main_branch.id,
            location_name=loc,
            condition=f"A mysterious {loc.lower()}",
            last_updated_scene=2
        )
        db.add(loc_state)
    db.flush()
    print(f"  Created {len(locations)} location states")

    # 10. Create ObjectStates
    objects = ["Magic Staff", "Dragon Scale", "Ancient Map"]
    for obj in objects:
        obj_state = ObjectState(
            story_id=story.id,
            branch_id=main_branch.id,
            object_name=obj,
            condition=f"A {obj.lower()} of great power",
            current_owner_id=characters[0].id,
            last_updated_scene=3
        )
        db.add(obj_state)
    db.flush()
    print(f"  Created {len(objects)} object states")

    # 11. Create EntityStateBatch
    batch = EntityStateBatch(
        story_id=story.id,
        branch_id=main_branch.id,
        start_scene_sequence=1,
        end_scene_sequence=3,
        character_states_snapshot=json.dumps({}),
        location_states_snapshot=json.dumps({}),
        object_states_snapshot=json.dumps({})
    )
    db.add(batch)
    db.flush()
    print("  Created 1 entity state batch")

    # 12. Create NPCMentions and NPCTracking
    npc_names = ["Village Elder", "Mysterious Stranger"]
    for npc_name in npc_names:
        # NPC Tracking
        tracking = NPCTracking(
            story_id=story.id,
            branch_id=main_branch.id,
            character_name=npc_name,
            first_appearance_scene=1,
            last_appearance_scene=3,
            total_mentions=5,
            importance_score=0.7,
        )
        db.add(tracking)
        db.flush()

        # NPC Mentions
        for scene in scenes[:3]:
            mention = NPCMention(
                story_id=story.id,
                branch_id=main_branch.id,
                scene_id=scene.id,
                character_name=npc_name,
                sequence_number=scene.sequence_number,
            )
            db.add(mention)

        # NPC Snapshot
        snapshot = NPCTrackingSnapshot(
            story_id=story.id,
            branch_id=main_branch.id,
            scene_id=scenes[2].id,
            scene_sequence=3,
            snapshot_data=json.dumps({"npcs": [npc_name]})
        )
        db.add(snapshot)
    db.flush()
    print(f"  Created {len(npc_names)} NPC tracking records, mentions, and snapshots")

    # 13. Create CharacterMemories
    for i, scene in enumerate(scenes[:3]):
        memory = CharacterMemory(
            story_id=story.id,
            branch_id=main_branch.id,
            scene_id=scene.id,
            chapter_id=chapter.id,
            character_id=characters[0].id,
            sequence_order=scene.sequence_number,
            moment_type="action",
            content=f"Memory from scene {scene.sequence_number}",
            embedding_id=f"mem_{story.id}_{scene.id}_{uuid.uuid4().hex[:8]}"
        )
        db.add(memory)
    db.flush()
    print("  Created 3 character memories")

    # 14. Create PlotEvents
    for i, scene in enumerate(scenes[:3]):
        event = PlotEvent(
            story_id=story.id,
            branch_id=main_branch.id,
            scene_id=scene.id,
            chapter_id=chapter.id,
            sequence_order=scene.sequence_number,
            event_type="introduction",
            description=f"Plot event at scene {scene.sequence_number}",
            embedding_id=f"plot_{story.id}_{scene.id}_{uuid.uuid4().hex[:8]}"
        )
        db.add(event)
    db.flush()
    print("  Created 3 plot events")

    # 15. Create SceneEmbeddings
    for scene, variant in zip(scenes, scene_variants):
        embedding = SceneEmbedding(
            story_id=story.id,
            branch_id=main_branch.id,
            scene_id=scene.id,
            variant_id=variant.id,
            chapter_id=chapter.id,
            sequence_order=scene.sequence_number,
            content_hash=f"hash_{scene.id}",
            embedding_id=f"emb_{story.id}_{scene.id}_{uuid.uuid4().hex[:8]}",
            content_length=len(variant.content)
        )
        db.add(embedding)
    db.flush()
    print(f"  Created {len(scenes)} scene embeddings")

    # 16. Create ChapterSummaryBatch
    summary_batch = ChapterSummaryBatch(
        chapter_id=chapter.id,
        start_scene_sequence=1,
        end_scene_sequence=3,
        summary="The heroes begin their journey..."
    )
    db.add(summary_batch)
    db.flush()
    print("  Created 1 chapter summary batch")

    # 17. Create ChapterPlotProgressBatch
    plot_batch = ChapterPlotProgressBatch(
        chapter_id=chapter.id,
        start_scene_sequence=1,
        end_scene_sequence=3,
        completed_events=json.dumps(["Main quest", "Character development"])
    )
    db.add(plot_batch)
    db.flush()
    print("  Created 1 chapter plot progress batch")

    # 18. Create CharacterInteractions
    interaction = CharacterInteraction(
        story_id=story.id,
        branch_id=main_branch.id,
        character_a_id=characters[0].id,
        character_b_id=characters[1].id,
        interaction_type="mentorship",
        first_occurrence_scene=1,
    )
    db.add(interaction)

    db.commit()
    print("  Committed all test data")

    return {
        "story_id": story.id,
        "branch_id": main_branch.id,
        "chapter_id": chapter.id,
        "scene_ids": [s.id for s in scenes],
        "character_ids": [c.id for c in characters],
        "story_character_ids": [sc.id for sc in story_characters]
    }


def count_branch_entities(db: Session, story_id: int, branch_id: int) -> dict:
    """Count all entities for a specific branch."""
    counts = {
        "chapters": db.query(Chapter).filter_by(story_id=story_id, branch_id=branch_id).count(),
        "scenes": db.query(Scene).filter_by(story_id=story_id, branch_id=branch_id).count(),
        "scene_choices": db.query(SceneChoice).filter_by(branch_id=branch_id).count(),
        "story_characters": db.query(StoryCharacter).filter_by(story_id=story_id, branch_id=branch_id).count(),
        "story_flows": db.query(StoryFlow).filter_by(story_id=story_id, branch_id=branch_id).count(),
        "character_states": db.query(CharacterState).filter_by(story_id=story_id, branch_id=branch_id).count(),
        "location_states": db.query(LocationState).filter_by(story_id=story_id, branch_id=branch_id).count(),
        "object_states": db.query(ObjectState).filter_by(story_id=story_id, branch_id=branch_id).count(),
        "entity_state_batches": db.query(EntityStateBatch).filter_by(story_id=story_id, branch_id=branch_id).count(),
        "npc_mentions": db.query(NPCMention).filter_by(story_id=story_id, branch_id=branch_id).count(),
        "npc_tracking": db.query(NPCTracking).filter_by(story_id=story_id, branch_id=branch_id).count(),
        "npc_tracking_snapshots": db.query(NPCTrackingSnapshot).filter_by(story_id=story_id, branch_id=branch_id).count(),
        "character_memories": db.query(CharacterMemory).filter_by(story_id=story_id, branch_id=branch_id).count(),
        "plot_events": db.query(PlotEvent).filter_by(story_id=story_id, branch_id=branch_id).count(),
        "scene_embeddings": db.query(SceneEmbedding).filter_by(story_id=story_id, branch_id=branch_id).count(),
        "character_interactions": db.query(CharacterInteraction).filter_by(story_id=story_id, branch_id=branch_id).count(),
    }
    return counts


def test_branch_cloning(db: Session, test_data: dict) -> bool:
    """Test branch cloning functionality."""
    print("\n" + "=" * 60)
    print("TEST 2: Branch Cloning")
    print("=" * 60)

    story_id = test_data['story_id']
    main_branch_id = test_data['branch_id']

    # Count entities in main branch
    print("\nCounting entities in main branch...")
    main_counts = count_branch_entities(db, story_id, main_branch_id)
    for entity, count in sorted(main_counts.items()):
        print(f"  {entity}: {count}")

    # Create a new branch (fork at scene 3)
    print("\nCreating new branch (forking at scene 3)...")
    branch_service = BranchService()
    new_branch, stats = branch_service.create_branch(
        db=db,
        story_id=story_id,
        name="Test Fork Branch",
        description="Branch created for testing",
        fork_from_scene_sequence=3,
        activate=False
    )
    print(f"  New Branch ID: {new_branch.id}")
    print(f"  Clone stats: {stats}")

    # Count entities in new branch
    print("\nCounting entities in new branch...")
    new_counts = count_branch_entities(db, story_id, new_branch.id)
    for entity, count in sorted(new_counts.items()):
        print(f"  {entity}: {count}")

    # Verify counts
    print("\nVerification Results:")
    print("-" * 40)
    all_passed = True

    # Expected: scenes should be 3 (fork at scene 3), characters should be all 3
    expected = {
        "chapters": 1,  # Only chapter 1
        "scenes": 3,  # Scenes 1-3
        "story_characters": 3,  # All characters
        "story_flows": 3,  # Flows for scenes 1-3
    }

    for entity, main_count in sorted(main_counts.items()):
        new_count = new_counts[entity]

        # For most entities, new branch should have fewer or equal records
        if entity in expected:
            expected_count = expected[entity]
            if new_count == expected_count:
                status = "PASS"
            else:
                status = f"FAIL (expected {expected_count})"
                all_passed = False
        elif new_count <= main_count:
            status = "PASS" if new_count > 0 else "SKIP (no data)"
        else:
            status = "FAIL"
            all_passed = False

        print(f"  {entity}: main={main_count}, new={new_count} - {status}")

    return all_passed


def cleanup_test_data(db: Session, story_id: int):
    """Clean up test data."""
    print("\nCleaning up test data...")
    story = db.query(Story).filter(Story.id == story_id).first()
    if story:
        db.delete(story)
        db.commit()
        print(f"  Deleted story {story_id} and all related data")


def main():
    """Run all tests."""
    print("=" * 60)
    print("BRANCH CLONING REGISTRY TEST")
    print("=" * 60)

    db = SessionLocal()
    test_data = None

    try:
        # Test 1: Registry configuration
        registry_ok = test_registry_configuration()

        if not registry_ok:
            print("\nRegistry configuration test failed. Exiting.")
            return 1

        # Test 2: Create test data and test cloning
        user = create_test_user(db)
        test_data = create_test_story(db, user.id)
        cloning_ok = test_branch_cloning(db, test_data)

        print("\n" + "=" * 60)
        if registry_ok and cloning_ok:
            print("ALL TESTS PASSED")
            result = 0
        else:
            print("SOME TESTS FAILED")
            result = 1
        print("=" * 60)

        return result

    except Exception as e:
        print(f"\nError during testing: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # Clean up
        if test_data:
            cleanup_test_data(db, test_data['story_id'])
        db.close()


if __name__ == "__main__":
    sys.exit(main())
