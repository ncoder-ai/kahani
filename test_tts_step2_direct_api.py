#!/usr/bin/env python3
"""
Step 2: Test TTS API Directly
Test ChatterboxTTS API directly with a simple request
"""
import asyncio
import httpx
import sys
import time

async def test_tts_api():
    print("\n" + "="*60)
    print("STEP 2: Test TTS API Directly")
    print("="*60 + "\n")
    
    api_url = "http://172.16.23.80:4321/v1"
    voice_id = "female_06"
    test_text = "This is a test of the text to speech system. The quick brown fox jumps over the lazy dog."
    
    print(f"API URL: {api_url}")
    print(f"Voice: {voice_id}")
    print(f"Test text ({len(test_text)} chars): {test_text}")
    print(f"\n⏱️  Testing with 60 second timeout...")
    
    endpoint = f"{api_url}/audio/speech"
    
    payload = {
        "model": "tts-1",
        "input": test_text,
        "voice": voice_id,
        "response_format": "mp3"
    }
    
    try:
        start_time = time.time()
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
        
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            audio_data = response.content
            duration_estimate = len(test_text) / 20  # rough estimate
            
            print(f"\n✅ SUCCESS!")
            print(f"   Status: {response.status_code}")
            print(f"   Response time: {elapsed:.2f} seconds")
            print(f"   Audio size: {len(audio_data):,} bytes ({len(audio_data)/1024:.2f} KB)")
            print(f"   Estimated duration: ~{duration_estimate:.1f} seconds")
            
            # Save to temp file
            output_file = "/tmp/test_tts_step2.mp3"
            with open(output_file, "wb") as f:
                f.write(audio_data)
            print(f"   Saved to: {output_file}")
            
            return True
        else:
            print(f"\n❌ FAILED!")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return False
            
    except httpx.TimeoutException as e:
        print(f"\n❌ TIMEOUT after 60 seconds!")
        print(f"   Error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_tts_api())
    sys.exit(0 if success else 1)
