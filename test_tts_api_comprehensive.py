"""
Comprehensive TTS API Test Suite

Tests all TTS endpoints with proper error handling and detailed logging.
"""

import asyncio
import httpx
import sys
import json
from pathlib import Path


class TTSAPITester:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.token = None
        self.headers = {}
        self.results = {
            "passed": [],
            "failed": [],
            "skipped": []
        }
    
    def log_success(self, test_name, details=""):
        print(f"✅ {test_name}")
        if details:
            print(f"   {details}")
        self.results["passed"].append(test_name)
    
    def log_failure(self, test_name, error):
        print(f"❌ {test_name}")
        print(f"   Error: {error}")
        self.results["failed"].append((test_name, str(error)))
    
    def log_skip(self, test_name, reason):
        print(f"⚠️  {test_name} - SKIPPED")
        print(f"   Reason: {reason}")
        self.results["skipped"].append((test_name, reason))
    
    def log_info(self, message):
        print(f"ℹ️  {message}")
    
    async def test_connection(self):
        """Test if backend is accessible"""
        print("\n" + "="*70)
        print("TEST 0: Backend Connection")
        print("="*70)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    self.log_success("Backend connection", 
                        f"Status: {data.get('status')}, Version: {data.get('version')}")
                    return True
                else:
                    self.log_failure("Backend connection", 
                        f"Status code: {response.status_code}")
                    return False
        except Exception as e:
            self.log_failure("Backend connection", f"Cannot connect: {e}")
            return False
    
    async def test_login(self, email="test@test.com", password="test"):
        """Test authentication"""
        print("\n" + "="*70)
        print("TEST 1: Authentication")
        print("="*70)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/auth/login",
                    json={"email": email, "password": password},
                    timeout=10.0
                )
                
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                
                if response.status_code == 200:
                    data = response.json()
                    self.token = data.get("access_token")
                    self.headers = {"Authorization": f"Bearer {self.token}"}
                    self.log_success("Authentication", 
                        f"Token received: {self.token[:20]}...")
                    return True
                else:
                    self.log_failure("Authentication", 
                        f"Status {response.status_code}: {response.text}")
                    return False
        except Exception as e:
            self.log_failure("Authentication", str(e))
            return False
    
    async def test_list_providers(self):
        """Test GET /api/tts/providers"""
        print("\n" + "="*70)
        print("TEST 2: List TTS Providers")
        print("="*70)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/tts/providers",
                    timeout=10.0
                )
                
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text[:500]}")
                
                if response.status_code == 200:
                    providers = response.json()
                    self.log_success("List providers", 
                        f"Found {len(providers)} provider(s)")
                    
                    if len(providers) > 0:
                        for p in providers:
                            print(f"      - {p.get('name', 'unknown')} "
                                  f"(type: {p.get('type', 'unknown')}, "
                                  f"streaming: {p.get('supports_streaming', False)})")
                    else:
                        self.log_info("No providers registered - this might be an issue!")
                    return True
                else:
                    self.log_failure("List providers", 
                        f"Status {response.status_code}: {response.text}")
                    return False
        except Exception as e:
            self.log_failure("List providers", str(e))
            return False
    
    async def test_get_settings(self):
        """Test GET /api/tts/settings"""
        print("\n" + "="*70)
        print("TEST 3: Get TTS Settings")
        print("="*70)
        
        if not self.token:
            self.log_skip("Get settings", "No authentication token")
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/tts/settings",
                    headers=self.headers,
                    timeout=10.0
                )
                
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text[:500]}")
                
                if response.status_code == 200:
                    settings = response.json()
                    self.log_success("Get settings", 
                        f"Settings retrieved for user {settings.get('user_id')}")
                    print(f"      Provider: {settings.get('provider_type', 'not set')}")
                    print(f"      API URL: {settings.get('api_url', 'not set')}")
                    print(f"      Voice: {settings.get('voice_id', 'not set')}")
                    return settings
                else:
                    self.log_failure("Get settings", 
                        f"Status {response.status_code}: {response.text}")
                    return None
        except Exception as e:
            self.log_failure("Get settings", str(e))
            return None
    
    async def test_update_settings(self):
        """Test PUT /api/tts/settings"""
        print("\n" + "="*70)
        print("TEST 4: Update TTS Settings")
        print("="*70)
        
        if not self.token:
            self.log_skip("Update settings", "No authentication token")
            return False
        
        settings_data = {
            "provider_type": "openai-compatible",
            "api_url": "http://172.16.23.80:4321/v1",
            "api_key": "",
            "voice_id": "female_06",
            "speed": 1.0,
            "timeout": 30,
            "extra_params": {"format": "wav"}
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.base_url}/api/tts/settings",
                    headers=self.headers,
                    json=settings_data,
                    timeout=10.0
                )
                
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text[:500]}")
                
                if response.status_code == 200:
                    settings = response.json()
                    self.log_success("Update settings", 
                        f"Settings updated successfully")
                    print(f"      Provider: {settings.get('provider_type')}")
                    print(f"      Voice: {settings.get('voice_id')}")
                    print(f"      Speed: {settings.get('speed')}")
                    return True
                else:
                    self.log_failure("Update settings", 
                        f"Status {response.status_code}: {response.text}")
                    return False
        except Exception as e:
            self.log_failure("Update settings", str(e))
            return False
    
    async def test_list_voices(self):
        """Test GET /api/tts/voices"""
        print("\n" + "="*70)
        print("TEST 5: List Available Voices")
        print("="*70)
        
        if not self.token:
            self.log_skip("List voices", "No authentication token")
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/tts/voices",
                    headers=self.headers,
                    timeout=30.0  # Longer timeout for voice discovery
                )
                
                print(f"   Status: {response.status_code}")
                
                if response.status_code == 200:
                    voices = response.json()
                    self.log_success("List voices", 
                        f"Found {len(voices)} voice(s)")
                    
                    # Show first 10 voices
                    print(f"      Sample voices (first 10):")
                    for voice in voices[:10]:
                        print(f"        - {voice.get('name')} "
                              f"({voice.get('language', 'unknown')})")
                    
                    if len(voices) > 10:
                        print(f"        ... and {len(voices) - 10} more")
                    
                    return True
                else:
                    self.log_failure("List voices", 
                        f"Status {response.status_code}: {response.text[:300]}")
                    return False
        except Exception as e:
            self.log_failure("List voices", str(e))
            return False
    
    async def test_tts_generation(self):
        """Test POST /api/tts/test"""
        print("\n" + "="*70)
        print("TEST 6: TTS Audio Generation")
        print("="*70)
        
        if not self.token:
            self.log_skip("TTS generation", "No authentication token")
            return False
        
        test_data = {
            "text": "Hello! This is a comprehensive test of the TTS system.",
            "voice_id": "female_06",
            "speed": 1.0
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/tts/test",
                    headers=self.headers,
                    json=test_data,
                    timeout=30.0  # Longer timeout for audio generation
                )
                
                print(f"   Status: {response.status_code}")
                
                if response.status_code == 200:
                    audio_size = len(response.content)
                    duration = response.headers.get("X-Audio-Duration", "unknown")
                    format_type = response.headers.get("X-Audio-Format", "unknown")
                    
                    self.log_success("TTS generation", 
                        f"Audio generated: {audio_size} bytes")
                    print(f"      Duration: {duration}s")
                    print(f"      Format: {format_type}")
                    
                    # Save audio file
                    output_file = "/tmp/tts_api_test.wav"
                    Path(output_file).write_bytes(response.content)
                    print(f"      Saved to: {output_file}")
                    
                    return True
                else:
                    print(f"   Response text: {response.text[:500]}")
                    self.log_failure("TTS generation", 
                        f"Status {response.status_code}: {response.text[:300]}")
                    return False
        except Exception as e:
            self.log_failure("TTS generation", str(e))
            import traceback
            traceback.print_exc()
            return False
    
    async def test_scene_audio_endpoints(self):
        """Test scene audio generation/retrieval/deletion"""
        print("\n" + "="*70)
        print("TEST 7: Scene Audio Endpoints")
        print("="*70)
        
        if not self.token:
            self.log_skip("Scene audio endpoints", "No authentication token")
            return False
        
        # We need a valid scene ID - let's check if user has any stories/scenes
        try:
            async with httpx.AsyncClient() as client:
                # Get user's stories
                response = await client.get(
                    f"{self.base_url}/api/stories",
                    headers=self.headers,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    stories = response.json()
                    if len(stories) > 0:
                        story_id = stories[0]["id"]
                        self.log_info(f"Using story ID: {story_id}")
                        
                        # Get scenes for this story
                        # TODO: Implement if scenes endpoint exists
                        self.log_skip("Scene audio endpoints", 
                            "Scene endpoint testing requires existing story with scenes")
                    else:
                        self.log_skip("Scene audio endpoints", 
                            "No stories found for user")
                else:
                    self.log_skip("Scene audio endpoints", 
                        "Could not retrieve stories")
        except Exception as e:
            self.log_skip("Scene audio endpoints", str(e))
        
        return False
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        
        total = len(self.results["passed"]) + len(self.results["failed"]) + len(self.results["skipped"])
        
        print(f"\n✅ Passed: {len(self.results['passed'])}/{total}")
        for test in self.results["passed"]:
            print(f"   - {test}")
        
        if self.results["failed"]:
            print(f"\n❌ Failed: {len(self.results['failed'])}/{total}")
            for test, error in self.results["failed"]:
                print(f"   - {test}")
                print(f"     Error: {error[:100]}")
        
        if self.results["skipped"]:
            print(f"\n⚠️  Skipped: {len(self.results['skipped'])}/{total}")
            for test, reason in self.results["skipped"]:
                print(f"   - {test}: {reason}")
        
        print("\n" + "="*70)
        if len(self.results["failed"]) == 0:
            print("🎉 ALL TESTS PASSED!")
        else:
            print("⚠️  SOME TESTS FAILED - Please review errors above")
        print("="*70 + "\n")
    
    async def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "🎙️ " * 20)
        print("COMPREHENSIVE TTS API TEST SUITE")
        print("Testing all endpoints with proper logging")
        print("🎙️ " * 20)
        
        # Test connection
        if not await self.test_connection():
            print("\n❌ Backend is not accessible. Please start the backend server.")
            print("   Command: cd backend && uvicorn app.main:app --reload")
            return
        
        # Test authentication
        if not await self.test_login():
            print("\n❌ Authentication failed. Skipping authenticated tests.")
            print("   Make sure test user exists: test@test.com / test")
        
        # Test providers (no auth required)
        await self.test_list_providers()
        
        # Test authenticated endpoints
        await self.test_get_settings()
        await self.test_update_settings()
        await self.test_list_voices()
        await self.test_tts_generation()
        await self.test_scene_audio_endpoints()
        
        # Print summary
        self.print_summary()


async def main():
    tester = TTSAPITester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
