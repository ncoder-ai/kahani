# Extraction LLM — Benchmark Design

**Purpose**: Decide whether smaller models (Gemma-3-4B, Qwen-3-4B, etc.) can replace Ministral-3-8B in the extraction-LLM slot at `localhost:5002`.

**Last updated**: 2026-05-12

---

## 1. Goals & Non-Goals

**Goals**
- Run a reproducible, **autonomous** battery of tests against each candidate model in the extraction slot.
- For every priority-ranked workload from the inventory: measure JSON validity, schema conformance, semantic correctness, latency.
- Produce a single recommendation per workload: *swap-safe*, *swap with caveat*, *keep on Ministral*.
- **Persistent reusable harness.** The harness + fixtures + scoring rubrics live in the repo so any future candidate model can be benchmarked with a one-liner — no rebuild of the test suite required. Adding a new model = one row in `config.yaml` + (optionally) one GGUF download.

**Non-goals**
- Not benchmarking the **main LLM**. Scene/choice generation stays untouched.
- Not redesigning prompts. We're benchmarking how each model responds to the **existing** prompts in `prompts.yml`. Prompt tuning is a follow-up if a model is otherwise good but underperforms on one task.
- Not testing roleplay, brainstorm, character generation (D1, D2, D5, D6) — they're main-LLM workloads per the inventory.

---

## 2. Models Under Test

**Baseline (current production)**:
- **Ministral-3-8B-Instruct-2512 (Q8_0)** — `${MODELS_DIR}/Ministral-3-8B-Instruct-2512-Q8_0.gguf`

**Candidates to download** — *latest releases only* (older Qwen3-4B/Gemma-3 GGUFs already on disk will NOT be used):

| Model | HF lookup target | Quant |
|---|---|---|
| **Qwen 3.5 — 4B Instruct (latest)** | Resolve at run-time: check `Qwen/` org on HF for the newest 4B instruct release (e.g. `Qwen3.5-4B-Instruct`). Prefer official Qwen GGUF if published; else `bartowski/Qwen3.5-4B-Instruct-GGUF`. | Q5_K_M or Q6_K |
| **Gemma 4 — ~4B (latest)** | Resolve at run-time: check `google/` for newest small Gemma 4 release. Prefer official `google/...-it-GGUF` if it exists; else `bartowski/...-GGUF`. | Q5_K_M or Q6_K |

> **Important**: Both repos will be looked up at benchmark-launch time, not pre-hardcoded — model numbering and HF repo names change frequently and the user explicitly asked for the latest. The launcher will query HF Hub for the actual current release names before download (`huggingface_hub.HfApi().list_models(author='Qwen', search='4B Instruct')` etc.).

**Optional contender (already on disk, included if user agrees):**
- Granite-4.1-8B (Q5_K_M) at `${MODELS_DIR}/granite-4.1-8b-Q5_K_M.gguf` — same size bracket as Ministral, useful as a control for whether the win/loss is about size or family.

**Excluded** per user direction:
- ~~`Huihui-Qwen3-4B-Instruct-2507-abliterated.i1-Q4_K_M.gguf`~~ (older Qwen 3 — superseded by Qwen 3.5)
- ~~`gemma-4-31B-it-uncensored-heretic-Q4_K_M.gguf`~~ (too big for the extraction slot anyway)

**Default candidate set for the first battery**: 3 models — Ministral-8B-Q8 (baseline), latest Qwen 3.5 4B, latest Gemma 4 small. User confirms model picks (and quant level) before download.

Each model loaded via a copy of `start-ministral-8b.sh` with `MODEL=` swapped — same context (32K), KV cache (Q8), batch size, GPU 0 only. **No prompt template manipulation** — relies on `--jinja` flag to use the model's bundled chat template. (Caveat: if a candidate model lacks a working Jinja template, the orchestrator falls back to `--chat-template <template_name>` per model from `config.yaml`.)

---

## 3. What Gets Tested (Tasks from the Inventory)

Ranked by the inventory's priority list. Each task corresponds to one **test suite** in the harness.

