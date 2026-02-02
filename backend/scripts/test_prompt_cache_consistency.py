#!/usr/bin/env python3
"""
Test script to verify prompt cache consistency across all generation types.

This script tests:
1. Scene generation
2. Variant generation (simple) - uses IDENTICAL prompt as scene
3. Variant generation (guided) - uses SAME PREFIX as scene, different task
4. Choice generation - uses SAME PREFIX as scene, different task
5. Summary generation - uses SAME PREFIX as scene, different task
6. Chapter conclusion - uses SAME PREFIX as scene, different task
7. Continue generation - uses SAME PREFIX as scene, different task

All generation types that share the same context should have identical message prefixes
for maximum cache utilization.

Tests performed:
- Test 1: Scene vs Simple Variant (FULL MESSAGE should be IDENTICAL)
- Test 2: Scene PREFIX vs Guided Variant PREFIX
- Test 3: Scene PREFIX vs Choice PREFIX
- Test 4: Simple Variant PREFIX vs Guided Variant PREFIX
- Test 5: Scene PREFIX vs Summary PREFIX
- Test 6: Scene PREFIX vs Conclude PREFIX
- Test 7: Scene PREFIX vs Continue PREFIX
"""

import asyncio
import json
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from difflib import unified_diff

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

# Fallback to PostgreSQL default (matches docker-compose)
os.environ.setdefault("DATABASE_URL", "postgresql://kahani:kahani@localhost:5432/kahani")

