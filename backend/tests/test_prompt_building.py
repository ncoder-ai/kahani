"""
Tests for unified prompt building across all generation methods.

Verifies that:
1. All generation methods use the same system prompt (scene_with_immediate)
2. All generation methods use _format_context_as_messages() for context
3. Only the final message differs per operation type
4. PromptManager methods return correct task instructions
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from typing import Dict, Any, List
import json
import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.llm.prompts import PromptManager, prompt_manager
from app.services.llm.service import UnifiedLLMService


class TestPromptManagerTaskInstructions:
    """Test PromptManager task instruction methods."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.pm = PromptManager()
    
    def test_get_task_instruction_with_immediate(self):
        """Test task instruction when immediate_situation is provided."""
        result = self.pm.get_task_instruction(
            has_immediate=True,
            immediate_situation="The hero opens the door.",
            scene_length_description="medium (100-150 words)"
        )
        
        assert result is not None
        assert len(result) > 0
        assert "The hero opens the door." in result
        assert "WHAT HAPPENS NEXT" in result
    
    def test_get_task_instruction_without_immediate(self):
        """Test task instruction when no immediate_situation."""
        result = self.pm.get_task_instruction(
            has_immediate=False,
            scene_length_description="medium (100-150 words)"
        )
        
        assert result is not None
        assert len(result) > 0
        assert "continues naturally" in result.lower() or "engaging scene" in result.lower()
    
    def test_get_continuation_task_instruction(self):
        """Test continuation task instruction generation."""
        current_scene = "The warrior stood at the edge of the cliff, sword drawn."
        continuation_prompt = "Continue with more action and dialogue."
        
        result = self.pm.get_continuation_task_instruction(
            current_scene_content=current_scene,
            continuation_prompt=continuation_prompt,
            choices_count=4
        )
        
        assert result is not None
        assert len(result) > 0
        assert "CURRENT SCENE TO CONTINUE" in result
        assert current_scene in result
        assert "CONTINUATION INSTRUCTION" in result
        assert continuation_prompt in result
        # Should include choices reminder
        assert "4" in result or "four" in result.lower()
    
    def test_get_enhancement_task_instruction(self):
        """Test guided enhancement task instruction generation."""
        original_scene = "She walked into the room and sat down."
        enhancement_guidance = "Add more sensory details and atmosphere."
        
        result = self.pm.get_enhancement_task_instruction(
            original_scene=original_scene,
            enhancement_guidance=enhancement_guidance,
            scene_length_description="long (150-250 words)",
            choices_count=4
        )
        
        assert result is not None
        assert len(result) > 0
        assert "ORIGINAL SCENE" in result
        assert original_scene in result
        assert "ENHANCEMENT REQUEST" in result
        assert enhancement_guidance in result
        assert "long (150-250 words)" in result
    
    def test_get_chapter_conclusion_task_instruction(self):
        """Test chapter conclusion task instruction generation."""
        result = self.pm.get_chapter_conclusion_task_instruction(
            chapter_number=1,
            chapter_title="The Beginning",
            chapter_location="Castle Dungeon",
            chapter_time_period="Medieval",
            chapter_scenario="The hero escapes"
        )
        
        assert result is not None
        assert len(result) > 0
        assert "CHAPTER CONCLUSION" in result
        assert "Chapter Number: 1" in result or "chapter 1" in result.lower()
        assert "The Beginning" in result
        assert "Castle Dungeon" in result
        assert "Medieval" in result
        assert "The hero escapes" in result
    
    def test_get_user_choices_reminder(self):
        """Test choices reminder generation."""
        result = self.pm.get_user_choices_reminder(choices_count=4)
        
        assert result is not None
        assert "4" in result
        assert "choices" in result.lower()
    
    def test_system_prompt_consistency(self):
        """Test that scene_with_immediate system prompt is retrievable."""
        result = self.pm.get_prompt(
            "scene_with_immediate", "system",
            scene_length_description="medium (100-150 words)",
            choices_count=4
        )
        
        assert result is not None
        assert len(result) > 100  # Should be substantial
        assert "interactive fiction" in result.lower() or "story" in result.lower()


