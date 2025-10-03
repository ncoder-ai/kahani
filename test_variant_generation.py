#!/usr/bin/env python3

import requests
import json

# Test variant generation functionality
BASE_URL = "http://localhost:8000"

def test_variant_generation():
    """Test the variant generation endpoint"""
    
    # First, get authentication token
    login_data = {
        "email": "test@test.com", 
        "password": "testpass"
    }
    
    print("🔐 Logging in...")
    auth_response = requests.post(f"{BASE_URL}/api/auth/login", json=login_data)
    if auth_response.status_code != 200:
        print(f"❌ Login failed: {auth_response.status_code} - {auth_response.text}")
        return
    
    token = auth_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Login successful!")
    
    # Get a story to work with
    print("\n📚 Getting stories...")
    stories_response = requests.get(f"{BASE_URL}/api/stories", headers=headers)
    if stories_response.status_code != 200:
        print(f"❌ Failed to get stories: {stories_response.status_code}")
        return
    
    stories = stories_response.json()
    if not stories:
        print("❌ No stories available for testing")
        return
    
    story_id = stories[0]["id"]
    print(f"✅ Using story ID: {story_id}")
    
    # Get scenes for the story
    print(f"\n🎬 Getting scenes for story {story_id}...")
    scenes_response = requests.get(f"{BASE_URL}/api/stories/{story_id}/scenes", headers=headers)
    if scenes_response.status_code != 200:
        print(f"❌ Failed to get scenes: {scenes_response.status_code}")
        return
    
    scenes = scenes_response.json()
    if not scenes:
        print("❌ No scenes available for testing")
        return
    
    scene_id = scenes[0]["id"]
    print(f"✅ Using scene ID: {scene_id}")
    
    # Test variant generation (non-streaming)
    print(f"\n🔄 Testing variant generation for scene {scene_id}...")
    variant_data = {
        "custom_prompt": "Create a dramatic and suspenseful variant of this scene"
    }
    
    variant_response = requests.post(
        f"{BASE_URL}/api/stories/{story_id}/scenes/{scene_id}/variants",
        json=variant_data,
        headers=headers
    )
    
    print(f"Response status: {variant_response.status_code}")
    if variant_response.status_code == 200:
        result = variant_response.json()
        print("✅ Variant generation successful!")
        print(f"📝 Variant ID: {result.get('variant', {}).get('id', 'N/A')}")
        print(f"📄 Content preview: {result.get('variant', {}).get('content', '')[:100]}...")
    else:
        print(f"❌ Variant generation failed: {variant_response.text}")
    
    # Test streaming variant generation
    print(f"\n🔄 Testing streaming variant generation for scene {scene_id}...")
    streaming_response = requests.post(
        f"{BASE_URL}/api/stories/{story_id}/scenes/{scene_id}/variants/stream",
        json=variant_data,
        headers=headers,
        stream=True
    )
    
    print(f"Streaming response status: {streaming_response.status_code}")
    if streaming_response.status_code == 200:
        print("✅ Streaming variant generation started!")
        # Process just the first few chunks to verify it's working
        chunk_count = 0
        for line in streaming_response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    try:
                        data = json.loads(line_str[6:])  # Remove 'data: ' prefix
                        if data.get('type') == 'error':
                            print(f"❌ Streaming error: {data.get('message')}")
                            break
                        elif data.get('type') == 'content':
                            chunk_count += 1
                            if chunk_count <= 3:  # Show first few chunks
                                print(f"📝 Chunk {chunk_count}: {data.get('chunk', '')[:50]}...")
                        elif data.get('type') == 'complete':
                            print("✅ Streaming completed successfully!")
                            break
                    except json.JSONDecodeError:
                        continue
                
                # Stop after processing a few chunks to avoid too much output
                if chunk_count >= 5:
                    print("✅ Streaming appears to be working (stopped after 5 chunks)")
                    break
    else:
        print(f"❌ Streaming variant generation failed: {streaming_response.text}")

if __name__ == "__main__":
    test_variant_generation()