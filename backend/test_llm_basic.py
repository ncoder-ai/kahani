#!/usr/bin/env python3
"""
Basic test script for the new unified LLM service implementation.

This script tests the basic functionality without requiring an actual LLM service
to be running, focusing on prompt loading, client configuration, and service setup.
"""

import sys
import os
import logging
from typing import Dict, Any

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app.services.llm import prompt_manager
from app.services.llm.client import LLMClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_prompt_manager():
    """Test the prompt manager functionality"""
    logger.info("🧪 Testing Prompt Manager...")
    
    try:
        # Test loading prompts
        system_prompt = prompt_manager.get_system_prompt("story_generation", "scenario")
        user_prompt = prompt_manager.get_user_prompt("story_generation", "scenario")
        
        assert system_prompt, "System prompt should not be empty"
        assert user_prompt, "User prompt should not be empty"
        
        logger.info("✅ Prompt Manager: Successfully loaded prompts")
        logger.info(f"   System prompt length: {len(system_prompt)} characters")
        logger.info(f"   User prompt length: {len(user_prompt)} characters")
        
        # Test prompt formatting
        formatted_prompt = prompt_manager.format_prompt(
            user_prompt,
            context="Test context",
            elements="Test elements"
        )
        
        assert "Test context" in formatted_prompt, "Prompt formatting should work"
        assert "Test elements" in formatted_prompt, "Prompt formatting should work"
        logger.info("✅ Prompt Manager: Successfully formatted prompts")
        
        # Test settings
        max_tokens = prompt_manager.get_max_tokens("scenario")
        temperature = prompt_manager.get_temperature("default")
        
        assert max_tokens > 0, "Max tokens should be positive"
        assert 0 <= temperature <= 2, "Temperature should be in valid range"
        
        logger.info(f"✅ Prompt Manager: Successfully retrieved settings")
        logger.info(f"   Max tokens for scenario: {max_tokens}")
        logger.info(f"   Default temperature: {temperature}")
        
        # Test all prompt categories
        categories = ["story_generation", "plot_generation", "summary_generation"]
        functions = ["scenario", "titles", "scene", "scene_continuation", "choices", "complete_plot", "single_plot_point", "story_summary", "scene_variants", "story_chapters"]
        
        for category in categories:
            for function in functions:
                try:
                    system_prompt = prompt_manager.get_system_prompt(category, function)
                    user_prompt = prompt_manager.get_user_prompt(category, function)
                    if system_prompt and user_prompt:
                        logger.info(f"✅ Found prompts for {category}.{function}")
                    else:
                        logger.warning(f"⚠️  Missing prompts for {category}.{function}")
                except:
                    logger.warning(f"⚠️  Error loading prompts for {category}.{function}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Prompt Manager test failed: {e}")
        return False

def test_llm_client_config():
    """Test the LLM client configuration"""
    logger.info("🧪 Testing LLM Client Configuration...")
    
    try:
        # Test different API types
        test_configs = [
            {
                "llm_settings": {
                    "api_url": "http://localhost:11434",
                    "api_key": "not-needed-for-local",
                    "api_type": "ollama",
                    "model_name": "llama3.2:3b",
                    "temperature": 0.7,
                    "max_tokens": 2048
                }
            },
            {
                "llm_settings": {
                    "api_url": "http://localhost:8000/v1",
                    "api_key": "test-key",
                    "api_type": "openai_compatible",
                    "model_name": "gpt-3.5-turbo",
                    "temperature": 0.8,
                    "max_tokens": 1024
                }
            },
            {
                "llm_settings": {
                    "api_url": "http://localhost:5001",
                    "api_key": "not-needed-for-local",
                    "api_type": "koboldcpp",
                    "model_name": "mythomax",
                    "temperature": 0.6,
                    "max_tokens": 4096
                }
            }
        ]
        
        for i, config in enumerate(test_configs):
            logger.info(f"   Testing config {i+1}: {config['llm_settings']['api_type']}")
            
            client = LLMClient(config)
            
            assert client.api_url, "API URL should be set"
            assert client.model_name, "Model name should be set"
            assert client.temperature >= 0, "Temperature should be valid"
            
            # Test model string generation
            model_string = client.model_string
            assert model_string, "Model string should be generated"
            
            logger.info(f"     ✅ Model string: {model_string}")
            logger.info(f"     ✅ API URL: {client.api_url}")
            logger.info(f"     ✅ Temperature: {client.temperature}")
            
            # Test generation parameters
            gen_params = client.get_generation_params()
            stream_params = client.get_streaming_params()
            
            assert "model" in gen_params, "Generation params should include model"
            assert "stream" in stream_params, "Streaming params should include stream flag"
            assert stream_params["stream"] is True, "Streaming params should have stream=True"
            
            logger.info(f"     ✅ Generation parameters: {list(gen_params.keys())}")
        
        logger.info("✅ LLM Client: Successfully tested all configurations")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ LLM Client test failed: {e}")
        return False