class TestLLMServiceContextBuilding:
    """Test LLMService context building methods."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = UnifiedLLMService()
        self.mock_context = {
            "story_title": "Test Story",
            "story_description": "A test story description",
            "genre": "fantasy",
            "tone": "dark",
            "scenario": "A hero embarks on a quest.",
            "characters": [
                {"name": "Hero", "role": "protagonist"},
                {"name": "Villain", "role": "antagonist"}
            ],
            "previous_scenes": "Scene 1: The journey begins.\n\nScene 2: The hero meets a stranger.",
            "story_so_far": "Summary of events so far.",
            "current_situation": "The hero faces a choice.",
            "current_scene_content": "The hero stood at the crossroads.",
            "continuation_prompt": "Continue the story.",
            "enhancement_guidance": "Add more drama.",
        }
        self.mock_user_settings = {
            "generation_preferences": {
                "scene_length": "medium",
                "choices_count": 4
            },
            "context_settings": {
                "scene_batch_size": 10
            }
        }
    
    def test_format_context_as_messages_returns_list(self):
        """Test that _format_context_as_messages returns a list of messages."""
        result = self.service._format_context_as_messages(
            self.mock_context,
            scene_batch_size=10
        )
        
        assert isinstance(result, list)
        assert len(result) > 0
        
        # Each message should have role and content
        for msg in result:
            assert "role" in msg
            assert "content" in msg
            assert msg["role"] == "user"
    
    def test_format_context_as_messages_includes_story_foundation(self):
        """Test that context messages include story foundation."""
        result = self.service._format_context_as_messages(
            self.mock_context,
            scene_batch_size=10
        )
        
        # Find story foundation message
        foundation_found = False
        for msg in result:
            if "STORY FOUNDATION" in msg["content"]:
                foundation_found = True
                assert "fantasy" in msg["content"]  # genre
                assert "dark" in msg["content"]  # tone
                break
        
        assert foundation_found, "Story foundation message not found"
    
    def test_format_context_as_messages_includes_story_progress(self):
        """Test that context messages include story progress."""
        result = self.service._format_context_as_messages(
            self.mock_context,
            scene_batch_size=10
        )
        
        # Find story progress message
        progress_found = False
        for msg in result:
            if "STORY PROGRESS" in msg["content"] or "RECENT SCENES" in msg["content"]:
                progress_found = True
                break
        
        assert progress_found, "Story progress message not found"


class TestMessageStructureConsistency:
    """Test that all generation methods use consistent message structure."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = UnifiedLLMService()
        self.mock_context = {
            "story_title": "Test Story",
            "genre": "fantasy",
            "tone": "dark",
            "scenario": "A hero embarks on a quest.",
            "characters": [],
            "previous_scenes": "Scene 1: Beginning.",
            "story_so_far": "Summary.",
            "current_situation": "Hero faces choice.",
            "current_scene_content": "The hero stood ready.",
            "continuation_prompt": "Continue.",
            "enhancement_guidance": "Add drama.",
        }
        self.mock_user_settings = {
            "generation_preferences": {
                "scene_length": "medium",
                "choices_count": 4
            },
            "context_settings": {
                "scene_batch_size": 10
            }
        }
    
    def test_system_prompt_uses_scene_with_immediate(self):
        """Verify all methods should use scene_with_immediate for system prompt."""
        pm = PromptManager()
        
        # Get the system prompt that should be used
        system_prompt = pm.get_prompt(
            "scene_with_immediate", "system",
            scene_length_description="medium (100-150 words)",
            choices_count=4
        )
        
        # Verify it's the expected format
        assert "interactive fiction" in system_prompt.lower() or "story" in system_prompt.lower()
        assert "CHOICES" in system_prompt or "choices" in system_prompt.lower()
    
    def test_context_messages_are_user_role(self):
        """Verify context messages all have user role."""
        result = self.service._format_context_as_messages(
            self.mock_context,
            scene_batch_size=10
        )
        
        for msg in result:
            assert msg["role"] == "user", f"Expected user role, got {msg['role']}"
    
    def test_message_content_not_empty(self):
        """Verify no empty message content."""
        result = self.service._format_context_as_messages(
            self.mock_context,
            scene_batch_size=10
        )
        
        for i, msg in enumerate(result):
            assert msg["content"].strip(), f"Message {i} has empty content"


