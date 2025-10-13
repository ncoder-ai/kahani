"""
Test ChatterboxTTS Provider

Tests the new ChatterboxTTS-specific provider with extended features.
"""

import sys
import asyncio
sys.path.insert(0, '/Users/user/apps/kahani/backend')

from app.services.tts.providers.chatterbox import ChatterboxProvider
from app.services.tts.base import TTSProviderConfig, TTSRequest, AudioFormat


async def test_chatterbox_provider():
    """Test ChatterboxTTS provider"""
    
    print("=" * 60)
    print("Testing ChatterboxTTS Provider")
    print("=" * 60)
    
    # Create provider configuration
    config = TTSProviderConfig(
        api_url="http://172.16.23.80:4321/v1",
        api_key="",  # No API key needed for ChatterboxTTS
        timeout=120,
        extra_params={
            "max_text_length": 3000
        }
    )
    
    provider = ChatterboxProvider(config)
    
    # Test 1: Get supported languages
    print("\n1. Testing get_supported_languages()...")
    try:
        languages = await provider.get_supported_languages()
        print(f"✓ Found {len(languages)} supported languages")
        if languages:
            print(f"  Sample languages: {[lang.get('name', 'N/A') for lang in languages[:5]]}")
    except Exception as e:
        print(f"✗ Failed: {e}")
    
    # Test 2: Get available voices
    print("\n2. Testing get_voices()...")
    try:
        voices = await provider.get_voices()
        print(f"✓ Found {len(voices)} voices")
        if voices:
            print(f"  Sample voices: {[v.id for v in voices[:5]]}")
    except Exception as e:
        print(f"✗ Failed: {e}")
    
    # Test 3: Get default voice
    print("\n3. Testing get_default_voice()...")
    try:
        default_voice = await provider.get_default_voice()
        if default_voice:
            print(f"✓ Default voice: {default_voice}")
        else:
            print("✓ No default voice set")
    except Exception as e:
        print(f"✗ Failed: {e}")
    
    # Test 4: Basic synthesis with ChatterboxTTS-specific parameters
    print("\n4. Testing synthesize() with extended parameters...")
    try:
        request = TTSRequest(
            text="Hello! This is a test of the ChatterboxTTS provider with custom parameters.",
            voice_id="female_06",
            speed=1.0,
            format=AudioFormat.WAV,
            sample_rate=22050,
            extra_params={
                "exaggeration": 1.5,     # Emotion intensity
                "cfg_weight": 0.7,       # Pace control
                "temperature": 0.5       # Sampling temperature
            }
        )
        
        response = await provider.synthesize(request)
        print(f"✓ Generated audio: {response.file_size} bytes")
        print(f"  Format: {response.format.value}")
        print(f"  Duration: {response.duration:.2f}s")
        print(f"  Metadata: {response.metadata}")
    except Exception as e:
        print(f"✗ Failed: {e}")
    
    # Test 5: Validate voice
    print("\n5. Testing validate_voice()...")
    try:
        is_valid = await provider.validate_voice("female_06")
        print(f"✓ Voice 'female_06' validation: {is_valid}")
    except Exception as e:
        print(f"✗ Failed: {e}")
    
    print("\n" + "=" * 60)
    print("ChatterboxTTS Provider Tests Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_chatterbox_provider())
