# Kahani Backend Refactoring Plan

## Overview

This plan outlines the systematic refactoring of large monolithic files into smaller, logically organized modules. The goal is to improve maintainability, testability, and code organization.

## Current State (After Phases 1-4)

| File | Lines | Status |
|------|-------|--------|
| `services/llm/service.py` | 5,543 | Needs further extraction |
| `api/stories.py` | 4,460 | Needs further extraction |
| `api/chapters.py` | 2,072 | Recently refactored |
| `routers/tts.py` | 1,875 | Lower priority |

### Already Extracted (Phases 1-4)
- `api/story_tasks/background_tasks.py` - Background task functions
- `api/entity_states.py` - Entity state endpoints
- `api/drafts.py` - Draft management endpoints
- `api/story_arc.py` - Story arc endpoints
- `api/interactions.py` - Interaction endpoints
- `api/story_generation.py` - Title/scenario/plot generation
- `api/chapter_brainstorm.py` - Chapter brainstorming endpoints
- `services/chapter_summary_service.py` - Chapter summary helpers
- `services/llm/content_cleaner.py` - Content cleaning utilities
- `services/llm/choice_parser.py` - Choice parsing utilities
- `services/llm/plot_parser.py` - Plot parsing utilities
- `services/llm/context_formatter.py` - Context formatting utilities

---

## Phase 5: LLM Service Decomposition

**Target:** `services/llm/service.py` (5,543 → ~2,500 lines)

### 5.1 Extract `scene_database_operations.py`
**Lines:** ~550 | **Priority:** High | **Effort:** Medium

Extract database operations from UnifiedLLMService:
- `create_scene_with_variant()` (~77 lines)
- `regenerate_scene_variant()` (~74 lines)
- `switch_to_variant()` (~30 lines)
- `get_scene_variants()` (~9 lines)
- `get_active_scene_count()` (~33 lines)
- `get_active_story_flow()` (~69 lines)
- `_update_story_flow()` (~32 lines)
- `delete_scenes_from_sequence()` (~345 lines)
- `_get_active_branch_id()` (~10 lines)

**Dependencies:** SQLAlchemy models (Scene, SceneVariant, StoryFlow)

### 5.2 Extract `llm_generation_core.py`
**Lines:** ~900 | **Priority:** High | **Effort:** High

Extract core generation methods:
- `_generate()` - Chat completion (~120 lines)
- `_generate_text_completion()` (~110 lines)
- `_direct_http_fallback()` (~175 lines)
- `_direct_http_text_completion_fallback()` (~200 lines)
- `_generate_stream()` (~120 lines)
- `_generate_text_completion_stream()` (~170 lines)

**Dependencies:** LiteLLM, httpx, NSFW filter

### 5.3 Extract `multi_variant_generation.py`
**Lines:** ~1,050 | **Priority:** Medium | **Effort:** High

Extract n-sampling generation methods:
- `_generate_stream_with_messages_multi()` (~90 lines)
- `_generate_multi_completions()` (~60 lines)
- `generate_scene_with_choices_streaming_multi()` (~145 lines)
- `generate_scene_with_choices_multi()` (~110 lines)
- `generate_scene_streaming_multi()` (~90 lines)
- `generate_scene_multi()` (~80 lines)
- `generate_choices_for_variants()` (~45 lines)
- `generate_concluding_scene_streaming_multi()` (~80 lines)
- `generate_concluding_scene_multi()` (~75 lines)
- `regenerate_scene_variant_streaming_multi()` (~140 lines)
- `regenerate_scene_variant_multi()` (~125 lines)

**Dependencies:** Core generation, context formatting

---

## Phase 6: Stories API Decomposition

**Target:** `api/stories.py` (4,460 → ~1,500 lines)

### 6.1 Extract `scene_endpoints.py`
**Lines:** ~1,230 | **Priority:** High | **Effort:** Medium

Extract scene generation endpoints:
- `generate_scene()` (~394 lines)
- `generate_scene_streaming_endpoint()` (~834 lines)

**Dependencies:** llm_service, context management, semantic integration

### 6.2 Extract `variant_endpoints.py`
**Lines:** ~1,600 | **Priority:** High | **Effort:** Medium

