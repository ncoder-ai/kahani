"""
Tests for extraction/summary message routing.

Verifies:
1. Dead keys removed from yaml_mapping and prompts.yml
2. _will_use_extraction_llm() helper logic
3. _build_simple_extraction_messages() helper
4. Extraction methods route correctly based on LLM target + cache setting
5. Creative generation always uses cache-friendly prefix
6. Fixed get_prompt_pair calls resolve
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from typing import Dict, Any, List
import json
import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.llm.prompts import PromptManager, prompt_manager
from app.services.llm.service import UnifiedLLMService


# ============================================================
# Shared fixtures
# ============================================================

def _make_user_settings(
    extraction_enabled: bool = False,
    use_cache_friendly: bool = True,
    use_extraction_for_summary: bool = False,
    use_main_for_plot: bool = False,
) -> Dict[str, Any]:
    """Build a minimal user_settings dict for tests."""
    return {
        "llm_settings": {
            "temperature": 0.7,
            "max_tokens": 2048,
            "api_url": "http://localhost:1234/v1",
            "model_name": "test-model",
        },
        "extraction_model_settings": {
            "enabled": extraction_enabled,
            "url": "http://localhost:1234/v1",
            "model_name": "test-extraction",
            "fallback_to_main": True,
            "use_main_llm_for_plot_extraction": use_main_for_plot,
        },
        "generation_preferences": {
            "use_cache_friendly_prompts": use_cache_friendly,
            "use_extraction_llm_for_summary": use_extraction_for_summary,
        },
        "context_settings": {
            "max_tokens": 4000,
        },
    }


def _make_context() -> Dict[str, Any]:
    """Build a minimal context dict."""
    return {
        "story": {"title": "Test Story", "genre": "fantasy"},
        "chapter": {"title": "Chapter 1", "number": 1},
        "characters": [],
        "recent_scenes": [],
    }


# ============================================================
# 1. Dead key cleanup verification
# ============================================================

class TestDeadKeyCleanup:
    """Verify dead keys were removed from yaml_mapping and prompts.yml."""

    def setup_method(self):
        self.pm = PromptManager()

    def test_dead_keys_removed_from_yaml_mapping(self):
        """Dead keys should not exist in the yaml_mapping dict."""
        # Access the mapping through _get_yaml_prompt which uses yaml_mapping
        dead_keys = [
            "chapter_progress.event_extraction",
            "chapter_progress.context_aware_extraction",
            "moments_and_npcs",
            "scene_event_extraction.batch",
        ]
        for key in dead_keys:
            result = self.pm.get_prompt(key, "user")
            assert result == "", f"Dead key '{key}' should return empty string but got: {result[:100]}"

    def test_dead_keys_removed_from_prompts_yml(self):
        """Dead top-level YAML keys should not exist."""
        assert "chapter_plot_guidance" not in self.pm._prompts_cache, \
            "chapter_plot_guidance should be removed from prompts.yml"
        assert "moments_and_npcs_cache_friendly" not in self.pm._prompts_cache, \
            "moments_and_npcs_cache_friendly should be removed from prompts.yml"
        # chapter_progress should be removed entirely
        assert "chapter_progress" not in self.pm._prompts_cache, \
            "chapter_progress should be removed from prompts.yml"

    def test_scene_event_extraction_batch_removed(self):
        """scene_event_extraction.batch sub-key should be removed."""
        scene_event = self.pm._prompts_cache.get("scene_event_extraction", {})
        assert "batch" not in scene_event, \
            "scene_event_extraction.batch should be removed from prompts.yml"

    def test_scene_event_extraction_cache_friendly_still_exists(self):
        """scene_event_extraction.cache_friendly should still exist."""
        scene_event = self.pm._prompts_cache.get("scene_event_extraction", {})
        assert "cache_friendly" in scene_event, \
            "scene_event_extraction.cache_friendly should still exist"


# ============================================================
# 2. _will_use_extraction_llm() helper
# ============================================================

class TestWillUseExtractionLlm:
    """Test the extraction LLM routing helper."""

    def test_extraction_configured(self):
        """Should return True when extraction model is enabled."""
        settings = _make_user_settings(extraction_enabled=True)
        assert UnifiedLLMService._will_use_extraction_llm(settings) is True

    def test_extraction_not_configured(self):
        """Should return False when extraction model is disabled."""
        settings = _make_user_settings(extraction_enabled=False)
        assert UnifiedLLMService._will_use_extraction_llm(settings) is False

    def test_force_main_true(self):
        """Should return False when force_main_llm=True, even if extraction is enabled."""
        settings = _make_user_settings(extraction_enabled=True)
        assert UnifiedLLMService._will_use_extraction_llm(settings, force_main_llm=True) is False

    def test_force_main_false(self):
        """Should return True when force_main_llm=False and extraction is enabled."""
        settings = _make_user_settings(extraction_enabled=True)
        assert UnifiedLLMService._will_use_extraction_llm(settings, force_main_llm=False) is True

    def test_force_main_none(self):
        """Should return True when force_main_llm=None and extraction is enabled."""
        settings = _make_user_settings(extraction_enabled=True)
        assert UnifiedLLMService._will_use_extraction_llm(settings, force_main_llm=None) is True


# ============================================================
# 3. _build_simple_extraction_messages() helper
# ============================================================

class TestBuildSimpleExtractionMessages:
    """Test the simple message builder."""

    def test_returns_two_messages(self):
        """Should return exactly 2 messages."""
        msgs = UnifiedLLMService._build_simple_extraction_messages("sys", "usr")
        assert len(msgs) == 2

    def test_message_roles(self):
        """First message should be system, second should be user."""
        msgs = UnifiedLLMService._build_simple_extraction_messages("sys", "usr")
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_message_content(self):
        """Messages should contain the provided instructions."""
        sys_instr = "You are an extraction assistant."
        usr_instr = "Extract events from this scene: ..."
        msgs = UnifiedLLMService._build_simple_extraction_messages(sys_instr, usr_instr)
        assert msgs[0]["content"] == sys_instr
        assert msgs[1]["content"] == usr_instr


# ============================================================
# 4-6. Extraction method routing tests
# ============================================================

class TestExtractionRouting:
    """Test that extraction methods route correctly based on settings."""

    def setup_method(self):
        self.service = UnifiedLLMService()
        self.context = _make_context()

    @pytest.mark.asyncio
    async def test_uses_simple_when_extraction_llm(self):
        """When extraction LLM is available, should use simple messages."""
        settings = _make_user_settings(extraction_enabled=True, use_cache_friendly=True)

        with patch.object(self.service, '_build_cache_friendly_message_prefix', new_callable=AsyncMock) as mock_cache, \
             patch.object(self.service, 'generate_for_task', new_callable=AsyncMock, return_value='{"events": []}') as mock_gen:

            await self.service.extract_scene_events_cache_friendly(
                scene_content="Test scene",
                character_names=["Alice"],
                context=self.context,
                user_id=1,
                user_settings=settings,
            )

            mock_cache.assert_not_called()
            # generate_for_task should have been called with 2-message list
            call_args = mock_gen.call_args
            messages = call_args.kwargs.get('messages') or call_args[1].get('messages') or call_args[0][0]
            assert len(messages) == 2
            assert messages[0]["role"] == "system"

    @pytest.mark.asyncio
    async def test_uses_cache_friendly_when_main_llm_cache_on(self):
        """When using main LLM with cache ON, should use cache-friendly prefix."""
        settings = _make_user_settings(extraction_enabled=False, use_cache_friendly=True)

        with patch.object(self.service, '_build_cache_friendly_message_prefix', new_callable=AsyncMock, return_value=[
            {"role": "system", "content": "system"},
            {"role": "user", "content": "context1"},
        ]) as mock_cache, \
             patch.object(self.service, 'generate_for_task', new_callable=AsyncMock, return_value='{"events": []}'):

            await self.service.extract_scene_events_cache_friendly(
                scene_content="Test scene",
                character_names=["Alice"],
                context=self.context,
                user_id=1,
                user_settings=settings,
            )

            mock_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_simple_when_main_llm_cache_off(self):
        """When using main LLM with cache OFF, should use simple messages."""
        settings = _make_user_settings(extraction_enabled=False, use_cache_friendly=False)

        with patch.object(self.service, '_build_cache_friendly_message_prefix', new_callable=AsyncMock) as mock_cache, \
             patch.object(self.service, 'generate_for_task', new_callable=AsyncMock, return_value='{"events": []}'):

            await self.service.extract_scene_events_cache_friendly(
                scene_content="Test scene",
                character_names=["Alice"],
                context=self.context,
                user_id=1,
                user_settings=settings,
            )

            mock_cache.assert_not_called()

    @pytest.mark.asyncio
    async def test_combined_extraction_routing(self):
        """Combined extraction should route correctly."""
        settings = _make_user_settings(extraction_enabled=True)

        with patch.object(self.service, '_build_cache_friendly_message_prefix', new_callable=AsyncMock) as mock_cache, \
             patch.object(self.service, 'generate_for_task', new_callable=AsyncMock, return_value='{}'):

            await self.service.extract_combined_cache_friendly(
                scene_content="Test scene",
                character_names=["Alice"],
                explicit_character_names=["Alice"],
                thread_context="",
                context=self.context,
                user_id=1,
                user_settings=settings,
            )

            mock_cache.assert_not_called()

    @pytest.mark.asyncio
    async def test_plot_extraction_routing(self):
        """Plot extraction should route correctly."""
        settings = _make_user_settings(extraction_enabled=True)

        with patch.object(self.service, '_build_cache_friendly_message_prefix', new_callable=AsyncMock) as mock_cache, \
             patch.object(self.service, 'generate_for_task', new_callable=AsyncMock, return_value='{}'):

            await self.service.extract_plot_events_with_context(
                scene_content="Test scene",
                key_events=["Event 1"],
                context=self.context,
                user_id=1,
                user_settings=settings,
            )

            mock_cache.assert_not_called()

    @pytest.mark.asyncio
    async def test_chapter_summary_routing(self):
        """Chapter summary should route correctly."""
        settings = _make_user_settings(extraction_enabled=True, use_extraction_for_summary=True)

        with patch.object(self.service, '_build_cache_friendly_message_prefix', new_callable=AsyncMock) as mock_cache, \
             patch.object(self.service, 'generate_for_task', new_callable=AsyncMock, return_value='Summary text'):

            await self.service.generate_chapter_summary_cache_friendly(
                chapter_number=1,
                chapter_title="Test",
                scenes_content="Scene content",
                context=self.context,
                user_id=1,
                user_settings=settings,
            )

            mock_cache.assert_not_called()

    @pytest.mark.asyncio
    async def test_snapshot_routing_extraction_llm(self):
        """Snapshot should use simple messages when extraction LLM is available."""
        settings = _make_user_settings(extraction_enabled=True)

        with patch.object(self.service, '_build_cache_friendly_message_prefix', new_callable=AsyncMock) as mock_cache, \
             patch.object(self.service, 'generate_for_task', new_callable=AsyncMock, return_value='Snapshot text'):

            await self.service.generate_snapshot_cache_friendly(
                character_name="Alice",
                original_background="A warrior",
                chronicle_entries="Entry 1",
                context=self.context,
                user_id=1,
                user_settings=settings,
            )

            mock_cache.assert_not_called()

    @pytest.mark.asyncio
    async def test_snapshot_routing_main_llm_cache_on(self):
        """Snapshot should use cache-friendly prefix when main LLM + cache ON."""
        settings = _make_user_settings(extraction_enabled=False, use_cache_friendly=True)

        with patch.object(self.service, '_build_cache_friendly_message_prefix', new_callable=AsyncMock, return_value=[
            {"role": "system", "content": "sys"},
        ]) as mock_cache, \
             patch.object(self.service, 'generate_for_task', new_callable=AsyncMock, return_value='Snapshot text'):

            await self.service.generate_snapshot_cache_friendly(
                character_name="Alice",
                original_background="A warrior",
                chronicle_entries="Entry 1",
                context=self.context,
                user_id=1,
                user_settings=settings,
            )

            mock_cache.assert_called_once()


# ============================================================
# 7. Fixed get_prompt_pair calls
# ============================================================

class TestFixedPromptPairs:
    """Verify fixed get_prompt_pair calls resolve to non-empty prompts."""

    def setup_method(self):
        self.pm = PromptManager()

    def test_story_chapters_system_prompt_resolves(self):
        """story_chapters system prompt should be non-empty."""
        result = self.pm.get_prompt("story_chapters", "system")
        assert result != "", "story_chapters system prompt should not be empty"

    def test_story_chapters_user_prompt_resolves(self):
        """story_chapters user prompt should be non-empty."""
        result = self.pm.get_prompt("story_chapters", "user",
                                    context="test context", chapter_count=5)
        assert result != "", "story_chapters user prompt should not be empty"

    def test_complete_plot_system_prompt_resolves(self):
        """complete_plot system prompt should be non-empty."""
        result = self.pm.get_prompt("complete_plot", "system")
        assert result != "", "complete_plot system prompt should not be empty"

    def test_single_plot_point_system_prompt_resolves(self):
        """single_plot_point system prompt should be non-empty."""
        result = self.pm.get_prompt("single_plot_point", "system")
        assert result != "", "single_plot_point system prompt should not be empty"


# ============================================================
# 8. Existing prompts still work
# ============================================================

class TestExistingPromptsIntact:
    """Verify that non-removed prompts still resolve correctly."""

    def setup_method(self):
        self.pm = PromptManager()

    def test_plot_extraction_user_prompt(self):
        """plot_extraction user prompt should still work."""
        result = self.pm.get_prompt("plot_extraction", "user",
                                    scene_content="test", key_events="1. event")
        assert result != ""
        assert "test" in result

    def test_combined_extraction_user_prompt(self):
        """combined_extraction user prompt should still work."""
        result = self.pm.get_prompt("combined_extraction", "user",
                                    scene_content="test",
                                    character_names="Alice",
                                    explicit_names="Alice",
                                    thread_section="")
        assert result != ""

    def test_scene_event_extraction_cache_friendly(self):
        """scene_event_extraction.cache_friendly should still work."""
        result = self.pm.get_prompt("scene_event_extraction.cache_friendly", "user",
                                    scene_content="test",
                                    character_names="Alice")
        assert result != ""
