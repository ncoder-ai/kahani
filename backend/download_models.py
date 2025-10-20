"""
Pre-download embedding models for semantic memory

Run this during deployment/installation to ensure all models are cached
before the application starts serving requests.
"""

import logging
import sys
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def download_sentence_transformer_model(model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
    """
    Pre-download the sentence-transformers model to cache.
    
    Args:
        model_name: The model identifier from HuggingFace
    """
    try:
        logger.info(f"🔽 Downloading embedding model: {model_name}")
        logger.info("This is a one-time download (about 90MB)...")
        
        from sentence_transformers import SentenceTransformer
        
        # Download and cache the model
        model = SentenceTransformer(model_name)
        
        # Verify it works
        embedding_dim = model.get_sentence_embedding_dimension()
        test_embedding = model.encode("test", convert_to_numpy=True)
        
        logger.info(f"✅ Model downloaded successfully!")
        logger.info(f"   - Model: {model_name}")
        logger.info(f"   - Embedding dimension: {embedding_dim}")
        logger.info(f"   - Test embedding shape: {test_embedding.shape}")
        logger.info(f"   - Cache location: {os.path.expanduser('~/.cache/torch/sentence_transformers/')}")
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ Failed to import sentence-transformers: {e}")
        logger.error("   Make sure you've installed dependencies: pip install -r requirements.txt")
        return False
        
    except Exception as e:
        logger.error(f"❌ Failed to download model: {e}")
        logger.error("   Check your internet connection and try again")
        return False


def download_cross_encoder_model(model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
    """
    Pre-download the cross-encoder model for reranking.
    
    Args:
        model_name: The cross-encoder model identifier
    """
    try:
        logger.info(f"🔽 Downloading reranker model: {model_name}")
        logger.info("This is a one-time download (about 80MB)...")
        
        from sentence_transformers import CrossEncoder
        
        # Download and cache the model
        model = CrossEncoder(model_name)
        
        # Verify it works
        test_score = model.predict([["test query", "test document"]])
        
        logger.info(f"✅ Reranker model downloaded successfully!")
        logger.info(f"   - Model: {model_name}")
        logger.info(f"   - Test prediction: {test_score[0]:.4f}")
        logger.info(f"   - Cache location: {os.path.expanduser('~/.cache/torch/sentence_transformers/')}")
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ Failed to import CrossEncoder: {e}")
        logger.error("   Make sure you've installed dependencies: pip install -r requirements.txt")
        return False
        
    except Exception as e:
        logger.error(f"❌ Failed to download reranker model: {e}")
        logger.error("   Check your internet connection and try again")
        return False


def download_all_models():
    """Download all required models for the application"""
    
    logger.info("=" * 60)
    logger.info("📦 Downloading AI Models for Semantic Memory")
    logger.info("=" * 60)
    
    # Model names - using defaults to avoid loading config
    embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    
    logger.info(f"Embedding model: {embedding_model}")
    logger.info(f"Reranker model: {reranker_model}")
    logger.info("")
    
    # Download embedding model
    logger.info("Step 1/2: Downloading embedding model...")
    embedding_success = download_sentence_transformer_model(embedding_model)
    
    if not embedding_success:
        logger.error("❌ Embedding model download failed!")
        return 1
    
    logger.info("")
    
    # Download reranker model
    logger.info("Step 2/2: Downloading reranker model...")
    reranker_success = download_cross_encoder_model(reranker_model)
    
    logger.info("=" * 60)
    
    if embedding_success and reranker_success:
        logger.info("✅ All models downloaded successfully!")
        logger.info("   - Embedding model (90MB): ✓")
        logger.info("   - Reranker model (80MB): ✓")
        logger.info("   Total download: ~170MB")
        logger.info("")
        logger.info("   The application is ready to use semantic memory with reranking.")
        return 0
    elif embedding_success:
        logger.warning("⚠️  Embedding model downloaded, but reranker failed")
        logger.warning("   Semantic search will work but without reranking")
        return 1
    else:
        logger.error("❌ Model downloads failed!")
        logger.error("   Semantic memory features will not work until models are downloaded.")
        return 1


if __name__ == "__main__":
    sys.exit(download_all_models())

