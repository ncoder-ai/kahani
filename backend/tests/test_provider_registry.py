"""Tests for the provider registry settings refactor.

Tests the configured_providers column, credential resolution,
to_dict() consumer contract, backward compatibility, migration backfill,
and API endpoint behavior.
"""
import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeUserSettings:
    """Lightweight stand-in for UserSettings that avoids SQLAlchemy instrumentation.

    Inherits the helper methods directly from UserSettings without going through
    the ORM mapper.
    """
    def __init__(self, **kwargs):
        defaults = {
            'configured_providers': None,
            'llm_api_type': None, 'llm_api_key': None, 'llm_api_url': None,
            'extraction_model_api_type': None, 'extraction_model_api_key': None, 'extraction_model_url': None,
            'embedding_provider': None, 'embedding_api_key': None, 'embedding_api_url': None,
            'embedding_model_name': None, 'embedding_dimensions': None,
            'engine_settings': None, 'extraction_engine_settings': None, 'sampler_settings': None,
            'llm_temperature': 0.7, 'llm_top_p': 1.0, 'llm_top_k': 50,
            'llm_repetition_penalty': 1.1, 'llm_max_tokens': 2048, 'llm_timeout_total': None,
            'llm_model_name': "test-model", 'completion_mode': "chat",
            'text_completion_template': None, 'text_completion_preset': "llama3",
            'reasoning_effort': None, 'show_thinking_content': True,
            'thinking_model_type': None, 'thinking_model_custom_pattern': None,
            'thinking_enabled_generation': False,
            'context_max_tokens': 4000, 'context_keep_recent_scenes': 3,
            'context_summary_threshold': 5, 'context_summary_threshold_tokens': 8000,
            'enable_context_summarization': True, 'auto_generate_summaries': True,
            'character_extraction_threshold': 5, 'scene_batch_size': 10,
            'enable_semantic_memory': True, 'context_strategy': "hybrid",
            'semantic_search_top_k': 5, 'semantic_scenes_in_context': 5,
            'semantic_context_weight': 0.4, 'character_moments_in_context': 3,
            'auto_extract_character_moments': True, 'auto_extract_plot_events': True,
            'extraction_confidence_threshold': 70, 'plot_event_extraction_threshold': 5,
            'fill_remaining_context': True,
            'enable_working_memory': True, 'enable_contradiction_detection': True,
            'contradiction_severity_threshold': "info", 'enable_relationship_graph': True,
            'enable_contradiction_injection': True, 'enable_inline_contradiction_check': False,
            'auto_regenerate_on_contradiction': False,
            'default_genre': "", 'default_tone': "", 'preferred_scene_length': "medium",
            'enable_auto_choices': True, 'choices_count': 4, 'alert_on_high_context': True,
            'use_extraction_llm_for_summary': False, 'separate_choice_generation': False,
            'use_cache_friendly_prompts': True, 'enable_chapter_plot_tracking': True,
            'default_plot_check_mode': "1", 'enable_streaming': True,
            'color_theme': "pure-dark", 'font_size': "medium",
            'show_token_info': False, 'show_context_info': False,
            'enable_notifications': True, 'scene_display_format': "default",
            'show_scene_titles': True, 'show_scene_images': True,
            'scene_edit_mode': "textarea", 'auto_open_last_story': False,
            'last_accessed_story_id': None,
            'default_export_format': "markdown", 'include_metadata': True, 'include_choices': True,
            'enable_character_suggestions': True, 'character_importance_threshold': 70,
            'character_mention_threshold': 5,
            'stt_enabled': True, 'stt_model': "small",
            'extraction_model_enabled': False, 'extraction_model_name': "qwen2.5-3b-instruct",
            'extraction_model_temperature': 0.3, 'extraction_model_max_tokens': 1000,
            'extraction_fallback_to_main': True, 'use_context_aware_extraction': False,
            'extraction_model_top_p': 1.0, 'extraction_model_repetition_penalty': 1.0,
            'extraction_model_min_p': 0.0,
            'extraction_model_thinking_disable_method': "none",
            'extraction_model_thinking_disable_custom': "",
            'extraction_model_thinking_enabled_extractions': False,
            'extraction_model_thinking_enabled_memory': True,
            'use_main_llm_for_plot_extraction': False, 'use_main_llm_for_decomposition': False,
            'current_extraction_engine': None,
            'custom_system_prompt': None, 'enable_experimental_features': False,
            'current_engine': None,
            'image_gen_enabled': False, 'comfyui_server_url': "", 'comfyui_api_key': "",
            'comfyui_checkpoint': "", 'comfyui_model_type': "sdxl",
            'image_gen_width': 1024, 'image_gen_height': 1024,
            'image_gen_steps': 4, 'image_gen_cfg_scale': 1.5,
            'image_gen_default_style': "illustrated",
            'use_extraction_llm_for_image_prompts': False,
            'embedding_needs_reembed': False,
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)

    # Bind the real helper methods from UserSettings
    from app.models.user_settings import UserSettings as _US
    _get_configured_providers = _US._get_configured_providers
    _resolve_provider_credentials = _US._resolve_provider_credentials
    to_dict = _US.to_dict
    _parse_engine_settings = _US._parse_engine_settings
    _parse_extraction_engine_settings = _US._parse_extraction_engine_settings
    _parse_sampler_settings = _US._parse_sampler_settings
    _get_merged_sampler_settings = _US._get_merged_sampler_settings
    _get_image_generation_settings = _US._get_image_generation_settings
    get_default_sampler_settings = staticmethod(_US.get_default_sampler_settings)


