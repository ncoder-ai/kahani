"""
Simplified LLM functions using the unified LLM service

This module provides a single, flexible generation function that can handle
all types of content generation with optional streaming support.
"""

from typing import Dict, Any, List, Optional, AsyncGenerator
from .llm.service import UnifiedLLMService
from .llm.prompts import prompt_manager
from app.database import get_db
import logging

logger = logging.getLogger(__name__)

# Initialize the unified LLM service
unified_llm_service = UnifiedLLMService()

async def generate_content(
    prompt: str,
    user_id: int,
    user_settings: Dict[str, Any],
    system_prompt: str = "",
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    stream: bool = False
) -> str:
    """
    Unified content generation function
    
    Args:
        prompt: The user prompt/context for generation
        user_id: User ID for client caching
        user_settings: User's LLM configuration
        system_prompt: System prompt to guide generation
        max_tokens: Maximum tokens to generate
        temperature: Generation temperature
        stream: Whether to use streaming (collected into complete text)
    
    Returns:
        Generated content as string
    """
    return await unified_llm_service.generate(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=stream
    )

async def generate_content_stream(
    prompt: str,
    user_id: int,
    user_settings: Dict[str, Any],
    system_prompt: str = "",
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None
) -> AsyncGenerator[str, None]:
    """
    Unified streaming content generation function
    
    Args:
        prompt: The user prompt/context for generation
        user_id: User ID for client caching
        user_settings: User's LLM configuration
        system_prompt: System prompt to guide generation
        max_tokens: Maximum tokens to generate
        temperature: Generation temperature
    
    Yields:
        Generated content chunks as strings
    """
    async for chunk in unified_llm_service.generate_stream(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        temperature=temperature
    ):
        yield chunk

# Convenience functions for specific use cases
async def generate_scenario(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], stream: bool = False) -> str:
    """Generate a story scenario based on characters and context"""
    
    # Get database session for prompt lookup
    db = next(get_db())
    
    try:
        # Get dynamic prompts (user custom or default)
        system_prompt = prompt_manager.get_prompt(
            template_key="scenario_generation",
            prompt_type="system",
            user_id=user_id,
            db=db
        )
        
        # Build context string for template variables
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
            
        # Character information
        characters = context.get("characters", [])
        if characters:
            char_descriptions = []
            for char in characters:
                char_info = f"• {char.get('name', 'Unknown')}"
                if char.get('role'):
                    char_info += f" ({char['role']})"
                if char.get('description'):
                    char_info += f": {char['description']}"
                char_descriptions.append(char_info)
            context_parts.append(f"Main Characters:\n{chr(10).join(char_descriptions)}")
            
        # Story elements
        elements = []
        if context.get("opening"):
            elements.append(f"Story opening: {context['opening']}")
        if context.get("setting"):
            elements.append(f"Setting: {context['setting']}")
        if context.get("conflict"):
            elements.append(f"Driving force: {context['conflict']}")
        
        context_str = chr(10).join(context_parts)
        elements_str = chr(10).join(elements)
        
        # Get user prompt with template variables
        user_prompt = prompt_manager.get_prompt(
            template_key="scenario_generation",
            prompt_type="user",
            user_id=user_id,
            db=db,
            context=context_str,
            elements=elements_str
        )
        
        # Get max tokens for this template
        max_tokens = prompt_manager.get_max_tokens("scenario_generation")
        
        return await generate_content(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            stream=stream
        )
    
    finally:
        db.close()

