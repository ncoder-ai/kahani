#!/usr/bin/env python3

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, '/Users/nishant/apps/kahani/backend')
os.chdir('/Users/nishant/apps/kahani/backend')

from app.services.llm_functions import generate_scene

async def test_generate_scene():
    """Test the fixed generate_scene function"""
    
    user_settings = {
        "api_url": "https://api.nrdd.us/v1",
        "api_key": "test_key_placeholder",
        "model_name": "behemoth-redux",
        "temperature": 0.8,
        "max_tokens": 1024
    }
    
    test_prompt = "Continue this adventure: You stand at the entrance to a mysterious cave..."
    
    print("Testing generate_scene with string prompt...")
    print(f"Prompt: {test_prompt[:100]}...")
    print(f"User settings: {user_settings}")
    
    try:
        result = await generate_scene(
            prompt=test_prompt,
            user_id=1,
            user_settings=user_settings,
            max_tokens=100
        )
        print(f"Success: {result[:200]}...")
    except Exception as e:
        print(f"Error: {e}")
        print(f"Error type: {type(e).__name__}")

if __name__ == "__main__":
    asyncio.run(test_generate_scene())