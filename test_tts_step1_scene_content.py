#!/usr/bin/env python3
"""
Step 1: Verify Scene Content Exists
Check if scene 2 has variant content and its length
"""
import sqlite3
import sys

def test_scene_content():
    print("\n" + "="*60)
    print("STEP 1: Verify Scene Content Exists")
    print("="*60 + "\n")
    
    db_path = 'backend/data/kahani.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    scene_id = 2
    
    # Get scene info
    cursor.execute('SELECT id, story_id, sequence_number FROM scenes WHERE id = ?', (scene_id,))
    scene = cursor.fetchone()
    
    if not scene:
        print(f"❌ Scene {scene_id} not found!")
        return False
    
    print(f"✅ Scene found:")
    print(f"   ID: {scene[0]}")
    print(f"   Story ID: {scene[1]}")
    print(f"   Sequence: {scene[2]}")
    
    # Get active variant from story flow
    cursor.execute('''
        SELECT sf.scene_variant_id, sv.content, sv.variant_number, sv.title
        FROM story_flows sf
        JOIN scene_variants sv ON sf.scene_variant_id = sv.id
        WHERE sf.scene_id = ? AND sf.is_active = 1
    ''', (scene_id,))
    
    variant = cursor.fetchone()
    
    if not variant:
        print(f"\n❌ No active variant found for scene {scene_id}")
        return False
    
    variant_id, content, variant_num, title = variant
    
    print(f"\n✅ Active variant found:")
    print(f"   Variant ID: {variant_id}")
    print(f"   Variant #: {variant_num}")
    print(f"   Title: {title}")
    print(f"   Content length: {len(content)} characters")
    print(f"\n📄 First 200 characters:")
    print(f"   {content[:200]}...")
    print(f"\n📄 Last 200 characters:")
    print(f"   ...{content[-200:]}")
    
    # Estimate audio generation time
    # Rough estimate: ~50 chars/second for TTS
    estimated_seconds = len(content) / 50
    print(f"\n⏱️  Estimated TTS generation time: {estimated_seconds:.1f} seconds")
    
    if estimated_seconds > 100:
        print(f"   ⚠️  WARNING: Content is very long! Consider testing with shorter scene first.")
    
    conn.close()
    
    return True

if __name__ == "__main__":
    success = test_scene_content()
    sys.exit(0 if success else 1)