async def generate_titles(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], stream: bool = False) -> List[str]:
    """Generate creative story titles based on story content"""
    
    # Get database session for prompt lookup
    db = next(get_db())
    
    try:
        # Get dynamic prompts (user custom or default)
        system_prompt = prompt_manager.get_prompt(
            template_key="title_generation",
            prompt_type="system",
            user_id=user_id,
            db=db
        )
        
        # Build context string for template variables
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
            
        # Character information
        characters = context.get("characters", [])
        if characters:
            char_descriptions = []
            for char in characters:
                char_info = f"• {char.get('name', 'Unknown')}"
                if char.get('role'):
                    char_info += f" ({char['role']})"
                if char.get('description'):
                    char_info += f": {char['description']}"
                char_descriptions.append(char_info)
            context_parts.append(f"Main Characters:\n{chr(10).join(char_descriptions)}")
            
        # Story scenario
        if context.get("scenario"):
            context_parts.append(f"Story Scenario:\n{context['scenario']}")
            
        # Story elements
        story_elements = context.get("story_elements", {})
        if story_elements:
            elements = []
            for key, value in story_elements.items():
                if value:
                    elements.append(f"{key.title()}: {value}")
            if elements:
                context_parts.append(f"Story Elements:\n{chr(10).join(elements)}")

        context_str = chr(10).join(context_parts)
        
        # Get user prompt with template variables
        user_prompt = prompt_manager.get_prompt(
            template_key="title_generation",
            prompt_type="user",
            user_id=user_id,
            db=db,
            context=context_str
        )
        
        # Get max tokens for this template
        max_tokens = prompt_manager.get_max_tokens("title_generation")
        
        response = await generate_content(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            stream=stream
        )
    
    finally:
        db.close()
    
    # Parse titles from response
    titles = [title.strip() for title in response.split('\n') if title.strip()]
    
    # Remove any numbers, bullets, or formatting from titles
    cleaned_titles = []
    for title in titles:
        # Remove common prefixes like "1.", "•", "-", etc.
        cleaned_title = title.strip()
        # Remove leading numbers and dots
        import re
        cleaned_title = re.sub(r'^[\d\.\-\*\•]\s*', '', cleaned_title)
        # Remove quotes if they wrap the entire title
        if cleaned_title.startswith('"') and cleaned_title.endswith('"'):
            cleaned_title = cleaned_title[1:-1]
        if cleaned_title.startswith("'") and cleaned_title.endswith("'"):
            cleaned_title = cleaned_title[1:-1]
        
        if cleaned_title and len(cleaned_title.split()) <= 8:  # Reasonable title length
            cleaned_titles.append(cleaned_title.strip())
    
    titles = cleaned_titles
    
    # Ensure we have exactly 5 titles
    if len(titles) < 5:
        # Add fallback titles if needed
        fallback_titles = [
            "The Journey Begins",
            "Shadows and Light", 
            "Destiny Calls",
            "The Final Choice",
            "Beyond the Horizon"
        ]
        titles.extend(fallback_titles[:5-len(titles)])
    
    return titles[:5]

async def generate_scene(
    prompt: str,
    user_id: int,
    user_settings: Dict[str, Any],
    system_prompt: str = "",
    max_tokens: int = 2048,
    stream: bool = False
) -> str:
    """Generate a story scene with optional streaming"""
    
    # Get database session for prompt lookup
    db = next(get_db())
    
    try:
        # Use dynamic prompt if no system_prompt provided
        if not system_prompt:
            system_prompt = prompt_manager.get_prompt(
                template_key="scene_generation",
                prompt_type="system",
                user_id=user_id,
                db=db
            )
        
        # Get max tokens for this template if using default
        if max_tokens == 2048:  # Default value
            max_tokens = prompt_manager.get_max_tokens("scene_generation")

        return await generate_content(
            prompt=prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            stream=stream
        )
    
    finally:
        db.close()

async def generate_scene_streaming(
    prompt: str,
    user_id: int,
    user_settings: Dict[str, Any],
    system_prompt: str = "",
    max_tokens: int = 2048
):
    """Generate a story scene with streaming response"""
    
    if not system_prompt:
        system_prompt = """You are a skilled interactive fiction writer. Create engaging, immersive story scenes that:
1. Advance the plot meaningfully
2. Develop characters through action and dialogue
3. Maintain consistency with established story elements
4. Create compelling choices for the reader
5. Use vivid, descriptive language that draws readers in
6. Keep appropriate pacing for the story moment

Write in second person ("you") to maintain reader immersion."""

    async for chunk in generate_content_stream(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt=system_prompt,
        max_tokens=max_tokens
    ):
        yield chunk

async def regenerate_scene_variant(
    original_scene: str,
    context: Dict[str, Any],
    user_id: int,
    user_settings: Dict[str, Any],
    stream: bool = False
) -> str:
    """Generate a scene variant based on original scene and context"""
    
    # Get database session for prompt lookup
    db = next(get_db())
    
    try:
        # Get dynamic prompts (user custom or default)
        system_prompt = prompt_manager.get_prompt(
            template_key="scene_variants",
            prompt_type="system",
            user_id=user_id,
            db=db
        )
        
        # Build context string for template variables
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
            
        if context.get("characters"):
            char_list = [char.get('name', 'Unknown') for char in context.get('characters', [])]
            if char_list:
                context_parts.append(f"Characters: {', '.join(char_list)}")
        
        if context.get("current_situation"):
            context_parts.append(f"Current situation: {context['current_situation']}")
        
        context_str = "\n".join(context_parts)
        
        # Get user prompt with template variables
        user_prompt = prompt_manager.get_prompt(
            template_key="scene_variants",
            prompt_type="user",
            user_id=user_id,
            db=db,
            original_scene=original_scene,
            context=context_str
        )
        
        # Get max tokens for this template
        max_tokens = prompt_manager.get_max_tokens("scene_variants")

        return await generate_content(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            stream=stream
        )
    
    finally:
        db.close()

