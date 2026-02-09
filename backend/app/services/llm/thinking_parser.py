"""
Thinking Tag Parser

Automatically detects and strips reasoning/thinking tags from LLM responses.
Supports various formats used by different models (DeepSeek, Qwen, etc.).
"""

import re
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


class ThinkingTagParser:
    """
    Parser for detecting and removing thinking/reasoning tags from LLM outputs.
    
    Many instruction-tuned models output their reasoning process in special tags
    before providing the final answer. This parser automatically detects and
    removes these tags to present clean output to users.
    """
    
    # Thinking tag patterns (tag_name, opening_pattern, closing_pattern)
    # Ordered by specificity (more specific patterns first)
    THINKING_PATTERNS = [
        # DeepSeek style
        ("DeepSeek think", r"<think>", r"</think>"),
        ("DeepSeek thinking", r"<thinking>", r"</thinking>"),
        
        # Qwen QwQ style
        ("Qwen reasoning", r"<reasoning>", r"</reasoning>"),
        
        # Generic XML-style tags
        ("Generic think", r"<think>", r"</think>"),
        ("Generic thinking", r"<thinking>", r"</thinking>"),
        ("Generic reasoning", r"<reasoning>", r"</reasoning>"),
        ("Generic reflection", r"<reflection>", r"</reflection>"),
        
        # Bracket style
        ("Bracket thinking", r"\[THINKING\]", r"\[/THINKING\]"),
        ("Bracket reasoning", r"\[REASONING\]", r"\[/REASONING\]"),
        ("Bracket no_think", r"\[no_think\]", r"\[/no_think\]"),
        
        # Special token style (used by some models)
        ("Token reasoning", r"<\|reasoning_start\|>", r"<\|reasoning_end\|>"),
        ("Token thinking", r"<\|thinking_start\|>", r"<\|thinking_end\|>"),
        ("Token reflection", r"<\|reflection_start\|>", r"<\|reflection_end\|>"),
        
        # Markdown-style code blocks sometimes used for thinking
        ("Markdown thinking", r"```thinking", r"```"),
        ("Markdown reasoning", r"```reasoning", r"```"),
    ]
    
    @classmethod
    def strip_thinking_tags(cls, text: str, preserve_whitespace: bool = False) -> str:
        """
        Remove all thinking/reasoning tags and their content from text.
        
        Args:
            text: Input text that may contain thinking tags
            preserve_whitespace: If True, preserve leading/trailing whitespace (for streaming chunks)
            
        Returns:
            Text with all thinking content removed
        """
        if not text or not isinstance(text, str):
            return text
        
        original_length = len(text)
        cleaned_text = text
        removed_count = 0
        
        # Try each pattern
        for pattern_name, opening, closing in cls.THINKING_PATTERNS:
            # Build regex pattern that matches opening tag, content, and closing tag
            # Use DOTALL flag to match across newlines
            # Use non-greedy matching to handle multiple occurrences
            pattern = f"{opening}.*?{closing}"
            
            # Find all matches first (for logging)
            matches = re.findall(pattern, cleaned_text, re.DOTALL | re.IGNORECASE)
            if matches:
                logger.debug(f"Found {len(matches)} '{pattern_name}' tag(s)")
                removed_count += len(matches)
            
            # Remove all occurrences
            cleaned_text = re.sub(pattern, "", cleaned_text, flags=re.DOTALL | re.IGNORECASE)
        
        # Clean up excessive whitespace that may result from tag removal
        # Replace multiple newlines with max 2 newlines
        cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
        
        # Only strip leading/trailing whitespace if preserve_whitespace is False
        # For streaming chunks, we need to preserve leading spaces to maintain word boundaries
        if not preserve_whitespace:
            cleaned_text = cleaned_text.strip()
        
        if removed_count > 0:
            removed_chars = original_length - len(cleaned_text)
            logger.info(f"Stripped {removed_count} thinking tag(s), removed {removed_chars} characters")
        
        return cleaned_text
    
    @classmethod
    def detect_thinking_tags(cls, text: str) -> List[Tuple[str, str]]:
        """
        Detect which thinking tags are present in the text without removing them.
        
        Args:
            text: Input text to analyze
            
        Returns:
            List of tuples (pattern_name, matched_content)
        """
        if not text or not isinstance(text, str):
            return []
        
        detected = []
        
        for pattern_name, opening, closing in cls.THINKING_PATTERNS:
            pattern = f"{opening}(.*?){closing}"
            matches = re.finditer(pattern, text, re.DOTALL | re.IGNORECASE)
            
            for match in matches:
                content = match.group(1).strip()
                detected.append((pattern_name, content))
        
        return detected
    
    @classmethod
    def has_thinking_tags(cls, text: str) -> bool:
        """
        Check if text contains any thinking tags.
        
        Args:
            text: Input text to check
            
        Returns:
            True if thinking tags are present, False otherwise
        """
        return len(cls.detect_thinking_tags(text)) > 0
    
    @classmethod
    def extract_thinking_content(cls, text: str) -> Tuple[str, Optional[str]]:
        """
        Extract thinking content from text and return both cleaned content and thinking.
        
        This method extracts the thinking/reasoning content from tag-based models
        (like DeepSeek, Qwen with <think> tags) and returns both the cleaned 
        response and the extracted thinking content.
        
        Args:
            text: Input text that may contain thinking tags
            
        Returns:
            Tuple of (cleaned_content, thinking_content or None)
            - cleaned_content: The text with thinking tags removed
            - thinking_content: The extracted thinking text, or None if no thinking found
        """
        if not text or not isinstance(text, str):
            return text, None
        
        thinking_parts = []
        cleaned = text
        
        # Try each pattern and extract thinking content
        for pattern_name, opening, closing in cls.THINKING_PATTERNS:
            # Build pattern to capture the content inside tags
            pattern = f"({opening})(.*?)({closing})"
            
            # Find all matches
            matches = list(re.finditer(pattern, cleaned, re.DOTALL | re.IGNORECASE))
            
            for match in matches:
                thinking_content = match.group(2).strip()
                if thinking_content:
                    thinking_parts.append(thinking_content)
                    logger.debug(f"Extracted {len(thinking_content)} chars from '{pattern_name}' tag")
            
            # Remove the matched tags from cleaned text
            cleaned = re.sub(f"{opening}.*?{closing}", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
        
        # Clean up excessive whitespace
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        cleaned = cleaned.strip()
        
        # Combine all thinking parts
        thinking = "\n\n".join(thinking_parts) if thinking_parts else None
        
        if thinking:
            logger.info(f"Extracted thinking content: {len(thinking)} chars from {len(thinking_parts)} tag(s)")
        
        return cleaned, thinking


# Convenience functions
def strip_thinking_tags(text: str, preserve_whitespace: bool = False) -> str:
    """
    Convenience function to strip thinking tags from text.
    
    Args:
        text: Input text
        preserve_whitespace: If True, preserve leading/trailing whitespace (for streaming chunks)
        
    Returns:
        Text with thinking tags removed
    """
    return ThinkingTagParser.strip_thinking_tags(text, preserve_whitespace=preserve_whitespace)


def extract_thinking_content(text: str) -> Tuple[str, Optional[str]]:
    """
    Convenience function to extract thinking content from text.
    
    Args:
        text: Input text that may contain thinking tags
        
    Returns:
        Tuple of (cleaned_content, thinking_content or None)
    """
    return ThinkingTagParser.extract_thinking_content(text)

