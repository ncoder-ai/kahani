"""
Test Real Streaming with Scene Content

Tests streaming audio generation with real scene content and demonstrates
that audio chunks are received progressively, not all at once.
"""

import sys
import asyncio
import time
import sqlite3
sys.path.insert(0, '/Users/user/apps/kahani/backend')

from app.services.tts.providers.openai_compatible import OpenAICompatibleProvider
from app.services.tts.base import TTSProviderConfig, TTSRequest, AudioFormat


async def test_streaming_with_scene():
    """Test streaming with actual scene content"""
    
    print("=" * 60)
    print("Testing Real Streaming with Scene Content")
    print("=" * 60)
    
    # Get scene content using direct SQLite connection
    db_path = 'backend/data/kahani.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get any scene with an active variant
    cursor.execute('''
        SELECT sf.scene_id, sf.story_id, sv.content
        FROM story_flows sf
        JOIN scene_variants sv ON sf.scene_variant_id = sv.id
        WHERE sf.is_active = 1
        LIMIT 1
    ''')
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print("✗ No scenes found in database")
        return
    
    scene_id, story_id, scene_text = result
    print(f"\n✓ Found scene content")
    print(f"  Story {story_id}, Scene {scene_id}")
    print(f"  Text length: {len(scene_text)} characters")
    print(f"  Preview: {scene_text[:100]}...")
    
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
    
    # Test streaming with timing
    print("\n" + "=" * 60)
    print("Starting Streaming Synthesis")
    print("=" * 60)
    print("\nWatch the timestamps - chunks should arrive progressively,")
    print("not all at once at the end!\n")
    
    try:
        request = TTSRequest(
            text=scene_text,
            voice_id="female_06",
            speed=1.0,
            format=AudioFormat.WAV,
            sample_rate=22050
        )
        
        start_time = time.time()
        chunks_received = 0
        total_bytes = 0
        all_chunks = []
        chunk_times = []
        
        print(f"[{0:.2f}s] Starting stream...")
        
        async for chunk in provider.synthesize_stream(request):
            elapsed = time.time() - start_time
            chunks_received += 1
            chunk_size = len(chunk)
            total_bytes += chunk_size
            all_chunks.append(chunk)
            chunk_times.append(elapsed)
            
            # Print every 10th chunk to avoid spam
            if chunks_received % 10 == 0:
                print(f"[{elapsed:.2f}s] Chunk {chunks_received}: {chunk_size} bytes (Total: {total_bytes:,} bytes)")
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        print(f"\n[{total_duration:.2f}s] ✓ Streaming completed!")
        print(f"\n" + "=" * 60)
        print("Streaming Statistics")
        print("=" * 60)
        print(f"Total chunks received: {chunks_received}")
        print(f"Total audio data: {total_bytes:,} bytes ({total_bytes/1024/1024:.2f} MB)")
        print(f"Total time: {total_duration:.2f} seconds")
        print(f"Average chunk size: {total_bytes/chunks_received:.0f} bytes")
        
        # Analyze streaming pattern
        if len(chunk_times) > 1:
            first_chunk_time = chunk_times[0]
            last_chunk_time = chunk_times[-1]
            
            print(f"\nStreaming Pattern Analysis:")
            print(f"  First chunk arrived at: {first_chunk_time:.2f}s")
            print(f"  Last chunk arrived at: {last_chunk_time:.2f}s")
            print(f"  Time between first and last: {last_chunk_time - first_chunk_time:.2f}s")
            
            if last_chunk_time - first_chunk_time > 1.0:
                print(f"  ✓ TRUE STREAMING - Chunks arrived progressively over {last_chunk_time - first_chunk_time:.2f}s")
            else:
                print(f"  ✗ NOT TRUE STREAMING - All chunks arrived within 1 second")
        
        # Save complete audio
        if all_chunks:
            complete_audio = b"".join(all_chunks)
            output_file = "/tmp/test_scene_streaming.wav"
            with open(output_file, "wb") as f:
                f.write(complete_audio)
            print(f"\n  Complete audio saved to: {output_file}")
            
            # Verify it's valid WAV
            if complete_audio[:4] == b'RIFF' and complete_audio[8:12] == b'WAVE':
                print(f"  ✓ Valid WAV format")
            
            # Get duration
            import subprocess
            result = subprocess.run(
                ['afinfo', output_file],
                capture_output=True,
                text=True
            )
            for line in result.stdout.split('\n'):
                if 'estimated duration' in line:
                    print(f"  {line.strip()}")
        
        print("\n" + "=" * 60)
        print("Now playing the complete audio...")
        print("=" * 60)
        
        # Play the audio
        import subprocess
        subprocess.run(['afplay', output_file])
        
    except Exception as e:
        print(f"\n✗ Streaming failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_streaming_with_scene())