def test_invalid_configurations():
    """Test handling of invalid configurations"""
    logger.info("🧪 Testing Invalid Configuration Handling...")
    
    try:
        # Test missing API URL
        invalid_config = {
            "llm_settings": {
                "api_key": "test-key",
                "api_type": "openai_compatible",
                "model_name": "gpt-3.5-turbo"
            }
        }
        
        try:
            client = LLMClient(invalid_config)
            logger.error("❌ Should have raised ValueError for missing API URL")
            return False
        except ValueError as e:
            assert "API URL not configured" in str(e), "Should raise appropriate error"
            logger.info("✅ Correctly handled missing API URL")
        
        # Test empty API URL
        invalid_config2 = {
            "llm_settings": {
                "api_url": "",
                "api_key": "test-key",
                "api_type": "openai_compatible",
                "model_name": "gpt-3.5-turbo"
            }
        }
        
        try:
            client = LLMClient(invalid_config2)
            logger.error("❌ Should have raised ValueError for empty API URL")
            return False
        except ValueError as e:
            assert "API URL not configured" in str(e), "Should raise appropriate error"
            logger.info("✅ Correctly handled empty API URL")
        
        logger.info("✅ Invalid Configuration Handling: All tests passed")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Invalid configuration test failed: {e}")
        return False

def test_prompt_formatting():
    """Test prompt formatting with various inputs"""
    logger.info("🧪 Testing Prompt Formatting...")
    
    try:
        # Test basic formatting
        template = "Hello {name}, you are in {location}."
        formatted = prompt_manager.format_prompt(template, name="Aria", location="the forest")
        
        assert "Aria" in formatted, "Should include name"
        assert "the forest" in formatted, "Should include location"
        logger.info("✅ Basic prompt formatting works")
        
        # Test missing variables (should not crash)
        try:
            formatted = prompt_manager.format_prompt(template, name="Aria")
            logger.info("✅ Handled missing variables gracefully")
        except Exception as e:
            logger.error(f"❌ Should handle missing variables gracefully: {e}")
            return False
        
        # Test complex formatting
        complex_template = """
        Story Context:
        {context}
        
        Characters:
        {characters}
        
        Generate a scene based on this information.
        """
        
        formatted = prompt_manager.format_prompt(
            complex_template,
            context="A magical forest adventure",
            characters="Aria (mage), Thorne (warrior)"
        )
        
        assert "magical forest adventure" in formatted, "Should include context"
        assert "Aria (mage)" in formatted, "Should include characters"
        logger.info("✅ Complex prompt formatting works")
        
        logger.info("✅ Prompt Formatting: All tests passed")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Prompt formatting test failed: {e}")
        return False

def run_basic_tests():
    """Run all basic tests and report results"""
    logger.info("🚀 Starting Basic LLM Service Tests")
    logger.info("=" * 60)
    
    tests = [
        ("Prompt Manager", test_prompt_manager),
        ("LLM Client Configuration", test_llm_client_config),
        ("Invalid Configuration Handling", test_invalid_configurations),
        ("Prompt Formatting", test_prompt_formatting),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
        
        logger.info("")  # Add spacing between tests
    
    # Report results
    logger.info("=" * 60)
    logger.info("📊 BASIC TEST RESULTS SUMMARY")
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
        logger.info("🎉 All basic tests passed! The LLM service components are working correctly.")
        logger.info("💡 Next step: Run the full test suite with an actual LLM service.")
    else:
        logger.info("⚠️  Some tests failed. Please review the errors above.")
    
    return failed == 0

if __name__ == "__main__":
    success = run_basic_tests()
    sys.exit(0 if success else 1)


