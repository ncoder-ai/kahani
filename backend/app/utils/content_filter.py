"""
Content filtering utilities for NSFW detection and prevention.
Protects children and restricted users from inappropriate content.
"""
import re
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)

# Comprehensive NSFW keyword list
# These words indicate adult, violent, or disturbing content
NSFW_KEYWORDS = [
    # Sexual/Adult content
    'sex', 'sexual', 'erotic', 'porn', 'pornography', 'xxx', 'nude', 'naked', 
    'nsfw', 'explicit', 'adult', 'mature', 'sensual', 'orgasm', 'arousal',
    'intercourse', 'seduction', 'lust', 'desire', 'passionate', 'intimate',
    'bedroom', 'strip', 'undress', 'breast', 'genitals',
    
    # Violence/Gore
    'gore', 'brutal', 'torture', 'mutilate', 'dismember', 'decapitate',
    'blood', 'massacre', 'slaughter', 'carnage', 'visceral', 'graphic violence',
    
    # Disturbing content
    'disturbing', 'horrific', 'gruesome', 'macabre', 'morbid',
    
    # Drugs/Substance abuse
    'drug abuse', 'overdose', 'addiction', 'narcotic',
    
    # Rating indicators
    'r-rated', '18+', 'adults only', 'not safe for work',
]

# Patterns for more sophisticated detection
NSFW_PATTERNS = [
    r'\b(sex|porn|nude|naked)\b',  # Word boundaries for common terms
    r'18\+',  # Age restrictions
    r'xxx',  # Common adult indicator
    r'nsfw',  # Not safe for work
]

# Compile patterns for performance
COMPILED_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in NSFW_PATTERNS]


def has_nsfw_keywords(text: str) -> Tuple[bool, List[str]]:
    """
    Check if text contains NSFW keywords.
    
    Args:
        text: The text to check
        
    Returns:
        Tuple of (has_nsfw, list_of_found_keywords)
    """
    if not text:
        return False, []
    
    text_lower = text.lower()
    found_keywords = []
    
    # Check for exact keyword matches
    for keyword in NSFW_KEYWORDS:
        if keyword in text_lower:
            found_keywords.append(keyword)
    
    # Check regex patterns
    for pattern in COMPILED_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            found_keywords.extend([m if isinstance(m, str) else m[0] for m in matches])
    
    # Remove duplicates
    found_keywords = list(set(found_keywords))
    
    has_nsfw = len(found_keywords) > 0
    
    if has_nsfw:
        logger.info(f"NSFW content detected. Keywords: {', '.join(found_keywords[:3])}...")
    
    return has_nsfw, found_keywords


def get_nsfw_prevention_prompt() -> str:
    """
    Get the prompt injection text to prevent NSFW content generation.
    This should be added to system prompts when generating content for restricted users.
    
    Returns:
        The NSFW prevention prompt text
    """
    return """
CRITICAL CONTENT POLICY - FAMILY-FRIENDLY MODE:
This story is being generated for a user with content restrictions. You MUST strictly follow these rules:

1. NO SEXUAL CONTENT: Absolutely no sexual content, romantic intimacy beyond holding hands, or suggestive situations.
2. NO GRAPHIC VIOLENCE: Avoid detailed descriptions of violence, blood, gore, or injury. Keep action sequences mild.
3. NO ADULT THEMES: No drugs, alcohol abuse, explicit language, or mature psychological content.
4. NO DISTURBING CONTENT: Avoid horror, terror, or disturbing imagery that could upset younger audiences.
5. KEEP IT PG-13: All content should be appropriate for ages 13 and up (equivalent to PG-13 rating).

If the user's input requests inappropriate content:
- Politely redirect to age-appropriate alternatives
- Focus on adventure, friendship, personal growth, and positive themes
- Keep the story engaging while maintaining family-friendly content

Remember: The safety of young readers is paramount. When in doubt, keep it safe and appropriate.
"""


def get_nsfw_warning_message(found_keywords: List[str]) -> str:
    """
    Generate a user-friendly warning message about NSFW content detection.
    
    Args:
        found_keywords: List of detected NSFW keywords
        
    Returns:
        User-friendly warning message
    """
    keyword_list = ", ".join(found_keywords[:3])
    if len(found_keywords) > 3:
        keyword_list += f" (and {len(found_keywords) - 3} more)"
    
    return (
        f"Your story contains content that may not be appropriate for all audiences. "
        f"Detected keywords: {keyword_list}. "
        f"Please modify your content or contact an administrator to enable NSFW permissions."
    )


def validate_story_content(title: str, description: str, allow_nsfw: bool = False) -> Tuple[bool, str]:
    """
    Validate story content for NSFW keywords.
    
    Args:
        title: Story title
        description: Story description
        allow_nsfw: Whether user has NSFW permissions
        
    Returns:
        Tuple of (is_valid, error_message)
        If is_valid is True, error_message will be empty string
    """
    if allow_nsfw:
        # User has NSFW permissions, no validation needed
        return True, ""
    
    # Check title
    has_nsfw_title, title_keywords = has_nsfw_keywords(title)
    
    # Check description
    has_nsfw_desc, desc_keywords = has_nsfw_keywords(description)
    
    # Combine results
    if has_nsfw_title or has_nsfw_desc:
        all_keywords = list(set(title_keywords + desc_keywords))
        error_message = get_nsfw_warning_message(all_keywords)
        logger.warning(f"NSFW content blocked in story creation. Keywords: {', '.join(all_keywords)}")
        return False, error_message
    
    return True, ""


def validate_genre(genre: str, allow_nsfw: bool = False) -> Tuple[bool, str]:
    """
    Validate that selected genre is allowed based on user permissions.
    
    Args:
        genre: Selected genre
        allow_nsfw: Whether user has NSFW permissions
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # NSFW genres (must match frontend list)
    NSFW_GENRES = ['erotica', 'violence', 'dark-fantasy', 'psychological']
    
    if not allow_nsfw and genre in NSFW_GENRES:
        error_message = (
            f"The '{genre}' genre requires NSFW permissions. "
            f"Please select a different genre or contact an administrator."
        )
        logger.warning(f"NSFW genre '{genre}' blocked for restricted user")
        return False, error_message
    
    return True, ""


def should_inject_nsfw_filter(user_allow_nsfw: bool) -> bool:
    """
    Determine if NSFW filter should be injected into LLM prompts.
    
    Args:
        user_allow_nsfw: User's allow_nsfw permission
        
    Returns:
        True if filter should be injected, False otherwise
    """
    return not user_allow_nsfw