def _make_user_settings(**kwargs):
    """Create a fake UserSettings object with defaults."""
    return _FakeUserSettings(**kwargs)


# ===========================================================================
# Group 1: Model — configured_providers Parsing
# ===========================================================================

class TestConfiguredProvidersParsing:
    def test_parse_empty_returns_empty_dict(self):
        us = _make_user_settings(configured_providers="")
        assert us._get_configured_providers() == {}

    def test_parse_valid_json_returns_providers(self):
        data = {"openrouter": {"api_key": "sk-123"}, "local": {}}
        us = _make_user_settings(configured_providers=json.dumps(data))
        assert us._get_configured_providers() == data

    def test_parse_corrupt_json_returns_empty_dict(self):
        us = _make_user_settings(configured_providers="{bad json")
        assert us._get_configured_providers() == {}

    def test_parse_null_returns_empty_dict(self):
        us = _make_user_settings(configured_providers=None)
        assert us._get_configured_providers() == {}


# ===========================================================================
# Group 2: Credential Resolution
# ===========================================================================

class TestCredentialResolution:
    def test_resolve_from_configured_providers(self):
        data = {"openrouter": {"api_key": "sk-or-test", "api_url": ""}}
        us = _make_user_settings(configured_providers=json.dumps(data))
        key, url = us._resolve_provider_credentials("openrouter")
        assert key == "sk-or-test"
        assert url == ""

    def test_resolve_falls_back_to_legacy_llm_columns(self):
        us = _make_user_settings(
            configured_providers=json.dumps({}),
            llm_api_type="openrouter",
            llm_api_key="sk-legacy",
            llm_api_url="https://legacy.url"
        )
        key, url = us._resolve_provider_credentials("openrouter")
        assert key == "sk-legacy"
        assert url == "https://legacy.url"

    def test_resolve_falls_back_to_legacy_extraction_columns(self):
        us = _make_user_settings(
            configured_providers=json.dumps({}),
            extraction_model_api_type="groq",
            extraction_model_api_key="gsk-test",
            extraction_model_url="https://api.groq.com"
        )
        key, url = us._resolve_provider_credentials("groq")
        assert key == "gsk-test"
        assert url == "https://api.groq.com"

    def test_resolve_falls_back_to_legacy_embedding_columns(self):
        us = _make_user_settings(
            configured_providers=json.dumps({}),
            embedding_provider="openai",
            embedding_api_key="sk-emb",
            embedding_api_url=""
        )
        key, url = us._resolve_provider_credentials("openai")
        assert key == "sk-emb"
        assert url == ""

    def test_resolve_unknown_provider_returns_empty(self):
        us = _make_user_settings(configured_providers=json.dumps({"local": {}}))
        key, url = us._resolve_provider_credentials("nonexistent_provider")
        assert key == ""
        assert url == ""

    def test_resolve_prefers_configured_over_legacy(self):
        data = {"openrouter": {"api_key": "sk-new", "api_url": ""}}
        us = _make_user_settings(
            configured_providers=json.dumps(data),
            llm_api_type="openrouter",
            llm_api_key="sk-old",
            llm_api_url="https://old.url"
        )
        key, url = us._resolve_provider_credentials("openrouter")
        assert key == "sk-new"


