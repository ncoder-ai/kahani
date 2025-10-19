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


def download_all_models():
    """Download all required models for the application"""
    
    logger.info("=" * 60)
    logger.info("📦 Downloading AI Models for Semantic Memory")
    logger.info("=" * 60)
    
    # Use default model name - don't load config to avoid loading entire app
    model_name = "sentence-transformers/all-MiniLM-L6-v2"
    logger.info(f"Using default model: {model_name}")
    
    # Download the model
    success = download_sentence_transformer_model(model_name)
    
    logger.info("=" * 60)
    
    if success:
        logger.info("✅ All models downloaded successfully!")
        logger.info("   The application is ready to use semantic memory features.")
        return 0
    else:
        logger.error("❌ Model download failed!")
        logger.error("   Semantic memory features will not work until models are downloaded.")
        return 1


if __name__ == "__main__":
    sys.exit(download_all_models())