| # | Suite | Source | Test count target |
|---|---|---|---|
| T1 | **Semantic Decompose** (B2) | `logs/prompt_sent*.json` (capture pre-decompose context) + synthetic edge cases | 12–15 cases |
| T2 | **Recall Agent (multi-turn)** (C1) | `logs/agent_traces/recall_agent_trace_*.json` — replay tool transcripts | 5–8 traces |
| T3 | **TTS Segment Extraction** (A1) | Real scene contents from `logs/prompt_sent_scene_*.json` | 10 scenes |
| T4 | **Scene Event Extraction** (A2) | Real scenes + 3 synthetic blunt-vocab probes | 10 + 3 |
| T5 | **Working Memory Update** (A7) | Real scenes; check for dict-instead-of-string nesting | 8 cases |
| T6 | **Chapter Summary** (A10) | Real chapter scene batches | 5 chapters |
| T7 | **Content Moderation** (B1) | Curated SFW/NSFW edge cases (must build) | 20 cases |
| T8 | **Plot Progress Extraction** (A5) | `logs/prompt_plot_extraction.json` + synthetic | 8 cases |
| T9 | **Entity State Extraction** (A6) | `logs/prompt_entity_extraction.json` + nested-output probes | 8 cases |
| T10 | **Character Moments / NPCs / Relationships** (A3, A4, A8, A9) | Real scenes, one combined suite | 6 cases |

