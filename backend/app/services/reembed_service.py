"""
Re-embedding Service

Handles re-embedding all vector data when the embedding model or dimensions change.
Runs as a background task with progress tracking.
"""

import logging
import asyncio
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ReembedService:
    """
    Re-embeds all vector tables when embedding model changes.

    Tables with embeddings:
    - scene_embeddings: uses stored embedding_text (falls back to scene content)
    - character_memories: uses content column
    - plot_events: uses description column
    - character_chronicles: uses description column
    - location_lorebooks: uses event_description column
    - scene_events: uses event_text column
    """

    # (table_name, model_class_path, text_column)
    # scene_embeddings disabled — recall now uses event embeddings exclusively
    TABLES = [
        # ("scene_embeddings", "SceneEmbedding", "embedding_text"),
        ("character_memories", "CharacterMemory", "content"),
        ("plot_events", "PlotEvent", "description"),
        ("character_chronicles", "CharacterChronicle", "description"),
        ("location_lorebooks", "LocationLorebook", "event_description"),
        ("scene_events", "SceneEvent", "event_text"),
    ]

    def __init__(self):
        self._progress: Dict[int, Dict[str, Any]] = {}
        self._cancel_flags: Dict[int, bool] = {}

    def get_progress(self, user_id: int) -> Dict[str, Any]:
        return self._progress.get(user_id, {
            "status": "idle",
            "current_table": "",
            "processed": 0,
            "total": 0,
            "errors": 0,
            "message": "",
        })

    def cancel(self, user_id: int):
        self._cancel_flags[user_id] = True

    async def start_reembed(self, user_id: int, new_dimension: int):
        """Main re-embedding workflow"""
        from ..database import SessionLocal, engine as db_engine

        self._cancel_flags[user_id] = False
        self._progress[user_id] = {
            "status": "running",
            "current_table": "initializing",
            "processed": 0,
            "total": 0,
            "errors": 0,
            "message": "Starting re-embedding...",
        }

        try:
            # Step 1: ALTER vector columns if dimension changed
            self._progress[user_id]["message"] = "Altering vector columns..."
            await self._alter_vector_columns(new_dimension, db_engine)

            # Step 2: Re-embed each table
            total_rows = 0
            total_errors = 0

            for table_name, model_name, text_column in self.TABLES:
                if self._cancel_flags.get(user_id):
                    self._progress[user_id]["status"] = "cancelled"
                    self._progress[user_id]["message"] = "Cancelled by user"
                    return

                self._progress[user_id]["current_table"] = table_name
                self._progress[user_id]["message"] = f"Processing {table_name}..."

                rows, errors = await self._reembed_table(
                    table_name, model_name, text_column, user_id
                )
                total_rows += rows
                total_errors += errors

            # Step 3: Clear event embedding cache
            try:
                from .context_manager import ContextManager
                ContextManager._event_embedding_cache = {}
                logger.info("Cleared event embedding cache")
            except Exception:
                pass

            # Step 4: Clear needs_reembed flag
            with SessionLocal() as db:
                from ..models import UserSettings
                us = db.query(UserSettings).first()
                if us:
                    us.embedding_needs_reembed = False
                    db.commit()

            self._progress[user_id] = {
                "status": "completed",
                "current_table": "",
                "processed": total_rows,
                "total": total_rows,
                "errors": total_errors,
                "message": f"Re-embedding complete. {total_rows} rows processed, {total_errors} errors.",
            }

        except Exception as e:
            logger.error(f"Re-embedding failed: {e}", exc_info=True)
            self._progress[user_id]["status"] = "error"
            self._progress[user_id]["message"] = f"Error: {str(e)}"

    async def _alter_vector_columns(self, new_dimension: int, engine):
        """ALTER all vector columns to new dimension and rebuild HNSW indexes"""
        from sqlalchemy import text

        # scene_embeddings disabled — recall now uses event embeddings exclusively
        tables_and_indexes = [
            # ("scene_embeddings", "ix_scene_embeddings_embedding_hnsw"),
            ("character_memories", "ix_character_memories_embedding_hnsw"),
            ("plot_events", "ix_plot_events_embedding_hnsw"),
            ("character_chronicles", "ix_character_chronicles_embedding_hnsw"),
            ("location_lorebooks", "ix_location_lorebooks_embedding_hnsw"),
            ("scene_events", "ix_scene_events_embedding_hnsw"),
        ]

        def _alter():
            with engine.connect() as conn:
                for table_name, index_name in tables_and_indexes:
                    # Drop HNSW index if exists (silently ignore if not found)
                    conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))

                    # Set all embeddings to NULL (required before ALTER type)
                    conn.execute(text(f"UPDATE {table_name} SET embedding = NULL"))

                    # ALTER column type
                    conn.execute(text(
                        f"ALTER TABLE {table_name} ALTER COLUMN embedding TYPE vector({new_dimension})"
                    ))

                    # Recreate HNSW index
                    conn.execute(text(
                        f"CREATE INDEX {index_name} ON {table_name} "
                        f"USING hnsw (embedding vector_cosine_ops)"
                    ))

                conn.commit()

        await asyncio.to_thread(_alter)
        logger.info(f"Altered all vector columns to dimension {new_dimension}")

    async def _reembed_table(
        self, table_name: str, model_name: str, text_column: str, user_id: int,
        batch_size: int = 50
    ) -> tuple:
        """Re-embed all rows in a table. Returns (processed_count, error_count)."""
        from ..database import SessionLocal
        from ..models.semantic_memory import SceneEmbedding, CharacterMemory, PlotEvent
        from ..models.chronicle import CharacterChronicle, LocationLorebook
        from ..models.scene_event import SceneEvent
        from .semantic_memory import get_semantic_memory_service

        model_map = {
            "SceneEmbedding": SceneEmbedding,
            "CharacterMemory": CharacterMemory,
            "PlotEvent": PlotEvent,
            "CharacterChronicle": CharacterChronicle,
            "LocationLorebook": LocationLorebook,
            "SceneEvent": SceneEvent,
        }

        model_class = model_map[model_name]
        semantic_memory = get_semantic_memory_service()

        processed = 0
        errors = 0

        with SessionLocal() as db:
            total = db.query(model_class).count()
            self._progress[user_id]["total"] = total

            offset = 0
            while True:
                if self._cancel_flags.get(user_id):
                    break

                rows = db.query(model_class).order_by(model_class.id).offset(offset).limit(batch_size).all()
                if not rows:
                    break

                texts = []
                valid_rows = []

                for row in rows:
                    text_value = getattr(row, text_column, None)

                    # For scene_embeddings, fall back to joining scene content if embedding_text is NULL
                    if not text_value and model_name == "SceneEmbedding":
                        try:
                            from ..models import SceneVariant
                            variant = db.query(SceneVariant).filter(
                                SceneVariant.id == row.variant_id
                            ).first()
                            if variant and variant.content:
                                text_value = variant.content[:1000]
                        except Exception:
                            pass

                    if text_value:
                        texts.append(text_value)
                        valid_rows.append(row)

                if texts:
                    try:
                        embeddings = await semantic_memory.encode_texts(texts)
                        for row, emb in zip(valid_rows, embeddings):
                            row.embedding = emb.tolist()
                        db.commit()
                        processed += len(valid_rows)
                    except Exception as e:
                        logger.error(f"Batch embedding failed for {table_name}: {e}")
                        db.rollback()
                        errors += len(texts)

                self._progress[user_id]["processed"] = processed
                self._progress[user_id]["errors"] = errors
                offset += batch_size

        return processed, errors


# Global singleton
_reembed_service: Optional[ReembedService] = None


def get_reembed_service() -> ReembedService:
    global _reembed_service
    if _reembed_service is None:
        _reembed_service = ReembedService()
    return _reembed_service
