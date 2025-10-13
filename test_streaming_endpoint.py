"""
Test Streaming Endpoint

Tests the new /api/tts/stream/{scene_id} endpoint that streams audio chunks
as they're generated, allowing frontend to play progressively.
"""

import sys
import sqlite3
import requests
import time
sys.path.insert(0, '/Users/nishant/apps/kahani/backend')


def test_streaming_endpoint():
    """Test the streaming endpoint with a real scene"""
    
    print("=" * 60)
    print("Testing Streaming Audio Endpoint")
    print("=" * 60)
    
    # Get any scene from database
    db_path = 'backend/data/kahani.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT sf.scene_id, sf.story_id, sv.content, LENGTH(sv.content) as len
        FROM story_flows sf
        JOIN scene_variants sv ON sf.scene_variant_id = sv.id
        WHERE sf.is_active = 1
        ORDER BY len DESC
        LIMIT 1
    ''')
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print("✗ No scenes found in database")
        return
    
    scene_id, story_id, scene_text, text_len = result
    print(f"\n✓ Found scene content")
    print(f"  Story {story_id}, Scene {scene_id}")
    print(f"  Text length: {text_len} characters")
    print(f"  Preview: {scene_text[:100]}...")
    
    # Test the streaming endpoint
    print(f"\n" + "=" * 60)
    print("Streaming Audio Chunks from API")
    print("=" * 60)
    
    # Login first to get token
    print("\nAuthenticating...")
    login_response = requests.post(
        "http://localhost:8000/api/auth/login",
        json={
            "email": "test@test.com",
            "password": "test"
        }
    )
    
    if login_response.status_code != 200:
        print(f"✗ Login failed: {login_response.status_code}")
        print(f"Response: {login_response.text}")
        return
    
    token = login_response.json()["access_token"]
    print("✓ Authenticated")
    
    url = f"http://localhost:8000/api/tts/stream/{scene_id}"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "force_regenerate": True
    }
    
    print(f"\nURL: {url}")
    print(f"Method: POST")
    print(f"Streaming: Yes\n")
    
    start_time = time.time()
    chunks_received = 0
    total_bytes = 0
    chunk_times = []
    all_chunks = []
    
    try:
        print("[{:.2f}s] Starting stream request...".format(0))
        
        response = requests.post(url, json=payload, headers=headers, stream=True)
        
        if response.status_code != 200:
            print(f"\n✗ Request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return
        
        print("[{:.2f}s] Connected, receiving chunks...\n".format(time.time() - start_time))
        
        # Read chunks as they arrive
        chunk_buffer = b""
        for chunk in response.iter_content(chunk_size=None):  # Let requests decide chunk size
            if chunk:
                elapsed = time.time() - start_time
                chunks_received += 1
                chunk_size = len(chunk)
                total_bytes += chunk_size
                chunk_buffer += chunk
                chunk_times.append(elapsed)
                
                # Check if we've received a complete WAV file
                # WAV files start with RIFF and contain WAVE
                if chunk_buffer.startswith(b'RIFF') and b'WAVE' in chunk_buffer:
                    # Try to extract complete WAV file
                    if len(chunk_buffer) >= 8:
                        # Get file size from RIFF header (bytes 4-7, little-endian)
                        import struct
                        file_size = struct.unpack('<I', chunk_buffer[4:8])[0]
                        expected_total_size = file_size + 8  # RIFF header adds 8 bytes
                        
                        if len(chunk_buffer) >= expected_total_size:
                            # We have a complete WAV file!
                            complete_wav = chunk_buffer[:expected_total_size]
                            all_chunks.append(complete_wav)
                            chunk_buffer = chunk_buffer[expected_total_size:]  # Keep remainder
                            
                            wav_num = len(all_chunks)
                            print(f"[{elapsed:.2f}s] 🎵 Chunk {wav_num} received: {len(complete_wav):,} bytes")
                
        end_time = time.time()
        total_duration = end_time - start_time
        
        # Save any remaining data
        if len(chunk_buffer) > 100:
            all_chunks.append(chunk_buffer)
            print(f"[{total_duration:.2f}s] 🎵 Final chunk: {len(chunk_buffer):,} bytes")
        
        print(f"\n" + "=" * 60)
        print("Streaming Complete!")
        print("=" * 60)
        print(f"Total audio chunks (WAV files): {len(all_chunks)}")
        print(f"Total data received: {total_bytes:,} bytes ({total_bytes/1024/1024:.2f} MB)")
        print(f"Total time: {total_duration:.2f} seconds")
        
        if chunk_times and len(chunk_times) > 1:
            first_chunk_time = chunk_times[0]
            last_chunk_time = chunk_times[-1]
            
            print(f"\nTiming Analysis:")
            print(f"  First data arrived at: {first_chunk_time:.2f}s")
            print(f"  Last data arrived at: {last_chunk_time:.2f}s")
            print(f"  Streaming duration: {last_chunk_time - first_chunk_time:.2f}s")
            
            if len(all_chunks) > 1:
                print(f"  ✓ TRUE STREAMING - Received {len(all_chunks)} separate audio chunks!")
                print(f"  💡 Frontend can play each chunk as it arrives")
            else:
                print(f"  ℹ Single audio chunk (scene text short enough for one generation)")
        
        # Save chunks for playback verification
        if all_chunks:
            print(f"\n" + "=" * 60)
            print("Saving Audio Chunks")
            print("=" * 60)
            
            for i, chunk_data in enumerate(all_chunks, 1):
                output_file = f"/tmp/stream_chunk_{i}.wav"
                with open(output_file, "wb") as f:
                    f.write(chunk_data)
                print(f"  Chunk {i}: {output_file} ({len(chunk_data):,} bytes)")
            
            print(f"\n💡 Play chunks sequentially:")
            for i in range(1, len(all_chunks) + 1):
                print(f"     afplay /tmp/stream_chunk_{i}.wav")
            
            if len(all_chunks) > 1:
                print(f"\n💡 Or play all at once:")
                cmd = " && ".join([f"afplay /tmp/stream_chunk_{i}.wav" for i in range(1, len(all_chunks) + 1)])
                print(f"     {cmd}")
        
    except Exception as e:
        print(f"\n✗ Streaming failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_streaming_endpoint()
