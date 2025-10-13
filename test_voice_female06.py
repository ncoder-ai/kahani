"""
Quick test of female_06 voice
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.services.tts import (
    TTSProviderFactory,
    TTSRequest,
    AudioFormat
)


async def test_female_06():
    print("\n🎙️  Testing female_06 voice...\n")
    
    # Create provider
    provider = TTSProviderFactory.create_provider(
        provider_type="openai-compatible",
        api_url="http://172.16.23.80:4321/v1",
        api_key="",
        timeout=30
    )
    
    # Test text
    test_text = "Hello! This is a test of the female zero six voice. How do I sound?"
    
    print(f"Text: '{test_text}'")
    print(f"Voice: female_06")
    print(f"Length: {len(test_text)} characters\n")
    
    try:
        request = TTSRequest(
            text=test_text,
            voice_id="female_06",
            speed=1.0,
            format=AudioFormat.MP3
        )
        
        print("Generating audio...")
        response = await provider.synthesize(request)
        
        print(f"✓ Audio generated!")
        print(f"  File size: {response.file_size} bytes ({response.file_size / 1024:.2f} KB)")
        print(f"  Duration: {response.duration:.2f} seconds")
        print(f"  Format: {response.format.value}")
        
        # Save audio
        output_path = "/tmp/test_female_06.wav"
        with open(output_path, "wb") as f:
            f.write(response.audio_data)
        
        print(f"\n✅ Audio saved to: {output_path}")
        print("🔊 Playing audio...")
        
        # Play the audio
        import subprocess
        subprocess.run(["afplay", output_path])
        
        print("✅ Done!\n")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_female_06())
