"""
Test Streaming Support

Tests streaming audio generation with OpenAI-compatible provider.
"""

import sys
import asyncio
sys.path.insert(0, '/Users/nishant/apps/kahani/backend')

from app.services.tts.providers.openai_compatible import OpenAICompatibleProvider
from app.services.tts.base import TTSProviderConfig, TTSRequest, AudioFormat


async def test_streaming():
    """Test streaming audio generation"""
    
    print("=" * 60)
    print("Testing Streaming Support")
    print("=" * 60)
    
    # Create provider configuration
    config = TTSProviderConfig(
        api_url="http://172.16.23.80:4321/v1",
        api_key="",
        timeout=120,
        extra_params={
            "max_text_length": 280
        }
    )
    
    provider = OpenAICompatibleProvider(config)
    
    # Test text
    test_text = "This is a streaming test. The audio should be generated and streamed in real-time, allowing playback to start before the entire generation is complete."
    
    print(f"\nTest text: '{test_text}'")
    print(f"Text length: {len(test_text)} characters")
    
    # Test streaming synthesis
    print("\nTesting synthesize_stream()...")
    try:
        request = TTSRequest(
            text=test_text,
            voice_id="female_06",
            speed=1.0,
            format=AudioFormat.WAV,
            sample_rate=22050
        )
        
        print("Starting streaming synthesis...")
        chunks_received = 0
        total_bytes = 0
        all_chunks = []
        
        async for chunk in provider.synthesize_stream(request):
            chunks_received += 1
            chunk_size = len(chunk)
            total_bytes += chunk_size
            all_chunks.append(chunk)
            print(f"  Chunk {chunks_received}: {chunk_size} bytes (Total: {total_bytes} bytes)")
        
        print(f"\n✓ Streaming completed!")
        print(f"  Total chunks received: {chunks_received}")
        print(f"  Total audio data: {total_bytes} bytes")
        
        # Verify we can reconstruct the audio
        if all_chunks:
            complete_audio = b"".join(all_chunks)
            print(f"  Reconstructed audio: {len(complete_audio)} bytes")
            
            # Save to file for verification
            output_file = "/tmp/test_streaming_output.wav"
            with open(output_file, "wb") as f:
                f.write(complete_audio)
            print(f"  Saved to: {output_file}")
            
            # Check if it's valid audio
            if complete_audio[:4] == b'RIFF' and complete_audio[8:12] == b'WAVE':
                print(f"  ✓ Valid WAV format detected")
            else:
                print(f"  ⚠ Audio format may not be WAV")
        
    except Exception as e:
        print(f"✗ Streaming failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("Streaming Test Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_streaming())
