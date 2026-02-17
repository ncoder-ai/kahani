# Services modules
from .llm.service import UnifiedLLMService

# Create a global instance for easy access
llm_service = UnifiedLLMService()

__all__ = ["generate_content", "generate_content_stream"]