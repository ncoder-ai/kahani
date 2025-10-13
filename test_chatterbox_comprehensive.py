"""
Comprehensive ChatterboxTTS Provider Testing

Tests all ChatterboxTTS-specific features:
1. Voice library management (list, get info)
2. Different voices
3. Advanced parameters (exaggeration, temperature, cfg_weight)
4. Streaming vs non-streaming
5. Default voice settings
"""

import sys
import asyncio
import time
sys.path.insert(0, '/Users/nishant/apps/kahani/backend')

from app.services.tts.providers.chatterbox import ChatterboxProvider
from app.services.tts.base import TTSProviderConfig, TTSRequest, AudioFormat


async def test_chatterbox_comprehensive():
    """Comprehensive test of ChatterboxTTS features"""
    
    print("=" * 70)
    print("COMPREHENSIVE CHATTERBOXTTS TESTING")
    print("=" * 70)
    
    # Create provider configuration
    config = TTSProviderConfig(
        api_url="http://172.16.23.80:4321/v1",
        api_key="",
        timeout=120,
        extra_params={
            "max_text_length": 3000
        }
    )
    
    provider = ChatterboxProvider(config)
    test_text = "This is a test of the ChatterboxTTS provider with different settings."
    
    # Test 1: List available voices
    print("\n" + "=" * 70)
    print("TEST 1: List Available Voices")
    print("=" * 70)
    try:
        voices = await provider.get_voices()
        print(f"✓ Found {len(voices)} voices")
        
        # Show sample of male and female voices
        male_voices = [v for v in voices if 'male' in v.id.lower() and 'female' not in v.id.lower()]
        female_voices = [v for v in voices if 'female' in v.id.lower()]
        
        print(f"\n  Male voices: {len(male_voices)}")
        print(f"  Sample: {[v.id for v in male_voices[:5]]}")
        
        print(f"\n  Female voices: {len(female_voices)}")
        print(f"  Sample: {[v.id for v in female_voices[:5]]}")
        
    except Exception as e:
        print(f"✗ Failed: {e}")
        return
    
    # Test 2: Get default voice
    print("\n" + "=" * 70)
    print("TEST 2: Get Default Voice")
    print("=" * 70)
    try:
        default_voice = await provider.get_default_voice()
        if default_voice:
            print(f"✓ Default voice:")
            print(f"  Name: {default_voice.get('default_voice')}")
            print(f"  Source: {default_voice.get('source')}")
        else:
            print("  No default voice set")
    except Exception as e:
        print(f"✗ Failed: {e}")
    
    # Test 3: Basic synthesis with different voices
    print("\n" + "=" * 70)
    print("TEST 3: Different Voices Comparison")
    print("=" * 70)
    
    test_voices = ["female_06", "male_01", "female_01", "male_05"]
    
    for voice in test_voices:
        try:
            print(f"\n  Testing voice: {voice}")
            
            request = TTSRequest(
                text=f"Hello, this is {voice} speaking.",
                voice_id=voice,
                speed=1.0,
                format=AudioFormat.WAV,
                sample_rate=22050
            )
            
            start = time.time()
            response = await provider.synthesize(request)
            elapsed = time.time() - start
            
            print(f"    ✓ Generated: {response.file_size:,} bytes in {elapsed:.2f}s")
            print(f"    Duration: {response.duration:.2f}s")
            
            # Save for listening
            output_file = f"/tmp/chatterbox_{voice}.wav"
            with open(output_file, "wb") as f:
                f.write(response.audio_data)
            print(f"    Saved to: {output_file}")
            
        except Exception as e:
            print(f"    ✗ Failed: {e}")
    
    # Test 4: Advanced parameters (exaggeration, temperature, cfg_weight)
    print("\n" + "=" * 70)
    print("TEST 4: Advanced Parameters")
    print("=" * 70)
    
    parameter_tests = [
        {
            "name": "Default",
            "params": {}
        },
        {
            "name": "High Exaggeration",
            "params": {"exaggeration": 1.8}
        },
        {
            "name": "Low Exaggeration",
            "params": {"exaggeration": 0.5}
        },
        {
            "name": "High Temperature",
            "params": {"temperature": 2.0}
        },
        {
            "name": "Low Temperature",
            "params": {"temperature": 0.2}
        },
        {
            "name": "High CFG Weight",
            "params": {"cfg_weight": 0.9}
        },
        {
            "name": "Low CFG Weight",
            "params": {"cfg_weight": 0.3}
        }
    ]
    
    test_sentence = "The quick brown fox jumps over the lazy dog with great enthusiasm!"
    
    for test in parameter_tests:
        try:
            print(f"\n  Testing: {test['name']}")
            print(f"    Parameters: {test['params']}")
            
            request = TTSRequest(
                text=test_sentence,
                voice_id="female_06",
                speed=1.0,
                format=AudioFormat.WAV,
                sample_rate=22050,
                extra_params=test['params']
            )
            
            start = time.time()
            response = await provider.synthesize(request)
            elapsed = time.time() - start
            
            print(f"    ✓ Generated: {response.file_size:,} bytes in {elapsed:.2f}s")
            
            # Save for comparison
            safe_name = test['name'].lower().replace(' ', '_')
            output_file = f"/tmp/chatterbox_{safe_name}.wav"
            with open(output_file, "wb") as f:
                f.write(response.audio_data)
            print(f"    Saved to: {output_file}")
            
        except Exception as e:
            print(f"    ✗ Failed: {e}")
    
    # Test 5: Streaming
    print("\n" + "=" * 70)
    print("TEST 5: Streaming Synthesis")
    print("=" * 70)
    
    longer_text = """
    This is a longer text to test streaming capabilities. 
    The audio should be generated and streamed in real-time.
    This allows for immediate playback while generation continues.
    Streaming is particularly useful for longer content where 
    users don't want to wait for the entire generation to complete.
    """
    
    try:
        print(f"\n  Text length: {len(longer_text)} characters")
        print(f"  Starting streaming synthesis...")
        
        request = TTSRequest(
            text=longer_text,
            voice_id="female_06",
            speed=1.0,
            format=AudioFormat.WAV,
            sample_rate=22050
        )
        
        chunks_received = 0
        total_bytes = 0
        start = time.time()
        
        async for chunk in provider.synthesize_stream(request):
            chunks_received += 1
            total_bytes += len(chunk)
            elapsed = time.time() - start
            print(f"    [{elapsed:.2f}s] Chunk {chunks_received}: {len(chunk):,} bytes")
        
        elapsed = time.time() - start
        print(f"\n    ✓ Streaming complete!")
        print(f"    Total chunks: {chunks_received}")
        print(f"    Total data: {total_bytes:,} bytes")
        print(f"    Time: {elapsed:.2f}s")
        
    except Exception as e:
        print(f"    ✗ Failed: {e}")
    
    # Test 6: Compare streaming vs non-streaming for same text
    print("\n" + "=" * 70)
    print("TEST 6: Streaming vs Non-Streaming Comparison")
    print("=" * 70)
    
    comparison_text = "This is a test to compare streaming versus non-streaming generation."
    
    # Non-streaming
    try:
        print(f"\n  Non-Streaming:")
        request = TTSRequest(
            text=comparison_text,
            voice_id="female_06",
            format=AudioFormat.WAV,
            sample_rate=22050
        )
        
        start = time.time()
        response = await provider.synthesize(request)
        elapsed = time.time() - start
        
        print(f"    Time: {elapsed:.2f}s")
        print(f"    Size: {response.file_size:,} bytes")
        
        with open("/tmp/chatterbox_nonstreaming.wav", "wb") as f:
            f.write(response.audio_data)
        
    except Exception as e:
        print(f"    ✗ Failed: {e}")
    
    # Streaming
    try:
        print(f"\n  Streaming:")
        request = TTSRequest(
            text=comparison_text,
            voice_id="female_06",
            format=AudioFormat.WAV,
            sample_rate=22050
        )
        
        start = time.time()
        chunks = []
        async for chunk in provider.synthesize_stream(request):
            chunks.append(chunk)
        elapsed = time.time() - start
        
        total_size = sum(len(c) for c in chunks)
        
        print(f"    Time: {elapsed:.2f}s")
        print(f"    Chunks: {len(chunks)}")
        print(f"    Total size: {total_size:,} bytes")
        
        # Save combined
        with open("/tmp/chatterbox_streaming.wav", "wb") as f:
            f.write(b"".join(chunks))
        
    except Exception as e:
        print(f"    ✗ Failed: {e}")
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print("\n✓ All ChatterboxTTS tests completed!")
    print("\nGenerated test files in /tmp/:")
    print("  - chatterbox_female_06.wav")
    print("  - chatterbox_male_01.wav")
    print("  - chatterbox_female_01.wav")
    print("  - chatterbox_male_05.wav")
    print("  - chatterbox_default.wav")
    print("  - chatterbox_high_exaggeration.wav")
    print("  - chatterbox_low_exaggeration.wav")
    print("  - chatterbox_high_temperature.wav")
    print("  - chatterbox_low_temperature.wav")
    print("  - chatterbox_high_cfg_weight.wav")
    print("  - chatterbox_low_cfg_weight.wav")
    print("  - chatterbox_nonstreaming.wav")
    print("  - chatterbox_streaming.wav")
    print("\n💡 Listen to compare:")
    print("     Different voices: afplay /tmp/chatterbox_female_06.wav")
    print("     Parameters: afplay /tmp/chatterbox_high_exaggeration.wav")
    print("     Streaming vs non: afplay /tmp/chatterbox_nonstreaming.wav && afplay /tmp/chatterbox_streaming.wav")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(test_chatterbox_comprehensive())
