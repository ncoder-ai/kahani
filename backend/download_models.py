"""
Pre-download embedding models for semantic memory and STT models

Run this during deployment/installation to ensure all models are cached
before the application starts serving requests.
"""

import logging
import sys
import os

# Set cache directory - use /app/.cache/huggingface in Docker, ~/.cache/huggingface on baremetal
cache_dir = '/app/.cache/huggingface' if os.path.exists('/app') else os.path.expanduser('~/.cache/huggingface')
os.environ['HF_HOME'] = cache_dir
os.environ['TRANSFORMERS_CACHE'] = cache_dir

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


def download_silero_vad_model():
    """
    Pre-download Silero VAD model.
    
    Silero VAD is downloaded via torch.hub and cached in ~/.cache/torch/hub/
    """
    try:
        logger.info(f"🔽 Downloading Silero VAD model...")
        logger.info("This is a one-time download (about 1.8MB)...")
        
        import torch
        
        # Check if model already exists
        # torch.hub stores models in ~/.cache/torch/hub/checkpoints/
        cache_dir = os.path.expanduser('~/.cache/torch/hub')
        model_cache_path = os.path.join(cache_dir, 'snakers4_silero-vad_master')
        
        if os.path.exists(model_cache_path):
            # Check if model files are present
            model_file = os.path.join(model_cache_path, 'silero_vad')
            if os.path.exists(model_file) or any(f.startswith('silero_vad') for f in os.listdir(model_cache_path) if os.path.isfile(os.path.join(model_cache_path, f))):
                logger.info(f"✅ Silero VAD model already exists at {model_cache_path}")
                return True
        
        # Download model using torch.hub (same way the service does it)
        logger.info("Downloading model via torch.hub...")
        model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            onnx=False
        )
        
        # Verify it works - just checking that model loaded successfully
        # The model initialization itself is sufficient verification
        logger.info("Model loaded successfully")
        
        logger.info(f"✅ Silero VAD model downloaded successfully!")
        logger.info(f"   - Cache location: {cache_dir}")
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ Failed to import torch: {e}")
        logger.error("   Make sure you've installed dependencies: pip install -r requirements.txt")
        return False
        
    except Exception as e:
        logger.error(f"❌ Failed to download Silero VAD model: {e}")
        logger.error("   Check your internet connection and try again")
        return False


def download_stt_model(model_name: str = "small", download_root: str = None):
    """
    Pre-download Whisper STT model.
    
    Args:
        model_name: Whisper model name (tiny, base, small, medium, large-v2)
        download_root: Directory to download models to (defaults to ./data/whisper_models)
    """
    try:
        logger.info(f"🔽 Downloading STT model: {model_name}")
        
        # Determine download root
        if download_root is None:
            # Use same logic as config.py
            data_dir = '/app/data' if os.path.exists('/app') else './data'
            download_root = os.path.join(data_dir, "whisper_models")
        
        # Create directory if it doesn't exist
        os.makedirs(download_root, exist_ok=True)
        
        # Check if model already exists
        model_path = os.path.join(download_root, model_name)
        if os.path.exists(model_path):
            logger.info(f"✅ STT model '{model_name}' already exists at {model_path}")
            return True
        
        logger.info(f"This is a one-time download (size varies by model)...")
        logger.info(f"   - tiny: ~75MB")
        logger.info(f"   - base: ~150MB")
        logger.info(f"   - small: ~500MB (recommended)")
        logger.info(f"   - medium: ~1.5GB")
        logger.info(f"   - large-v2: ~3GB")
        
        from faster_whisper import WhisperModel
        
        # Determine device and compute type
        import torch
        device = "cpu"
        compute_type = "int8"
        
        try:
            if torch.cuda.is_available():
                device = "cuda"
                compute_type = "float16"
                logger.info(f"Using CUDA GPU with {compute_type}")
            else:
                device = "cpu"
                compute_type = "int8"
                logger.info(f"Using CPU with {compute_type}")
        except Exception:
            device = "cpu"
            compute_type = "int8"
            logger.info(f"Fallback to CPU with {compute_type}")
        
        # Download and cache the model
        # This will automatically download if not present
        logger.info(f"Downloading model to {download_root}...")
        model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            download_root=download_root
        )
        
        # Verify it works - just checking that model loaded successfully
        # The model initialization itself is sufficient verification
        logger.info("Model loaded successfully")
        
        logger.info(f"✅ STT model downloaded successfully!")
        logger.info(f"   - Model: {model_name}")
        logger.info(f"   - Device: {device}")
        logger.info(f"   - Compute type: {compute_type}")
        logger.info(f"   - Cache location: {download_root}")
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ Failed to import faster-whisper: {e}")
        logger.error("   Make sure you've installed dependencies: pip install -r requirements.txt")
        return False
        
    except Exception as e:
        logger.error(f"❌ Failed to download STT model: {e}")
        logger.error("   Check your internet connection and try again")
        return False