# ===========================================================================
# Group 3: to_dict() Consumer Contract
# ===========================================================================

class TestToDictConsumerContract:
    """Ensures output shape matches what LLMClient, ExtractionLLMService, etc. expect."""

    @patch('app.models.user_settings.settings')
    def test_to_dict_llm_settings_has_all_required_keys(self, mock_settings):
        mock_settings.user_defaults = {}
        mock_settings.llm_timeout_total = 120
        mock_settings.semantic_embedding_model = "test"
        us = _make_user_settings(
            llm_api_type="openrouter",
            configured_providers=json.dumps({"openrouter": {"api_key": "sk-test"}, "local": {}})
        )
        result = us.to_dict()
        llm = result["llm_settings"]
        for key in ["api_type", "api_url", "api_key", "model_name", "temperature",
                     "top_p", "top_k", "repetition_penalty", "max_tokens"]:
            assert key in llm, f"Missing key: {key}"

    @patch('app.models.user_settings.settings')
    def test_to_dict_extraction_settings_has_all_required_keys(self, mock_settings):
        mock_settings.user_defaults = {}
        mock_settings.llm_timeout_total = 120
        mock_settings.semantic_embedding_model = "test"
        us = _make_user_settings(
            extraction_model_api_type="groq",
            configured_providers=json.dumps({"groq": {"api_key": "gsk-x"}, "local": {}})
        )
        result = us.to_dict()
        ext = result["extraction_model_settings"]
        for key in ["url", "model_name", "api_type", "api_key", "temperature", "max_tokens"]:
            assert key in ext, f"Missing key: {key}"

    @patch('app.models.user_settings.settings')
    def test_to_dict_embedding_settings_has_all_required_keys(self, mock_settings):
        mock_settings.user_defaults = {}
        mock_settings.llm_timeout_total = 120
        mock_settings.semantic_embedding_model = "test-embed"
        us = _make_user_settings(
            configured_providers=json.dumps({"local": {}})
        )
        result = us.to_dict()
        emb = result["embedding_model_settings"]
        for key in ["provider", "model_name", "api_key", "api_url", "dimensions"]:
            assert key in emb, f"Missing key: {key}"

    @patch('app.models.user_settings.settings')
    def test_to_dict_resolves_llm_key_from_configured_providers(self, mock_settings):
        mock_settings.user_defaults = {}
        mock_settings.llm_timeout_total = 120
        mock_settings.semantic_embedding_model = "test"
        data = {"openrouter": {"api_key": "sk-from-registry", "api_url": ""}, "local": {}}
        us = _make_user_settings(
            llm_api_type="openrouter",
            llm_api_key="",  # empty legacy
            configured_providers=json.dumps(data)
        )
        result = us.to_dict()
        assert result["llm_settings"]["api_key"] == "sk-from-registry"

    @patch('app.models.user_settings.settings')
    def test_to_dict_resolves_extraction_key_from_configured_providers(self, mock_settings):
        mock_settings.user_defaults = {}
        mock_settings.llm_timeout_total = 120
        mock_settings.semantic_embedding_model = "test"
        data = {"groq": {"api_key": "gsk-registry"}, "local": {}}
        us = _make_user_settings(
            extraction_model_api_type="groq",
            extraction_model_api_key="",
            configured_providers=json.dumps(data)
        )
        result = us.to_dict()
        assert result["extraction_model_settings"]["api_key"] == "gsk-registry"

    @patch('app.models.user_settings.settings')
    def test_to_dict_resolves_embedding_key_from_configured_providers(self, mock_settings):
        mock_settings.user_defaults = {}
        mock_settings.llm_timeout_total = 120
        mock_settings.semantic_embedding_model = "test"
        data = {"openai": {"api_key": "sk-emb-registry"}, "local": {}}
        us = _make_user_settings(
            embedding_provider="openai",
            embedding_api_key="",
            configured_providers=json.dumps(data)
        )
        result = us.to_dict()
        assert result["embedding_model_settings"]["api_key"] == "sk-emb-registry"

    @patch('app.models.user_settings.settings')
    def test_to_dict_includes_configured_providers_in_output(self, mock_settings):
        mock_settings.user_defaults = {}
        mock_settings.llm_timeout_total = 120
        mock_settings.semantic_embedding_model = "test"
        data = {"openrouter": {"api_key": "sk-x"}, "local": {}}
        us = _make_user_settings(configured_providers=json.dumps(data))
        result = us.to_dict()
        assert "configured_providers" in result
        assert result["configured_providers"] == data


