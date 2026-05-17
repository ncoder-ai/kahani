# Extraction LLM Benchmark Harness

Persistent test suite for evaluating candidate extraction-LLM models against the current production model (Ministral-3-8B-Q8). Lives in-repo so a new model can be benchmarked with one command — no rebuild of fixtures or rubrics.

See `docs/EXTRACTION_LLM_BENCHMARK_DESIGN.md` for the full design.

## Quick start

### Benchmark the currently-loaded model
The extraction LLM at `localhost:5002` is whatever you started last. To benchmark it:
```bash
cd backend/benchmarks/extraction_llm
python orchestrator/run_baseline.py --label ministral-8b-q8
```
Writes results to `reports/ministral-8b-q8_<timestamp>/`.

### Benchmark a different model (full swap + run)
```bash
# 1. tear down the current llama-server
./orchestrator/teardown.sh

# 2. start the candidate
./orchestrator/launch_model.sh ${MODELS_DIR}/Qwen3.5-4B-Q5_K_M.gguf &

# 3. wait for health, then run
./orchestrator/wait_for_health.sh
python orchestrator/run_baseline.py --label qwen3.5-4b-q5
```

### Add a model to config and run the full battery
Edit `config.yaml` to add the candidate, then:
```bash
python orchestrator/run_all.py    # cycles through every model in config.yaml
```

### Compare two reports
```bash
python orchestrator/compare.py reports/ministral-8b-q8_*  reports/qwen3.5-4b-q5_*
```

## Layout

```
fixtures/             # Test cases (committed) — one dir per task suite
  T1_semantic_decompose/
  T2_recall_agent/
  T3_tts_segments/
  T4_scene_events/
  T5_working_memory/
  T6_chapter_summary/
  T7_content_moderation/
  T8_plot_progress/
  T9_entity_state/
  T10_npc_characters/
runners/              # HTTP client, retry, latency capture
scoring/              # Auto-checks + judge rubrics
orchestrator/         # Launch/teardown/run scripts
reports/              # Per-run output (gitignored)
config.yaml           # Models registered for benchmarking
```

## Adding a new model
1. Download the GGUF to `${MODELS_DIR}/`
2. Add an entry to `config.yaml` under `models:`
3. Run `python orchestrator/run_all.py` — it'll swap each model and run the full battery

## Adding a new fixture
1. Drop a JSON file in the appropriate `fixtures/T<N>_<task>/` directory (format: see `fixtures/README.md`)
2. Re-run the baseline to capture Ministral's output as the reference
3. Commit — every future model gets tested against it

## Fixture provenance (important)

Every fixture in `fixtures/T*/` uses **real production prompt templates** from
`backend/prompts.yml`. There are two flavors, both legitimate:

1. **Captured fixtures** (`real_NNN.json`) — pulled from `logs/prompt_*.json`,
   which are the exact rendered messages kahani sent to the LLM at runtime.
2. **Rendered fixtures** (`<story_slug>_seqNNN.json`) — built by
   `render_real_fixtures.py`, which reads the prompt template straight from
   `prompts.yml` and fills its `{scene_content}`, `{character_names}`, etc.
   placeholders using real scenes from `_scenes_pool/`.

Hand-written probes live ONLY in `fixtures/_synthetic_probes/` and are not
run by default. They exist for supplementary edge-case coverage (e.g. JSON
nesting probes for small-model failure modes) and never substitute for real
prompts.

## What's tested

| Suite | Workload (from inventory) | Fixture source |
|---|---|---|
| T1 | Semantic query decomposition (B2) | **needs capture hook** — see follow-ups |
| T2 | Recall agent multi-turn (C1) | `logs/agent_traces/*.json` (real traces) |
| T4 | Scene event extraction (A2) | `prompts.yml: scene_event_extraction.cache_friendly` × scene pool |
| T5 | Working memory update (A7) | `prompts.yml: working_memory_update` × scene pool + captured `real_001` |
| T7 | Content moderation (B1) | `prompts.yml: content_moderation.output` × scene pool |
| T9 | Entity state extraction (A6) | `prompts.yml: entity_state_extraction.single` × scene pool + captured `real_001` |
| T10_char_moments | Character moments (A3) | `prompts.yml: character_moments_cache_friendly` × scene pool |
| T10_npcs | NPC extraction (A8) | `prompts.yml: npc_extraction_cache_friendly` × scene pool |

Scene pool: 17 scenes from 4 stories (2 SFW + 2 NSFW), pulled from the
kahani DB via `db_extract_scenes.py`. Genres span erotica, romance, drama,
fantasy. Each story contributes scenes from early/mid/late timeline
positions for variety.

**Moved out of the default battery**:
- T8 plot progress, T_chronicle — captured prompts are from kahani's
  main-LLM (plot extraction is `force_main_llm=True`); they appear with
  14 consecutive user messages which Ministral's strict Jinja template
  rejects. Stashed under `fixtures/_main_llm_captures/`.
- T6 chapter summary — needs full chapter scene batches; separate renderer.

## Not in this harness
- Main-LLM workloads (scene/choice generation, brainstorm, roleplay, character generation) — separate concern, not affected by extraction-LLM swap.
- D3b character detail extraction — pending move to main LLM (see inventory Follow-up #1).
- Chronicle extraction main-LLM pass — uses main LLM today; could be added as future suite.
