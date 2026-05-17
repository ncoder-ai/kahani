# Scenes Pool

Real scene content pulled from the kahani database — diverse mix of SFW and NSFW stories,
with scenes from early/middle/late timeline positions in each.

Each file is a raw scene record. Used as input to the scene-driven task suites
(T3 TTS segments, T4 scene events, T5 working memory probes, T6 chapter summary, T10 NPCs).

**This directory is checked in** — fixtures must be reproducible across machines without DB access.
Regenerate with `python orchestrator/db_extract_scenes.py --force` after major story changes.

**Privacy note**: real character names from your stories ARE captured here.
If this repo ever becomes public, regenerate the pool from sanitized stub stories.