Extract variant management endpoints:
- `get_scene_variants()` (~69 lines)
- `create_scene_variant()` (~234 lines)
- `create_scene_variant_streaming()` (~567 lines)
- `activate_scene_variant()` (~32 lines)
- `continue_scene()` (~104 lines)
- `continue_scene_streaming()` (~140 lines)
- `update_scene_variant()` (~147 lines)
- `regenerate_scene_variant_choices()` (~149 lines)

**Dependencies:** llm_service, scene models, semantic integration

### 6.3 Extract `story_helpers.py`
**Lines:** ~450 | **Priority:** Medium | **Effort:** Low

Extract helper functions:
- `SceneVariantServiceAdapter` class (~42 lines)
- `get_n_value_from_settings()` (~17 lines)
- `create_scene_with_multi_variants()` (~94 lines)
- `create_additional_variants()` (~81 lines)
- `setup_auto_play_if_enabled()` (~77 lines)
- `trigger_auto_play_tts()` (~9 lines)
- `invalidate_extractions_for_scene()` (~33 lines)
- `invalidate_and_regenerate_extractions_for_scene()` (~144 lines)
- `get_or_create_user_settings()` (~51 lines)

**Dependencies:** Various services, models

---

## Phase 7: TTS Router Decomposition (Lower Priority)

**Target:** `routers/tts.py` (1,875 → ~1,275 lines)

### 7.1 Extract `tts_generation_service.py`
**Lines:** ~600 | **Priority:** Low | **Effort:** Medium

Extract generation logic:
- `generate_scene_audio()` (~69 lines)
- `generate_scene_audio_websocket()` (~87 lines)
- `generate_and_stream_chunks()` (~446 lines)

**Dependencies:** TTS providers, WebSocket, background tasks

---

## Phase 8: Frontend Refactoring

### 8.1 Component Library Expansion
- Extract more reusable UI components
- Create consistent form patterns
- Standardize modal dialogs

### 8.2 State Management
- Review Zustand store organization
- Extract slice-specific logic
- Add proper TypeScript types

### 8.3 API Layer
- Consolidate API calls
- Add proper error handling patterns
- Implement request caching where appropriate

---

## Execution Checklist

### Phase 5: LLM Service
- [ ] 5.1 Extract scene_database_operations.py
- [ ] 5.2 Extract llm_generation_core.py
- [ ] 5.3 Extract multi_variant_generation.py
- [ ] Verify all imports work correctly
- [ ] Test scene generation flow
- [ ] Test variant generation flow

### Phase 6: Stories API
- [ ] 6.1 Extract scene_endpoints.py
- [ ] 6.2 Extract variant_endpoints.py
- [ ] 6.3 Extract story_helpers.py
- [ ] Update main.py router registrations
- [ ] Test all story endpoints

### Phase 7: TTS Router
- [ ] 7.1 Extract tts_generation_service.py
- [ ] Test audio generation
- [ ] Test WebSocket streaming

### Phase 8: Frontend
- [ ] 8.1 Component library expansion
- [ ] 8.2 State management review
- [ ] 8.3 API layer consolidation

---

## Success Metrics

| File | Current | Target | Reduction |
|------|---------|--------|-----------|
| `services/llm/service.py` | 5,543 | ~2,500 | 55% |
| `api/stories.py` | 4,460 | ~1,500 | 66% |
| `routers/tts.py` | 1,875 | ~1,275 | 32% |
| **Total** | **11,878** | **~5,275** | **56%** |

---

## Notes

- Each extraction should maintain backward compatibility via wrapper functions
- Test thoroughly after each phase
- Commit after each successful extraction
- Update imports in dependent files
- Keep the plan updated as work progresses

---

## Progress Log

| Date | Phase | Task | Status |
|------|-------|------|--------|
| 2026-01-19 | 1 | Extract background tasks, UI components | Done |
| 2026-01-19 | 2 | Extract entity_states, drafts, story_arc, interactions | Done |
| 2026-01-19 | 3 | Extract story_generation.py | Done |
| 2026-01-19 | 4 | Extract LLM utility modules | Done |
| 2026-01-20 | - | Extract chapter_brainstorm.py | Done |
| 2026-01-20 | - | Extract chapter_summary_service.py | Done |
| | 5.1 | Extract scene_database_operations.py | Pending |
| | 5.2 | Extract llm_generation_core.py | Pending |
| | 5.3 | Extract multi_variant_generation.py | Pending |
| | 6.1 | Extract scene_endpoints.py | Pending |
| | 6.2 | Extract variant_endpoints.py | Pending |
| | 6.3 | Extract story_helpers.py | Pending |