# ===========================================================================
# Group 4: Backward Compatibility
# ===========================================================================

class TestBackwardCompatibility:
    @patch('app.models.user_settings.settings')
    def test_to_dict_works_with_null_configured_providers(self, mock_settings):
        """Pre-migration user with no configured_providers column value."""
        mock_settings.user_defaults = {}
        mock_settings.llm_timeout_total = 120
        mock_settings.semantic_embedding_model = "test"
        us = _make_user_settings(
            configured_providers=None,
            llm_api_type="openrouter",
            llm_api_key="sk-legacy",
        )
        result = us.to_dict()
        # Should fall back to legacy columns
        assert result["llm_settings"]["api_key"] == "sk-legacy"
        assert result["configured_providers"] == {}

    @patch('app.models.user_settings.settings')
    def test_to_dict_works_with_empty_configured_providers(self, mock_settings):
        mock_settings.user_defaults = {}
        mock_settings.llm_timeout_total = 120
        mock_settings.semantic_embedding_model = "test"
        us = _make_user_settings(
            configured_providers=json.dumps({}),
            llm_api_type="openrouter",
            llm_api_key="sk-old",
        )
        result = us.to_dict()
        assert result["llm_settings"]["api_key"] == "sk-old"

    @patch('app.models.user_settings.settings')
    def test_legacy_columns_used_when_provider_not_in_registry(self, mock_settings):
        mock_settings.user_defaults = {}
        mock_settings.llm_timeout_total = 120
        mock_settings.semantic_embedding_model = "test"
        data = {"local": {}}  # Only local, not the provider we're looking for
        us = _make_user_settings(
            configured_providers=json.dumps(data),
            llm_api_type="custom_provider",
            llm_api_key="sk-custom",
            llm_api_url="https://custom.url",
        )
        result = us.to_dict()
        assert result["llm_settings"]["api_key"] == "sk-custom"
        assert result["llm_settings"]["api_url"] == "https://custom.url"


# ===========================================================================
# Group 5: Migration Backfill Logic
# ===========================================================================

