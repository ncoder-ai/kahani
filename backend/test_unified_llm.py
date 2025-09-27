#!/usr/bin/env python3
"""
Test script for the new unified LLM service implementation.

This script tests all the major functions of the new LLM service to ensure
they work correctly before integrating with the API endpoints.
"""

import asyncio
import sys
import os
import logging
from typing import Dict, Any

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app.services.llm import unified_llm_service, prompt_manager
from app.services.llm_compatibility import (
    generate_scenario,
    generate_titles,
    generate_complete_plot,
    generate_single_plot_point,
    generate_scene,
    generate_scene_streaming,
    generate_choices,
    generate_scene_continuation,
    generate_scene_continuation_streaming,
    invalidate_user_llm_cache
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test user settings (you'll need to update these with your actual LLM configuration)
TEST_USER_SETTINGS = {
    "llm_settings": {
        "api_url": "https://api.nrdd.us/v1",  # TabbyAPI with /v1 (required)
        "api_key": "7737f04fc27582d52c284c6e1dcdcf43",
        "api_type": "openai_compatible",
        "model_name": "behemoth-redux",  # TabbyAPI model
        "temperature": 0.7,
        "top_p": 1.0,
        "top_k": 50,
        "repetition_penalty": 1.1,
        "max_tokens": 2048
    }
}

# Test settings for incorrect URL (without /v1)
TEST_USER_SETTINGS_INCORRECT = {
    "llm_settings": {
        "api_url": "https://api.nrdd.us",  # TabbyAPI without /v1 (should fail with helpful error)
        "api_key": "7737f04fc27582d52c284c6e1dcdcf43",
        "api_type": "openai_compatible",
        "model_name": "behemoth-redux",  # TabbyAPI model
        "temperature": 0.7,
        "top_p": 1.0,
        "top_k": 50,
        "repetition_penalty": 1.1,
        "max_tokens": 2048
    }
}

TEST_USER_ID = 1

# Test context data
TEST_CONTEXT = {
    "genre": "Fantasy",
    "tone": "Adventure",
    "characters": [
        {
            "name": "Aria",
            "role": "Protagonist",
            "description": "A young mage with untapped potential"
        },
        {
            "name": "Thorne",
            "role": "Mentor",
            "description": "An experienced warrior with a mysterious past"
        }
    ],
    "world_setting": "A magical realm where ancient powers are awakening",
    "scenario": "Aria discovers an ancient artifact that could change the fate of the realm",
    "story_elements": {
        "opening": "A mysterious light in the forest",
        "setting": "The Enchanted Woods",
        "conflict": "Dark forces seek the same artifact"
    }
}

async def test_prompt_manager():
    """Test the prompt manager functionality"""
    logger.info("🧪 Testing Prompt Manager...")
    
    try:
        # Test loading prompts
        system_prompt = prompt_manager.get_system_prompt("story_generation", "scenario")
        user_prompt = prompt_manager.get_user_prompt("story_generation", "scenario")
        
        assert system_prompt, "System prompt should not be empty"
        assert user_prompt, "User prompt should not be empty"
        
        logger.info("✅ Prompt Manager: Successfully loaded prompts")
        
        # Test prompt formatting
        formatted_prompt = prompt_manager.format_prompt(
            user_prompt,
            context="Test context",
            elements="Test elements"
        )
        
        assert "Test context" in formatted_prompt, "Prompt formatting should work"
        logger.info("✅ Prompt Manager: Successfully formatted prompts")
        
        # Test settings
        max_tokens = prompt_manager.get_max_tokens("scenario")
        temperature = prompt_manager.get_temperature("default")
        
        assert max_tokens > 0, "Max tokens should be positive"
        assert 0 <= temperature <= 2, "Temperature should be in valid range"
        
        logger.info("✅ Prompt Manager: Successfully retrieved settings")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Prompt Manager test failed: {e}")
        return False

async def test_llm_client():
    """Test the LLM client configuration"""
    logger.info("🧪 Testing LLM Client...")
    
    try:
        from app.services.llm.client import LLMClient
        
        # Test client creation
        client = LLMClient(TEST_USER_SETTINGS)
        
        assert client.api_url, "API URL should be set"
        assert client.model_name, "Model name should be set"
        assert client.temperature >= 0, "Temperature should be valid"
        
        logger.info(f"✅ LLM Client: Successfully created client for {client.api_type}")
        logger.info(f"   Model: {client.model_name}")
        logger.info(f"   API URL: {client.api_url}")
        
        # Test generation parameters
        gen_params = client.get_generation_params()
        stream_params = client.get_streaming_params()
        
        assert "model" in gen_params, "Generation params should include model"
        assert "stream" in stream_params, "Streaming params should include stream flag"
        
        logger.info("✅ LLM Client: Successfully generated parameters")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ LLM Client test failed: {e}")
        return False

async def test_unified_service_basic():
    """Test basic unified service functionality"""
    logger.info("🧪 Testing Unified Service (Basic)...")
    
    try:
        # Test client caching
        client = unified_llm_service.get_user_client(TEST_USER_ID, TEST_USER_SETTINGS)
        assert client, "Should return a client"
        
        # Test cache invalidation
        unified_llm_service.invalidate_user_client(TEST_USER_ID)
        logger.info("✅ Unified Service: Successfully tested client caching")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Unified Service basic test failed: {e}")
        return False

async def test_scenario_generation():
    """Test scenario generation"""
    logger.info("🧪 Testing Scenario Generation...")
    
    try:
        scenario = await generate_scenario(TEST_CONTEXT, TEST_USER_ID, TEST_USER_SETTINGS)
        
        assert scenario, "Scenario should not be empty"
        assert len(scenario) > 50, "Scenario should be substantial"
        
        logger.info(f"✅ Scenario Generation: Successfully generated scenario")
        logger.info(f"   Length: {len(scenario)} characters")
        logger.info(f"   Preview: {scenario[:100]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Scenario generation test failed: {e}")
        return False

async def test_title_generation():
    """Test title generation"""
    logger.info("🧪 Testing Title Generation...")
    
    try:
        titles = await generate_titles(TEST_CONTEXT, TEST_USER_ID, TEST_USER_SETTINGS)
        
        assert titles, "Titles should not be empty"
        assert len(titles) == 5, "Should generate exactly 5 titles"
        assert all(isinstance(title, str) for title in titles), "All titles should be strings"
        assert all(len(title) > 0 for title in titles), "All titles should be non-empty"
        
        logger.info(f"✅ Title Generation: Successfully generated {len(titles)} titles")
        for i, title in enumerate(titles, 1):
            logger.info(f"   {i}. {title}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Title generation test failed: {e}")
        return False

async def test_plot_generation():
    """Test plot generation"""
    logger.info("🧪 Testing Plot Generation...")
    
    try:
        # Test complete plot
        plot_points = await generate_complete_plot(TEST_CONTEXT, TEST_USER_ID, TEST_USER_SETTINGS)
        
        assert plot_points, "Plot points should not be empty"
        assert len(plot_points) == 5, "Should generate exactly 5 plot points"
        assert all(isinstance(point, str) for point in plot_points), "All plot points should be strings"
        
        logger.info(f"✅ Complete Plot Generation: Successfully generated {len(plot_points)} plot points")
        for i, point in enumerate(plot_points, 1):
            logger.info(f"   {i}. {point[:100]}...")
        
        # Test single plot point
        single_point = await generate_single_plot_point(TEST_CONTEXT, TEST_USER_ID, TEST_USER_SETTINGS)
        
        assert single_point, "Single plot point should not be empty"
        assert isinstance(single_point, str), "Single plot point should be a string"
        
        logger.info(f"✅ Single Plot Point Generation: Successfully generated plot point")
        logger.info(f"   Preview: {single_point[:100]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Plot generation test failed: {e}")
        return False

async def test_scene_generation():
    """Test scene generation"""
    logger.info("🧪 Testing Scene Generation...")
    
    try:
        # Test non-streaming scene generation
        scene_context = {
            **TEST_CONTEXT,
            "previous_scenes": "Aria was walking through the forest when she noticed a strange glow.",
            "current_situation": "She approaches the mysterious light source."
        }
        
        scene = await generate_scene("Generate a scene where Aria discovers the artifact", TEST_USER_ID, TEST_USER_SETTINGS)
        
        assert scene, "Scene should not be empty"
        assert len(scene) > 100, "Scene should be substantial"
        
        logger.info(f"✅ Scene Generation: Successfully generated scene")
        logger.info(f"   Length: {len(scene)} characters")
        logger.info(f"   Preview: {scene[:150]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Scene generation test failed: {e}")
        return False

async def test_scene_streaming():
    """Test streaming scene generation"""
    logger.info("🧪 Testing Scene Streaming...")
    
    try:
        scene_context = {
            **TEST_CONTEXT,
            "previous_scenes": "Aria was walking through the forest when she noticed a strange glow.",
            "current_situation": "She approaches the mysterious light source."
        }
        
        chunks = []
        async for chunk in generate_scene_streaming("Generate a scene where Aria discovers the artifact", TEST_USER_ID, TEST_USER_SETTINGS):
            chunks.append(chunk)
        
        full_scene = "".join(chunks)
        
        assert chunks, "Should receive streaming chunks"
        assert full_scene, "Full scene should not be empty"
        assert len(full_scene) > 50, "Streamed scene should be substantial"
        
        logger.info(f"✅ Scene Streaming: Successfully streamed scene")
        logger.info(f"   Chunks received: {len(chunks)}")
        logger.info(f"   Total length: {len(full_scene)} characters")
        logger.info(f"   Preview: {full_scene[:150]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Scene streaming test failed: {e}")
        return False

async def test_choices_generation():
    """Test choices generation"""
    logger.info("🧪 Testing Choices Generation...")
    
    try:
        scene_content = "Aria stood before the ancient artifact, its power pulsing with an otherworldly light. She could feel the magic coursing through her veins, calling to her."
        
        choices = await generate_choices(scene_content, TEST_CONTEXT, TEST_USER_ID, TEST_USER_SETTINGS)
        
        assert choices, "Choices should not be empty"
        assert len(choices) <= 4, "Should generate at most 4 choices"
        assert all(isinstance(choice, str) for choice in choices), "All choices should be strings"
        assert all(len(choice) > 10 for choice in choices), "All choices should be substantial"
        
        logger.info(f"✅ Choices Generation: Successfully generated {len(choices)} choices")
        for i, choice in enumerate(choices, 1):
            logger.info(f"   {i}. {choice}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Choices generation test failed: {e}")
        return False

async def test_scene_continuation():
    """Test scene continuation"""
    logger.info("🧪 Testing Scene Continuation...")
    
    try:
        continuation_context = {
            **TEST_CONTEXT,
            "previous_content": "Aria reached out toward the artifact, her hand trembling with anticipation.",
            "choice_made": "Touch the artifact carefully",
            "current_situation": "She is about to make contact with the ancient power."
        }
        
        continuation = await generate_scene_continuation(continuation_context, TEST_USER_ID, TEST_USER_SETTINGS)
        
        assert continuation, "Continuation should not be empty"
        assert len(continuation) > 50, "Continuation should be substantial"
        
        logger.info(f"✅ Scene Continuation: Successfully generated continuation")
        logger.info(f"   Length: {len(continuation)} characters")
        logger.info(f"   Preview: {continuation[:150]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Scene continuation test failed: {e}")
        return False

async def test_scene_continuation_streaming():
    """Test streaming scene continuation"""
    logger.info("🧪 Testing Scene Continuation Streaming...")
    
    try:
        continuation_context = {
            **TEST_CONTEXT,
            "previous_content": "Aria reached out toward the artifact, her hand trembling with anticipation.",
            "choice_made": "Touch the artifact carefully",
            "current_situation": "She is about to make contact with the ancient power."
        }
        
        chunks = []
        async for chunk in generate_scene_continuation_streaming(continuation_context, TEST_USER_ID, TEST_USER_SETTINGS):
            chunks.append(chunk)
        
        full_continuation = "".join(chunks)
        
        assert chunks, "Should receive streaming chunks"
        assert full_continuation, "Full continuation should not be empty"
        assert len(full_continuation) > 50, "Streamed continuation should be substantial"
        
        logger.info(f"✅ Scene Continuation Streaming: Successfully streamed continuation")
        logger.info(f"   Chunks received: {len(chunks)}")
        logger.info(f"   Total length: {len(full_continuation)} characters")
        logger.info(f"   Preview: {full_continuation[:150]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Scene continuation streaming test failed: {e}")
        return False

async def test_cache_invalidation():
    """Test cache invalidation"""
    logger.info("🧪 Testing Cache Invalidation...")
    
    try:
        # This should not raise an exception
        invalidate_user_llm_cache(TEST_USER_ID)
        
        logger.info("✅ Cache Invalidation: Successfully invalidated cache")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Cache invalidation test failed: {e}")
        return False

async def test_connection_validation():
    """Test connection validation with helpful error messages"""
    logger.info("🧪 Testing Connection Validation...")
    
    try:
        # Test with correct URL
        success, message = await unified_llm_service.validate_user_connection(TEST_USER_ID, TEST_USER_SETTINGS)
        if success:
            logger.info("✅ Connection Validation: Correct URL works")
        else:
            logger.error(f"❌ Connection Validation: Correct URL failed: {message}")
            return False
        
        # Test with incorrect URL (without /v1)
        success, message = await unified_llm_service.validate_user_connection(TEST_USER_ID + 1, TEST_USER_SETTINGS_INCORRECT)
        if not success and "/v1" in message:
            logger.info("✅ Connection Validation: Incorrect URL provides helpful error message")
            logger.info(f"   Error message: {message}")
        else:
            logger.error(f"❌ Connection Validation: Expected helpful error for incorrect URL, got: {message}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Connection validation test failed: {e}")
        return False

async def run_all_tests():
    """Run all tests and report results"""
    logger.info("🚀 Starting Unified LLM Service Tests")
    logger.info("=" * 60)
    
    tests = [
        ("Prompt Manager", test_prompt_manager),
        ("LLM Client", test_llm_client),
        ("Unified Service Basic", test_unified_service_basic),
        ("Connection Validation", test_connection_validation),
        ("Scenario Generation", test_scenario_generation),
        ("Title Generation", test_title_generation),
        ("Plot Generation", test_plot_generation),
        ("Scene Generation", test_scene_generation),
        ("Scene Streaming", test_scene_streaming),
        ("Choices Generation", test_choices_generation),
        ("Scene Continuation", test_scene_continuation),
        ("Scene Continuation Streaming", test_scene_continuation_streaming),
        ("Cache Invalidation", test_cache_invalidation),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
        
        logger.info("")  # Add spacing between tests
    
    # Report results
    logger.info("=" * 60)
    logger.info("📊 TEST RESULTS SUMMARY")
    logger.info("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{status} - {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    logger.info("=" * 60)
    logger.info(f"📈 Total: {len(results)} tests")
    logger.info(f"✅ Passed: {passed}")
    logger.info(f"❌ Failed: {failed}")
    
    if failed == 0:
        logger.info("🎉 All tests passed! The unified LLM service is ready for integration.")
    else:
        logger.info("⚠️  Some tests failed. Please review the errors above.")
    
    return failed == 0

if __name__ == "__main__":
    # Check if user wants to update test settings
    print("🧪 Unified LLM Service Test Suite")
    print("=" * 60)
    print("Before running tests, please ensure:")
    print("1. Your LLM service is running and accessible")
    print("2. Update TEST_USER_SETTINGS in this script with your configuration")
    print("3. The model specified in TEST_USER_SETTINGS is available")
    print("")
    print("Using TabbyAPI on https://api.nrdd.us")
    print("")
    
    # Run the tests
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
