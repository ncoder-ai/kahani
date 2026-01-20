# Kahani Refactoring Plan

## Overview

This plan outlines the systematic refactoring of large monolithic files into smaller, logically organized modules. The goal is to improve maintainability, testability, and code organization.

## Final State (Refactoring Complete)

### Backend

| File | Original | Final | Reduction |
|------|----------|-------|-----------|
| `services/llm/service.py` | 5,543 | 3,346 | 40% |
| `api/stories.py` | 4,460 | 1,182 | 73% |
| `routers/tts.py` | 1,875 | 1,875 | Deferred |

### Frontend

| File | Original | Final | Reduction |
|------|----------|-------|-----------|
| `components/SettingsModal.tsx` | 5,038 | 442 | 91% |
| `lib/api.ts` | ~1,200 | ~200 | 83% (modularized) |

---

## Extracted Modules

### Backend - LLM Service (Phase 5)
- `services/llm/scene_database_operations.py` - Scene database operations (~550 lines)
- `services/llm/llm_generation_core.py` - Core LLM generation methods (~800 lines)
- `services/llm/multi_variant_generation.py` - Multi-variant generation (~1,050 lines)
- `services/llm/content_cleaner.py` - Content cleaning utilities
- `services/llm/choice_parser.py` - Choice parsing utilities
- `services/llm/plot_parser.py` - Plot parsing utilities
- `services/llm/context_formatter.py` - Context formatting utilities

### Backend - Stories API (Phase 6)
- `api/scene_endpoints.py` - Scene generation endpoints (1,283 lines)
- `api/variant_endpoints.py` - Variant management endpoints (1,513 lines)
- `api/story_helpers.py` - Story helper functions (663 lines)
- `api/story_generation.py` - Title/scenario/plot generation
- `api/chapter_brainstorm.py` - Chapter brainstorming endpoints
- `api/entity_states.py` - Entity state endpoints
- `api/drafts.py` - Draft management endpoints
- `api/story_arc.py` - Story arc endpoints
- `api/interactions.py` - Interaction endpoints

### Backend - Services
- `services/chapter_summary_service.py` - Chapter summary helpers
- `api/story_tasks/background_tasks.py` - Background task functions

### Frontend - API Layer (Phase 8.1)
- `lib/api/index.ts` - Core API client and exports
- `lib/api/stories.ts` - Story CRUD operations
- `lib/api/scenes.ts` - Scene generation and management
- `lib/api/chapters.ts` - Chapter operations
- `lib/api/characters.ts` - Character management
- `lib/api/brainstorm.ts` - Brainstorming features
- `lib/api/settings.ts` - User settings
- `lib/api/tts.ts` - Text-to-speech
- `lib/api/auth.ts` - Authentication

### Frontend - Settings Components (Phase 8.2)
- `components/settings/types.ts` - Shared type definitions
- `components/settings/tabs/InterfaceSettingsTab.tsx` - UI preferences
- `components/settings/tabs/WritingSettingsTab.tsx` - Writing style presets
- `components/settings/tabs/LLMSettingsTab.tsx` - LLM configuration
- `components/settings/tabs/ContextSettingsTab.tsx` - Context management
- `components/settings/tabs/VoiceSettingsTab.tsx` - TTS/STT settings
- `components/settings/index.ts` - Module exports

---

## Execution Checklist

### Phase 5: LLM Service ✅
- [x] 5.1 Extract scene_database_operations.py
- [x] 5.2 Extract llm_generation_core.py
- [x] 5.3 Extract multi_variant_generation.py
- [x] Verify all imports work correctly
- [x] Test scene generation flow
- [x] Test variant generation flow

### Phase 6: Stories API ✅
- [x] 6.1 Extract scene_endpoints.py (1,283 lines)
- [x] 6.2 Extract variant_endpoints.py (1,513 lines)
- [x] 6.3 Extract story_helpers.py (663 lines)
- [x] Update main.py router registrations
- [x] Test all story endpoints

### Phase 7: TTS Router (Deferred)
- [ ] 7.1 Extract tts_generation_service.py
- [ ] Test audio generation
- [ ] Test WebSocket streaming

### Phase 8: Frontend ✅
- [x] 8.1 API layer modularization (9 domain-specific modules)
- [x] 8.2 SettingsModal decomposition (5 tab components, 91% reduction)
- [ ] 8.3 State management review (optional future work)

---

## Success Metrics

| Area | Original Lines | Final Lines | Reduction |
|------|----------------|-------------|-----------|
| Backend LLM Service | 5,543 | 3,346 | 40% |
| Backend Stories API | 4,460 | 1,182 | 73% |
| Frontend SettingsModal | 5,038 | 442 | 91% |
| Frontend API Client | ~1,200 | ~200 | 83% |
| **Total Impact** | **~16,241** | **~5,170** | **68%** |

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
| 2026-01-20 | 5.1 | Extract scene_database_operations.py | Done |
| 2026-01-20 | 5.2 | Extract llm_generation_core.py | Done |
| 2026-01-20 | 5.3 | Extract multi_variant_generation.py | Done |
| 2026-01-20 | 6.1 | Extract scene_endpoints.py (1,283 lines) | Done |
| 2026-01-20 | 6.2 | Extract variant_endpoints.py (1,513 lines) | Done |
| 2026-01-20 | 6.3 | Extract story_helpers.py (663 lines) | Done |
| 2026-01-20 | 8.1 | Frontend API modularization (9 modules) | Done |
| 2026-01-20 | 8.2 | SettingsModal decomposition (5 tabs, 91% reduction) | Done |

---

## Future Considerations

### Phase 7: TTS Router (Low Priority)
If needed, extract ~600 lines from `routers/tts.py`:
- `generate_scene_audio()`
- `generate_scene_audio_websocket()`
- `generate_and_stream_chunks()`

### Phase 8.3: State Management (Optional)
- Review Zustand store organization
- Extract slice-specific logic
- Add proper TypeScript types

---

## Notes

- Each extraction maintains backward compatibility via wrapper functions
- All phases tested after extraction
- Commits made after each successful extraction
- Imports updated in dependent files
