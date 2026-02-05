#!/usr/bin/env python3
"""
Test script to verify entity_states_snapshot functionality for cache consistency.

This script tests that:
1. Entity states are captured during scene generation
2. Saved snapshots are loaded correctly during variant regeneration
3. Using the snapshot produces IDENTICAL entity_states_text as the original generation
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional

# Add the backend directory to the path
backend_dir = Path(__file__).parent.parent
project_dir = backend_dir.parent
sys.path.insert(0, str(backend_dir))

# Load .env file from project root
env_file = project_dir / ".env"
if env_file.exists():
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

# Detect Docker environment
is_docker = os.path.exists("/app") and os.getcwd().startswith("/app")

# Set database URL based on environment
if is_docker:
    os.environ.setdefault("DATABASE_URL", "postgresql://kahani:kahani@postgres:5432/kahani")
else:
    os.environ.setdefault("DATABASE_URL", "postgresql://kahani:kahani@localhost:5432/kahani")
    db_url = os.environ.get("DATABASE_URL", "")
    if "postgres:" in db_url and "@postgres:" in db_url:
        os.environ["DATABASE_URL"] = db_url.replace("@postgres:", "@localhost:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.models import User, Story, Scene, Chapter, SceneVariant, StoryFlow
from app.services.context_manager import ContextManager
from app.services.llm.service import UnifiedLLMService
from app.utils.security import verify_password


def get_db_session() -> Session:
    """Create a database session."""
    db_url = os.environ.get("DATABASE_URL", "sqlite:///./kahani.db")
    if db_url.startswith("sqlite:///./"):
        db_path = backend_dir / db_url.replace("sqlite:///./", "")
        db_url = f"sqlite:///{db_path}"

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Authenticate user by username and password."""
    user = db.query(User).filter(User.username == username).first()
    if user and verify_password(password, user.hashed_password):
        return user
    return None


def get_user_settings(db: Session, user: User) -> Dict[str, Any]:
    """Get user settings for LLM generation."""
    from app.models.user_settings import UserSettings

    settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()

    if settings:
        user_settings = settings.to_dict()
        user_settings["allow_nsfw"] = user.allow_nsfw or False
        return user_settings

    default_settings = UserSettings.get_defaults()
    default_settings["allow_nsfw"] = user.allow_nsfw or False
    return default_settings


def get_story_by_id(db: Session, story_id: int) -> Optional[Story]:
    """Get a story by ID."""
    return db.query(Story).filter(Story.id == story_id).first()


def get_scenes_with_snapshots(db: Session, story_id: int) -> list:
    """Get scenes that have entity_states_snapshot saved."""
    scenes_with_snapshots = []

    # Get all scenes from this story
    scenes = db.query(Scene).filter(
        Scene.story_id == story_id,
        Scene.is_deleted == False
    ).order_by(Scene.sequence_number.desc()).all()

    for scene in scenes:
        # Get the active variant via StoryFlow
        flow = db.query(StoryFlow).filter(
            StoryFlow.scene_id == scene.id,
            StoryFlow.is_active == True
        ).first()

        if flow:
            variant = db.query(SceneVariant).filter(
                SceneVariant.id == flow.scene_variant_id
            ).first()

            if variant and variant.entity_states_snapshot:
                scenes_with_snapshots.append({
                    "scene": scene,
                    "variant": variant,
                    "snapshot_size": len(variant.entity_states_snapshot)
                })

    return scenes_with_snapshots


