# Backfill Report - Story ID 5

**Date:** 2026-01-25 / 2026-01-26
**Script:** `docker compose exec -d backend python scripts/backfill_story.py --story-id 5 --user-id 2`
**Process PID:** 208 (inside container)
**Duration:** ~3 hours 45 minutes (monitored from start to completion across 45 checks at 5-min intervals)

---

## Summary

All 4 backfill operations completed successfully without any crashes or restarts required. The process ran continuously from start to finish.

| Operation | Status | Details |
|-----------|--------|---------|
| Relationships | PASS | 839 events, seq range 1-218 |
| Chapter Summaries | PASS | 15/15 chapters summarized |
| Entity States | PASS | 81 entity state batches (pre-existing, validated) |
| Working Memory | PASS | 1 entry for branch 8 |

---

## 1. Character Relationships

### Counts
- **Total relationship events:** 839
- **Sequence range:** 1 to 218
- **Expected:** 400+ events, max seq ~218
- **Result:** PASS

### Branch Breakdown
| Branch | Events | Max Sequence |
|--------|--------|-------------|
| Branch 8 | 454 | 218 |
| Branch 6 | 385 | 186 |

### Character Pair Breakdown
| Pair | Events |
|------|--------|
| Ali <-> Radhika Sharma | 299 |
| Nishant Saran <-> Radhika Sharma | 245 |
| Ali <-> Nishant Saran | 174 |
| Ahmad <-> Radhika Sharma | 64 |
| Ahmad <-> Ali | 56 |
| Divit <-> Radhika Sharma | 1 |

### Character Names
- **Canonical names found:** Ali, Nishant Saran, Radhika Sharma, Ahmad
- **Additional names:** Divit (1 event at scene 144, branch 6 -- a legitimate minor character, Radhika's friend at school)
- **Non-canonical/duplicate names:** None
- **Result:** PASS (Divit is a valid minor character, not a data issue)

### Duplicate Check
- **Duplicate pairs per scene+branch:** None found
- **Result:** PASS

### Relationship Summaries
- **Total:** 11 summaries generated
- Nishant Saran <-> Radhika Sharma (branches 6, 8)
- Ali <-> Radhika Sharma (branches 6, 8)
- Ali <-> Nishant Saran (branches 6, 8)
- Ahmad <-> Ali (branches 6, 8)
- Ahmad <-> Radhika Sharma (branches 6, 8)
- Divit <-> Radhika Sharma (branch 6)

---

## 2. Chapter Summaries

- **Chapters with summaries:** 15/15
- **Summary batches created:** 48
- **Result:** PASS

| Chapter | Branch | Summary Length |
|---------|--------|---------------|
| Ch 1 | (branch A) | 8,047 chars |
| Ch 1 | (branch B) | 8,108 chars |
| Ch 2 | (branch A) | 8,773 chars |
| Ch 2 | (branch B) | 8,800 chars |
| Ch 3 | (branch A) | 6,403 chars |
| Ch 3 | (branch B) | 8,637 chars |
| Ch 4 | (branch A) | 8,640 chars |
| Ch 4 | (branch B) | 8,571 chars |
| Ch 5 | (branch A) | 8,678 chars |
| Ch 5 | (branch B) | 8,708 chars |
| Ch 6 | (branch A) | 8,708 chars |
| Ch 6 | (branch B) | 9,584 chars |
| Ch 7 | (branch A) | 8,019 chars |
| Ch 7 | (branch B) | 8,796 chars |
| Ch 8 | (one branch) | 3,007 chars |

Note: The story has branching at some point, resulting in 2 versions of chapters 1-7 across branches 6 and 8, and chapter 8 on one branch. This is 15 total chapter records, all successfully summarized.

---

## 3. Entity States

- **Entity state batches:** 81
- These were pre-existing from prior story operations and were validated/re-extracted during the backfill
- **Result:** PASS

---

## 4. Working Memory

- **Entries:** 1
- **Branch:** 8
- **Last scene sequence:** 218
- **Chapter ID:** 35
- **Recent focus items:** 3 (covering Radhika's emotional growth, Nishant's role, and theme of visibility)
- **Character spotlight:** Divit (breakfast scene follow-up)
- **Pending items:** 0
- **Result:** PASS

---

## Processing Timeline

| Time (approx) | Milestone |
|---------------|-----------|
| T+0 min | Start - relationships begin processing |
| T+5 min | 41 events, seq 16 |
| T+10 min | 99 events, seq 29 |
| T+25 min | 204 events, seq 52 |
| T+45 min | 340 events, seq 85 |
| T+65 min | 470 events, seq 117 |
| T+80 min | 570 events, seq 138 |
| T+90 min | 616 events, seq 147 |
| T+95 min | 664 events, seq 163 |
| T+105 min | 764 events, seq 185 |
| T+115 min | 811 events, seq 204 |
| T+120 min | 839 events, seq 218 -- Relationships COMPLETE |
| T+120 min | Chapter summaries begin, 1/15 done |
| T+135 min | 3/15 chapters |
| T+155 min | 5/15 chapters |
| T+180 min | 7/15 chapters |
| T+205 min | 9/15 chapters |
| T+215 min | 10/15 chapters |
| T+225 min | 12/15 chapters |
| T+235 min | 14/15 chapters |
| T+245 min | 15/15 chapters -- Summaries COMPLETE |
| T+245 min | Entity states + Working memory complete |
| T+245 min | Process exits cleanly |

**Total wall time:** ~245 minutes (~4 hours 5 minutes)
- Relationships: ~120 minutes
- Chapter summaries: ~125 minutes
- Entity states + Working memory: <5 minutes (entities pre-existing, memory rebuilt quickly)

---

## Incidents

**None.** The backfill process ran without interruption. No crashes, no restarts required. All 45 monitoring checks showed consistent forward progress.

---

## Overall Assessment

**ALL CHECKS PASS.** The backfill completed successfully with:
- 839 relationship events covering all 218 scene sequences across 2 branches
- 11 relationship summaries for all significant character pairs
- 15/15 chapter summaries with substantive content (3,000-9,600 chars each)
- 81 entity state batches
- Working memory rebuilt for the latest branch (branch 8, seq 218)
- Zero duplicate relationship entries
- Clean character name canonicalization (only 1 minor character "Divit" beyond the 4 main characters)