def download_all_models(include_stt: bool = True, stt_model: str = "small", include_vad: bool = True):
    """
    Download all required models for the application
    
    Args:
        include_stt: Whether to download STT models (default: True)
        stt_model: STT model to download (default: "small")
        include_vad: Whether to download Silero VAD model (default: True)
    """
    
    logger.info("=" * 60)
    logger.info("📦 Downloading AI Models")
    logger.info("=" * 60)
    
    # Model names - using defaults to avoid loading config
    embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    
    logger.info(f"Embedding model: {embedding_model}")
    logger.info(f"Reranker model: {reranker_model}")
    if include_stt:
        logger.info(f"STT model: {stt_model}")
    if include_vad:
        logger.info("Silero VAD model: yes")
    logger.info("")
    
    results = {}
    
    # Download embedding model
    logger.info("Step 1/4: Downloading embedding model...")
    embedding_success = download_sentence_transformer_model(embedding_model)
    results['embedding'] = embedding_success
    
    if not embedding_success:
        logger.error("❌ Embedding model download failed!")
        return 1
    
    logger.info("")
    
    # Download reranker model
    logger.info("Step 2/4: Downloading reranker model...")
    reranker_success = download_cross_encoder_model(reranker_model)
    results['reranker'] = reranker_success
    
    logger.info("")
    
    # Download STT model (optional)
    stt_success = True
    if include_stt:
        logger.info(f"Step 3/4: Downloading STT model ({stt_model})...")
        stt_success = download_stt_model(stt_model)
        results['stt'] = stt_success
    else:
        logger.info("Step 3/4: Skipping STT model download")
        results['stt'] = None
    
    logger.info("")
    
    # Download Silero VAD model (optional)
    vad_success = True
    if include_vad:
        logger.info("Step 4/4: Downloading Silero VAD model...")
        vad_success = download_silero_vad_model()
        results['vad'] = vad_success
    else:
        logger.info("Step 4/4: Skipping Silero VAD model download")
        results['vad'] = None
    
    logger.info("=" * 60)
    
    # Summary
    all_success = embedding_success and reranker_success and (not include_stt or stt_success) and (not include_vad or vad_success)
    
    if all_success:
        logger.info("✅ All models downloaded successfully!")
        logger.info("   - Embedding model (90MB): ✓")
        logger.info("   - Reranker model (80MB): ✓")
        if include_stt and stt_success:
            logger.info(f"   - STT model ({stt_model}): ✓")
        if include_vad and vad_success:
            logger.info("   - Silero VAD model (1.8MB): ✓")
        logger.info("")
        logger.info("   The application is ready to use all features.")
        return 0
    else:
        logger.warning("⚠️  Some model downloads failed:")
        if not embedding_success:
            logger.warning("   - Embedding model: ❌")
        if not reranker_success:
            logger.warning("   - Reranker model: ❌")
        if include_stt and not stt_success:
            logger.warning(f"   - STT model ({stt_model}): ❌")
        if include_vad and not vad_success:
            logger.warning("   - Silero VAD model: ❌")
        
        if embedding_success and reranker_success:
            logger.warning("   Semantic search will work but without reranking")
        else:
            logger.warning("   Some features may not work until models are downloaded.")
        return 1


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Download AI models for Kahani')
    parser.add_argument('--no-stt', action='store_true', help='Skip STT model download')
    parser.add_argument('--no-vad', action='store_true', help='Skip Silero VAD model download')
    parser.add_argument('--stt-model', type=str, default='small', 
                       choices=['tiny', 'base', 'small', 'medium', 'large-v2'],
                       help='STT model to download (default: small)')
    
    args = parser.parse_args()
    
    sys.exit(download_all_models(include_stt=not args.no_stt, stt_model=args.stt_model, include_vad=not args.no_vad))

