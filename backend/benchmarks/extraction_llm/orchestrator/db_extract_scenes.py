#!/usr/bin/env python3
"""Extract a diverse pool of real scenes from the kahani database.

Pulls actual scene content from real stories — both SFW and NSFW —
across early/middle/late points in the story timeline. The output
populates `fixtures/_scenes_pool/`, which scene-driven suites (T3 TTS,
T4 scene events, T6 chapter summary, T10 NPCs) consume.

Why this matters:
- The captured `logs/prompt_*.json` files reflect only one user session
  on one story. The DB has 4 SFW + 3 NSFW stories with thousands of
  scenes — much better variety for benchmarking.
- Real scenes hit failure modes synthetic prompts never reach
  (e.g. character names that the model doesn't know how to attribute).

Reads the DB directly via psycopg, mapping to localhost:5432 (the
postgres container exposes it). Auth from the docker-compose default.

Usage:
    python orchestrator/db_extract_scenes.py [--user-id 2] [--per-story 4] [--force]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS_ROOT = HERE.parent
POOL_DIR = HARNESS_ROOT / "fixtures" / "_scenes_pool"


def run_psql_json(sql_select: str) -> list[dict]:
    """Run a SELECT and return rows as a list of dicts via json_agg.

    Why JSON instead of CSV/TSV: scene content has embedded newlines that
    break line-based parsing, and the postgres TTY layer mangles single-byte
    delimiters like \\x1f. JSON is unambiguous and round-trips cleanly.

    sql_select must be a SELECT statement (no trailing semicolon).
    """
    wrapped = f"SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) FROM ({sql_select}) t;"
    cmd = [
        "docker", "compose", "exec", "-T", "postgres",
        "psql", "-U", "kahani", "-d", "kahani",
        "-t", "-A",  # tuples only, unaligned
        "-c", wrapped,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True,
                          cwd=str(HARNESS_ROOT.parent.parent.parent))
    raw = proc.stdout.strip()
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"psql JSON output did not parse: {exc}\nfirst 500 chars: {raw[:500]}")


def pick_scenes_from_story(story_id: int, branch_id: int | None, per_story: int) -> list[dict]:
    """Pick scenes from beginning/middle/end of the story's active branch."""
    if branch_id is None:
        branch_filter = "AND s.branch_id IS NULL"
    else:
        branch_filter = f"AND s.branch_id = {branch_id}"

    stats = run_psql_json(
        f"SELECT MIN(sequence_number) AS min_seq, MAX(sequence_number) AS max_seq, "
        f"COUNT(*) AS cnt FROM scenes s WHERE s.story_id={story_id} "
        f"AND s.is_deleted=false {branch_filter}"
    )
    if not stats or not stats[0] or stats[0].get("cnt", 0) == 0:
        return []
    min_seq = stats[0]["min_seq"]
    max_seq = stats[0]["max_seq"]
    count = stats[0]["cnt"]

    if count <= per_story:
        select = f"""
        SELECT s.id AS scene_id, s.sequence_number, COALESCE(sv.title,'') AS title,
               sv.content,
               COALESCE(sv.characters_present, '[]'::json) AS characters_present
        FROM scenes s
        JOIN scene_variants sv ON sv.scene_id = s.id AND sv.is_original = true
        WHERE s.story_id = {story_id} AND s.is_deleted = false {branch_filter}
        ORDER BY s.sequence_number
        """
    else:
        step = (max_seq - min_seq) / (per_story - 1) if per_story > 1 else 0
        targets = [round(min_seq + step * i) for i in range(per_story)]
        select = f"""
        SELECT DISTINCT ON (s.sequence_number)
               s.id AS scene_id, s.sequence_number, COALESCE(sv.title,'') AS title,
               sv.content,
               COALESCE(sv.characters_present, '[]'::json) AS characters_present
        FROM scenes s
        JOIN scene_variants sv ON sv.scene_id = s.id AND sv.is_original = true
        WHERE s.story_id = {story_id}
          AND s.is_deleted = false
          {branch_filter}
          AND s.sequence_number IN (
            SELECT (
              SELECT s2.sequence_number FROM scenes s2
              WHERE s2.story_id = {story_id}
                AND s2.is_deleted = false
                {branch_filter.replace('s.', 's2.')}
              ORDER BY ABS(s2.sequence_number - targets.t) LIMIT 1
            )
            FROM (VALUES {','.join('(' + str(t) + ')' for t in targets)}) AS targets(t)
          )
        ORDER BY s.sequence_number
        """
    return run_psql_json(select)