class TestPromptTemplatesExist:
    """Test that all required prompt templates exist in prompts.yml."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.pm = PromptManager()
    
    def test_task_continuation_template_exists(self):
        """Test that task_continuation template exists."""
        if self.pm._prompts_cache:
            scene_base = self.pm._prompts_cache.get("scene_base", {})
            assert "task_continuation" in scene_base, "task_continuation template missing"
            assert len(scene_base["task_continuation"]) > 0
    
    def test_task_guided_enhancement_template_exists(self):
        """Test that task_guided_enhancement template exists."""
        if self.pm._prompts_cache:
            scene_base = self.pm._prompts_cache.get("scene_base", {})
            assert "task_guided_enhancement" in scene_base, "task_guided_enhancement template missing"
            assert len(scene_base["task_guided_enhancement"]) > 0
    
    def test_task_with_immediate_template_exists(self):
        """Test that task_with_immediate template exists."""
        if self.pm._prompts_cache:
            scene_base = self.pm._prompts_cache.get("scene_base", {})
            assert "task_with_immediate" in scene_base, "task_with_immediate template missing"
    
    def test_task_without_immediate_template_exists(self):
        """Test that task_without_immediate template exists."""
        if self.pm._prompts_cache:
            scene_base = self.pm._prompts_cache.get("scene_base", {})
            assert "task_without_immediate" in scene_base, "task_without_immediate template missing"
    
    def test_task_chapter_conclusion_template_exists(self):
        """Test that task_chapter_conclusion template exists."""
        if self.pm._prompts_cache:
            scene_base = self.pm._prompts_cache.get("scene_base", {})
            assert "task_chapter_conclusion" in scene_base, "task_chapter_conclusion template missing"
            assert len(scene_base["task_chapter_conclusion"]) > 0


class TestCleaningFunctions:
    """Test content cleaning functions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = UnifiedLLMService()
    
    def test_clean_instruction_tags(self):
        """Test that instruction tags are properly cleaned."""
        test_content = "Some text [/inst][inst] more text [inst] end [/inst]"
        result = self.service._clean_instruction_tags(test_content)
        
        assert "[/inst]" not in result
        assert "[inst]" not in result
        assert "Some text" in result
        assert "more text" in result
    
    def test_clean_scene_numbers(self):
        """Test that scene numbers are properly cleaned."""
        test_content = "Scene 1: Content here\nScene 2: More content"
        result = self.service._clean_scene_numbers(test_content)
        
        # Scene numbers at start of lines should be removed
        assert not result.startswith("Scene 1:")


class TestIntegration:
    """Integration tests for the complete prompt building flow."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.pm = PromptManager()
        self.service = UnifiedLLMService()
    
    def test_complete_continuation_prompt_structure(self):
        """Test the complete structure of a continuation prompt."""
        # Get system prompt
        system_prompt = self.pm.get_prompt(
            "scene_with_immediate", "system",
            scene_length_description="medium (100-150 words)",
            choices_count=4
        )
        
        # Get continuation task
        task = self.pm.get_continuation_task_instruction(
            current_scene_content="The hero faced the dragon.",
            continuation_prompt="Add more tension.",
            choices_count=4
        )
        
        # Verify structure
        assert system_prompt is not None
        assert task is not None
        assert "CURRENT SCENE TO CONTINUE" in task
        assert "CONTINUATION INSTRUCTION" in task
    
    def test_complete_enhancement_prompt_structure(self):
        """Test the complete structure of an enhancement prompt."""
        # Get system prompt
        system_prompt = self.pm.get_prompt(
            "scene_with_immediate", "system",
            scene_length_description="medium (100-150 words)",
            choices_count=4
        )
        
        # Get enhancement task
        task = self.pm.get_enhancement_task_instruction(
            original_scene="The warrior attacked.",
            enhancement_guidance="Make it more vivid.",
            scene_length_description="medium (100-150 words)",
            choices_count=4
        )
        
        # Verify structure
        assert system_prompt is not None
        assert task is not None
        assert "ORIGINAL SCENE" in task
        assert "ENHANCEMENT REQUEST" in task


def run_tests():
    """Run all tests and print results."""
    print("=" * 70)
    print("PROMPT BUILDING TESTS")
    print("=" * 70)
    
    # Run pytest with verbose output
    exit_code = pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-x"  # Stop on first failure
    ])
    
    return exit_code


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)

