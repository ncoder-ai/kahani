"""
Semantic Memory Service using ChromaDB and Sentence Transformers

Provides vector-based semantic search capabilities for story content,
enabling intelligent context retrieval beyond simple recency-based selection.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import chromadb
from chromadb.config import Settings
# SentenceTransformer is imported lazily in _ensure_model_loaded to avoid blocking startup
from sqlalchemy.orm import Session
import os

logger = logging.getLogger(__name__)


class SemanticMemoryService:
    """
    Manages semantic memory using ChromaDB for vector storage and retrieval.
    
    Features:
    - Scene-level embeddings for semantic search
    - Character moment embeddings for character consistency
    - Plot event embeddings for thread tracking
    - Efficient similarity search with metadata filtering
    """
    
    def __init__(self, persist_directory: str = "./data/chromadb", embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2", reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """
        Initialize the semantic memory service
        
        Args:
            persist_directory: Directory for ChromaDB persistence
            embedding_model: Sentence transformer model name
            reranker_model: Cross-encoder model for reranking
        """
        self.persist_directory = persist_directory
        self.embedding_model_name = embedding_model
        self.reranker_model_name = reranker_model
        
        # Ensure persist directory exists
        os.makedirs(persist_directory, exist_ok=True)
        
        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Lazy-load embedding model to avoid blocking startup
        self.embedding_model = None
        self._embedding_dimension = None
        
        # Lazy-load reranker model
        self.reranker = None
        self.enable_reranking = True  # Can be disabled if needed
        
        # Initialize collections
        self._init_collections()
    
    def _init_collections(self):
        """Initialize or get ChromaDB collections"""
        
        # Scene embeddings collection
        self.scenes_collection = self.client.get_or_create_collection(
            name="story_scenes",
            metadata={"description": "Scene-level embeddings for semantic search"}
        )
        
        # Character moments collection
        self.character_moments_collection = self.client.get_or_create_collection(
            name="character_moments",
            metadata={"description": "Character-specific moments for tracking development"}
        )
        
        # Plot events collection
        self.plot_events_collection = self.client.get_or_create_collection(
            name="plot_events",
            metadata={"description": "Key plot events and story threads"}
        )
        
        logger.info("ChromaDB collections initialized successfully")
    
    def _ensure_model_loaded(self):
        """Lazy-load the embedding model on first use"""
        if self.embedding_model is None:
            logger.info(f"Loading embedding model: {self.embedding_model_name}")
            # Import SentenceTransformer only when actually needed to avoid blocking startup
            from sentence_transformers import SentenceTransformer
            self.embedding_model = SentenceTransformer(self.embedding_model_name)
            self._embedding_dimension = self.embedding_model.get_sentence_embedding_dimension()
            logger.info(f"Embedding model loaded successfully. Dimension: {self._embedding_dimension}")
    
    def _ensure_reranker_loaded(self):
        """Lazy-load the reranker model on first use"""
        if self.reranker is None and self.enable_reranking:
            logger.info(f"Loading reranker model: {self.reranker_model_name}")
            # Import CrossEncoder only when actually needed
            from sentence_transformers import CrossEncoder
            self.reranker = CrossEncoder(self.reranker_model_name)
            logger.info(f"Reranker model loaded successfully")
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding
        """
        try:
            self._ensure_model_loaded()
            embedding = self.embedding_model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
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
    ) -> str:
        """
        Add or update a scene embedding
        
        Args:
            scene_id: Scene ID
            variant_id: Scene variant ID
            story_id: Story ID
            content: Scene content text
            metadata: Additional metadata (chapter_id, sequence, characters, etc.)
            
        Returns:
            Embedding ID
        """
        try:
            embedding_id = f"scene_{scene_id}_v{variant_id}"
            
            # Generate embedding
            embedding = self.generate_embedding(content)
            
            # Prepare metadata
            meta = {
                "story_id": story_id,
                "scene_id": scene_id,
                "variant_id": variant_id,
                "sequence": metadata.get("sequence", 0),
                "chapter_id": metadata.get("chapter_id", 0),
                "timestamp": metadata.get("timestamp", datetime.utcnow().isoformat()),
                "characters": str(metadata.get("characters", [])),  # ChromaDB requires string metadata
                "content_length": len(content)
            }
            
            # Add to collection (upsert behavior)
            self.scenes_collection.upsert(
                ids=[embedding_id],
                embeddings=[embedding],
                documents=[content[:1000]],  # Store first 1000 chars for reference
                metadatas=[meta]
            )
            
            logger.info(f"Added scene embedding: {embedding_id}")
            return embedding_id
            
        except Exception as e:
            logger.error(f"Failed to add scene embedding: {e}")
            raise
    
    async def search_similar_scenes(
        self,
        query_text: str,
        story_id: int,
        top_k: int = 5,
        exclude_sequences: Optional[List[int]] = None,
        chapter_id: Optional[int] = None,
        use_reranking: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search for semantically similar scenes with optional cross-encoder reranking
        
        Two-stage retrieval:
        1. Fast bi-encoder retrieval (get candidates)
        2. Precise cross-encoder reranking (narrow to top_k)
        
        Args:
            query_text: Query text (e.g., recent scene content)
            story_id: Story ID to filter by
            top_k: Number of results to return
            exclude_sequences: Scene sequences to exclude (e.g., recent scenes)
            chapter_id: Optional chapter filter
            use_reranking: Whether to use cross-encoder reranking
            
        Returns:
            List of similar scenes with metadata and similarity scores
        """
        try:
            # Stage 1: Fast retrieval with bi-encoder
            # Get more candidates for reranking (3x oversample)
            retrieval_k = top_k * 3 if (use_reranking and self.enable_reranking) else top_k * 2
            
            # Generate query embedding
            query_embedding = self.generate_embedding(query_text)
            
            # Build where filter
            where_filter = {"story_id": story_id}
            if chapter_id is not None:
                where_filter["chapter_id"] = chapter_id
            
            # Query collection
            results = self.scenes_collection.query(
                query_embeddings=[query_embedding],
                n_results=retrieval_k,
                where=where_filter,
                include=["metadatas", "distances", "documents"]  # Include documents for reranking
            )
            
            # Process and filter results
            candidates = []
            for i, (doc_id, doc_text, metadata, distance) in enumerate(zip(
                results['ids'][0],
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            )):
                # Skip excluded sequences
                if exclude_sequences and metadata['sequence'] in exclude_sequences:
                    continue
                
                candidates.append({
                    'embedding_id': doc_id,
                    'scene_id': metadata['scene_id'],
                    'variant_id': metadata['variant_id'],
                    'sequence': metadata['sequence'],
                    'chapter_id': metadata['chapter_id'],
                    'bi_encoder_score': 1 - distance,  # Initial similarity
                    'timestamp': metadata['timestamp'],
                    'characters': metadata.get('characters', '[]'),
                    'document_text': doc_text  # For reranking
                })
            
            if not candidates:
                logger.info(f"No candidates found for story {story_id}")
                return []
            
            # Stage 2: Cross-encoder reranking (if enabled)
            if use_reranking and self.enable_reranking and len(candidates) > top_k:
                try:
                    self._ensure_reranker_loaded()
                    
                    # Prepare query-document pairs
                    pairs = [[query_text, candidate['document_text']] for candidate in candidates]
                    
                    # Get reranking scores
                    rerank_scores = self.reranker.predict(pairs)
                    
                    # Update candidates with reranked scores
                    for candidate, rerank_score in zip(candidates, rerank_scores):
                        candidate['rerank_score'] = float(rerank_score)
                        candidate['similarity_score'] = float(rerank_score)  # Use reranked score as final
                    
                    # Sort by reranked scores
                    candidates.sort(key=lambda x: x['rerank_score'], reverse=True)
                    
                    logger.info(f"Reranked {len(candidates)} candidates for story {story_id}")
                    
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
            
            # Return top_k results (remove document_text to save memory)
            final_results = []
            for candidate in candidates[:top_k]:
                result = {k: v for k, v in candidate.items() if k != 'document_text'}
                final_results.append(result)
            
            logger.info(f"Returning {len(final_results)} similar scenes for story {story_id}")
            return final_results
            
        except Exception as e:
            logger.error(f"Failed to search similar scenes: {e}")
            return []
    
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
    ) -> str:
        """
        Add a character moment embedding
        
        Args:
            character_id: Character ID
            character_name: Character name
            scene_id: Scene ID
            story_id: Story ID
            moment_type: Type of moment (action, dialogue, development, relationship)
            content: Moment content/description
            metadata: Additional metadata
            
        Returns:
            Embedding ID
        """
        try:
            embedding_id = f"char_{character_id}_scene_{scene_id}_{moment_type}"
            
            # Generate embedding
            embedding = self.generate_embedding(content)
            
            # Prepare metadata
            meta = {
                "character_id": character_id,
                "character_name": character_name,
                "scene_id": scene_id,
                "story_id": story_id,
                "moment_type": moment_type,
                "sequence": metadata.get("sequence", 0),
                "timestamp": metadata.get("timestamp", datetime.utcnow().isoformat())
            }
            
            # Add to collection
            self.character_moments_collection.upsert(
                ids=[embedding_id],
                embeddings=[embedding],
                documents=[content[:500]],
                metadatas=[meta]
            )
            
            logger.info(f"Added character moment: {embedding_id}")
            return embedding_id
            
        except Exception as e:
            logger.error(f"Failed to add character moment: {e}")
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
        try:
            # Get more candidates if reranking
            retrieval_k = top_k * 3 if (use_reranking and self.enable_reranking) else top_k * 2
            
            # Generate query embedding
            query_embedding = self.generate_embedding(query_text)
            
            # Build where filter
            where_filter = {
                "character_id": character_id,
                "story_id": story_id
            }
            if moment_type:
                where_filter["moment_type"] = moment_type
            
            # Query collection
            results = self.character_moments_collection.query(
                query_embeddings=[query_embedding],
                n_results=retrieval_k,
                where=where_filter,
                include=["metadatas", "distances", "documents"]
            )
            
            # Process results
            candidates = []
            for doc_id, doc_text, metadata, distance in zip(
                results['ids'][0],
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            ):
                candidates.append({
                    'embedding_id': doc_id,
                    'character_id': metadata['character_id'],
                    'character_name': metadata['character_name'],
                    'scene_id': metadata['scene_id'],
                    'moment_type': metadata['moment_type'],
                    'sequence': metadata['sequence'],
                    'bi_encoder_score': 1 - distance,
                    'timestamp': metadata['timestamp'],
                    'document_text': doc_text
                })
            
            if not candidates:
                return []
            
            # Apply reranking if enabled
            if use_reranking and self.enable_reranking and len(candidates) > top_k:
                try:
                    self._ensure_reranker_loaded()
                    pairs = [[query_text, c['document_text']] for c in candidates]
                    rerank_scores = self.reranker.predict(pairs)
                    
                    for candidate, score in zip(candidates, rerank_scores):
                        candidate['similarity_score'] = float(score)
                    
                    candidates.sort(key=lambda x: x['similarity_score'], reverse=True)
                    logger.info(f"Reranked {len(candidates)} character moments")
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
        try:
            # Get all moments for this character
            results = self.character_moments_collection.get(
                where={
                    "character_id": character_id,
                    "story_id": story_id
                }
            )
            
            # Process and sort by sequence
            moments = []
            if results['ids']:
                for doc_id, metadata in zip(results['ids'], results['metadatas']):
                    moments.append({
                        'embedding_id': doc_id,
                        'character_name': metadata['character_name'],
                        'scene_id': metadata['scene_id'],
                        'moment_type': metadata['moment_type'],
                        'sequence': metadata['sequence'],
                        'timestamp': metadata['timestamp']
                    })
                
                # Sort by sequence
                moments.sort(key=lambda x: x['sequence'])
            
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
    ) -> str:
        """
        Add a plot event embedding
        
        Args:
            event_id: Unique event ID
            story_id: Story ID
            scene_id: Scene ID
            event_type: Event type (introduction, complication, revelation, resolution)
            description: Event description
            metadata: Additional metadata
            
        Returns:
            Embedding ID
        """
        try:
            embedding_id = f"plot_{event_id}"
            
            # Generate embedding
            embedding = self.generate_embedding(description)
            
            # Prepare metadata
            meta = {
                "event_id": event_id,
                "story_id": story_id,
                "scene_id": scene_id,
                "event_type": event_type,
                "sequence": metadata.get("sequence", 0),
                "is_resolved": metadata.get("is_resolved", False),
                "involved_characters": str(metadata.get("involved_characters", [])),
                "timestamp": metadata.get("timestamp", datetime.utcnow().isoformat())
            }
            
            # Add to collection
            self.plot_events_collection.upsert(
                ids=[embedding_id],
                embeddings=[embedding],
                documents=[description[:500]],
                metadatas=[meta]
            )
            
            logger.info(f"Added plot event: {embedding_id}")
            return embedding_id
            
        except Exception as e:
            logger.error(f"Failed to add plot event: {e}")
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
        try:
            # Get more candidates if reranking
            retrieval_k = top_k * 3 if (use_reranking and self.enable_reranking) else top_k * 2
            
            # Generate query embedding
            query_embedding = self.generate_embedding(query_text)
            
            # Build where filter
            where_filter = {"story_id": story_id}
            if only_unresolved:
                where_filter["is_resolved"] = False
            
            # Query collection
            results = self.plot_events_collection.query(
                query_embeddings=[query_embedding],
                n_results=retrieval_k,
                where=where_filter,
                include=["metadatas", "distances", "documents"]
            )
            
            # Process results
            candidates = []
            for doc_id, doc_text, metadata, distance in zip(
                results['ids'][0],
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            ):
                candidates.append({
                    'embedding_id': doc_id,
                    'event_id': metadata['event_id'],
                    'scene_id': metadata['scene_id'],
                    'event_type': metadata['event_type'],
                    'sequence': metadata['sequence'],
                    'is_resolved': metadata['is_resolved'],
                    'involved_characters': metadata.get('involved_characters', '[]'),
                    'bi_encoder_score': 1 - distance,
                    'timestamp': metadata['timestamp'],
                    'document_text': doc_text
                })
            
            if not candidates:
                return []
            
            # Apply reranking if enabled
            if use_reranking and self.enable_reranking and len(candidates) > top_k:
                try:
                    self._ensure_reranker_loaded()
                    pairs = [[query_text, c['document_text']] for c in candidates]
                    rerank_scores = self.reranker.predict(pairs)
                    
                    for candidate, score in zip(candidates, rerank_scores):
                        candidate['similarity_score'] = float(score)
                    
                    candidates.sort(key=lambda x: x['similarity_score'], reverse=True)
                    logger.info(f"Reranked {len(candidates)} plot events")
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
    
    def delete_story_embeddings(self, story_id: int):
        """
        Delete all embeddings for a story
        
        Args:
            story_id: Story ID to delete
        """
        try:
            # Delete from scenes collection
            self.scenes_collection.delete(
                where={"story_id": story_id}
            )
            
            # Delete from character moments collection
            self.character_moments_collection.delete(
                where={"story_id": story_id}
            )
            
            # Delete from plot events collection
            self.plot_events_collection.delete(
                where={"story_id": story_id}
            )
            
            logger.info(f"Deleted all embeddings for story {story_id}")
            
        except Exception as e:
            logger.error(f"Failed to delete story embeddings: {e}")
    
    def delete_scene_embedding(self, scene_id: int, variant_id: int):
        """
        Delete a specific scene embedding
        
        Args:
            scene_id: Scene ID
            variant_id: Variant ID
        """
        try:
            embedding_id = f"scene_{scene_id}_v{variant_id}"
            self.scenes_collection.delete(ids=[embedding_id])
            logger.info(f"Deleted scene embedding: {embedding_id}")
        except Exception as e:
            logger.error(f"Failed to delete scene embedding: {e}")
    
    def get_collection_stats(self) -> Dict[str, int]:
        """
        Get statistics about collection sizes
        
        Returns:
            Dictionary with collection names and counts
        """
        try:
            return {
                "scenes": self.scenes_collection.count(),
                "character_moments": self.character_moments_collection.count(),
                "plot_events": self.plot_events_collection.count()
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {"scenes": 0, "character_moments": 0, "plot_events": 0}
    
    def reset_all_collections(self):
        """
        Reset all collections (use with caution!)
        """
        logger.warning("Resetting all semantic memory collections!")
        self.client.reset()
        self._init_collections()


# Global instance (initialized in main.py)
semantic_memory_service: Optional[SemanticMemoryService] = None


def get_semantic_memory_service() -> SemanticMemoryService:
    """Get the global semantic memory service instance"""
    if semantic_memory_service is None:
        raise RuntimeError("Semantic memory service not initialized")
    return semantic_memory_service


def initialize_semantic_memory_service(persist_directory: str, embedding_model: str) -> SemanticMemoryService:
    """
    Initialize the global semantic memory service
    
    Args:
        persist_directory: ChromaDB persistence directory
        embedding_model: Embedding model name
        
    Returns:
        Initialized SemanticMemoryService instance
    """
    global semantic_memory_service
    semantic_memory_service = SemanticMemoryService(
        persist_directory=persist_directory,
        embedding_model=embedding_model
    )
    logger.info("Semantic memory service initialized successfully")
    return semantic_memory_service