def list_stories(owner_id: int) -> list[dict]:
    """Return all stories for the owner with metadata."""
    select = (
        f"SELECT id AS story_id, COALESCE(title,'') AS title, "
        f"COALESCE(content_rating,'sfw') AS content_rating, "
        f"COALESCE(genre,'') AS genre, "
        f"current_branch_id, "
        f"(SELECT COUNT(*) FROM scenes WHERE story_id=stories.id AND is_deleted=false)::int AS scene_count "
        f"FROM stories WHERE owner_id={owner_id} ORDER BY id"
    )
    return run_psql_json(select)


def write_pool_fixture(story: dict, scene: dict, force: bool) -> bool:
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    safe_title = "".join(c if c.isalnum() else "_" for c in story["title"]).strip("_")[:30]
    case_label = f"s{story['story_id']:02d}_{safe_title}_seq{scene['sequence_number']:03d}"
    path = POOL_DIR / f"{case_label}.json"
    if path.exists() and not force:
        return False

    fixture = {
        "task": "_scenes_pool",
        "case_id": case_label,
        "source": f"DB story_id={story['story_id']} sequence={scene['sequence_number']}",
        "story_meta": {
            "story_id": story["story_id"],
            "title": story["title"],
            "content_rating": story["content_rating"],
            "genre": story["genre"],
        },
        "scene": {
            "scene_id": scene["scene_id"],
            "sequence_number": scene["sequence_number"],
            "title": scene["title"],
            "content": scene["content"],
            "characters_present": scene["characters_present"],
        },
    }
    with path.open("w") as f:
        json.dump(fixture, f, indent=2, ensure_ascii=False)
    return True


def write_pool_readme():
    readme = POOL_DIR / "README.md"
    if readme.exists():
        return
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    readme.write_text(
        "# Scenes Pool\n\n"
        "Real scene content pulled from the kahani database — diverse mix of SFW and NSFW stories,\n"
        "with scenes from early/middle/late timeline positions in each.\n\n"
        "Each file is a raw scene record. Used as input to the scene-driven task suites\n"
        "(T3 TTS segments, T4 scene events, T5 working memory probes, T6 chapter summary, T10 NPCs).\n\n"
        "**This directory is checked in** — fixtures must be reproducible across machines without DB access.\n"
        "Regenerate with `python orchestrator/db_extract_scenes.py --force` after major story changes.\n\n"
        "**Privacy note**: real character names from your stories ARE captured here.\n"
        "If this repo ever becomes public, regenerate the pool from sanitized stub stories.\n"
    )


def main():
    parser = argparse.ArgumentParser(description="Extract scene pool from kahani DB.")
    parser.add_argument("--user-id", type=int, default=2, help="Owner user_id (default: 2)")
    parser.add_argument("--per-story", type=int, default=4,
                        help="Scenes per story to extract (default: 4 — beginning/early-mid/late-mid/end)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing pool fixtures")
    parser.add_argument("--max-stories-per-rating", type=int, default=2,
                        help="Cap stories per content_rating (default: 2 SFW + 2 NSFW)")
    args = parser.parse_args()

    stories = list_stories(args.user_id)
    if not stories:
        print(f"No stories for user_id={args.user_id}")
        return 1

    print(f"Found {len(stories)} stories for user {args.user_id}:")
    for s in stories:
        print(f"  [{s['content_rating']}] story {s['story_id']}: '{s['title']}' "
              f"({s['scene_count']} scenes, genre={s['genre']!r})")

    # Group + cap per rating; prefer stories with the most scenes
    by_rating: dict[str, list] = {}
    for s in sorted(stories, key=lambda x: -x["scene_count"]):
        rating = s["content_rating"].lower()
        if s["scene_count"] < args.per_story:
            continue  # not enough scenes to sample
        by_rating.setdefault(rating, []).append(s)

    picks = []
    for rating, story_list in by_rating.items():
        picks.extend(story_list[: args.max_stories_per_rating])

    print(f"\nWill extract {args.per_story} scenes from each of {len(picks)} stories:")
    written_count = 0
    for story in picks:
        print(f"\n  [{story['content_rating']}] {story['title']} (story_id={story['story_id']}):")
        scenes = pick_scenes_from_story(story["story_id"], story.get("current_branch_id"), args.per_story)
        for scene in scenes:
            written = write_pool_fixture(story, scene, args.force)
            marker = "+" if written else "="
            print(f"    {marker} seq {scene['sequence_number']:>3} "
                  f"({len(scene['content']):>5} chars, "
                  f"{len(scene['characters_present'])} chars present)")
            if written:
                written_count += 1

    write_pool_readme()
    print(f"\nDone. {written_count} scene fixtures written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
