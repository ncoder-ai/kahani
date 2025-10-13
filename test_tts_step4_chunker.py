#!/usr/bin/env python3
"""
Step 4: Test Text Chunker with Scene Content
Test text chunker with actual scene content
"""
import sys
import os
import sqlite3

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.services.tts.text_chunker import TextChunker

def test_text_chunker():
    print("\n" + "="*60)
    print("STEP 4: Test Text Chunker with Scene Content")
    print("="*60 + "\n")
    
    # Get scene content
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
    print(f"Scene content: {len(content)} characters")
    
    # Create chunker
    chunker = TextChunker(max_chunk_size=280)
    print(f"\nChunking with max_chunk_size={chunker.max_chunk_size}...")
    
    chunks = chunker.chunk_text(content)
    
    print(f"\n✅ Chunked into {len(chunks)} chunks:\n")
    
    total_chars = 0
    for i, chunk in enumerate(chunks):
        print(f"Chunk {i+1}:")
        print(f"  Length: {len(chunk.text)} chars")
        print(f"  Start: {chunk.start_pos}, End: {chunk.end_pos}")
        print(f"  Preview: {chunk.text[:100]}...")
        total_chars += len(chunk.text)
        print()
    
    print(f"Total characters: {total_chars} (original: {len(content)})")
    print(f"Average chunk size: {total_chars / len(chunks):.1f} chars")
    
    # Estimate time
    # Rough estimate: 5 seconds per chunk for API call + processing
    estimated_time = len(chunks) * 5
    print(f"\n⏱️  Estimated total generation time: {estimated_time} seconds")
    
    if estimated_time > 120:
        print(f"   ⚠️  WARNING: Estimated time exceeds timeout!")
        print(f"   Consider reducing chunk count or increasing timeout")
    
    return True

if __name__ == "__main__":
    success = test_text_chunker()
    sys.exit(0 if success else 1)