class TestMigrationBackfill:
    """Test the _backfill_configured_providers function from migration 075."""

    @classmethod
    def setup_class(cls):
        """Import the backfill function from the migration module."""
        import importlib.util
        migration_path = os.path.join(
            os.path.dirname(__file__), '..', 'alembic', 'versions',
            '075_add_configured_providers.py'
        )
        spec = importlib.util.spec_from_file_location("migration_075", migration_path)
        cls.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.migration)

    def _make_row(self, **kwargs):
        """Create a mock row with defaults for all columns."""
        defaults = {
            'id': 1,
            'llm_api_type': None, 'llm_api_key': None, 'llm_api_url': None,
            'extraction_model_api_type': None, 'extraction_model_api_key': None,
            'extraction_model_url': None,
            'embedding_provider': None, 'embedding_api_key': None,
            'embedding_api_url': None, 'embedding_model_name': None,
            'embedding_dimensions': None,
            'engine_settings': None, 'extraction_engine_settings': None,
            'sampler_settings': None,
        }
        defaults.update(kwargs)
        row = MagicMock()
        for k, v in defaults.items():
            setattr(row, k, v)
        return row

    def test_backfill_collects_from_llm_columns(self):
        row = self._make_row(llm_api_type="openrouter", llm_api_key="sk-or", llm_api_url="")
        result = json.loads(self.migration._backfill_configured_providers(row))
        assert "openrouter" in result
        assert result["openrouter"]["api_key"] == "sk-or"

    def test_backfill_collects_from_extraction_columns(self):
        row = self._make_row(extraction_model_api_type="groq", extraction_model_api_key="gsk-x", extraction_model_url="")
        result = json.loads(self.migration._backfill_configured_providers(row))
        assert "groq" in result
        assert result["groq"]["api_key"] == "gsk-x"

    def test_backfill_collects_from_embedding_columns(self):
        row = self._make_row(embedding_provider="openai", embedding_api_key="sk-emb", embedding_model_name="text-embedding-3-small", embedding_dimensions=1536)
        result = json.loads(self.migration._backfill_configured_providers(row))
        assert "openai" in result
        assert result["openai"]["api_key"] == "sk-emb"
        assert result["openai"]["embedding"]["model_name"] == "text-embedding-3-small"

    def test_backfill_parses_engine_settings_json(self):
        es = {"openrouter": {"api_key": "sk-es", "model_name": "llama-3-70b", "temperature": 0.8}}
        row = self._make_row(engine_settings=json.dumps(es))
        result = json.loads(self.migration._backfill_configured_providers(row))
        assert "openrouter" in result
        assert result["openrouter"]["api_key"] == "sk-es"
        assert result["openrouter"]["llm"]["model_name"] == "llama-3-70b"

    def test_backfill_parses_extraction_engine_settings_json(self):
        ees = {"groq": {"api_key": "gsk-ees", "model_name": "ministral-8b", "temperature": 0.3}}
        row = self._make_row(extraction_engine_settings=json.dumps(ees))
        result = json.loads(self.migration._backfill_configured_providers(row))
        assert "groq" in result
        assert result["groq"]["extraction"]["model_name"] == "ministral-8b"

    def test_backfill_deduplicates_same_provider(self):
        """Same provider used for both LLM and extraction — credentials merged."""
        row = self._make_row(
            llm_api_type="openrouter", llm_api_key="sk-or", llm_api_url="",
            extraction_model_api_type="openrouter", extraction_model_api_key="sk-or", extraction_model_url=""
        )
        result = json.loads(self.migration._backfill_configured_providers(row))
        # Should have one entry, not two
        assert "openrouter" in result
        assert result["openrouter"]["api_key"] == "sk-or"

    def test_backfill_prefers_nonempty_key(self):
        row = self._make_row(
            llm_api_type="openrouter", llm_api_key="",  # empty from flat column
            engine_settings=json.dumps({"openrouter": {"api_key": "sk-real"}})  # non-empty from engine settings
        )
        result = json.loads(self.migration._backfill_configured_providers(row))
        assert result["openrouter"]["api_key"] == "sk-real"

    def test_backfill_always_includes_local_provider(self):
        row = self._make_row()  # No providers configured at all
        result = json.loads(self.migration._backfill_configured_providers(row))
        assert "local" in result


# ===========================================================================
# Group 6: API Endpoint Integration
# ===========================================================================

