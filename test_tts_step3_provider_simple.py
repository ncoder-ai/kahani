#!/usr/bin/env python3
"""
Step 3: Test Provider with Simple Text
Test our TTS provider with short text
"""
import sys
import os
import asyncio

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.services.tts.factory import TTSProviderFactory
from app.services.tts.base import TTSRequest, AudioFormat

async def test_provider_simple():
    print("\n" + "="*60)
    print("STEP 3: Test Provider with Simple Text")
    print("="*60 + "\n")
    
    # Create provider
    print("Creating TTS provider...")
    provider = TTSProviderFactory.create_provider(
        provider_type="openai-compatible",
        api_url="http://172.16.23.80:4321/v1",
        api_key="",
        timeout=60,
        extra_params={"response_format": "mp3"}
    )
    
    print(f"✅ Provider created: {provider.__class__.__name__}")
    print(f"   Max text length: {provider.max_text_length}")
    
    # Test with simple text
    test_text = "Hello world! This is a simple test."
    print(f"\nTest text ({len(test_text)} chars): {test_text}")
    
    request = TTSRequest(
        text=test_text,
        voice_id="female_06",
        speed=1.0,
        format=AudioFormat.MP3
    )
    
    print(f"\n⏱️  Generating audio...")
    
    try:
        response = await provider.synthesize(request)
        
        print(f"\n✅ SUCCESS!")
        print(f"   Audio size: {len(response.audio_data):,} bytes")
        print(f"   Format: {response.format}")
        print(f"   Duration: {response.duration:.2f} seconds")
        
        # Get proper file extension from detected format
        extension = response.format.value  # e.g., "mp3", "wav"
        output_file = f"/tmp/test_tts_step3.{extension}"
        
        with open(output_file, "wb") as f:
            f.write(response.audio_data)
        print(f"   Saved to: {output_file}")
        
        # Show metadata if available
        if response.metadata:
            requested = response.metadata.get('requested_format', 'unknown')
            actual = response.metadata.get('actual_format', 'unknown')
            if requested != actual:
                print(f"   ℹ️  Note: Requested {requested} but got {actual}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ FAILED!")
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_provider_simple())
    sys.exit(0 if success else 1)
