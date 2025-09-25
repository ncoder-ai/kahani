#!/usr/bin/env python3

import asyncio
import httpx
import json
import sys
import os

# Add the backend to the Python path
backend_path = '/Users/nishant/apps/kahani/backend'
sys.path.insert(0, backend_path)

# Change to the backend directory to help with imports
os.chdir(backend_path)

from app.services.improved_llm_service import ImprovedLLMService

async def test_payload_comparison():
    """Compare working streaming vs failing non-streaming payloads"""
    
    # Use known working settings from user 1
    settings_dict = {
        "api_url": "https://api.nrdd.us/v1",
        "api_key": "your_api_key_here",  # We'll get this from the working requests
        "model_name": "behemoth-redux",
        "temperature": 0.8,
        "max_tokens": 1024
    }
    
    print(f"Test settings: {settings_dict}")
    
    test_prompt = "Write a short paragraph about adventure."
    messages = [{"role": "user", "content": test_prompt}]
    
    # Simple payload comparison - what we know works vs fails
    streaming_payload = {
        "model": "behemoth-redux",
        "messages": messages,
        "max_tokens": 512,
        "temperature": 0.8,
        "stream": True
    }
    
    non_streaming_payload = {
        "model": "behemoth-redux",
        "messages": messages, 
        "max_tokens": 512,
        "temperature": 0.8,
        "stream": False
    }
    
    print("\n=== STREAMING PAYLOAD (WORKS) ===")
    print(json.dumps(streaming_payload, indent=2))
    
    print("\n=== NON-STREAMING PAYLOAD (FAILS WITH 422) ===")
    print(json.dumps(non_streaming_payload, indent=2))
    
    print("\n=== PAYLOAD DIFFERENCES ===")
    for key in set(streaming_payload.keys()) | set(non_streaming_payload.keys()):
        s_val = streaming_payload.get(key, "NOT_PRESENT")
        ns_val = non_streaming_payload.get(key, "NOT_PRESENT")
        if s_val != ns_val:
            print(f"{key}: streaming={s_val}, non-streaming={ns_val}")
    
    # The only difference should be stream: True vs False
    print("\nConclusion: The only difference is 'stream' parameter")
    print("This suggests TabbyAPI may not properly support non-streaming mode")
    print("or there's a configuration issue with non-streaming requests")
    
    # Test minimal payloads
    print("\n=== TESTING MINIMAL PAYLOADS ===")
    
    minimal_streaming = {
        "model": "behemoth-redux",
        "messages": messages,
        "stream": True
    }
    
    minimal_non_streaming = {
        "model": "behemoth-redux", 
        "messages": messages,
        "stream": False
    }
    
    print("Minimal streaming:")
    print(json.dumps(minimal_streaming, indent=2))
    print("\nMinimal non-streaming:")
    print(json.dumps(minimal_non_streaming, indent=2))

if __name__ == "__main__":
    asyncio.run(test_payload_comparison())