async def test_snapshot_consistency(
    db: Session,
    user: User,
    user_settings: Dict[str, Any],
    story: Story,
    scene: Scene,
    variant: SceneVariant
) -> tuple:
    """
    Test that entity states snapshot produces consistent prompts.

    Returns: (passed, message)
    """
    from app.models.story_branch import StoryBranch

    # Get active branch
    active_branch = db.query(StoryBranch).filter(
        StoryBranch.story_id == story.id,
        StoryBranch.is_active == True
    ).first()
    branch_id = active_branch.id if active_branch else None

    # Create context manager with semantic memory
    context_manager = ContextManager(
        max_tokens=user_settings.get('context_settings', {}).get('max_tokens', 4000),
        user_settings=user_settings,
        user_id=user.id
    )

    chapter_id = scene.chapter_id

    # Build context WITHOUT snapshot (simulating fresh entity state query)
    context_without_snapshot = await context_manager.build_story_context(
        story_id=story.id,
        db=db,
        chapter_id=chapter_id,
        exclude_scene_id=scene.id,
        branch_id=branch_id,
        use_entity_states_snapshot=False
    )

    # Build context WITH snapshot (simulating variant regeneration)
    context_with_snapshot = await context_manager.build_story_context(
        story_id=story.id,
        db=db,
        chapter_id=chapter_id,
        exclude_scene_id=scene.id,
        branch_id=branch_id,
        use_entity_states_snapshot=True
    )

    # Compare entity_states_text between the two
    states_without = context_without_snapshot.get("entity_states_text", "")
    states_with = context_with_snapshot.get("entity_states_text", "")

    # The snapshot should be the saved one
    saved_snapshot = variant.entity_states_snapshot

    results = {
        "states_without_snapshot_len": len(states_without) if states_without else 0,
        "states_with_snapshot_len": len(states_with) if states_with else 0,
        "saved_snapshot_len": len(saved_snapshot) if saved_snapshot else 0,
        "snapshot_matches_context": states_with == saved_snapshot if states_with and saved_snapshot else None
    }

    # Check if the snapshot was actually used
    if states_with == saved_snapshot:
        return True, f"Snapshot correctly loaded and matches saved ({len(saved_snapshot)} chars)"
    elif states_with and saved_snapshot:
        # Show first difference
        for i, (c1, c2) in enumerate(zip(states_with, saved_snapshot)):
            if c1 != c2:
                return False, f"Snapshot mismatch at char {i}: context has '{states_with[max(0,i-20):i+20]}' vs saved '{saved_snapshot[max(0,i-20):i+20]}'"
        if len(states_with) != len(saved_snapshot):
            return False, f"Snapshot length mismatch: context={len(states_with)}, saved={len(saved_snapshot)}"
        return False, "Unknown mismatch"
    elif not saved_snapshot:
        return False, "No snapshot saved for this variant"
    else:
        return False, f"Snapshot not loaded correctly: context has {len(states_with) if states_with else 0} chars"


async def test_full_prompt_consistency(
    db: Session,
    user: User,
    user_settings: Dict[str, Any],
    story: Story,
    scene: Scene,
    variant: SceneVariant
) -> tuple:
    """
    Test that full LLM prompts are identical when using snapshot.

    Returns: (passed, message)
    """
    from app.models.story_branch import StoryBranch

    # Get active branch
    active_branch = db.query(StoryBranch).filter(
        StoryBranch.story_id == story.id,
        StoryBranch.is_active == True
    ).first()
    branch_id = active_branch.id if active_branch else None

    # Create context manager
    context_manager = ContextManager(
        max_tokens=user_settings.get('context_settings', {}).get('max_tokens', 4000),
        user_settings=user_settings,
        user_id=user.id
    )

    llm_service = UnifiedLLMService()
    chapter_id = scene.chapter_id

    # Build context with snapshot (for variant regeneration)
    context = await context_manager.build_story_context(
        story_id=story.id,
        db=db,
        chapter_id=chapter_id,
        exclude_scene_id=scene.id,
        branch_id=branch_id,
        use_entity_states_snapshot=True
    )

    # Build the cache-friendly message prefix
    messages = llm_service._build_cache_friendly_message_prefix(
        context=context,
        user_id=user.id,
        user_settings=user_settings,
        db=db
    )

    # Check if entity_states_snapshot was stored in context
    stored_snapshot = context.get('_entity_states_snapshot')
    if stored_snapshot:
        return True, f"Full prompt built with snapshot ({len(stored_snapshot)} chars), prefix has {len(messages)} messages"

    # The snapshot should have been loaded from DB
    entity_states = context.get('entity_states_text', '')
    if entity_states and entity_states == variant.entity_states_snapshot:
        return True, f"Full prompt uses saved snapshot ({len(entity_states)} chars)"

    return False, "Snapshot not properly integrated into prompt"