async def generate_story_chapter(
    context: Dict[str, Any],
    user_id: int,
    user_settings: Dict[str, Any],
    chapter_count: int = 5,
    stream: bool = False
) -> str:
    """Generate a story chapter structure"""
    
    # Get database session for prompt lookup
    db = next(get_db())
    
    try:
        # Get dynamic prompts (user custom or default)
        system_prompt = prompt_manager.get_prompt(
            template_key="story_chapters",
            prompt_type="system",
            user_id=user_id,
            db=db
        )
        
        # Build context string for template variables
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
            
        if context.get("characters"):
            char_descriptions = []
            for char in context.get('characters', []):
                char_info = f"• {char.get('name', 'Unknown')}"
                if char.get('role'):
                    char_info += f" ({char['role']})"
                if char.get('description'):
                    char_info += f": {char['description']}"
                char_descriptions.append(char_info)
            context_parts.append(f"Main Characters:\n{chr(10).join(char_descriptions)}")
            
        if context.get("scenario"):
            context_parts.append(f"Story Scenario:\n{context['scenario']}")
            
        if context.get("world_setting"):
            context_parts.append(f"World Setting:\n{context['world_setting']}")

        context_str = "\n".join(context_parts)
        
        # Get user prompt with template variables
        user_prompt = prompt_manager.get_prompt(
            template_key="story_chapters",
            prompt_type="user",
            user_id=user_id,
            db=db,
            context=context_str,
            chapter_count=chapter_count
        )
        
        # Get max tokens for this template
        max_tokens = prompt_manager.get_max_tokens("story_chapters")

        return await generate_content(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            stream=stream
        )
    
    finally:
        db.close()

# Function to invalidate user cache when settings change
def invalidate_user_llm_cache(user_id: int):
    """Call this when user updates their LLM settings"""
    unified_llm_service.invalidate_user_client(user_id)
    logger.info(f"Invalidated LLM cache for user {user_id}")

