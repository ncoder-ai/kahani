#!/usr/bin/env python3
"""
Step 5: Test Full Scene Audio Generation
Test the complete scene audio generation flow
"""
import sys
import os
import asyncio

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.services.tts.factory import TTSProviderFactory
from app.services.tts.text_chunker import TextChunker
from app.services.tts.base import TTSRequest, AudioFormat
import sqlite3
import time

async def test_scene_generation():
    print("\n" + "="*60)
    print("STEP 5: Test Full Scene Audio Generation")
    print("="*60 + "\n")
    
    # Get scene content
    print("1️⃣  Fetching scene content...")
    db_path = 'backend/data/kahani.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    scene_id = 2
    cursor.execute('''
        SELECT sv.content
        FROM story_flows sf
        JOIN scene_variants sv ON sf.scene_variant_id = sv.id
        WHERE sf.scene_id = ? AND sf.is_active = 1
    ''', (scene_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print(f"❌ No content found for scene {scene_id}")
        return False
    
    content = result[0]
    print(f"   ✅ Content loaded: {len(content)} characters\n")
    
    # Create chunker and chunk text
    print("2️⃣  Chunking text...")
    chunker = TextChunker(max_chunk_size=280)
    chunks = chunker.chunk_text(content)
    print(f"   ✅ Split into {len(chunks)} chunks\n")
    
    # Create provider
    print("3️⃣  Creating TTS provider...")
    provider = TTSProviderFactory.create_provider(
        provider_type="openai-compatible",
        api_url="http://172.16.23.80:4321/v1",
        api_key="",
        timeout=120,
        extra_params={"response_format": "mp3"}
    )
    print(f"   ✅ Provider created\n")
    
    # Generate audio for each chunk
    print("4️⃣  Generating audio for all chunks...")
    all_audio_data = []
    total_duration = 0
    start_time = time.time()
    
    for i, chunk in enumerate(chunks, 1):
        print(f"\n   Chunk {i}/{len(chunks)} ({len(chunk.text)} chars)...")
        chunk_start = time.time()
        
        try:
            request = TTSRequest(
                text=chunk.text,
                voice_id="female_06",
                speed=1.0,
                format=AudioFormat.MP3
            )
            
            response = await provider.synthesize(request)
            chunk_elapsed = time.time() - chunk_start
            
            all_audio_data.append(response.audio_data)
            total_duration += response.duration
            
            print(f"      ✅ Generated {len(response.audio_data):,} bytes in {chunk_elapsed:.2f}s")
            print(f"      Format: {response.format.value}, Duration: {response.duration:.2f}s")
            
        except Exception as e:
            print(f"      ❌ Failed: {e}")
            return False
    
    total_elapsed = time.time() - start_time
    
    # Combine audio
    print(f"\n5️⃣  Combining audio chunks...")
    combined_audio = b''.join(all_audio_data)
    print(f"   ✅ Combined size: {len(combined_audio):,} bytes\n")
    
    # Save to file
    # Use the format from the last chunk (they should all be the same)
    extension = response.format.value
    output_file = f"/tmp/test_tts_step5_full_scene.{extension}"
    with open(output_file, "wb") as f:
        f.write(combined_audio)
    
    print("="*60)
    print("✅ SUCCESS!")
    print("="*60)
    print(f"Chunks generated: {len(chunks)}")
    print(f"Total audio size: {len(combined_audio):,} bytes ({len(combined_audio)/1024:.2f} KB)")
    print(f"Estimated duration: {total_duration:.2f} seconds")
    print(f"Generation time: {total_elapsed:.2f} seconds")
    print(f"Saved to: {output_file}")
    print(f"\nTo play: afplay {output_file}")
    print("="*60 + "\n")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_scene_generation())
    sys.exit(0 if success else 1)
