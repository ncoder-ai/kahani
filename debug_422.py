#!/usr/bin/env python3

import asyncio
import httpx
import json

async def test_tabby_api():
    """Test TabbyAPI directly to see what's causing the 422 error"""
    
    # Headers with API key
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer your_actual_token_here"  # Replace with actual token
    }
    
    # Basic payload like our working streaming version
    payload = {
        "model": "behemoth-redux",
        "messages": [{"role": "user", "content": "Write a short paragraph about adventure."}],
        "max_tokens": 1024,
        "temperature": 0.8
    }
    
    print("Testing non-streaming request to TabbyAPI...")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.nrdd.us/v1/chat/completions",
                headers=headers,
                json=payload
            )
            
            print(f"Response status: {response.status_code}")
            print(f"Response headers: {dict(response.headers)}")
            
            if response.status_code == 422:
                print("422 Error response:")
                print(response.text)
            else:
                print("Success response:")
                result = response.json()
                print(json.dumps(result, indent=2))
                
        except Exception as e:
            print(f"Error: {e}")
            if hasattr(e, 'response'):
                print(f"Response: {e.response.text}")

if __name__ == "__main__":
    asyncio.run(test_tabby_api())