# Additional convenience functions for backward compatibility
async def generate_complete_plot(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], stream: bool = False) -> List[str]:
    """Generate a complete 5-point plot structure based on characters and scenario"""
    
    # Get database session for prompt lookup
    db = next(get_db())
    
    try:
        # Get dynamic prompts (user custom or default)
        system_prompt = prompt_manager.get_prompt(
            template_key="complete_plot",
            prompt_type="system",
            user_id=user_id,
            db=db
        )
        
        # Build context prompt
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
            
        # Character information
        characters = context.get("characters", [])
        if characters:
            char_descriptions = []
            for char in characters:
                char_info = f"• {char.get('name', 'Unknown')}"
                if char.get('role'):
                    char_info += f" ({char['role']})"
                if char.get('description'):
                    char_info += f": {char['description']}"
                char_descriptions.append(char_info)
            context_parts.append(f"Main Characters:\n{chr(10).join(char_descriptions)}")
            
        # Story scenario
        if context.get("scenario"):
            context_parts.append(f"Story Scenario:\n{context['scenario']}")
            
        # World setting
        if context.get("world_setting"):
            context_parts.append(f"World Setting:\n{context['world_setting']}")

        context_str = chr(10).join(context_parts)
        
        # Get user prompt with template variables
        user_prompt = prompt_manager.get_prompt(
            template_key="complete_plot",
            prompt_type="user",
            user_id=user_id,
            db=db,
            context=context_str
        )
        
        # Get max tokens for this template
        max_tokens = prompt_manager.get_max_tokens("complete_plot")

        response = await generate_content(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            stream=stream
        )
    
    finally:
        db.close()
    
    # Parse plot points from response
    import re
    
    # Clean up the response and look for plot points
    lines = response.split('\n')
    plot_points = []
    current_point = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Look for plot point markers (numbers, bullets, or keywords)
        if (re.match(r'^[\d\.\-\*\•]\s*', line) or 
            re.search(r'\*\*(Opening Hook|Inciting Incident|Rising Action|Climax|Resolution)\*\*', line, re.IGNORECASE)):
            
            # Save previous point if exists
            if current_point:
                # Clean the point
                clean_point = current_point.strip()
                # Remove leading markers and formatting
                clean_point = re.sub(r'^[\d\.\-\*\•\s]*', '', clean_point)
                clean_point = re.sub(r'^\*\*(Opening Hook|Inciting Incident|Rising Action|Climax|Resolution)\*\*:\s*', '', clean_point, flags=re.IGNORECASE)
                clean_point = re.sub(r'^(Opening Hook|Inciting Incident|Rising Action|Climax|Resolution):\s*', '', clean_point, flags=re.IGNORECASE)
                if clean_point and len(clean_point) > 20:  # Ensure it's substantial content
                    plot_points.append(clean_point)
            
            current_point = line
        else:
            # Continuation of current point
            if current_point:
                current_point += " " + line
    
    # Don't forget the last point
    if current_point:
        clean_point = current_point.strip()
        clean_point = re.sub(r'^[\d\.\-\*\•\s]*', '', clean_point)
        clean_point = re.sub(r'^\*\*(Opening Hook|Inciting Incident|Rising Action|Climax|Resolution)\*\*:\s*', '', clean_point, flags=re.IGNORECASE)
        clean_point = re.sub(r'^(Opening Hook|Inciting Incident|Rising Action|Climax|Resolution):\s*', '', clean_point, flags=re.IGNORECASE)
        if clean_point and len(clean_point) > 20:
            plot_points.append(clean_point)
    
    # Ensure we have exactly 5 plot points
    if len(plot_points) < 5:
        fallback_points = [
            "The story begins with an intriguing hook that draws readers in.",
            "A pivotal event changes everything and sets the main conflict in motion.",
            "Challenges and obstacles test the characters' resolve and growth.",
            "The climax brings all conflicts to a head in an intense confrontation.",
            "The resolution ties up loose ends and shows character transformation."
        ]
        plot_points.extend(fallback_points[len(plot_points):])
    
    return plot_points[:5]

async def generate_single_plot_point(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], stream: bool = False) -> str:
    """Generate a single plot point based on characters and scenario"""
    
    # Get database session for prompt lookup
    db = next(get_db())
    
    try:
        plot_point_names = [
            "Opening Hook", "Inciting Incident", "Rising Action", "Climax", "Resolution"
        ]
        
        index = context.get("plot_point_index", 0)
        point_name = plot_point_names[min(index, len(plot_point_names)-1)]
        
        # Get dynamic prompts (user custom or default)
        system_prompt = prompt_manager.get_prompt(
            template_key="single_plot_point",
            prompt_type="system",
            user_id=user_id,
            db=db,
            point_name=point_name
        )
        
        # Build context prompt
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
            
        # Character information
        characters = context.get("characters", [])
        if characters:
            char_descriptions = []
            for char in characters:
                char_info = f"• {char.get('name', 'Unknown')}"
                if char.get('role'):
                    char_info += f" ({char['role']})"
                if char.get('description'):
                    char_info += f": {char['description']}"
                char_descriptions.append(char_info)
            context_parts.append(f"Main Characters:\n{chr(10).join(char_descriptions)}")
            
        # Story scenario
        if context.get("scenario"):
            context_parts.append(f"Story Scenario:\n{context['scenario']}")
            
        # World setting
        if context.get("world_setting"):
            context_parts.append(f"World Setting:\n{context['world_setting']}")

        context_str = chr(10).join(context_parts)
        
        # Get user prompt with template variables
        user_prompt = prompt_manager.get_prompt(
            template_key="single_plot_point",
            prompt_type="user",
            user_id=user_id,
            db=db,
            context=context_str,
            point_name=point_name
        )
        
        # Get max tokens for this template
        max_tokens = prompt_manager.get_max_tokens("single_plot_point")

        return await generate_content(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            stream=stream
        )
    
    finally:
        db.close()

