#!/usr/bin/env python3
"""Test backend TTS endpoints"""

import requests
import json

BASE_URL = "http://172.16.23.125:8000"

# First, login to get token
print("1. Logging in...")
login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
    "email": "test@test.com",
    "password": "test"
})
if login_response.status_code != 200:
    print(f"❌ Login failed: {login_response.text}")
    exit(1)

token = login_response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print(f"✅ Logged in, token: {token[:20]}...")

# Test providers endpoint
print("\n2. Testing GET /api/tts/providers...")
providers_response = requests.get(f"{BASE_URL}/api/tts/providers", headers=headers)
if providers_response.status_code == 200:
    providers = providers_response.json()
    print(f"✅ Found {len(providers)} providers:")
    for p in providers:
        print(f"   - {p['id']}: {p['name']}")
else:
    print(f"❌ Failed: {providers_response.text}")

# Test get settings
print("\n3. Testing GET /api/tts/settings...")
settings_response = requests.get(f"{BASE_URL}/api/tts/settings", headers=headers)
if settings_response.status_code == 200:
    settings = settings_response.json()
    print(f"✅ Current settings:")
    print(f"   Provider: {settings.get('provider_type', 'None')}")
    print(f"   API URL: {settings.get('api_url', 'None')}")
    print(f"   Voice: {settings.get('voice_id', 'None')}")
else:
    print(f"❌ Failed: {settings_response.text}")

# Test update settings
print("\n4. Testing PUT /api/tts/settings...")
update_response = requests.put(f"{BASE_URL}/api/tts/settings", 
    headers=headers,
    json={
        "provider_type": "chatterbox",
        "api_url": "http://172.16.23.80:8880/v1",
        "voice_id": "male_05",
        "speed": 1.0,
        "timeout": 30
    }
)
if update_response.status_code == 200:
    print(f"✅ Settings updated successfully")
else:
    print(f"❌ Failed: {update_response.text}")

# Test voices endpoint
print("\n5. Testing GET /api/tts/voices...")
voices_response = requests.get(f"{BASE_URL}/api/tts/voices", headers=headers)
if voices_response.status_code == 200:
    voices = voices_response.json()
    print(f"✅ Found {len(voices)} voices")
    if len(voices) > 0:
        print(f"   First 5 voices: {[v['id'] for v in voices[:5]]}")
else:
    print(f"❌ Failed: {voices_response.text}")

# Test TTS test endpoint
print("\n6. Testing POST /api/tts/test...")
test_response = requests.post(f"{BASE_URL}/api/tts/test",
    headers=headers,
    json={
        "text": "Hello, this is a test of the text to speech system.",
        "voice_id": "male_05"
    }
)
if test_response.status_code == 200:
    result = test_response.json()
    print(f"✅ TTS test successful:")
    print(f"   Duration: {result.get('duration', 0):.2f}s")
    print(f"   Format: {result.get('format', 'unknown')}")
else:
    print(f"❌ Failed: {test_response.text}")

print("\n" + "="*50)
print("Backend TTS test complete!")
