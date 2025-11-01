#!/usr/bin/env python3
"""
Test text completion using Kahani's actual code.
This simulates what happens when you generate a scene.
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

async def test_kahani_text_completion():
    """Test using Kahani's actual LLM service"""
    
    from app.services.llm.service import UnifiedLLMService
    from app.models.user_settings import UserSettings
    
    print("=" * 80)
    print("KAHANI TEXT COMPLETION TEST")
    print("=" * 80)
    
    # Create LLM service
    llm_service = UnifiedLLMService()
    
    # Simulate user settings with text completion enabled
    user_settings = {
        'llm_settings': {
            'api_url': 'http://localhost:1234',
            'api_key': '',
            'api_type': 'lm_studio',
            'model_name': 'qwen3-coder-30b-a3b-instruct-mlx',
            'temperature': 0.7,
            'top_p': 0.9,
            'top_k': 40,
            'repetition_penalty': 1.1,
            'max_tokens': 2048,
            'completion_mode': 'text',  # TEXT COMPLETION MODE
            'text_completion_template': None,  # Will use preset
            'text_completion_preset': 'qwen'  # Qwen preset
        }
    }
    
    system_prompt = "You are a creative storyteller. Write engaging narrative text in a fantasy setting."
    user_prompt = "Write a vivid description of a mysterious ancient library filled with magical books."
    
    print(f"\nAPI Type: {user_settings['llm_settings']['api_type']}")
    print(f"Model: {user_settings['llm_settings']['model_name']}")
    print(f"Completion Mode: {user_settings['llm_settings']['completion_mode']}")
    print(f"Template Preset: {user_settings['llm_settings']['text_completion_preset']}")
    print(f"\nSystem Prompt: {system_prompt}")
    print(f"User Prompt: {user_prompt}")
    print("\n" + "-" * 80)
    print("Generating...")
    print("-" * 80)
    
    try:
        # Call the generate method (non-streaming)
        result = await llm_service.generate(
            prompt=user_prompt,
            user_id=1,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=300,
            temperature=0.7,
            stream=False
        )
        
        print("\n✅ SUCCESS!")
        print("\n" + "=" * 80)
        print("GENERATED TEXT:")
        print("=" * 80)
        print(result)
        print("=" * 80)
        
        # Analyze the output
        print("\n" + "=" * 80)
        print("ANALYSIS:")
        print("=" * 80)
        print(f"Length: {len(result)} characters")
        print(f"Word count: {len(result.split())} words")
        print(f"Contains template tokens: {'<|im_' in result or '<|end' in result}")
        print(f"Looks like narrative: {len(result.split()) > 20}")
        
        # Check for common issues
        issues = []
        if len(result) < 50:
            issues.append("Text is too short")
        if '<|im_' in result or '<|end' in result:
            issues.append("Contains template tokens (not cleaned)")
        if result.count('\n') > 10:
            issues.append("Too many line breaks")
        if not any(c.isalpha() for c in result):
            issues.append("No alphabetic characters")
        
        if issues:
            print("\n⚠️  POTENTIAL ISSUES:")
            for issue in issues:
                print(f"  - {issue}")
            return False
        else:
            print("\n✅ Text generation looks good!")
            return True
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_kahani_streaming():
    """Test streaming text completion"""
    
    from app.services.llm.service import UnifiedLLMService
    
    print("\n\n" + "=" * 80)
    print("KAHANI STREAMING TEXT COMPLETION TEST")
    print("=" * 80)
    
    llm_service = UnifiedLLMService()
    
    user_settings = {
        'llm_settings': {
            'api_url': 'http://localhost:1234',
            'api_key': '',
            'api_type': 'lm_studio',
            'model_name': 'qwen3-coder-30b-a3b-instruct-mlx',
            'temperature': 0.7,
            'top_p': 0.9,
            'top_k': 40,
            'repetition_penalty': 1.1,
            'max_tokens': 2048,
            'completion_mode': 'text',
            'text_completion_template': None,
            'text_completion_preset': 'qwen'
        }
    }
    
    system_prompt = "You are a creative storyteller."
    user_prompt = "Write a short story opening about a dragon."
    
    print(f"\nStreaming generation...")
    print("-" * 80)
    
    try:
        chunks = []
        async for chunk in llm_service._generate_stream(
            prompt=user_prompt,
            user_id=1,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=200,
            temperature=0.7
        ):
            print(chunk, end='', flush=True)
            chunks.append(chunk)
        
        full_text = ''.join(chunks)
        print("\n" + "-" * 80)
        print(f"\n✅ Streaming completed!")
        print(f"Total length: {len(full_text)} characters")
        
        return len(full_text) > 20
        
    except Exception as e:
        print(f"\n❌ STREAMING ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("RUNNING KAHANI TEXT COMPLETION TESTS")
    print("=" * 80)
    
    # Test 1: Non-streaming
    test1 = await test_kahani_text_completion()
    
    # Test 2: Streaming
    test2 = await test_kahani_streaming()
    
    print("\n\n" + "=" * 80)
    print("TEST RESULTS:")
    print("=" * 80)
    print(f"Non-streaming: {'✅ PASS' if test1 else '❌ FAIL'}")
    print(f"Streaming: {'✅ PASS' if test2 else '❌ FAIL'}")
    print("=" * 80)
    
    return test1 and test2

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