**Out-of-scope for this round**: D3a/D3b/D3c, D4 image prompts. They have lower volume and a clearer path forward (D3b moves to main LLM per Follow-up #1).

---

## 4. Test Data Sourcing

### 4a. Real captured prompts (preferred — they ARE the production payload)

Available now in `logs/`:
- `prompt_sent.json` (scene generation prefix — useful as cache-prefix context for extraction tests)
- `prompt_sent_choices.json`
- `prompt_plot_extraction.json` → T8 directly
- `prompt_entity_extraction.json` → T9 directly
- `prompt_chronicle_extraction.json` → bonus
- `prompt_sent_scene_*.json` (many) — extract the `current scene content` field → drive T3, T4, T5, T6
- `agent_traces/recall_agent_trace_*.json` → T2 directly (replay multi-turn tool transcripts)

**Capture step (one-time)**: enable `prompt_debug` in config, run ~5 scenes in a real story, also dump the semantic-decompose call (need a small code-level capture hook for T1 — patch `service.py:_maybe_improve_semantic_scenes` to write `logs/prompt_semantic_decompose.json`).

### 4b. Synthetic edge cases (catch known failure modes)

Hand-written, ~3 cases per suite, exercising the specific failure modes called out in CLAUDE.md / memory:

- **Blunt vocab probe** (T4): a scene written with literary euphemisms — does the model emit blunt extraction vocab ("groped breasts") or copy the euphemism ("brushing the undersides of her breasts")?
- **JSON nesting probe** (T5, T9): does it emit `{"recent_focus": {"type": "...", "description": "..."}}` (broken) instead of `{"recent_focus": "..."}` (correct)?
- **Plot progress booleans** (T8): can it emit `{"1": true, "2": false}` cleanly, or does it return an array of strings?
- **Content moderation false-positive probe** (T7): mildly suggestive but SFW content — does the model over-block?
- **Ambiguous recall vs direct intent** (T1): a user prompt that could be either direct continuation OR a callback ("she's wearing the dress from the party") — does it correctly classify as `recall` and decompose into sub-queries?

### 4c. Ground truth

- **Deterministic checks** (auto-graded): JSON parses, schema conformance, no nested objects where flat strings expected, enum values within allowed set, output length within range.
- **Reference outputs**: run **each captured fixture through the current Ministral-8B-Q8 production model ONCE** at the start to capture a reference output. This becomes the "Ministral baseline" — not ground truth, but the bar candidates must clear.
- **LLM-as-judge** (for semantic correctness): a separate judge call to the user's **main LLM** (the strong creative model) compares candidate output vs reference, scoring on a 0–4 rubric per task. Rubric is task-specific (see §5).

---

## 5. Scoring

### 5a. Auto-graded (cheap, runs on every output)

| Check | Applies to | Pass criteria |
|---|---|---|
| `parses_json` | T1, T3, T4, T5, T7, T8, T9, T10 | `json.loads()` succeeds |
| `schema_ok` | as above | Required keys present, types correct |
| `no_nesting` | T5, T9 | Values that should be strings are strings (not dicts) |
| `enum_in_set` | T1 intent, T3 emotion | Values within allowed enum |
| `len_in_range` | T6 chapter summary, T1 sub-query count | Output length within sane bounds |
| `latency_ms` | all | Wall-clock from request to last token |
| `tokens_per_sec` | all | From server `usage` field if available |
| `tool_call_well_formed` | T2 | Each tool call in the trace replay parses |
| `terminates_in_max_turns` | T2 | Agent stops before `max_turns=8` |

### 5b. Judge-LLM rubric (per-task, 0–4 scale)

One judge prompt per task type. Judge sees: **task description**, **input**, **reference output (from Ministral)**, **candidate output**. Returns JSON `{score: 0-4, reasoning: "..."}`.

Sample rubric anchors:
- **4 — Equal or better than reference**: would not need correction.
- **3 — Minor issues**: e.g. missed one minor character moment, summary slightly long.
- **2 — Notable degradation**: missed a significant event, wrong intent classification, nested JSON.
- **1 — Major errors**: hallucinated entities, garbled output, wrong format.
- **0 — Unusable**: fails to parse, completely off-task.

Judge runs **3 times per output, scores are averaged** (mitigates judge variance).

### 5c. Final task verdict

A model **passes a task** if:
- ≥ 95% auto-graded pass rate, AND
- Mean judge score ≥ 3.0 with ≥ 80% of cases scoring ≥ 3.
- Latency: not strictly required to beat Ministral, but report side-by-side.

A model is **swap-safe** for production if it passes **every priority-1 task** (T1, T2, T3) AND ≥ 70% of remaining tasks. Anything else gets a per-task recommendation (e.g. "swap on T4–T10 but stay on Ministral for T2").

---

## 6. Harness Architecture

**Location**: `backend/benchmarks/extraction_llm/` — **lives in the repo, committed alongside code.** Future models benchmark with `python run_all.py --model <hf_repo_or_path>`. No re-setup needed.

What gets committed (durable):
- All `fixtures/*.json` (captured prompts + synthetic edge cases + reference Ministral outputs)
- All scoring rubrics in `scoring/judge_prompts.yml`
- All runners + orchestrator + launch script template
- `config.yaml` schema (model list itself is editable)
- `README.md` with the one-liner to add and benchmark a new model

What's gitignored (per-run output):
- `reports/` (timestamped MD + CSV + per-run JSON records)
- Any downloaded GGUFs (kept in `${MODELS_DIR}/`, not in repo)



```
backend/benchmarks/extraction_llm/
├── README.md
├── config.yaml                 # models list, endpoints, judge model
├── fixtures/
│   ├── T1_semantic_decompose/
│   │   ├── real_001.json       # captured input + system/user messages
│   │   ├── synthetic_001.json
│   │   └── reference_ministral_8b_q8.json   # baseline outputs
│   ├── T2_recall_agent/        # full trace replays
│   ├── T3_tts_segments/
│   └── ... (one dir per suite)
├── runners/
│   ├── base_runner.py          # OpenAI-compat client, retry, latency capture
│   ├── single_turn_runner.py   # for T1, T3–T10
│   └── agent_replay_runner.py  # for T2 — replays tool transcripts
├── scoring/
│   ├── auto_checks.py          # JSON parse, schema, nesting, enum, length
│   ├── judge_prompts.yml       # one rubric per task
│   └── judge.py                # calls main LLM, averages 3 runs
├── orchestrator/
│   ├── launch_model.sh         # template that swaps MODEL= and execs llama-server
│   ├── wait_for_health.sh      # polls /v1/models until ready
│   ├── teardown.sh             # kills llama-server cleanly
│   └── run_all.py              # main entry point — see §6c
├── reports/                    # gitignored; one MD + one CSV per run
└── capture/
    └── patch_for_decompose_capture.diff   # one-off patch to dump T1 inputs
```

### 6a. Test case format (fixture JSON)

```json
{
  "task": "T1_semantic_decompose",
  "case_id": "real_003",
  "source": "captured from logs/prompt_sent_scene_1772062446322.json @ 2026-04-12",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "request_params": {
    "max_tokens": 400,
    "temperature": 0.3,
    "stop": ["</response>"]
  },
  "expected_schema": {
    "type": "object",
    "required": ["intent", "queries"],
    "properties": {
      "intent": {"enum": ["direct", "recall", "react"]},
      "queries": {"type": "array", "items": {"type": "string"}, "maxItems": 6}
    }
  },
  "rubric_notes": "Multi-attribute user intent — expect 2–4 sub-queries, one per attribute (clothing, location). Intent should be 'recall' due to callback to past event."
}
```

### 6b. Output record (one per run)

```json
{
  "model": "Qwen3-4B-Q4_K_M",
  "task": "T1_semantic_decompose",
  "case_id": "real_003",
  "run_idx": 1,
  "latency_ms": 1247,
  "tokens_in": 4123,
  "tokens_out": 87,
  "tokens_per_sec": 69.8,
  "raw_output": "...",
  "auto_checks": {"parses_json": true, "schema_ok": true, "enum_in_set": true},
  "judge_scores": [3, 4, 3],
  "judge_mean": 3.33,
  "verdict": "pass"
}
```

### 6c. Orchestrator flow (`run_all.py`)

```
For each model in config.yaml:
  1. teardown.sh  (kill current llama-server)
  2. launch_model.sh <model_path> &  (start in background)
  3. wait_for_health.sh  (poll /v1/models, ~30s timeout)
  4. For each task suite T1..T10:
     For each fixture in suite:
       For run_idx in 1..N (default N=3):
         - POST messages to localhost:5002/v1/chat/completions
         - Record latency + tokens + raw output
         - Run auto_checks → record
         - Send to judge → record 3 scores
         - Write output record to reports/<model>/<task>/<case>_<run>.json
  5. teardown.sh
After all models:
  6. Aggregate → reports/SUMMARY.md (per-task pass rates, side-by-side) + reports/SUMMARY.csv
```

**Failure handling**: per-case timeout (60s for single-turn, 180s for T2 agent). On timeout → record as `verdict: fail_timeout` and continue. One bad case doesn't kill the whole run.

**Resume support**: orchestrator writes a `progress.jsonl` and skips already-completed (model, task, case, run) tuples on restart. Lets the user `Ctrl-C` and resume without losing the morning's run.

### 6d. The model-swap script (key automation piece)

`orchestrator/launch_model.sh` is a parameterized copy of `start-ministral-8b.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
export CUDA_VISIBLE_DEVICES=0

MODEL_PATH="${1:?usage: launch_model.sh <gguf-path>}"
CTX_SIZE="${2:-32768}"
PORT="${3:-5002}"

BIN="${IK_LLAMA_BIN:-$HOME/App/ik_llama.cpp/build/bin/llama-server}"
exec "$BIN" \
  --model        "$MODEL_PATH" \
  --ctx-size     "$CTX_SIZE" \
  --n-gpu-layers 999 \
  --split-mode   none \
  --main-gpu     0 \
  --flash-attn   on \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --context-shift on \
  --batch-size   2048 \
  --ubatch-size  512 \
  --threads      13 \
  --parallel     1 \
  --host         0.0.0.0 \
  --port         "$PORT" \
  --jinja
```

**One caveat**: 4B models will fit at much higher contexts than 32K — but we hold context fixed to match production. KV cache stays Q8 throughout to match production behavior. **If a candidate model lacks a working Jinja chat template**, the orchestrator falls back to `--chat-template <template_name>` per model from `config.yaml`.

---

## 7. Special Case — Recall Agent Replay (T2)

The recall agent is multi-turn with tool calls. We can't just replay a prompt — we need to replay a **conversation**.

Approach: use the existing traces in `logs/agent_traces/recall_agent_trace_*.json`. Each trace contains the full ReAct loop: input → LLM call → tool call → tool result → LLM call → ... → final answer.

**Replay strategy**: At each turn, feed the candidate model the same accumulated context Ministral saw, plus the same tool results. Score:
1. **Tool call format**: does the candidate emit a parseable tool call?
2. **Tool name validity**: does the chosen tool exist?
3. **Termination**: does it stop within `max_turns=8`?
4. **Final output overlap**: do the scene IDs cited in the final formatted text overlap with Ministral's reference? (Jaccard ≥ 0.5 = pass)
5. **Judge score**: did the candidate's final formatted recall text help the scene generation? (Judge sees: user intent, both outputs, top-5 scene contents.)

This is the **hardest** workload to pass — small models often fail tool-call discipline. Expect Qwen3-4B and Gemma-3-4B to struggle; Granite-8B might do better.

---

## 8. Decision Criteria — When to Swap

Per task, three outcomes:

| Outcome | Definition | Action |
|---|---|---|
| **Swap-safe** | ≥ 95% auto-checks pass, judge ≥ 3.0 mean, ≥ 80% cases ≥ 3 | Update prod, monitor for one week |
| **Swap with caveat** | Auto-checks ≥ 95% but judge 2.5–3.0, OR auto ≥ 90% | Document caveat, hold for prompt tuning round before swap |
| **Keep on Ministral** | Anything below | No swap |

**Production swap criteria** (cumulative across tasks):
- Must be swap-safe on **T1 (decompose), T2 (recall agent), T3 (TTS), T7 (moderation)** — these are user-facing or block scene start.
- T4–T10 can each be evaluated independently; partial swaps are fine if routing supports it.

If a model wins decisively on cost/latency but loses on quality on one specific task, the routing layer (`_will_use_extraction_llm`) could be extended with per-task overrides — but that's a follow-up code change, not part of this benchmark.

---

## 9. Runtime & Cost Estimate

Per fixture: avg ~3s for single-turn (incl. judge), ~30s for T2 (8-turn agent replay).

Per model:
- T1 (15) + T3–T10 (~70 single-turn fixtures) × 3 runs × ~3s + judge ≈ 13 min
- T2 (6 traces) × 3 runs × ~30s + judge ≈ 9 min
- Model load + warm-up: ~2 min
- **Per model total: ~25 min**

3 models × 25 min ≈ **~75 min total wall-clock** for a full battery (baseline + 2 candidates). Add ~30 min for downloading the 2 candidate GGUFs from HF. Run unattended overnight or during a long meeting.

GPU power draw is the only cost — no API spend (judge is local main LLM too).

---

## 10. Report Format

`reports/<timestamp>/SUMMARY.md` example:

```markdown
# Extraction LLM Benchmark — 2026-05-13

## Models tested
- Ministral-3-8B-Q8 (baseline, current prod)
- Qwen3.5-4B (latest, Q5_K_M)
- Gemma-4-4B (latest, Q5_K_M)

## Per-task verdict

| Task | Ministral-8B (baseline) | Qwen3.5-4B | Gemma-4-4B |
|---|---|---|---|
| T1 Semantic Decompose | ✓ (3.7, 1.1s) | ✓ swap-safe (3.5, 0.7s) | ⚠ caveat (3.1, 0.6s) |
| T2 Recall Agent | ✓ (3.4, 28s) | ✗ keep (2.1 — tool format fails) | ✗ keep (1.8) |
| ... |

## Recommendation
- Swap to Qwen3.5-4B for T1, T3, T4, T5, T6, T8, T9, T10 — saves ~40% latency
- Stay on Ministral for T2 (recall agent) and T7 (moderation)
- Requires routing-layer change to support per-task model selection (out of scope this round)
```

---

## 11. Maintenance & Reuse — Adding a Future Model

The harness is built once and lives in the repo. To benchmark a future candidate (e.g. Qwen 4 5B when it ships, or Llama 5 nano):

```bash
cd backend/benchmarks/extraction_llm

# Option A — model already downloaded
python orchestrator/run_all.py --model ${MODELS_DIR}/SomeNewModel-Q5.gguf

# Option B — fetch from HF first, then benchmark
python orchestrator/run_all.py --hf-repo Qwen/Qwen4-5B-Instruct-GGUF --quant Q5_K_M

# Option C — add to config.yaml and re-run the full battery vs baseline + previous candidates
echo "  - name: Qwen4-5B-Q5" >> config.yaml
echo "    path: ${MODELS_DIR}/Qwen4-5B-Q5_K_M.gguf" >> config.yaml
python orchestrator/run_all.py --all
```

The harness:
- Always runs Ministral-8B-Q8 as the **baseline-of-record** at the start of every run (regenerates reference outputs so the comparison stays current with any production prompt changes).
- Uses the **same fixtures** every time (they're checked in). New models are evaluated against the same questions Ministral and earlier candidates were.
- Versions reports by timestamp in `reports/`, so historical comparisons remain on disk: `reports/2026-05-13_Qwen3.5-4B/`, `reports/2026-08-01_Qwen4-5B/`, etc. Aggregate trend reports are cheap to add later.

**Fixture additions are append-only**: when a new failure mode surfaces in production (e.g. a model nests JSON in a new way), add a synthetic fixture for it, commit, and from then on every model gets tested for that mode.

**Updating the baseline**: if production swaps to a new extraction model, change one line in `config.yaml` (`baseline_model:`). The new baseline becomes the bar for future candidates. Old reference outputs stay in fixture dirs as `reference_<model_name>.json` for diff comparisons.

---

## 12. Open Questions Before I Start

1. **Model set** — Lock in candidates: latest Qwen 3.5 4B + latest Gemma 4 small (both fresh from HF, NOT the older Qwen 3.0 / Gemma 3 already on disk). Add Granite-4.1-8B as a same-size control to Ministral?
2. **Quant choice** — Default plan is Q5_K_M for both candidates (~3 GB each, comfortably fits VRAM and roughly matches Q8 quality at ~⅔ the size). Bump to Q6_K if disk/VRAM allows for tighter quality match against baseline Q8?
3. **Capture window** — How many real scenes worth of debug logs do we capture before building fixtures? I'd suggest running 5–10 scenes in a real story to populate `logs/`.
4. **Judge model** — Use your main LLM (whichever provider you've configured)? Or use a known strong model like Mistral-Small-4-119B which is on disk?
5. **Run unattended** — OK for me to launch the full battery in the background and report results, or do you want me to walk through each model launch first to confirm it's loading correctly?

---

## 13. Phased Implementation

If you greenlight this design, I'd build it in phases so we can validate each piece:

1. **Phase 1 — Capture & fixtures** (1 hr): set up the dir, add the decompose-capture patch, run a few scenes, build the first 2-3 fixtures per task. Sanity-check fixtures by replaying through Ministral and confirming the recorded baseline output matches what production produced.
2. **Phase 2 — Single-turn runner + auto checks** (1–2 hr): T1, T3–T10 runners, auto-grading. Run Ministral baseline to populate reference outputs.
3. **Phase 3 — Judge layer** (1 hr): judge prompts, 3-call averaging, score aggregation.
4. **Phase 4 — Agent replay runner** (1–2 hr): T2 replay, scene-overlap scoring.
5. **Phase 5 — Orchestrator + model swap** (1 hr): `run_all.py`, launch/health/teardown scripts.
6. **Phase 6 — Full battery run + report** (~2 hr wall-clock).

Total active dev: ~7 hr. Plus 2 hr wall-clock for the actual benchmark run.