# Fix Docker-internal hostnames for bare metal execution
db_url = os.environ.get("DATABASE_URL", "")
if "postgres:" in db_url and "@postgres:" in db_url:
    # Replace Docker-internal 'postgres' hostname with 'localhost'
    os.environ["DATABASE_URL"] = db_url.replace("@postgres:", "@localhost:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.models import User, Story, Scene, Chapter
from app.services.llm.service import UnifiedLLMService
from app.services.context_manager import ContextManager
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
        # Use the to_dict method which properly handles defaults
        user_settings = settings.to_dict()
        # Add allow_nsfw from user model
        user_settings["allow_nsfw"] = user.allow_nsfw or False
        return user_settings

    # Default settings from UserSettings class
    default_settings = UserSettings.get_defaults()
    default_settings["allow_nsfw"] = user.allow_nsfw or False
    return default_settings


def find_story_by_title(db: Session, user_id: int, title_pattern: str) -> Optional[Story]:
    """Find a story by title pattern."""
    stories = db.query(Story).filter(
        Story.owner_id == user_id,
        Story.title.ilike(f"%{title_pattern}%")
    ).all()

    if stories:
        return stories[0]
    return None


def get_latest_scene(db: Session, story_id: int) -> Optional[Scene]:
    """Get the latest scene from a story."""
    return db.query(Scene).filter(
        Scene.story_id == story_id
    ).order_by(Scene.id.desc()).first()


def compare_messages(messages1: List[Dict], messages2: List[Dict], name1: str, name2: str) -> Tuple[bool, List[str]]:
    """Compare two message lists and return differences."""
    differences = []
    all_same = True

    if len(messages1) != len(messages2):
        differences.append(f"Message count differs: {name1}={len(messages1)}, {name2}={len(messages2)}")
        all_same = False
        return all_same, differences

    for i in range(len(messages1)):
        msg1 = messages1[i]
        msg2 = messages2[i]

        if msg1.get("role") != msg2.get("role"):
            differences.append(f"Message {i}: Role differs - {name1}='{msg1.get('role')}', {name2}='{msg2.get('role')}'")
            all_same = False

        content1 = msg1.get("content", "")
        content2 = msg2.get("content", "")

        if content1 != content2:
            all_same = False
            differences.append(f"Message {i} ({msg1.get('role', 'unknown')}): Content differs")
            differences.append(f"  {name1}: {len(content1)} chars")
            differences.append(f"  {name2}: {len(content2)} chars")

            # Show first difference
            for j, (c1, c2) in enumerate(zip(content1, content2)):
                if c1 != c2:
                    differences.append(f"  First diff at char {j}: '{content1[max(0,j-20):j+20]}' vs '{content2[max(0,j-20):j+20]}'")
                    break

    return all_same, differences


def format_message_summary(messages: List[Dict[str, str]]) -> str:
    """Format a summary of messages."""
    lines = []
    for i, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        content_preview = content[:80].replace('\n', '\\n') + "..." if len(content) > 80 else content.replace('\n', '\\n')
        lines.append(f"  [{i}] {role}: {len(content)} chars")
    return '\n'.join(lines)


async def run_single_test(
    db: Session,
    user: User,
    user_settings: Dict[str, Any],
    story: Story,
    scene: Scene,
    chapter: Optional[Chapter],
    branch_id: Optional[int],
    separate_choice_mode: bool,
    mode_label: str
) -> Tuple[int, int, Dict[str, Any]]:
    """
    Run cache consistency test for a single choice mode setting.

    Returns: (passed_count, failed_count, results_dict)
    """
    import copy

    # Create a copy of user_settings with the specified separate_choice_generation mode
    test_settings = copy.deepcopy(user_settings)
    test_settings['generation_preferences']['separate_choice_generation'] = separate_choice_mode

    print(f"\n{'='*80}")
    print(f"TESTING MODE: {mode_label}")
    print(f"separate_choice_generation = {separate_choice_mode}")
    print(f"{'='*80}")

    # Initialize services
    llm_service = UnifiedLLMService()
    context_manager = ContextManager(
        max_tokens=test_settings.get('context_settings', {}).get('max_tokens', 4000),
        user_settings=test_settings,
        user_id=user.id
    )

    # Get the original continue option
    from app.models.story_flow import StoryFlow
    flow = db.query(StoryFlow).filter(StoryFlow.scene_id == scene.id).first()
    original_continue_option = flow.choice_text if flow and flow.choice_text else "The protagonist explores further"

    chapter_id = chapter.id if chapter else None

    # Build contexts
    scene_context = await context_manager.build_scene_generation_context(
        story_id=story.id,
        db=db,
        custom_prompt=original_continue_option,
        is_variant_generation=False,
        exclude_scene_id=scene.id,
        chapter_id=chapter_id,
        branch_id=branch_id
    )

    variant_context = await context_manager.build_scene_generation_context(
        story_id=story.id,
        db=db,
        custom_prompt=original_continue_option,
        is_variant_generation=False,
        exclude_scene_id=scene.id,
        chapter_id=chapter_id,
        branch_id=branch_id
    )

    guided_context = await context_manager.build_scene_generation_context(
        story_id=story.id,
        db=db,
        custom_prompt="Make the scene more dramatic with heightened tension",
        is_variant_generation=True,
        exclude_scene_id=scene.id,
        chapter_id=chapter_id,
        branch_id=branch_id
    )

    # Build messages for all generation types
    all_results = {}
    separate_choice = separate_choice_mode

    # Get prose_style and active_preset for later use
    from app.models.writing_style_preset import WritingStylePreset
    from app.services.llm.prompts import prompt_manager

    generation_prefs = test_settings.get("generation_preferences", {})
    scene_length = generation_prefs.get("scene_length", "medium")
    choices_count = generation_prefs.get("choices_count", 4)
    scene_length_description = llm_service._get_scene_length_description(scene_length)

    prose_style = 'balanced'
    active_preset = db.query(WritingStylePreset).filter(
        WritingStylePreset.user_id == user.id,
        WritingStylePreset.is_active == True
    ).first()
    if active_preset and hasattr(active_preset, 'prose_style') and active_preset.prose_style:
        prose_style = active_preset.prose_style

    # 1. SCENE generation messages
    scene_messages = llm_service._build_cache_friendly_message_prefix(
        context=scene_context,
        user_id=user.id,
        user_settings=test_settings,
        db=db
    )
    scene_task = llm_service._build_scene_task_message(
        context=scene_context,
        user_settings=test_settings,
        db=db,
        include_choices_reminder=not separate_choice
    )
    scene_full = scene_messages + [{"role": "user", "content": scene_task}]
    all_results["scene"] = {"prefix": scene_messages, "task": scene_task, "full": scene_full}

    # 2. VARIANT generation messages (simple)
    variant_messages = llm_service._build_cache_friendly_message_prefix(
        context=variant_context,
        user_id=user.id,
        user_settings=test_settings,
        db=db
    )
    variant_task = llm_service._build_scene_task_message(
        context=variant_context,
        user_settings=test_settings,
        db=db,
        include_choices_reminder=not separate_choice
    )
    variant_full = variant_messages + [{"role": "user", "content": variant_task}]
    all_results["variant_simple"] = {"prefix": variant_messages, "task": variant_task, "full": variant_full}

    # 3. GUIDED VARIANT generation messages
    guided_messages = llm_service._build_cache_friendly_message_prefix(
        context=guided_context,
        user_id=user.id,
        user_settings=test_settings,
        db=db
    )
    immediate_situation = guided_context.get("current_situation") or ""
    has_immediate = bool(immediate_situation and str(immediate_situation).strip())
    tone = guided_context.get('tone', '')

    custom_prompt = "Make the scene more dramatic with heightened tension"
    guided_task = f"Regenerate the scene with the following guidance: {custom_prompt}\n\n"
    guided_task += prompt_manager.get_task_instruction(
        has_immediate=has_immediate,
        prose_style=prose_style,
        tone=tone,
        immediate_situation=str(immediate_situation) if immediate_situation else "",
        scene_length_description=scene_length_description
    )
    if not separate_choice:
        choices_reminder = prompt_manager.get_user_choices_reminder(choices_count=choices_count)
        if choices_reminder:
            guided_task = guided_task + "\n\n" + choices_reminder

    guided_full = guided_messages + [{"role": "user", "content": guided_task}]
    all_results["variant_guided"] = {"prefix": guided_messages, "task": guided_task, "full": guided_full}

    # 4. CHOICE generation messages
    choice_messages = llm_service._build_cache_friendly_message_prefix(
        context=scene_context,
        user_id=user.id,
        user_settings=test_settings,
        db=db
    )
    scene_content_for_choices = scene.content if scene and scene.content else "The protagonist stood at the crossroads."
    cleaned_scene_for_choices = llm_service._clean_instruction_tags(scene_content_for_choices)
    cleaned_scene_for_choices = llm_service._clean_scene_numbers(cleaned_scene_for_choices)

    pov = 'third'
    if active_preset and hasattr(active_preset, 'pov') and active_preset.pov:
        pov = active_preset.pov
    if pov == "first":
        pov_instruction = "in first person perspective (using 'I', 'me', 'my')"
    elif pov == "second":
        pov_instruction = "in second person perspective (using 'you', 'your')"
    else:
        pov_instruction = "in third person perspective (using 'he', 'she', 'they', character names)"

    choice_task = prompt_manager.get_prompt(
        "choice_generation", "user",
        scene_content=cleaned_scene_for_choices,
        choices_count=choices_count,
        pov_instruction=pov_instruction
    )
    choice_full = choice_messages + [{"role": "user", "content": choice_task}]
    all_results["choice"] = {"prefix": choice_messages, "task": choice_task, "full": choice_full}

    # 5. SUMMARY generation messages
    summary_messages = llm_service._build_cache_friendly_message_prefix(
        context=scene_context,
        user_id=user.id,
        user_settings=test_settings,
        db=db
    )
    chapter_number_for_summary = chapter.chapter_number if chapter else 1
    chapter_title_for_summary = chapter.title if chapter and chapter.title else "Untitled Chapter"
    scenes_content_for_summary = scene.content if scene and scene.content else "The chapter's events unfolded..."

    summary_task = prompt_manager.get_prompt(
        "chapter_summary_cache_friendly", "user",
        context_section="",
        chapter_number=chapter_number_for_summary,
        chapter_title=chapter_title_for_summary,
        scenes_content=scenes_content_for_summary
    )
    summary_full = summary_messages + [{"role": "user", "content": summary_task}]
    all_results["summary"] = {"prefix": summary_messages, "task": summary_task, "full": summary_full}

    # 6. CONCLUDING scene messages
    conclude_messages = llm_service._build_cache_friendly_message_prefix(
        context=scene_context,
        user_id=user.id,
        user_settings=test_settings,
        db=db
    )
    chapter_info = {
        "chapter_number": chapter.chapter_number if chapter else 1,
        "chapter_title": chapter.title if chapter and chapter.title else "Untitled Chapter"
    }
    conclude_task = llm_service._build_concluding_task_message(
        context=scene_context,
        chapter_info=chapter_info,
        user_settings=test_settings,
        db=db
    )
    conclude_full = conclude_messages + [{"role": "user", "content": conclude_task}]
    all_results["conclude"] = {"prefix": conclude_messages, "task": conclude_task, "full": conclude_full}

    # 7. CONTINUE generation messages
    continue_messages = llm_service._build_cache_friendly_message_prefix(
        context=scene_context,
        user_id=user.id,
        user_settings=test_settings,
        db=db
    )
    continue_context = scene_context.copy()
    continue_context["current_scene_content"] = scene.content if scene and scene.content else "The protagonist waited."
    continue_context["continuation_prompt"] = "Continue this scene with more details and development."
    continue_context["user_id"] = user.id

    continue_task = llm_service._build_continuation_task_message(
        context=continue_context,
        user_settings=test_settings,
        db=db,
        include_choices_reminder=not separate_choice
    )
    continue_full = continue_messages + [{"role": "user", "content": continue_task}]
    all_results["continue"] = {"prefix": continue_messages, "task": continue_task, "full": continue_full}

    # Run comparisons
    test_results = []

    # Test 1: Scene vs Simple Variant (IDENTICAL)
    same, diffs = compare_messages(all_results["scene"]["full"], all_results["variant_simple"]["full"], "scene", "variant")
    if same:
        test_results.append(("scene_vs_variant_simple", "PASS", "100% cache hit"))
        print(f"  ✓ Scene vs Simple Variant: IDENTICAL")
    else:
        test_results.append(("scene_vs_variant_simple", "FAIL", diffs))
        print(f"  ✗ Scene vs Simple Variant: DIFFER")

    # Test 2-7: Prefix comparisons
    prefix_tests = [
        ("scene", "variant_guided", "scene_prefix_vs_guided_prefix"),
        ("scene", "choice", "scene_prefix_vs_choice_prefix"),
        ("variant_simple", "variant_guided", "variant_prefix_vs_guided_prefix"),
        ("scene", "summary", "scene_prefix_vs_summary_prefix"),
        ("scene", "conclude", "scene_prefix_vs_conclude_prefix"),
        ("scene", "continue", "scene_prefix_vs_continue_prefix"),
    ]

    for name1, name2, test_name in prefix_tests:
        same, diffs = compare_messages(all_results[name1]["prefix"], all_results[name2]["prefix"], f"{name1}_prefix", f"{name2}_prefix")
        if same:
            test_results.append((test_name, "PASS", "Prefix cache hit"))
            print(f"  ✓ {name1} prefix vs {name2} prefix: IDENTICAL")
        else:
            test_results.append((test_name, "FAIL", diffs))
            print(f"  ✗ {name1} prefix vs {name2} prefix: DIFFER")

    passed = sum(1 for r in test_results if r[1] == "PASS")
    failed = sum(1 for r in test_results if r[1] == "FAIL")

    # Token summary
    prefix_chars = sum(len(m.get("content", "")) for m in all_results["scene"]["prefix"])
    print(f"\n  Prefix size: {prefix_chars} chars (~{prefix_chars // 4} tokens)")
    print(f"  Tests: {passed} passed, {failed} failed")

    return passed, failed, {
        "mode": mode_label,
        "separate_choice_generation": separate_choice_mode,
        "test_results": test_results,
        "passed": passed,
        "failed": failed,
        "prefix_chars": prefix_chars
    }


async def run_test():
    """Main test function - runs both choice modes."""
    print("=" * 80)
    print("PROMPT CACHE CONSISTENCY TEST - ALL GENERATION TYPES")
    print("Testing BOTH separate_choice_generation modes (True and False)")
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
        print(f"   Scene length: {user_settings['generation_preferences'].get('scene_length', 'medium')}")
        print(f"   Choices count: {user_settings['generation_preferences'].get('choices_count', 4)}")

        # Find the memory test story
        print("4. Finding 'memory test' story...")
        story = find_story_by_title(db, user.id, "memory test")
        if not story:
            print("   ERROR: Story not found! Available stories:")
            all_stories = db.query(Story).filter(Story.owner_id == user.id).all()
            for s in all_stories[:10]:
                print(f"     - {s.title} (ID: {s.id})")
            return False
        print(f"   SUCCESS: Found story '{story.title}' (ID: {story.id})")

        # Get the latest scene
        print("5. Getting latest scene...")
        scene = get_latest_scene(db, story.id)
        if not scene:
            print("   ERROR: No scenes found in story!")
            return False
        print(f"   SUCCESS: Found scene ID {scene.id}")

        # Get active branch
        from app.models.story_branch import StoryBranch
        active_branch = db.query(StoryBranch).filter(
            StoryBranch.story_id == story.id,
            StoryBranch.is_active == True
        ).first()
        branch_id = active_branch.id if active_branch else None
        print(f"   Active branch ID: {branch_id}")

        # Get chapter
        chapter = db.query(Chapter).filter(Chapter.id == scene.chapter_id).first() if scene.chapter_id else None
        print(f"   Chapter ID: {chapter.id if chapter else None}")

        # ===================================================================
        # RUN TESTS IN BOTH MODES
        # ===================================================================
        all_mode_results = []

        # Test Mode 1: Inline choices (separate_choice_generation=False)
        passed1, failed1, results1 = await run_single_test(
            db=db,
            user=user,
            user_settings=user_settings,
            story=story,
            scene=scene,
            chapter=chapter,
            branch_id=branch_id,
            separate_choice_mode=False,
            mode_label="INLINE CHOICES (choices generated with scene)"
        )
        all_mode_results.append(results1)

        # Test Mode 2: Separate choices (separate_choice_generation=True)
        passed2, failed2, results2 = await run_single_test(
            db=db,
            user=user,
            user_settings=user_settings,
            story=story,
            scene=scene,
            chapter=chapter,
            branch_id=branch_id,
            separate_choice_mode=True,
            mode_label="SEPARATE CHOICES (choices generated separately)"
        )
        all_mode_results.append(results2)

        # ===================================================================
        # FINAL SUMMARY
        # ===================================================================
        print("\n" + "=" * 80)
        print("FINAL SUMMARY - BOTH MODES")
        print("=" * 80)

        total_passed = passed1 + passed2
        total_failed = failed1 + failed2

        print(f"\nMode 1 (Inline Choices):   {passed1} passed, {failed1} failed")
        print(f"Mode 2 (Separate Choices): {passed2} passed, {failed2} failed")
        print(f"\nTotal: {total_passed} passed, {total_failed} failed")

        if total_failed > 0:
            print("\n⚠️  CACHE CONSISTENCY ISSUES DETECTED!")
            print("   Some generation types have different message prefixes,")
            print("   which will cause cache misses.")
        else:
            print("\n✓ ALL TESTS PASSED IN BOTH MODES!")
            print("  Cache consistency verified for both inline and separate choice generation.")

        # Write detailed report
        output_file = backend_dir / "prompt_comparison_report.json"
        report = {
            "summary": {
                "total_passed": total_passed,
                "total_failed": total_failed,
                "mode_1_inline_choices": {"passed": passed1, "failed": failed1},
                "mode_2_separate_choices": {"passed": passed2, "failed": failed2}
            },
            "story": {"id": story.id, "title": story.title},
            "scene": {"id": scene.id},
            "mode_results": all_mode_results
        }

        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nDetailed report written to: {output_file}")

        return total_failed == 0

    finally:
        db.close()


if __name__ == "__main__":
    result = asyncio.run(run_test())
    sys.exit(0 if result else 1)
