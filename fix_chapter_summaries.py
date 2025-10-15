#!/usr/bin/env python3
"""
Retroactively generate missing summaries for existing chapters.

This script will:
1. Find all chapters with scenes but no auto_summary
2. Generate auto_summary for each chapter
3. Regenerate story_so_far for all chapters in proper order
"""
import requests
import sys

BASE_URL = "http://localhost:8000"
EMAIL = "test@test.com"
PASSWORD = "test"

def login():
    """Login and get token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": EMAIL,
        "password": PASSWORD
    })
    if response.status_code == 200:
        token = response.json().get("access_token")
        print(f"✓ Logged in successfully\n")
        return token
    else:
        print(f"✗ Login failed: {response.status_code}")
        return None

def get_headers(token):
    return {"Authorization": f"Bearer {token}"}

def get_stories(token):
    """Get all stories"""
    headers = get_headers(token)
    response = requests.get(f"{BASE_URL}/api/stories/", headers=headers)
    if response.status_code == 200:
        return response.json()
    return []

def get_chapters(token, story_id):
    """Get all chapters for a story"""
    headers = get_headers(token)
    response = requests.get(f"{BASE_URL}/api/stories/{story_id}/chapters", headers=headers)
    if response.status_code == 200:
        return response.json()
    return []

def generate_chapter_summary(token, story_id, chapter_id, regenerate_story_so_far=False):
    """Generate summary for a chapter"""
    headers = get_headers(token)
    params = {"regenerate_story_so_far": str(regenerate_story_so_far).lower()}
    response = requests.post(
        f"{BASE_URL}/api/stories/{story_id}/chapters/{chapter_id}/generate-summary",
        headers=headers,
        params=params
    )
    return response.status_code == 200, response.json() if response.status_code == 200 else None

def main():
    print("=" * 80)
    print("RETROACTIVE CHAPTER SUMMARY GENERATOR")
    print("=" * 80)
    print()
    
    # Login
    token = login()
    if not token:
        sys.exit(1)
    
    # Get all stories
    stories = get_stories(token)
    if not stories:
        print("✗ No stories found")
        sys.exit(0)
    
    print(f"Found {len(stories)} stories\n")
    
    # Process each story
    for story in stories:
        story_id = story['id']
        story_title = story['title']
        
        print("=" * 80)
        print(f"STORY: {story_title} (ID: {story_id})")
        print("=" * 80)
        
        # Get chapters
        chapters = get_chapters(token, story_id)
        if not chapters:
            print("  No chapters found\n")
            continue
        
        chapters_to_fix = []
        for ch in chapters:
            if ch['scenes_count'] > 0 and not ch.get('auto_summary'):
                chapters_to_fix.append(ch)
        
        if not chapters_to_fix:
            print(f"  ✓ All chapters already have summaries\n")
            continue
        
        print(f"  Found {len(chapters_to_fix)} chapter(s) needing summaries:\n")
        
        # Step 1: Generate auto_summary for each chapter (in order)
        print("  Step 1: Generating chapter summaries (auto_summary)...")
        for ch in sorted(chapters_to_fix, key=lambda x: x['chapter_number']):
            chapter_num = ch['chapter_number']
            chapter_id = ch['id']
            scenes_count = ch['scenes_count']
            
            print(f"    Chapter {chapter_num} ({scenes_count} scenes)...", end=" ")
            success, result = generate_chapter_summary(token, story_id, chapter_id, regenerate_story_so_far=False)
            
            if success:
                summary = result.get('chapter_summary', '')
                preview = summary[:60] + "..." if len(summary) > 60 else summary
                print(f"✓ Generated")
                print(f"      Preview: {preview}")
            else:
                print(f"✗ Failed")
        
        # Step 2: Regenerate story_so_far for ALL chapters (in order)
        print(f"\n  Step 2: Regenerating 'Story So Far' for all chapters...")
        all_chapters_sorted = sorted(chapters, key=lambda x: x['chapter_number'])
        
        for ch in all_chapters_sorted:
            chapter_num = ch['chapter_number']
            chapter_id = ch['id']
            
            print(f"    Chapter {chapter_num}...", end=" ")
            success, result = generate_chapter_summary(token, story_id, chapter_id, regenerate_story_so_far=True)
            
            if success:
                story_so_far = result.get('story_so_far', '')
                if story_so_far:
                    preview = story_so_far[:60] + "..." if len(story_so_far) > 60 else story_so_far
                    print(f"✓ Updated")
                    print(f"      Preview: {preview}")
                else:
                    print(f"✓ Skipped (no previous chapters)")
            else:
                print(f"✗ Failed")
        
        print()
    
    print("=" * 80)
    print("COMPLETE!")
    print("=" * 80)
    print("\nAll chapters have been updated with:")
    print("  1. auto_summary - Summary of each chapter's scenes")
    print("  2. story_so_far - Cascading summary of all previous + current chapters")
    print("\nYou can now:")
    print("  - Open any chapter to see the updated 'Story So Far'")
    print("  - Create new chapters that will automatically get proper summaries")
    print("  - Generate new scenes with auto-summary triggering at the threshold")

if __name__ == "__main__":
    main()
