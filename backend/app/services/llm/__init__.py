"""
Unified LLM Service Package

This package provides a clean, unified interface for all LLM operations
using LiteLLM for multi-provider support and centralized prompt management.
"""

from .service import UnifiedLLMService
from .client import LLMClient
from .prompts import PromptManager, prompt_manager
from .llm_generation_core import LLMConnectionError

__all__ = ['UnifiedLLMService', 'LLMClient', 'PromptManager', 'prompt_manager', 'LLMConnectionError']

# Global service instance
unified_llm_service = UnifiedLLMService()
