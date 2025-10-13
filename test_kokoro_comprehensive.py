"""
Comprehensive Kokoro TTS Provider Testing

Tests all Kokoro-specific features:
1. Voice retrieval
2. Different voices (American, British)
3. Speed control (0.25 - 4.0)
4. Volume multiplier
5. Streaming vs non-streaming
6. Voice combining
7. Phoneme generation
8. Multiple audio formats
"""

import sys
import asyncio
import time
sys.path.insert(0, '/Users/user/apps/kahani/backend')

from app.services.tts.providers.kokoro import KokoroProvider
from app.services.tts.base import TTSProviderConfig, TTSRequest, AudioFormat


async def test_kokoro_comprehensive():
    """Comprehensive test of Kokoro TTS features"""
    
    print("=" * 70)
    print("COMPREHENSIVE KOKORO TTS TESTING")
    print("API URL: http://172.16.23.80:8880")
    print("=" * 70)
    
    # Create provider configuration
    config = TTSProviderConfig(
        api_url="http://172.16.23.80:8880",
        api_key="",
        timeout=120,
        extra_params={
            "max_text_length": 5000
        }
    )
    
    provider = KokoroProvider(config)
    test_text = "This is a test of the Kokoro text to speech system."
    
    # Test 1: List available voices
    print("\n" + "=" * 70)
    print("TEST 1: List Available Voices")
    print("=" * 70)
    try:
        voices = await provider.get_voices()
        print(f"✓ Found {len(voices)} voices")
        
        # Group by language
        american = [v for v in voices if v.language.startswith("American")]
        british = [v for v in voices if v.language.startswith("British")]
        japanese = [v for v in voices if v.language.startswith("Japanese")]
        
        print(f"\n  American English: {len(american)}")
        print(f"    Sample: {[v.id for v in american[:5]]}")
        
        print(f"\n  British English: {len(british)}")
        print(f"    Sample: {[v.id for v in british[:5]]}")
        
        if japanese:
            print(f"\n  Japanese: {len(japanese)}")
            print(f"    Sample: {[v.id for v in japanese[:3]]}")
        
    except Exception as e:
        print(f"✗ Failed: {e}")
        return
    
    # Test 2: Basic synthesis with different voices
    print("\n" + "=" * 70)
    print("TEST 2: Different Voices Comparison")
    print("=" * 70)
    
    test_voices = ["af_heart", "af_bella", "am_adam", "bf_emma"]
    
    for voice in test_voices:
        try:
            print(f"\n  Testing voice: {voice}")
            
            request = TTSRequest(
                text=f"Hello, this is {voice} speaking. Nice to meet you!",
                voice_id=voice,
                speed=1.0,
                format=AudioFormat.WAV,
                sample_rate=24000
            )
            
            start = time.time()
            response = await provider.synthesize(request)
            elapsed = time.time() - start
            
            print(f"    ✓ Generated: {response.file_size:,} bytes in {elapsed:.2f}s")
            print(f"    Duration: {response.duration:.2f}s")
            
            # Save for listening
            output_file = f"/tmp/kokoro_{voice}.wav"
            with open(output_file, "wb") as f:
                f.write(response.audio_data)
            print(f"    Saved to: {output_file}")
            
        except Exception as e:
            print(f"    ✗ Failed: {e}")
    
    # Test 3: Speed variations
    print("\n" + "=" * 70)
    print("TEST 3: Speed Control")
    print("=" * 70)
    
    speed_tests = [0.5, 1.0, 1.5, 2.0]
    speed_text = "The quick brown fox jumps over the lazy dog."
    
    for speed in speed_tests:
        try:
            print(f"\n  Testing speed: {speed}x")
            
            request = TTSRequest(
                text=speed_text,
                voice_id="af_heart",
                speed=speed,
                format=AudioFormat.WAV,
                sample_rate=24000
            )
            
            start = time.time()
            response = await provider.synthesize(request)
            elapsed = time.time() - start
            
            print(f"    ✓ Generated: {response.file_size:,} bytes in {elapsed:.2f}s")
            print(f"    Duration: {response.duration:.2f}s")
            
            # Save for comparison
            output_file = f"/tmp/kokoro_speed_{str(speed).replace('.', '_')}x.wav"
            with open(output_file, "wb") as f:
                f.write(response.audio_data)
            print(f"    Saved to: {output_file}")
            
        except Exception as e:
            print(f"    ✗ Failed: {e}")
    
    # Test 4: Volume multiplier
    print("\n" + "=" * 70)
    print("TEST 4: Volume Multiplier")
    print("=" * 70)
    
    volume_tests = [0.5, 1.0, 1.5]
    
    for volume in volume_tests:
        try:
            print(f"\n  Testing volume: {volume}x")
            
            request = TTSRequest(
                text="Testing volume control with different multipliers.",
                voice_id="af_heart",
                speed=1.0,
                format=AudioFormat.WAV,
                sample_rate=24000,
                extra_params={"volume_multiplier": volume}
            )
            
            start = time.time()
            response = await provider.synthesize(request)
            elapsed = time.time() - start
            
            print(f"    ✓ Generated: {response.file_size:,} bytes in {elapsed:.2f}s")
            
            # Save for comparison
            output_file = f"/tmp/kokoro_volume_{str(volume).replace('.', '_')}x.wav"
            with open(output_file, "wb") as f:
                f.write(response.audio_data)
            print(f"    Saved to: {output_file}")
            
        except Exception as e:
            print(f"    ✗ Failed: {e}")
    
    # Test 5: Different audio formats
    print("\n" + "=" * 70)
    print("TEST 5: Audio Format Support")
    print("=" * 70)
    
    format_tests = [
        (AudioFormat.WAV, "wav"),
        (AudioFormat.MP3, "mp3"),
        (AudioFormat.FLAC, "flac"),
        (AudioFormat.OPUS, "opus")
    ]
    
    for audio_format, ext in format_tests:
        try:
            print(f"\n  Testing format: {ext}")
            
            request = TTSRequest(
                text="Testing different audio formats.",
                voice_id="af_heart",
                speed=1.0,
                format=audio_format,
                sample_rate=24000
            )
            
            start = time.time()
            response = await provider.synthesize(request)
            elapsed = time.time() - start
            
            print(f"    ✓ Generated: {response.file_size:,} bytes in {elapsed:.2f}s")
            
            # Save
            output_file = f"/tmp/kokoro_format.{ext}"
            with open(output_file, "wb") as f:
                f.write(response.audio_data)
            print(f"    Saved to: {output_file}")
            
        except Exception as e:
            print(f"    ✗ Failed: {e}")
    
    # Test 6: Streaming
    print("\n" + "=" * 70)
    print("TEST 6: Streaming Synthesis")
    print("=" * 70)
    
    longer_text = """
    This is a longer text to test Kokoro's streaming capabilities. 
    The audio should be generated and streamed sentence by sentence.
    Streaming allows for immediate playback while generation continues.
    This is particularly useful for longer content where users want
    to start listening without waiting for complete generation.
    """
    
    try:
        print(f"\n  Text length: {len(longer_text)} characters")
        print(f"  Starting streaming synthesis...")
        
        request = TTSRequest(
            text=longer_text,
            voice_id="af_heart",
            speed=1.0,
            format=AudioFormat.WAV,
            sample_rate=24000
        )
        
        chunks_received = 0
        total_bytes = 0
        start = time.time()
        first_chunk_time = None
        
        async for chunk in provider.synthesize_stream(request):
            chunks_received += 1
            total_bytes += len(chunk)
            elapsed = time.time() - start
            
            if first_chunk_time is None:
                first_chunk_time = elapsed
            
            print(f"    [{elapsed:.2f}s] Chunk {chunks_received}: {len(chunk):,} bytes")
        
        elapsed = time.time() - start
        print(f"\n    ✓ Streaming complete!")
        print(f"    First chunk at: {first_chunk_time:.2f}s")
        print(f"    Total chunks: {chunks_received}")
        print(f"    Total data: {total_bytes:,} bytes")
        print(f"    Total time: {elapsed:.2f}s")
        
    except Exception as e:
        print(f"    ✗ Failed: {e}")
    
    # Test 7: Compare streaming vs non-streaming
    print("\n" + "=" * 70)
    print("TEST 7: Streaming vs Non-Streaming Comparison")
    print("=" * 70)
    
    comparison_text = "This is a test to compare streaming versus non-streaming generation with Kokoro."
    
    # Non-streaming
    try:
        print(f"\n  Non-Streaming:")
        request = TTSRequest(
            text=comparison_text,
            voice_id="af_heart",
            format=AudioFormat.WAV,
            sample_rate=24000
        )
        
        start = time.time()
        response = await provider.synthesize(request)
        elapsed = time.time() - start
        
        print(f"    Time: {elapsed:.2f}s")
        print(f"    Size: {response.file_size:,} bytes")
        
        with open("/tmp/kokoro_nonstreaming.wav", "wb") as f:
            f.write(response.audio_data)
        
    except Exception as e:
        print(f"    ✗ Failed: {e}")
    
    # Streaming
    try:
        print(f"\n  Streaming:")
        request = TTSRequest(
            text=comparison_text,
            voice_id="af_heart",
            format=AudioFormat.WAV,
            sample_rate=24000
        )
        
        start = time.time()
        chunks = []
        first_chunk_time = None
        
        async for chunk in provider.synthesize_stream(request):
            if first_chunk_time is None:
                first_chunk_time = time.time() - start
            chunks.append(chunk)
        
        elapsed = time.time() - start
        total_size = sum(len(c) for c in chunks)
        
        print(f"    First chunk at: {first_chunk_time:.2f}s")
        print(f"    Total time: {elapsed:.2f}s")
        print(f"    Chunks: {len(chunks)}")
        print(f"    Total size: {total_size:,} bytes")
        
        # Save combined
        with open("/tmp/kokoro_streaming.wav", "wb") as f:
            f.write(b"".join(chunks))
        
    except Exception as e:
        print(f"    ✗ Failed: {e}")
    
    # Test 8: Voice combining (Kokoro-specific)
    print("\n" + "=" * 70)
    print("TEST 8: Voice Combining (Kokoro-specific)")
    print("=" * 70)
    
    try:
        print(f"\n  Combining voices: af_heart + af_bella")
        
        combined_voice_data = await provider.combine_voices(["af_heart", "af_bella"])
        print(f"    ✓ Combined voice created: {len(combined_voice_data):,} bytes")
        
        # Save the .pt file
        with open("/tmp/kokoro_combined_voice.pt", "wb") as f:
            f.write(combined_voice_data)
        print(f"    Saved to: /tmp/kokoro_combined_voice.pt")
        
    except Exception as e:
        print(f"    ✗ Failed: {e}")
    
    # Test 9: Phonemization (Kokoro-specific)
    print("\n" + "=" * 70)
    print("TEST 9: Text Phonemization (Kokoro-specific)")
    print("=" * 70)
    
    try:
        print(f"\n  Phonemizing text...")
        
        phoneme_result = await provider.phonemize_text(
            "Hello, how are you today?",
            language="a"  # American English
        )
        
        print(f"    ✓ Phonemized successfully")
        print(f"    Phonemes: {phoneme_result.get('phonemes', '')}")
        print(f"    Token count: {len(phoneme_result.get('tokens', []))}")
        
    except Exception as e:
        print(f"    ✗ Failed: {e}")
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print("\n✓ All Kokoro TTS tests completed!")
    print("\nGenerated test files in /tmp/:")
    print("  Voices: kokoro_af_heart.wav, kokoro_af_bella.wav, kokoro_am_adam.wav, kokoro_bf_emma.wav")
    print("  Speed: kokoro_speed_0_5x.wav, kokoro_speed_1_0x.wav, kokoro_speed_1_5x.wav, kokoro_speed_2_0x.wav")
    print("  Volume: kokoro_volume_0_5x.wav, kokoro_volume_1_0x.wav, kokoro_volume_1_5x.wav")
    print("  Formats: kokoro_format.wav, kokoro_format.mp3, kokoro_format.flac, kokoro_format.opus")
    print("  Streaming: kokoro_nonstreaming.wav, kokoro_streaming.wav")
    print("  Combined voice: kokoro_combined_voice.pt")
    print("\n💡 Listen to compare:")
    print("     Different voices: afplay /tmp/kokoro_af_heart.wav && afplay /tmp/kokoro_am_adam.wav")
    print("     Speed variations: afplay /tmp/kokoro_speed_0_5x.wav && afplay /tmp/kokoro_speed_2_0x.wav")
    print("     Volume levels: afplay /tmp/kokoro_volume_0_5x.wav && afplay /tmp/kokoro_volume_1_5x.wav")
    print("\n" + "=" * 70)
    
    # Close provider
    await provider.close()


if __name__ == "__main__":
    asyncio.run(test_kokoro_comprehensive())