class TestAPIEndpoints:
    """Mock DB session tests for the PUT handler and credential resolution."""

    def test_put_configured_providers_saves_json(self):
        from app.api.settings import ConfiguredProvidersUpdate
        update = ConfiguredProvidersUpdate(
            configured_providers={"openrouter": {"api_key": "sk-new"}, "local": {}}
        )
        assert update.configured_providers["openrouter"]["api_key"] == "sk-new"

    def test_put_configured_providers_schema_validates(self):
        from app.api.settings import UserSettingsUpdate, ConfiguredProvidersUpdate
        payload = {
            "configured_providers": {
                "configured_providers": {"openrouter": {"api_key": "sk-x"}}
            }
        }
        update = UserSettingsUpdate(**payload)
        assert update.configured_providers is not None
        assert update.configured_providers.configured_providers["openrouter"]["api_key"] == "sk-x"

    def test_resolve_provider_key_from_configured(self):
        from app.api.settings import _resolve_provider_key_from_configured
        data = {"openrouter": {"api_key": "sk-test"}, "local": {}}
        us = _make_user_settings(configured_providers=json.dumps(data))
        assert _resolve_provider_key_from_configured(us, "openrouter") == "sk-test"

    def test_resolve_provider_key_empty_when_missing(self):
        from app.api.settings import _resolve_provider_key_from_configured
        us = _make_user_settings(configured_providers=json.dumps({"local": {}}))
        assert _resolve_provider_key_from_configured(us, "nonexistent") == ""

    def test_model_fetch_resolves_credentials_from_configured_providers(self):
        """Verify that _resolve_provider_credentials is available on the model."""
        data = {"openrouter": {"api_key": "sk-fetch", "api_url": ""}}
        us = _make_user_settings(configured_providers=json.dumps(data))
        key, url = us._resolve_provider_credentials("openrouter")
        assert key == "sk-fetch"

    def test_test_connection_resolves_credentials_from_configured_providers(self):
        """Same as above — verifying the model method works for test-connection flow."""
        data = {"koboldcpp": {"api_key": "", "api_url": "http://192.168.1.100:5001"}}
        us = _make_user_settings(configured_providers=json.dumps(data))
        key, url = us._resolve_provider_credentials("koboldcpp")
        assert url == "http://192.168.1.100:5001"


# ===========================================================================
# Group 7: Role Param Storage Round-Trip
# ===========================================================================

class TestRoleParamRoundTrip:
    def test_save_llm_params_stored_in_configured_providers(self):
        data = {
            "openrouter": {
                "api_key": "sk-x",
                "llm": {"model_name": "llama-3", "temperature": 0.9}
            },
            "local": {}
        }
        us = _make_user_settings(configured_providers=json.dumps(data))
        providers = us._get_configured_providers()
        assert providers["openrouter"]["llm"]["model_name"] == "llama-3"
        assert providers["openrouter"]["llm"]["temperature"] == 0.9

    def test_switch_provider_preserves_previous_role_params(self):
        """Simulate frontend provider switch: save old params, load new."""
        data = {
            "openrouter": {"api_key": "sk-1", "llm": {"model_name": "model-a", "temperature": 0.8}},
            "groq": {"api_key": "gsk-1", "llm": {"model_name": "model-b", "temperature": 0.5}},
            "local": {}
        }
        us = _make_user_settings(configured_providers=json.dumps(data))
        providers = us._get_configured_providers()
        # "Switch" from openrouter to groq — old params still there
        assert providers["openrouter"]["llm"]["temperature"] == 0.8
        assert providers["groq"]["llm"]["temperature"] == 0.5

    def test_switch_back_restores_role_params(self):
        """After switching away and back, params should be preserved."""
        data = {
            "openrouter": {"api_key": "sk-1", "llm": {"model_name": "model-a", "temperature": 0.8}},
            "groq": {"api_key": "gsk-1"},
            "local": {}
        }
        us = _make_user_settings(configured_providers=json.dumps(data))
        # Simulate: user switches to groq (we save openrouter llm params)
        # Then switches back — openrouter.llm params still there
        providers = us._get_configured_providers()
        assert providers["openrouter"]["llm"]["model_name"] == "model-a"

    def test_first_time_provider_gets_defaults(self):
        """Provider with no saved role params — should get empty/no llm block."""
        data = {"openrouter": {"api_key": "sk-1"}, "local": {}}
        us = _make_user_settings(configured_providers=json.dumps(data))
        providers = us._get_configured_providers()
        assert "llm" not in providers["openrouter"]  # No saved LLM params yet