async def generate_choices(scene_content: str, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], stream: bool = False) -> List[str]:
    """Generate choices for a scene"""
    
    # Get database session for prompt lookup
    db = next(get_db())
    
    try:
        # Get dynamic prompts (user custom or default)
        system_prompt = prompt_manager.get_prompt(
            template_key="choice_generation",
            prompt_type="system",
            user_id=user_id,
            db=db
        )
        
        # Build context for choices
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
            
        if context.get("characters"):
            char_list = [char.get('name', 'Unknown') for char in context.get('characters', [])]
            if char_list:
                context_parts.append(f"Characters involved: {', '.join(char_list)}")
        
        if context.get("current_situation"):
            context_parts.append(f"Current situation: {context['current_situation']}")

        context_str = chr(10).join(context_parts)
        
        # Get user prompt with template variables
        user_prompt = prompt_manager.get_prompt(
            template_key="choice_generation",
            prompt_type="user",
            user_id=user_id,
            db=db,
            scene_content=scene_content[-800:],  # Last 800 chars to avoid token limits
            context=context_str
        )
        
        # Get max tokens for this template
        max_tokens = prompt_manager.get_max_tokens("choice_generation")
        
        response = await generate_content(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            stream=stream
        )
    
    finally:
        db.close()
    
    # Parse choices from response
    choices = []
    lines = response.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Look for numbered choices
        import re
        if re.match(r'^[\d\.\-\*]\s*', line):
            # Clean the choice text
            choice_text = re.sub(r'^[\d\.\-\*]\s*', '', line).strip()
            if choice_text and len(choice_text) > 10:  # Ensure substantial content
                choices.append(choice_text)
    
    # Ensure we have at least some choices
    if len(choices) < 2:
        choices = [
            "Continue forward cautiously",
            "Take a different approach", 
            "Investigate further",
            "Make a bold decision"
        ]
    
    return choices[:4]  # Return up to 4 choices

async def generate_scene_continuation(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any], stream: bool = False) -> str:
    """Generate a scene continuation based on context"""
    
    # Get database session for prompt lookup
    db = next(get_db())
    
    try:
        # Get dynamic prompts (user custom or default)
        system_prompt = prompt_manager.get_prompt(
            template_key="scene_continuation",
            prompt_type="system",
            user_id=user_id,
            db=db
        )
        
        # Build context for continuation
        context_parts = []
        
        if context.get("genre"):
            context_parts.append(f"Genre: {context['genre']}")
        
        if context.get("tone"):
            context_parts.append(f"Tone: {context['tone']}")
            
        if context.get("previous_content"):
            context_parts.append(f"Previous content: {context['previous_content'][-600:]}")  # Last 600 chars
            
        if context.get("choice_made"):
            context_parts.append(f"Reader's choice: {context['choice_made']}")
            
        if context.get("current_situation"):
            context_parts.append(f"Current situation: {context['current_situation']}")

        context_str = chr(10).join(context_parts)
        
        # Get user prompt with template variables
        user_prompt = prompt_manager.get_prompt(
            template_key="scene_continuation",
            prompt_type="user",
            user_id=user_id,
            db=db,
            context=context_str
        )
        
        # Get max tokens for this template
        max_tokens = prompt_manager.get_max_tokens("scene_continuation")

        return await generate_content(
            prompt=user_prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            stream=stream
        )
    
    finally:
        db.close()

async def generate_scene_continuation_streaming(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]):
    """Generate a scene continuation with streaming response"""
    
    system_prompt = """You are a skilled creative writer continuing an interactive story. Your task is to:
1. Continue the narrative naturally from where it left off
2. Maintain consistency with established characters and plot
3. Advance the story while respecting the chosen direction
4. Create engaging content that draws the reader in
5. Write in a style consistent with the existing story

Keep the continuation focused and purposeful, advancing the plot meaningfully."""

    # Build context for continuation
    context_parts = []
    
    if context.get("genre"):
        context_parts.append(f"Genre: {context['genre']}")
    
    if context.get("tone"):
        context_parts.append(f"Tone: {context['tone']}")
        
    if context.get("previous_content"):
        context_parts.append(f"Previous content: {context['previous_content'][-600:]}")  # Last 600 chars
        
    if context.get("choice_made"):
        context_parts.append(f"Reader's choice: {context['choice_made']}")
        
    if context.get("current_situation"):
        context_parts.append(f"Current situation: {context['current_situation']}")

    prompt = f"""Continue this story naturally:

{chr(10).join(context_parts)}

Write a compelling continuation that follows from the established context and any reader choices. Focus on moving the story forward with engaging narrative and dialogue."""

    async for chunk in generate_content_stream(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt=system_prompt,
        max_tokens=400
    ):
        yield chunk