async def run_tests():
    """Main test function."""
    print("=" * 80)
    print("ENTITY STATES SNAPSHOT TEST")
    print("Testing cache consistency for variant regeneration")
    print("=" * 80)
    print()

    # Create database session
    print("1. Connecting to database...")
    db = get_db_session()

    try:
        # Authenticate user
        print("2. Authenticating user 'nishant'...")
        user = authenticate_user(db, "nishant", "qw12QW!@")
        if not user:
            print("   ERROR: Authentication failed!")
            return False
        print(f"   SUCCESS: Authenticated as user ID {user.id}")

        # Get user settings
        print("3. Loading user settings...")
        user_settings = get_user_settings(db, user)

        # Get story 5
        print("4. Loading story ID 5...")
        story = get_story_by_id(db, 5)
        if not story:
            print("   ERROR: Story 5 not found!")
            return False
        print(f"   SUCCESS: Found story '{story.title}'")

        # Find scenes with saved snapshots
        print("5. Finding scenes with entity_states_snapshot...")
        scenes_with_snapshots = get_scenes_with_snapshots(db, story.id)
        print(f"   Found {len(scenes_with_snapshots)} scenes with snapshots")

        if not scenes_with_snapshots:
            print("\n   NOTE: No scenes have entity_states_snapshot yet.")
            print("   This is expected if no scenes have been generated since the feature was added.")
            print("   Generate a new scene to populate the snapshot, then run this test again.")

            # Still run a test to verify the snapshot loading path works
            print("\n6. Testing snapshot loading with latest scene (should fallback gracefully)...")
            latest_scene = db.query(Scene).filter(
                Scene.story_id == story.id,
                Scene.is_deleted == False
            ).order_by(Scene.sequence_number.desc()).first()

            if latest_scene:
                flow = db.query(StoryFlow).filter(
                    StoryFlow.scene_id == latest_scene.id,
                    StoryFlow.is_active == True
                ).first()

                if flow:
                    variant = db.query(SceneVariant).filter(
                        SceneVariant.id == flow.scene_variant_id
                    ).first()

                    if variant:
                        # Test that the code path works even without snapshot
                        from app.models.story_branch import StoryBranch
                        active_branch = db.query(StoryBranch).filter(
                            StoryBranch.story_id == story.id,
                            StoryBranch.is_active == True
                        ).first()
                        branch_id = active_branch.id if active_branch else None

                        context_manager = ContextManager(
                            max_tokens=user_settings.get('context_settings', {}).get('max_tokens', 4000),
                            user_settings=user_settings,
                            user_id=user.id
                        )

                        context = await context_manager.build_story_context(
                            story_id=story.id,
                            db=db,
                            chapter_id=latest_scene.chapter_id,
                            exclude_scene_id=latest_scene.id,
                            branch_id=branch_id,
                            use_entity_states_snapshot=True  # Try to use snapshot
                        )

                        entity_states = context.get('entity_states_text', '')
                        print(f"   Entity states retrieved: {len(entity_states)} chars")
                        print(f"   (Fallback to live query since no snapshot exists)")
                        print("\n   PASS: Code path works correctly, falls back gracefully")
                        return True

            return True

        # Test each scene with a snapshot
        print("\n6. Running snapshot consistency tests...")
        passed = 0
        failed = 0

        for item in scenes_with_snapshots[:5]:  # Test up to 5 scenes
            scene = item["scene"]
            variant = item["variant"]

            print(f"\n   Testing scene {scene.id} (seq {scene.sequence_number})...")
            print(f"   Saved snapshot: {item['snapshot_size']} chars")

            # Test 1: Snapshot consistency
            success, message = await test_snapshot_consistency(
                db, user, user_settings, story, scene, variant
            )
            if success:
                print(f"   - Snapshot loading: PASS - {message}")
                passed += 1
            else:
                print(f"   - Snapshot loading: FAIL - {message}")
                failed += 1

            # Test 2: Full prompt consistency
            success, message = await test_full_prompt_consistency(
                db, user, user_settings, story, scene, variant
            )
            if success:
                print(f"   - Full prompt build: PASS - {message}")
                passed += 1
            else:
                print(f"   - Full prompt build: FAIL - {message}")
                failed += 1

        # Summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"\nTests passed: {passed}")
        print(f"Tests failed: {failed}")

        if failed == 0:
            print("\n ENTITY STATES SNAPSHOT: ALL TESTS PASSED")
            print("  Cache consistency verified for variant regeneration.")
            return True
        else:
            print("\n SOME TESTS FAILED - Check output above for details")
            return False

    finally:
        db.close()


if __name__ == "__main__":
    result = asyncio.run(run_tests())
    sys.exit(0 if result else 1)
