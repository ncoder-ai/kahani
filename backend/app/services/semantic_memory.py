"""
Semantic Memory Service using pgvector and Sentence Transformers

Provides vector-based semantic search capabilities for story content,
enabling intelligent context retrieval beyond simple recency-based selection.

Vectors are stored directly in PostgreSQL via pgvector — no external vector DB.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

# SentenceTransformer is imported lazily in _ensure_model_loaded to avoid blocking startup
import hashlib

logger = logging.getLogger(__name__)


class SemanticMemoryService:
    """
    Manages semantic memory using pgvector for vector storage and retrieval.

    Features:
    - Scene-level embeddings for semantic search
    - Character moment embeddings for character consistency
    - Plot event embeddings for thread tracking
    - Efficient similarity search with metadata filtering
    - SQL-native branch filtering (no post-hoc filtering)

    Note: All blocking operations (model inference, database I/O) are wrapped
    in asyncio.to_thread() to prevent blocking the event loop.
    """

    def __init__(self, embedding_model: str = "sentence-transformers/all-mpnet-base-v2", reranker_model: str = "BAAI/bge-reranker-v2-m3", enable_reranking: bool = True):
        """
        Initialize the semantic memory service

        Args:
            embedding_model: Sentence transformer model name
            reranker_model: Cross-encoder model for reranking
            enable_reranking: Whether to enable cross-encoder reranking
        """
        self.embedding_model_name = embedding_model
        self.reranker_model_name = reranker_model

        # Import SessionLocal for database access (search + delete ops)
        from ..database import SessionLocal
        self._session_factory = SessionLocal

        # Lazy-load embedding model to avoid blocking startup
        self.embedding_model = None
        self._embedding_dimension = None

        # Lazy-load reranker model
        self.reranker = None
        self.enable_reranking = enable_reranking

        logger.info("SemanticMemoryService initialized (pgvector backend)")

    async def check_embedding_dimension_compatibility(self) -> Dict[str, Any]:
        """
        Check if existing embeddings are compatible with current model dimension.

        Returns:
            Dict with compatibility info
        """
        from ..models.semantic_memory import SceneEmbedding

        await self._ensure_model_loaded()
        current_dim = self._embedding_dimension

        try:
            def _check():
                with self._session_factory() as session:
                    count = session.query(SceneEmbedding).filter(
                        SceneEmbedding.embedding.isnot(None)
                    ).count()
                    return count

            count = await asyncio.to_thread(_check)

            if count == 0:
                return {
                    'compatible': True,
                    'current_model_dimension': current_dim,
                    'existing_dimension': None,
                    'existing_count': 0,
                    'needs_reembed': False,
                    'message': 'No existing embeddings'
                }

            # pgvector enforces dimension at column level (Vector(768)),
            # so if data exists, it matches the column dimension
            return {
                'compatible': current_dim == 768,
                'current_model_dimension': current_dim,
                'existing_dimension': 768,
                'existing_count': count,
                'needs_reembed': current_dim != 768,
                'message': 'Embeddings compatible' if current_dim == 768 else f'Dimension mismatch: column is 768 but model produces {current_dim}'
            }

        except Exception as e:
            logger.error(f"Error checking embedding compatibility: {e}")
            return {
                'compatible': False,
                'current_model_dimension': current_dim,
                'existing_dimension': None,
                'existing_count': 0,
                'needs_reembed': True,
                'message': f'Error checking compatibility: {str(e)}'
            }

    async def clear_story_embeddings(self, story_id: int) -> int:
        """
        Clear all scene embeddings for a specific story.

        Args:
            story_id: Story ID to clear embeddings for

        Returns:
            Number of embeddings cleared
        """
        from ..models.semantic_memory import SceneEmbedding

        try:
            def _clear():
                with self._session_factory() as session:
                    count = session.query(SceneEmbedding).filter(
                        SceneEmbedding.story_id == story_id,
                        SceneEmbedding.embedding.isnot(None)
                    ).count()
                    session.query(SceneEmbedding).filter(
                        SceneEmbedding.story_id == story_id
                    ).update({SceneEmbedding.embedding: None})
                    session.commit()
                    return count

            count = await asyncio.to_thread(_clear)
            logger.info(f"Cleared {count} scene embeddings for story {story_id}")
            return count

        except Exception as e:
            logger.error(f"Error clearing story embeddings: {e}")
            raise

    async def clear_all_scene_embeddings(self) -> int:
        """
        Clear ALL scene embeddings.
        Use this when embedding model dimension changes.

        Returns:
            Number of embeddings that were cleared
        """
        from ..models.semantic_memory import SceneEmbedding

        try:
            def _clear_all():
                with self._session_factory() as session:
                    count = session.query(SceneEmbedding).filter(
                        SceneEmbedding.embedding.isnot(None)
                    ).count()
                    session.query(SceneEmbedding).update({SceneEmbedding.embedding: None})
                    session.commit()
                    return count

            count = await asyncio.to_thread(_clear_all)
            logger.warning(f"Cleared all scene embeddings ({count} total)")
            return count

        except Exception as e:
            logger.error(f"Error clearing all embeddings: {e}")
            raise

    def _load_embedding_model_sync(self):
        """Synchronous model loading - to be called via asyncio.to_thread()"""
        from sentence_transformers import SentenceTransformer
        self.embedding_model = SentenceTransformer(self.embedding_model_name)
        self._embedding_dimension = self.embedding_model.get_sentence_embedding_dimension()

    async def _ensure_model_loaded(self):
        """Lazy-load the embedding model on first use (async)"""
        if self.embedding_model is None:
            logger.info(f"Loading embedding model: {self.embedding_model_name}")
            # Run blocking model loading in thread pool
            await asyncio.to_thread(self._load_embedding_model_sync)
            logger.info(f"Embedding model loaded successfully. Dimension: {self._embedding_dimension}")

    def _load_reranker_model_sync(self):
        """Synchronous reranker loading - to be called via asyncio.to_thread()"""
        from sentence_transformers import CrossEncoder
        self.reranker = CrossEncoder(self.reranker_model_name)

    async def encode_texts(self, texts: List[str]) -> "np.ndarray":
        """
        Encode a list of texts into embeddings using the bi-encoder.
        Returns numpy array of shape (len(texts), embedding_dim).
        Handles model loading and threading automatically.
        """
        import numpy as np
        await self._ensure_model_loaded()
        embeddings = await asyncio.to_thread(
            lambda: self.embedding_model.encode(
                texts, convert_to_numpy=True, show_progress_bar=False
            )
        )
        return embeddings

    async def _ensure_reranker_loaded(self):
        """Lazy-load the reranker model on first use (async)"""
        if self.reranker is None and self.enable_reranking:
            logger.info(f"Loading reranker model: {self.reranker_model_name}")
            # Run blocking model loading in thread pool
            await asyncio.to_thread(self._load_reranker_model_sync)
            logger.info(f"Reranker model loaded successfully")

    async def rerank_scenes(
        self,
        query_text: str,
        scene_contents: Dict[int, str],
        top_k: int = 30
    ) -> Optional[Dict[int, float]]:
        """
        Rerank scenes using cross-encoder for precise relevance scoring.

        Takes (query, document) pairs and scores them jointly, enabling the model
        to detect semantic matches that bi-encoders miss.

        Args:
            query_text: User intent / query string
            scene_contents: Dict of scene_id -> scene content text
            top_k: Max scenes to rerank (for performance)

        Returns:
            Dict of scene_id -> normalized cross-encoder score [0, 1], or None if
            reranking is disabled or fails.
        """
        if not self.enable_reranking or not scene_contents:
            return None

        try:
            await self._ensure_reranker_loaded()
            if self.reranker is None:
                return None

            # Build (query, document) pairs for top_k scenes
            scene_ids = list(scene_contents.keys())[:top_k]
            pairs = [(query_text, scene_contents[sid]) for sid in scene_ids]

            # Run cross-encoder in thread pool (CPU-intensive)
            raw_scores = await asyncio.to_thread(self.reranker.predict, pairs)

            # Normalize scores to [0, 1] via sigmoid (bge-reranker outputs raw logits)
            import math
            scores = {}
            for sid, raw in zip(scene_ids, raw_scores):
                scores[sid] = 1.0 / (1.0 + math.exp(-float(raw)))

            logger.info(f"[RERANK] Reranked {len(scores)} scenes. "
                       f"Score range: [{min(scores.values()):.3f}, {max(scores.values()):.3f}]")
            return scores

        except Exception as e:
            logger.warning(f"[RERANK] Cross-encoder reranking failed: {e}")
            return None

    def _generate_embedding_sync(self, text: str) -> List[float]:
        """Synchronous embedding generation - to be called via asyncio.to_thread()"""
        embedding = self.embedding_model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text (async)

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding
        """
        try:
            await self._ensure_model_loaded()
            # Run CPU-intensive encoding in thread pool
            embedding = await asyncio.to_thread(self._generate_embedding_sync, text)
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

    # Scene Embeddings

    async def add_scene_embedding(
        self,
        scene_id: int,
        variant_id: int,
        story_id: int,
        content: str,
        metadata: Dict[str, Any]
    ) -> Tuple[str, List[float]]:
        """
        Generate embedding for a scene.

        Pure computation — no database side-effects. Caller stores the result.

        Args:
            scene_id: Scene ID
            variant_id: Scene variant ID
            story_id: Story ID
            content: Scene content text
            metadata: Additional metadata (chapter_id, sequence, characters, etc.)

        Returns:
            Tuple of (embedding_id, embedding_vector)
        """
        try:
            embedding_id = f"scene_{scene_id}_v{variant_id}"

            # Generate embedding (async)
            embedding = await self.generate_embedding(content)

            logger.info(f"Generated scene embedding: {embedding_id}")
            return embedding_id, embedding

        except Exception as e:
            logger.error(f"Failed to generate scene embedding: {e}")
            raise

    async def search_similar_scenes(
        self,
        query_text: str,
        story_id: int,
        top_k: int = 5,
        exclude_sequences: Optional[List[int]] = None,
        chapter_id: Optional[int] = None,
        branch_id: Optional[int] = None,
        use_reranking: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search for semantically similar scenes with optional cross-encoder reranking

        Two-stage retrieval:
        1. Fast bi-encoder retrieval via pgvector (get candidates)
        2. Precise cross-encoder reranking (narrow to top_k)

        Args:
            query_text: Query text (e.g., recent scene content)
            story_id: Story ID to filter by
            top_k: Number of results to return
            exclude_sequences: Scene sequences to exclude (e.g., recent scenes)
            chapter_id: Optional chapter filter
            branch_id: Optional branch filter (SQL-native, not post-hoc)
            use_reranking: Whether to use cross-encoder reranking

        Returns:
            List of similar scenes with metadata and similarity scores
        """
        from ..models.semantic_memory import SceneEmbedding

        try:
            # Stage 1: Fast retrieval with bi-encoder
            retrieval_k = top_k * 3 if (use_reranking and self.enable_reranking) else top_k * 2

            # Generate query embedding (async)
            query_embedding = await self.generate_embedding(query_text)

            def _db_search():
                with self._session_factory() as session:
                    query = (
                        session.query(
                            SceneEmbedding,
                            SceneEmbedding.embedding.cosine_distance(query_embedding).label('distance')
                        )
                        .filter(SceneEmbedding.story_id == story_id)
                        .filter(SceneEmbedding.embedding.isnot(None))
                    )
                    # Branch filtering — SQL-native, not post-hoc
                    if branch_id is not None:
                        query = query.filter(
                            (SceneEmbedding.branch_id == branch_id) |
                            (SceneEmbedding.branch_id.is_(None))
                        )
                    if chapter_id is not None:
                        query = query.filter(SceneEmbedding.chapter_id == chapter_id)
                    if exclude_sequences:
                        query = query.filter(~SceneEmbedding.sequence_order.in_(exclude_sequences))

                    query = query.order_by('distance').limit(retrieval_k)
                    return query.all()

            results = await asyncio.to_thread(_db_search)

            # Process and filter results
            candidates = []
            for row, distance in results:
                # Normalize cosine distance to similarity score
                # pgvector cosine_distance returns [0, 2] where 0 = identical
                # Cosine distance range [0, 2]: similarity = max(0, 1 - (distance / 2))
                normalized_similarity = max(0.0, 1.0 - (distance / 2.0))

                candidates.append({
                    'embedding_id': row.embedding_id,
                    'scene_id': row.scene_id,
                    'variant_id': row.variant_id,
                    'sequence': row.sequence_order,
                    'chapter_id': row.chapter_id,
                    'bi_encoder_score': normalized_similarity,
                    'timestamp': row.created_at.isoformat() if row.created_at else '',
                    'characters': '[]',
                })

            if not candidates:
                logger.info(f"No candidates found for story {story_id}")
                return []

            # Stage 2: Cross-encoder reranking (if enabled)
            if use_reranking and self.enable_reranking and len(candidates) > top_k:
                try:
                    await self._ensure_reranker_loaded()

                    # We need the document text for reranking — fetch from DB
                    embedding_ids = [c['embedding_id'] for c in candidates]

                    def _fetch_texts():
                        with self._session_factory() as session:
                            from ..models import SceneVariant
                            rows = session.query(
                                SceneEmbedding.embedding_id,
                                SceneVariant.content
                            ).join(
                                SceneVariant, SceneEmbedding.variant_id == SceneVariant.id
                            ).filter(
                                SceneEmbedding.embedding_id.in_(embedding_ids)
                            ).all()
                            return {r[0]: r[1] for r in rows}

                    doc_texts = await asyncio.to_thread(_fetch_texts)

                    # Prepare query-document pairs
                    pairs = []
                    valid_candidates = []
                    for candidate in candidates:
                        text = doc_texts.get(candidate['embedding_id'])
                        if text:
                            pairs.append([query_text, text[:2000]])
                            valid_candidates.append(candidate)

                    if pairs:
                        # Get reranking scores - run in thread pool
                        rerank_scores = await asyncio.to_thread(self.reranker.predict, pairs)

                        # Update candidates with reranked scores
                        for candidate, rerank_score in zip(valid_candidates, rerank_scores):
                            candidate['rerank_score'] = float(rerank_score)
                            candidate['similarity_score'] = float(rerank_score)

                        # Sort by reranked scores
                        valid_candidates.sort(key=lambda x: x['rerank_score'], reverse=True)
                        candidates = valid_candidates

                        logger.info(f"Reranked {len(candidates)} candidates for story {story_id}")
                    else:
                        # No texts found for reranking, fall back to bi-encoder scores
                        for candidate in candidates:
                            candidate['similarity_score'] = candidate['bi_encoder_score']
                        candidates.sort(key=lambda x: x['bi_encoder_score'], reverse=True)

                except Exception as e:
                    logger.warning(f"Reranking failed, falling back to bi-encoder scores: {e}")
                    # Fall back to bi-encoder scores
                    for candidate in candidates:
                        candidate['similarity_score'] = candidate['bi_encoder_score']
                    candidates.sort(key=lambda x: x['bi_encoder_score'], reverse=True)
            else:
                # No reranking - use bi-encoder scores
                for candidate in candidates:
                    candidate['similarity_score'] = candidate['bi_encoder_score']
                candidates.sort(key=lambda x: x['bi_encoder_score'], reverse=True)

            # Return top_k results
            final_results = candidates[:top_k]

            logger.info(f"Returning {len(final_results)} similar scenes for story {story_id}")
            return final_results

        except Exception as e:
            logger.error(f"Failed to search similar scenes: {e}")
            return []

    async def search_similar_scenes_batch(
        self,
        query_texts: List[str],
        story_id: Optional[int] = None,
        story_ids: Optional[List[int]] = None,
        branch_map: Optional[Dict[int, int]] = None,
        top_k: int = 5,
        exclude_sequences: Optional[List[int]] = None,
        exclude_story_id: Optional[int] = None,
        chapter_id: Optional[int] = None
    ) -> List[List[Dict[str, Any]]]:
        """
        Batch search for semantically similar scenes using multiple queries.

        Uses single batch encode + per-query pgvector searches for efficiency.
        No reranking — RRF acts as the fusion mechanism downstream.

        Args:
            query_texts: List of query texts to search for
            story_id: Single story ID to filter by (backward compat)
            story_ids: Multiple story IDs for world-scope search
            branch_map: {story_id: branch_id} for per-story branch filtering (world-scope)
            top_k: Number of results per query
            exclude_sequences: Scene sequences to exclude (only for exclude_story_id)
            exclude_story_id: Story whose sequences to exclude (defaults to story_id)
            chapter_id: Optional chapter filter

        Returns:
            List of result lists — one per query, same dict structure as search_similar_scenes()
        """
        from ..models.semantic_memory import SceneEmbedding
        from sqlalchemy import or_, and_

        if not query_texts:
            return []

        # Backward compat: if story_id provided but not story_ids, use single-story mode
        if story_ids is None and story_id is not None:
            story_ids = [story_id]
        if exclude_story_id is None:
            exclude_story_id = story_id

        try:
            await self._ensure_model_loaded()

            # Single batch encode (one GPU pass)
            query_embeddings = await asyncio.to_thread(
                lambda: self.embedding_model.encode(query_texts, convert_to_numpy=True).tolist()
            )

            retrieval_k = top_k * 2

            def _db_batch_search():
                all_results = []
                with self._session_factory() as session:
                    for emb in query_embeddings:
                        query = (
                            session.query(
                                SceneEmbedding,
                                SceneEmbedding.embedding.cosine_distance(emb).label('distance')
                            )
                            .filter(SceneEmbedding.embedding.isnot(None))
                        )

                        # Story filtering
                        if story_ids and len(story_ids) == 1:
                            query = query.filter(SceneEmbedding.story_id == story_ids[0])
                        elif story_ids:
                            query = query.filter(SceneEmbedding.story_id.in_(story_ids))

                        # Per-story branch filtering for world-scope
                        if branch_map:
                            branch_conditions = []
                            for sid, bid in branch_map.items():
                                if bid is not None:
                                    branch_conditions.append(
                                        and_(SceneEmbedding.story_id == sid, SceneEmbedding.branch_id == bid)
                                    )
                                else:
                                    branch_conditions.append(SceneEmbedding.story_id == sid)
                            if branch_conditions:
                                query = query.filter(or_(*branch_conditions))

                        if chapter_id is not None:
                            query = query.filter(SceneEmbedding.chapter_id == chapter_id)

                        # Exclude sequences only from the specified story
                        if exclude_sequences and exclude_story_id:
                            query = query.filter(
                                ~and_(
                                    SceneEmbedding.story_id == exclude_story_id,
                                    SceneEmbedding.sequence_order.in_(exclude_sequences)
                                )
                            )

                        query = query.order_by('distance').limit(retrieval_k)
                        # Materialize results while session is open
                        results = []
                        for row, distance in query.all():
                            results.append({
                                'embedding_id': row.embedding_id,
                                'scene_id': row.scene_id,
                                'story_id': row.story_id,
                                'variant_id': row.variant_id,
                                'sequence': row.sequence_order,
                                'chapter_id': row.chapter_id,
                                'branch_id': row.branch_id,
                                'distance': distance,
                                'timestamp': row.created_at.isoformat() if row.created_at else '',
                            })
                        all_results.append(results)
                return all_results

            raw_results = await asyncio.to_thread(_db_batch_search)

            # Format each query's results
            all_formatted = []
            for q_results in raw_results:
                candidates = []
                for r in q_results:
                    normalized_similarity = max(0.0, 1.0 - (r['distance'] / 2.0))
                    candidates.append({
                        'embedding_id': r['embedding_id'],
                        'scene_id': r['scene_id'],
                        'story_id': r['story_id'],
                        'variant_id': r['variant_id'],
                        'sequence': r['sequence'],
                        'chapter_id': r['chapter_id'],
                        'branch_id': r['branch_id'],
                        'similarity_score': normalized_similarity,
                        'bi_encoder_score': normalized_similarity,
                        'timestamp': r['timestamp'],
                        'characters': '[]',
                    })

                # Sort by score descending, limit to top_k
                candidates.sort(key=lambda x: x['similarity_score'], reverse=True)
                all_formatted.append(candidates[:top_k])

            scope_desc = f"stories {story_ids}" if story_ids and len(story_ids) > 1 else f"story {story_id}"
            logger.info(f"[SEMANTIC BATCH] Searched {len(query_texts)} queries for {scope_desc}, "
                       f"results per query: {[len(r) for r in all_formatted]}")
            return all_formatted

        except Exception as e:
            logger.error(f"Failed batch search for similar scenes: {e}")
            return [[] for _ in query_texts]

    # Character Moments

    async def add_character_moment(
        self,
        character_id: int,
        character_name: str,
        scene_id: int,
        story_id: int,
        moment_type: str,
        content: str,
        metadata: Dict[str, Any]
    ) -> Tuple[str, List[float]]:
        """
        Generate embedding for a character moment.

        Pure computation — no database side-effects. Caller stores the result.

        Args:
            character_id: Character ID
            character_name: Character name
            scene_id: Scene ID
            story_id: Story ID
            moment_type: Type of moment
            content: Moment content/description
            metadata: Additional metadata

        Returns:
            Tuple of (embedding_id, embedding_vector)
        """
        try:
            # Generate content hash to ensure uniqueness for multiple moments of same type
            content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:8]
            embedding_id = f"char_{character_id}_scene_{scene_id}_{moment_type}_{content_hash}"

            # Generate embedding (async)
            embedding = await self.generate_embedding(content)

            logger.info(f"Generated character moment embedding: {embedding_id}")
            return embedding_id, embedding

        except Exception as e:
            logger.error(f"Failed to generate character moment embedding: {e}")
            raise

    async def search_character_moments(
        self,
        character_id: int,
        query_text: str,
        story_id: int,
        top_k: int = 3,
        moment_type: Optional[str] = None,
        use_reranking: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant character moments with optional reranking

        Args:
            character_id: Character ID
            query_text: Query text (current situation)
            story_id: Story ID
            top_k: Number of results
            moment_type: Optional filter by moment type
            use_reranking: Whether to use cross-encoder reranking

        Returns:
            List of relevant character moments
        """
        from ..models.semantic_memory import CharacterMemory

        try:
            # Get more candidates if reranking
            retrieval_k = top_k * 3 if (use_reranking and self.enable_reranking) else top_k * 2

            # Generate query embedding (async)
            query_embedding = await self.generate_embedding(query_text)

            def _db_search():
                with self._session_factory() as session:
                    query = (
                        session.query(
                            CharacterMemory,
                            CharacterMemory.embedding.cosine_distance(query_embedding).label('distance')
                        )
                        .filter(CharacterMemory.character_id == character_id)
                        .filter(CharacterMemory.story_id == story_id)
                        .filter(CharacterMemory.embedding.isnot(None))
                    )
                    if moment_type:
                        query = query.filter(CharacterMemory.moment_type == moment_type)

                    query = query.order_by('distance').limit(retrieval_k)

                    results = []
                    for row, distance in query.all():
                        results.append({
                            'embedding_id': row.embedding_id,
                            'character_id': row.character_id,
                            'scene_id': row.scene_id,
                            'moment_type': row.moment_type.value if row.moment_type else 'action',
                            'sequence': row.sequence_order,
                            'distance': distance,
                            'timestamp': row.created_at.isoformat() if row.created_at else '',
                            'content': row.content,
                        })
                    return results

            raw_results = await asyncio.to_thread(_db_search)

            if not raw_results:
                return []

            # Process results
            candidates = []
            for r in raw_results:
                normalized_similarity = max(0.0, 1.0 - (r['distance'] / 2.0))
                candidates.append({
                    'embedding_id': r['embedding_id'],
                    'character_id': r['character_id'],
                    'character_name': '',  # Will be enriched by caller if needed
                    'scene_id': r['scene_id'],
                    'moment_type': r['moment_type'],
                    'sequence': r['sequence'],
                    'bi_encoder_score': normalized_similarity,
                    'timestamp': r['timestamp'],
                    'document_text': r['content'],
                })

            # Apply reranking if enabled
            if use_reranking and self.enable_reranking and len(candidates) > top_k:
                try:
                    await self._ensure_reranker_loaded()
                    pairs = [[query_text, c['document_text']] for c in candidates if c.get('document_text')]

                    if pairs:
                        rerank_scores = await asyncio.to_thread(self.reranker.predict, pairs)

                        valid_idx = 0
                        for candidate in candidates:
                            if candidate.get('document_text'):
                                candidate['similarity_score'] = float(rerank_scores[valid_idx])
                                valid_idx += 1
                            else:
                                candidate['similarity_score'] = candidate['bi_encoder_score']

                        candidates.sort(key=lambda x: x['similarity_score'], reverse=True)
                        logger.info(f"Reranked {len(candidates)} character moments")
                    else:
                        for c in candidates:
                            c['similarity_score'] = c['bi_encoder_score']
                        candidates.sort(key=lambda x: x['bi_encoder_score'], reverse=True)
                except Exception as e:
                    logger.warning(f"Reranking failed for character moments: {e}")
                    for c in candidates:
                        c['similarity_score'] = c['bi_encoder_score']
                    candidates.sort(key=lambda x: x['bi_encoder_score'], reverse=True)
            else:
                for c in candidates:
                    c['similarity_score'] = c['bi_encoder_score']
                candidates.sort(key=lambda x: x['bi_encoder_score'], reverse=True)

            # Return top_k without document_text
            final_results = []
            for c in candidates[:top_k]:
                result = {k: v for k, v in c.items() if k != 'document_text'}
                final_results.append(result)

            logger.info(f"Returning {len(final_results)} character moments for character {character_id}")
            return final_results

        except Exception as e:
            logger.error(f"Failed to search character moments: {e}")
            return []

    async def get_character_arc(
        self,
        character_id: int,
        story_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get chronological character arc (all moments ordered by sequence)

        Args:
            character_id: Character ID
            story_id: Story ID

        Returns:
            List of character moments in chronological order
        """
        from ..models.semantic_memory import CharacterMemory

        try:
            def _db_get():
                with self._session_factory() as session:
                    rows = session.query(CharacterMemory).filter(
                        CharacterMemory.character_id == character_id,
                        CharacterMemory.story_id == story_id,
                    ).order_by(CharacterMemory.sequence_order).all()

                    moments = []
                    for row in rows:
                        moments.append({
                            'embedding_id': row.embedding_id,
                            'character_name': '',
                            'scene_id': row.scene_id,
                            'moment_type': row.moment_type.value if row.moment_type else 'action',
                            'sequence': row.sequence_order,
                            'timestamp': row.created_at.isoformat() if row.created_at else '',
                        })
                    return moments

            moments = await asyncio.to_thread(_db_get)
            logger.info(f"Retrieved {len(moments)} moments for character arc")
            return moments

        except Exception as e:
            logger.error(f"Failed to get character arc: {e}")
            return []

    # Plot Events

    async def add_plot_event(
        self,
        event_id: str,
        story_id: int,
        scene_id: int,
        event_type: str,
        description: str,
        metadata: Dict[str, Any]
    ) -> Tuple[str, List[float]]:
        """
        Generate embedding for a plot event.

        Pure computation — no database side-effects. Caller stores the result.

        Args:
            event_id: Unique event ID
            story_id: Story ID
            scene_id: Scene ID
            event_type: Event type
            description: Event description
            metadata: Additional metadata

        Returns:
            Tuple of (embedding_id, embedding_vector)
        """
        try:
            embedding_id = f"plot_{event_id}"

            # Generate embedding (async)
            embedding = await self.generate_embedding(description)

            logger.info(f"Generated plot event embedding: {embedding_id}")
            return embedding_id, embedding

        except Exception as e:
            logger.error(f"Failed to generate plot event embedding: {e}")
            raise

    async def search_related_plot_events(
        self,
        query_text: str,
        story_id: int,
        top_k: int = 5,
        only_unresolved: bool = False,
        use_reranking: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search for related plot events with optional reranking

        Args:
            query_text: Query text (current scene/situation)
            story_id: Story ID
            top_k: Number of results
            only_unresolved: Only return unresolved plot threads
            use_reranking: Whether to use cross-encoder reranking

        Returns:
            List of related plot events
        """
        from ..models.semantic_memory import PlotEvent

        try:
            # Get more candidates if reranking
            retrieval_k = top_k * 3 if (use_reranking and self.enable_reranking) else top_k * 2

            # Generate query embedding (async)
            query_embedding = await self.generate_embedding(query_text)

            def _db_search():
                with self._session_factory() as session:
                    query = (
                        session.query(
                            PlotEvent,
                            PlotEvent.embedding.cosine_distance(query_embedding).label('distance')
                        )
                        .filter(PlotEvent.story_id == story_id)
                        .filter(PlotEvent.embedding.isnot(None))
                    )
                    if only_unresolved:
                        query = query.filter(PlotEvent.is_resolved == False)

                    query = query.order_by('distance').limit(retrieval_k)

                    results = []
                    for row, distance in query.all():
                        results.append({
                            'embedding_id': row.embedding_id,
                            'event_id': row.thread_id or '',
                            'scene_id': row.scene_id,
                            'event_type': row.event_type.value if row.event_type else 'complication',
                            'sequence': row.sequence_order,
                            'is_resolved': row.is_resolved,
                            'involved_characters': str(row.involved_characters) if row.involved_characters else '[]',
                            'distance': distance,
                            'timestamp': row.created_at.isoformat() if row.created_at else '',
                            'document_text': row.description,
                        })
                    return results

            raw_results = await asyncio.to_thread(_db_search)

            if not raw_results:
                return []

            # Process results
            candidates = []
            for r in raw_results:
                normalized_similarity = max(0.0, 1.0 - (r['distance'] / 2.0))
                candidates.append({
                    'embedding_id': r['embedding_id'],
                    'event_id': r['event_id'],
                    'scene_id': r['scene_id'],
                    'event_type': r['event_type'],
                    'sequence': r['sequence'],
                    'is_resolved': r['is_resolved'],
                    'involved_characters': r['involved_characters'],
                    'bi_encoder_score': normalized_similarity,
                    'timestamp': r['timestamp'],
                    'document_text': r['document_text'],
                })

            # Apply reranking if enabled
            if use_reranking and self.enable_reranking and len(candidates) > top_k:
                try:
                    await self._ensure_reranker_loaded()
                    pairs = [[query_text, c['document_text']] for c in candidates if c.get('document_text')]

                    if pairs:
                        rerank_scores = await asyncio.to_thread(self.reranker.predict, pairs)

                        valid_idx = 0
                        for candidate in candidates:
                            if candidate.get('document_text'):
                                candidate['similarity_score'] = float(rerank_scores[valid_idx])
                                valid_idx += 1
                            else:
                                candidate['similarity_score'] = candidate['bi_encoder_score']

                        candidates.sort(key=lambda x: x['similarity_score'], reverse=True)
                        logger.info(f"Reranked {len(candidates)} plot events")
                    else:
                        for c in candidates:
                            c['similarity_score'] = c['bi_encoder_score']
                        candidates.sort(key=lambda x: x['bi_encoder_score'], reverse=True)
                except Exception as e:
                    logger.warning(f"Reranking failed for plot events: {e}")
                    for c in candidates:
                        c['similarity_score'] = c['bi_encoder_score']
                    candidates.sort(key=lambda x: x['bi_encoder_score'], reverse=True)
            else:
                for c in candidates:
                    c['similarity_score'] = c['bi_encoder_score']
                candidates.sort(key=lambda x: x['bi_encoder_score'], reverse=True)

            # Return top_k without document_text
            final_results = []
            for c in candidates[:top_k]:
                result = {k: v for k, v in c.items() if k != 'document_text'}
                final_results.append(result)

            logger.info(f"Returning {len(final_results)} plot events for story {story_id}")
            return final_results

        except Exception as e:
            logger.error(f"Failed to search plot events: {e}")
            return []

    # Utility Methods

    async def delete_story_embeddings(self, story_id: int):
        """
        Null out all embedding vectors for a story (async).
        Row lifecycle is managed by callers.

        Args:
            story_id: Story ID to delete
        """
        from ..models.semantic_memory import SceneEmbedding, CharacterMemory, PlotEvent

        try:
            def _db_delete():
                with self._session_factory() as session:
                    session.query(SceneEmbedding).filter(
                        SceneEmbedding.story_id == story_id
                    ).update({SceneEmbedding.embedding: None})
                    session.query(CharacterMemory).filter(
                        CharacterMemory.story_id == story_id
                    ).update({CharacterMemory.embedding: None})
                    session.query(PlotEvent).filter(
                        PlotEvent.story_id == story_id
                    ).update({PlotEvent.embedding: None})
                    session.commit()

            await asyncio.to_thread(_db_delete)
            logger.info(f"Deleted all embeddings for story {story_id}")

        except Exception as e:
            logger.error(f"Failed to delete story embeddings: {e}")

    async def delete_scene_embedding(self, scene_id: int, variant_id: int):
        """
        Null out a specific scene embedding vector (async).

        Args:
            scene_id: Scene ID
            variant_id: Variant ID
        """
        from ..models.semantic_memory import SceneEmbedding

        try:
            embedding_id = f"scene_{scene_id}_v{variant_id}"

            def _db_delete():
                with self._session_factory() as session:
                    session.query(SceneEmbedding).filter(
                        SceneEmbedding.embedding_id == embedding_id
                    ).update({SceneEmbedding.embedding: None})
                    session.commit()

            await asyncio.to_thread(_db_delete)
            logger.info(f"Deleted scene embedding: {embedding_id}")
        except Exception as e:
            logger.error(f"Failed to delete scene embedding: {e}")

    async def get_collection_stats(self) -> Dict[str, int]:
        """
        Get statistics about embedding counts (async)

        Returns:
            Dictionary with collection names and counts
        """
        from ..models.semantic_memory import SceneEmbedding, CharacterMemory, PlotEvent

        try:
            def _db_stats():
                with self._session_factory() as session:
                    scenes = session.query(SceneEmbedding).filter(
                        SceneEmbedding.embedding.isnot(None)).count()
                    moments = session.query(CharacterMemory).filter(
                        CharacterMemory.embedding.isnot(None)).count()
                    events = session.query(PlotEvent).filter(
                        PlotEvent.embedding.isnot(None)).count()
                    return {"scenes": scenes, "character_moments": moments, "plot_events": events}

            return await asyncio.to_thread(_db_stats)
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {"scenes": 0, "character_moments": 0, "plot_events": 0}

    async def reset_all_collections(self):
        """
        Null out all embedding vectors (use with caution!) (async)
        """
        from ..models.semantic_memory import SceneEmbedding, CharacterMemory, PlotEvent

        logger.warning("Resetting all semantic memory embeddings!")

        def _db_reset():
            with self._session_factory() as session:
                session.query(SceneEmbedding).update({SceneEmbedding.embedding: None})
                session.query(CharacterMemory).update({CharacterMemory.embedding: None})
                session.query(PlotEvent).update({PlotEvent.embedding: None})
                session.commit()

        await asyncio.to_thread(_db_reset)


# Global instance (initialized in main.py)
semantic_memory_service: Optional[SemanticMemoryService] = None


def get_semantic_memory_service() -> SemanticMemoryService:
    """Get the global semantic memory service instance"""
    if semantic_memory_service is None:
        raise RuntimeError("Semantic memory service not initialized")
    return semantic_memory_service


def initialize_semantic_memory_service(
    embedding_model: str,
    enable_reranking: bool = True,
    reranker_model: Optional[str] = None,
) -> SemanticMemoryService:
    """
    Initialize the global semantic memory service

    Args:
        embedding_model: Embedding model name
        enable_reranking: Whether to enable cross-encoder reranking
        reranker_model: Cross-encoder model name (None = use default)

    Returns:
        Initialized SemanticMemoryService instance
    """
    global semantic_memory_service
    kwargs = {
        "embedding_model": embedding_model,
        "enable_reranking": enable_reranking,
    }
    if reranker_model:
        kwargs["reranker_model"] = reranker_model
    semantic_memory_service = SemanticMemoryService(**kwargs)
    logger.info(f"Semantic memory service initialized (reranking={'enabled' if enable_reranking else 'disabled'})")
    return semantic_memory_service
