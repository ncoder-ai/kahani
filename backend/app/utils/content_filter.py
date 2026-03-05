"""
Content filtering utilities for NSFW detection and prevention.
Protects children and restricted users from inappropriate content.
"""
import re
from typing import List, Tuple, Dict, Any
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


def get_nsfw_allowed_prompt() -> str:
    """
    Get the prompt text for uncensored content mode.
    Injected when the user has allow_nsfw=True.

    Returns:
        The uncensored content permission text
    """
    return "CONTENT POLICY: Content is uncensored. Sexual, profane, and mature language is permitted when it fits the scene and characters."


def get_content_permission_prompt(allow_nsfw: bool) -> str:
    """
    Get the appropriate content permission prompt based on user's NSFW setting.
    Always returns a prompt — either uncensored permission or family-friendly restriction.

    Args:
        allow_nsfw: Whether the user has NSFW content enabled

    Returns:
        Content permission prompt text
    """
    # Normalize the allow_nsfw value (handle None, strings, etc.)
    if allow_nsfw is None:
        normalized = False
    elif isinstance(allow_nsfw, str):
        normalized = allow_nsfw.lower() in ('true', '1', 'yes')
    else:
        normalized = bool(allow_nsfw)

    if normalized:
        return get_nsfw_allowed_prompt()
    else:
        return get_nsfw_prevention_prompt()


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
    # Handle None, string "True"/"False", and other types
    if user_allow_nsfw is None:
        return True  # Default to filtering if not set
    if isinstance(user_allow_nsfw, str):
        # Handle string booleans
        return user_allow_nsfw.lower() not in ('true', '1', 'yes')
    # For boolean or int (0/1), use truthiness
    return not bool(user_allow_nsfw)


async def moderate_content(
    text: str,
    user_settings: Dict[str, Any],
    content_type: str = "input"
) -> Tuple[bool, str]:
    """
    LLM-based content moderation for SFW stories.

    Uses the extraction model (fast, small) for classification.
    Falls back to main LLM if extraction model is unavailable.

    Args:
        text: The text to moderate (user input or generated output)
        user_settings: User settings dict
        content_type: "input" for user prompts, "output" for generated text

    Returns:
        Tuple of (is_blocked, reason)
    """
    if not text or not text.strip():
        return False, ""

    # Get moderation prompt from prompts.yml
    from ..services.llm.prompts import prompt_manager
    prompt_key = f"content_moderation.{content_type}"
    system_prompt = prompt_manager.get_raw_prompt(prompt_key)
    if not system_prompt:
        # Hardcoded fallback
        if content_type == "input":
            system_prompt = (
                "You are a content moderator for a family-friendly (SFW) story app.\n"
                "Determine if this user prompt is requesting sexual, graphically violent, or otherwise adult content.\n"
                "Misspellings, euphemisms, slang, and coded language count as violations.\n"
                "Reply with exactly one word: ALLOW or BLOCK"
            )
        else:
            system_prompt = (
                "You are a content moderator for a family-friendly (SFW) story app.\n"
                "Determine if this generated story text contains sexual content, graphic violence, or adult themes.\n"
                "Reply with exactly one word: ALLOW or BLOCK"
            )

    # Try extraction model first (fast, cheap)
    try:
        from ..services.llm.extraction_service import ExtractionLLMService
        extraction_service = ExtractionLLMService.from_settings(
            user_settings,
            max_tokens_override=10,
            temperature_override=0.0,
        )
        if extraction_service:
            response = await extraction_service.generate(
                prompt=text.strip()[:2000],
                system_prompt=system_prompt,
                max_tokens=10,
            )
            response_clean = response.strip().upper() if response else ""
            if "BLOCK" in response_clean:
                logger.warning(f"[MODERATION] Content blocked ({content_type}): {text[:80]}...")
                return True, "Content flagged by moderation"
            return False, ""
    except Exception as e:
        logger.warning(f"[MODERATION] Extraction model failed, trying main LLM: {e}")

    # Fallback to main LLM
    try:
        from ..services.llm.llm_generation_core import LLMGenerationCore
        from ..services.llm.service import UnifiedLLMService
        service = UnifiedLLMService()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text.strip()[:2000]},
        ]
        response = await service._generate_with_messages(
            messages=messages,
            user_id=0,
            user_settings=user_settings,
            max_tokens=10,
            temperature=0.0,
            skip_nsfw_filter=True,
        )
        response_clean = response.strip().upper() if response else ""
        if "BLOCK" in response_clean:
            logger.warning(f"[MODERATION] Content blocked by main LLM ({content_type}): {text[:80]}...")
            return True, "Content flagged by moderation"
        return False, ""
    except Exception as e:
        logger.error(f"[MODERATION] Both extraction and main LLM failed: {e}")
        # Fail open — don't block if moderation itself fails
        return False, ""


def inject_nsfw_filter_if_needed(
    system_prompt: str,
    user_settings: dict,
    user_id: int = None,
    skip_nsfw_filter: bool = False,
    context: str = ""
) -> str:
    """
    Inject NSFW filter into system prompt if needed.

    This is a helper function to reduce code duplication in LLM services.
    It checks user permissions and injects the NSFW prevention prompt when needed.

    Args:
        system_prompt: The existing system prompt (may be None or empty)
        user_settings: User settings dictionary containing 'allow_nsfw' key
        user_id: User ID for logging purposes
        skip_nsfw_filter: If True, skip injection regardless of user permissions
        context: Optional context string for logging (e.g., "streaming", "text completion")

    Returns:
        The system prompt with NSFW filter injected if needed, or the original prompt
    """
    if skip_nsfw_filter:
        return system_prompt

    user_allow_nsfw = user_settings.get('allow_nsfw', False) if user_settings else False

    if not should_inject_nsfw_filter(user_allow_nsfw):
        return system_prompt

    # Need to inject NSFW filter
    nsfw_prompt = get_nsfw_prevention_prompt()
    context_str = f" ({context})" if context else ""

    if system_prompt:
        result = system_prompt.strip() + "\n\n" + nsfw_prompt
        logger.debug(f"NSFW filter injected{context_str} for user {user_id}")
        return result
    else:
        logger.debug(f"NSFW filter injected (no system prompt){context_str} for user {user_id}")
        return nsfw_prompt

