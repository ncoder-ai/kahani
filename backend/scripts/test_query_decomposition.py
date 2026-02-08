"""
Test query decomposition + RRF using the ACTUAL prompt from logs/prompt_sent_scene.json.

Usage:
    docker compose exec backend python3 scripts/test_query_decomposition.py
"""

import asyncio
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def main():
    from app.database import SessionLocal
    from app.models import Story, Scene, Chapter
    from app.models.scene_variant import SceneVariant
    from app.services.context_manager import ContextManager
    from app.services.semantic_memory import initialize_semantic_memory_service
    from app.services.llm.service import UnifiedLLMService
    from app.config import settings as app_settings

    STORY_ID = 5
    USER_ID = 2

    # The REAL user_intent from logs/prompt_sent_scene.json message[16]
    USER_INTENT = (
        "After Ali leaves, Radhika also leaves to pick up the kids. "
        "Nishant is alone and incredibly turned on and hard. He goes to the living room and takes off his pants. "
        "His hands on his cock as he relives all the events, from Ali kissing her to undressing her "
        "bending her over the counter and teasing her and finally making her strip and roughly spanking and groping her."
    )

    db = SessionLocal()

    try:
        # Init semantic memory
        sm = initialize_semantic_memory_service(
            persist_directory=app_settings.semantic_db_path,
            embedding_model=app_settings.semantic_embedding_model
        )
        stats = await sm.get_collection_stats()
        print(f"\nChromaDB: {stats['scenes']} scene embeddings\n")

        # Get user settings
        from app.models.user_settings import UserSettings
        user_settings_row = db.query(UserSettings).filter(UserSettings.user_id == USER_ID).first()
        user_settings = user_settings_row.to_dict() if user_settings_row else {}

        print(f"{'='*70}")
        print(f"USER INTENT (from logs/prompt_sent_scene.json):")
        print(f"{USER_INTENT}")
        print(f"{'='*70}\n")

        # =====================================================
        # A) BASELINE: Single-query search (what we had before)
        # =====================================================
        print("=" * 70)
        print("A) BASELINE — Single combined query")
        print("=" * 70)
        baseline = await sm.search_similar_scenes(
            query_text=USER_INTENT,
            story_id=STORY_ID,
            top_k=15,
        )
        for r in baseline[:10]:
            sid = r['scene_id']
            scene = db.query(Scene).filter(Scene.id == sid).first()
            variant = db.query(SceneVariant).filter(SceneVariant.id == r['variant_id']).first()
            preview = (variant.content[:100] if variant else "?").replace('\n', ' ')
            print(f"  seq={r['sequence']:>3}  ch={r['chapter_id']:>3}  "
                  f"score={r['similarity_score']:.3f}  {preview}...")
        print()

        # =====================================================
        # B) Manually decomposed sub-queries (what the events actually are)
        # =====================================================
        sub_queries = [
            "Ali kissing Radhika",
            "Ali undressing Radhika",
            "Ali bending Radhika over the counter",
            "Ali teasing Radhika",
            "Ali making Radhika strip",
            "Ali spanking and groping Radhika",
        ]

        print("=" * 70)
        print("B) MANUAL SUB-QUERIES — Batch search + RRF")
        print(f"   Sub-queries: {sub_queries}")
        print("=" * 70)

        all_queries = [USER_INTENT] + sub_queries
        batch_results = await sm.search_similar_scenes_batch(
            query_texts=all_queries,
            story_id=STORY_ID,
            top_k=15,
        )

        # Show per-query top 3
        for i, results in enumerate(batch_results):
            label = "COMBINED" if i == 0 else f"sub-query: {sub_queries[i-1]}"
            top3 = [(r['sequence'], r['chapter_id'], r['similarity_score']) for r in results[:3]]
            print(f"  [{label}] top3 = {top3}")
        print()

        # RRF
        fused = ContextManager._reciprocal_rank_fusion(batch_results)
        print(f"  RRF fused {sum(len(r) for r in batch_results)} → {len(fused)} unique scenes\n")

        print("  TOP 15 after RRF:")
        for r in fused[:15]:
            sid = r['scene_id']
            variant = db.query(SceneVariant).filter(SceneVariant.id == r['variant_id']).first()
            preview = (variant.content[:100] if variant else "?").replace('\n', ' ')
            print(f"  seq={r['sequence']:>3}  ch={r['chapter_id']:>3}  "
                  f"rrf={r['similarity_score']:.3f}  {preview}...")
        print()

        # =====================================================
        # C) Full pipeline: extraction LLM decomposition + RRF
        # =====================================================
        ext_settings = user_settings.get('extraction_model_settings', {})
        if ext_settings.get('enabled'):
            print("=" * 70)
            print("C) FULL PIPELINE — Extraction LLM decomposition + multi-query + RRF")
            print("=" * 70)

            # Build context like real scene generation does
            ctx_settings = user_settings.get("context_settings", {})
            ctx_settings["context_strategy"] = "hybrid"
            ctx_settings["enable_semantic_memory"] = True
            user_settings_copy = dict(user_settings)
            user_settings_copy["context_settings"] = ctx_settings

            cm = ContextManager(user_settings=user_settings_copy, user_id=USER_ID)

            scenes = db.query(Scene).filter(
                Scene.story_id == STORY_ID
            ).order_by(Scene.sequence_number).all()

            active_chapter = db.query(Chapter).filter(
                Chapter.story_id == STORY_ID,
                Chapter.status == 'active'
            ).first()
            chapter_id = active_chapter.id if active_chapter else None

            context = await cm._build_hybrid_scene_context(
                story_id=STORY_ID,
                scenes=scenes[-30:],
                available_tokens=8000,
                db=db,
                chapter_id=chapter_id,
                user_intent=USER_INTENT,
            )

            # Build messages
            llm_service = UnifiedLLMService()
            messages = llm_service._build_cache_friendly_message_prefix(
                context=context,
                user_id=USER_ID,
                user_settings=user_settings,
                db=db
            )

            # Show BEFORE
            for m in messages:
                if "=== RELATED PAST SCENES ===" in m.get("content", ""):
                    print(f"\n  BEFORE decomposition ({len(m['content'])} chars):")
                    # Show scene numbers found
                    import re
                    scene_nums = re.findall(r'Relevant from Scene (\d+)', m['content'])
                    print(f"  Scenes: {scene_nums}")
                    break

            # Run full pipeline
            improved = await llm_service._maybe_improve_semantic_scenes(
                messages=messages,
                context=context,
                user_settings=user_settings,
                db=db
            )

            print(f"\n  Decomposition result: {'IMPROVED' if improved else 'NOT IMPROVED'}")

            if improved:
                for m in messages:
                    if "=== RELATED PAST SCENES ===" in m.get("content", ""):
                        print(f"\n  AFTER decomposition ({len(m['content'])} chars):")
                        scene_nums = re.findall(r'Relevant from Scene (\d+)', m['content'])
                        print(f"  Scenes: {scene_nums}")
                        # Show content
                        print(f"\n{m['content'][:3000]}")
                        break
        else:
            print("C) SKIPPED — Extraction model not enabled")

        print(f"\n{'='*70}")
        print("DONE")
        print(f"{'='*70}")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
