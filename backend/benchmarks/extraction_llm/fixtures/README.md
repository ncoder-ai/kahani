# Fixtures

Each subdirectory is a test suite. Fixtures are JSON files with this shape:

```json
{
  "task": "T<N>_<name>",
  "case_id": "real_001" | "probe_<failure_mode>_NN",
  "source": "captured from logs/..." | "synthetic — <intent>",
  "messages": [...],
  "request_params": {"temperature": ..., "max_tokens": ...},
  "expected_schema": { ... },        // task-specific shape
  "rubric_notes": "..."           // optional — guides judge
}
```

Two categories:
- `real_NN` — extracted from captured `logs/prompt_*.json` files.
- `probe_NN` — hand-written edge cases targeting known small-model failure modes.

Adding a fixture: drop a JSON file in the appropriate suite dir and re-run baseline.
T2 fixtures (recall agent) are full trace replays — different shape, see one to learn the format.
