#!/usr/bin/env python3
"""
Direct HTTP test for text completion endpoint.
Tests the /v1/completions endpoint directly without any framework.
"""

import httpx
import json
import sys

# Configuration
API_URL = "http://localhost:1234"  # Change to your LM Studio URL
MODEL_NAME = "qwen3-coder-30b-a3b-instruct-mlx"  # Change to your model name

def test_text_completion():
    """Test direct HTTP call to /v1/completions endpoint"""
    
    # Determine endpoint URL
    if API_URL.endswith("/v1"):
        endpoint_url = f"{API_URL}/completions"
    else:
        endpoint_url = f"{API_URL}/v1/completions"
    
    # Prepare payload
    payload = {
        "model": MODEL_NAME,
        "prompt": "Once upon a time, in a land far away,",
        "max_tokens": 100,
        "temperature": 0.7,
        "stream": False
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    print("=" * 80)
    print("TEXT COMPLETION DIRECT HTTP TEST")
    print("=" * 80)
    print(f"\nEndpoint: {endpoint_url}")
    print(f"Model: {MODEL_NAME}")
    print(f"Prompt: {payload['prompt']}")
    print("\nSending request...")
    print("-" * 80)
    
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                endpoint_url,
                json=payload,
                headers=headers
            )
            
            print(f"Status Code: {response.status_code}")
            print(f"Response Headers: {dict(response.headers)}")
            print("-" * 80)
            
            if response.status_code == 200:
                data = response.json()
                print("\n✅ SUCCESS!")
                print("\nFull Response:")
                print(json.dumps(data, indent=2))
                
                if "choices" in data and len(data["choices"]) > 0:
                    generated_text = data["choices"][0].get("text", "")
                    print("\n" + "=" * 80)
                    print("GENERATED TEXT:")
                    print("=" * 80)
                    print(generated_text)
                    print("=" * 80)
                    
                    # Check if text looks reasonable
                    if len(generated_text) > 10:
                        print("\n✅ Text generation appears successful!")
                        return True
                    else:
                        print("\n❌ Generated text is too short!")
                        return False
                else:
                    print("\n❌ No choices in response!")
                    return False
            else:
                print(f"\n❌ FAILED with status {response.status_code}")
                print("Response body:")
                print(response.text)
                return False
                
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_text_completion()
    sys.exit(0 if success else 1)

