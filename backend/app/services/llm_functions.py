"""
High-level LLM functions using the improved service
These functions provide the same interface as your current code
but use efficient client management under the hood
"""

from typing import Dict, Any, List
from .improved_llm_service import improved_llm_service
import logging

logger = logging.getLogger(__name__)

async def _collect_streaming_response(stream_generator):
    """Helper function to collect streaming chunks into complete text"""
    complete_text = ""
    async for chunk in stream_generator:
        if chunk:
            complete_text += chunk
    return complete_text

async def generate_scenario(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
    """Generate a story scenario based on characters and context"""
    
    system_prompt = """You are a creative storytelling assistant. Generate an engaging story scenario that:
1. Incorporates the provided characters as central figures
2. Creates meaningful personal stakes for each character
3. Establishes relationships and conflicts between characters
4. Matches the specified genre and tone
5. Weaves together the story elements into a cohesive setup
6. Is 3-5 sentences long and creates a compelling hook
7. Sets up dramatic tension that involves the characters' goals and relationships

Write in an engaging narrative style that makes readers care about what happens to these specific characters."""

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
        context_parts.append(f"Main Characters:\\n{chr(10).join(char_descriptions)}")
        
    # Story elements
    elements = []
    if context.get("opening"):
        elements.append(f"Story opening: {context['opening']}")
    if context.get("setting"):
        elements.append(f"Setting: {context['setting']}")
    if context.get("conflict"):
        elements.append(f"Driving force: {context['conflict']}")
        
    prompt = f"""Please create a scenario based on these elements:

{chr(10).join(context_parts)}

Story elements to incorporate:
{chr(10).join(elements)}

Generate a creative scenario that:
- Places these specific characters at the center of the story
- Creates personal stakes and meaningful relationships between them
- Incorporates the story elements naturally
- Sets up compelling dramatic tension that makes readers invested in these characters' journey

Scenario:"""

    return await improved_llm_service.generate(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt=system_prompt,
        max_tokens=400
    )

async def generate_titles(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> List[str]:
    """Generate creative story titles based on story content"""
    
    system_prompt = """You are a creative title generator for interactive stories. Generate 5 compelling story titles that:
1. Capture the essence of the story scenario and characters
2. Match the specified genre and tone perfectly
3. Are memorable and intriguing
4. Reflect the key themes, conflicts, or character relationships
5. Range from 2-6 words each
6. Avoid clichés and generic phrases
7. Create emotional hooks that make readers want to explore the story

Provide ONLY the 5 titles, one per line, without numbers or additional text."""

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
        context_parts.append(f"Main Characters:\\n{chr(10).join(char_descriptions)}")
        
    # Story scenario
    if context.get("scenario"):
        context_parts.append(f"Story Scenario:\\n{context['scenario']}")
        
    # Story elements
    story_elements = context.get("story_elements", {})
    if story_elements:
        elements = []
        for key, value in story_elements.items():
            if value:
                elements.append(f"{key.title()}: {value}")
        if elements:
            context_parts.append(f"Story Elements:\\n{chr(10).join(elements)}")

    prompt = f"""Based on these story details:

{chr(10).join(context_parts)}

Generate 5 compelling titles that capture the heart of this specific story. Focus on the unique characters, their relationships, and the central conflict. Make each title distinctive and emotionally engaging.

Titles:"""

    response = await improved_llm_service.generate(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt=system_prompt,
        max_tokens=150
    )
    
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
    max_tokens: int = 2048
) -> str:
    """Generate a story scene using streaming (workaround for TabbyAPI non-streaming 422 issue)"""
    
    if not system_prompt:
        system_prompt = """You are a skilled interactive fiction writer. Create engaging, immersive story scenes that:
1. Advance the plot meaningfully
2. Develop characters through action and dialogue
3. Maintain consistency with established story elements
4. Create compelling choices for the reader
5. Use vivid, descriptive language that draws readers in
6. Keep appropriate pacing for the story moment

Write in second person ("you") to maintain reader immersion."""

    # Use streaming internally to work around TabbyAPI 422 issues
    stream_generator = improved_llm_service.generate_stream(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt=system_prompt,
        max_tokens=max_tokens
    )
    
    # Collect all streaming chunks into complete response
    return await _collect_streaming_response(stream_generator)

async def generate_scene_streaming(
    prompt: str,
    user_id: int,
    user_settings: Dict[str, Any],
    system_prompt: str = "",
    max_tokens: int = 2048
):
    """Generate a story scene with streaming"""
    
    if not system_prompt:
        system_prompt = """You are a skilled interactive fiction writer. Create engaging, immersive story scenes that:
1. Advance the plot meaningfully
2. Develop characters through action and dialogue
3. Maintain consistency with established story elements
4. Create compelling choices for the reader
5. Use vivid, descriptive language that draws readers in
6. Keep appropriate pacing for the story moment

Write in second person ("you") to maintain reader immersion."""

    async for chunk in improved_llm_service.generate_stream(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt=system_prompt,
        max_tokens=max_tokens
    ):
        yield chunk

# Function to invalidate user cache when settings change
def invalidate_user_llm_cache(user_id: int):
    """Call this when user updates their LLM settings"""
    improved_llm_service.invalidate_user_config(user_id)
    logger.info(f"Invalidated LLM cache for user {user_id}")

async def generate_complete_plot(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> List[str]:
    """Generate a complete 5-point plot structure based on characters and scenario"""
    
    system_prompt = """You are a master storyteller and plot architect. Generate a complete 5-point plot structure that:
1. Is perfectly tailored to the specific characters and their relationships
2. Builds naturally from the established scenario
3. Creates meaningful character arcs and development
4. Escalates tension and stakes progressively
5. Delivers satisfying character-driven resolutions
6. Incorporates the genre and tone seamlessly
7. Creates opportunities for character growth and conflict

Provide exactly 5 plot points in this order:
1. Opening Hook - How the story begins with character-specific elements
2. Inciting Incident - The event that sets everything in motion for THESE characters
3. Rising Action - Character-specific challenges and conflicts
4. Climax - The ultimate confrontation involving these characters' arcs
5. Resolution - How these specific characters' journeys conclude

Write each plot point as 2-3 sentences. Focus on how the plot serves these specific characters' growth and relationships."""

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
        context_parts.append(f"Main Characters:\\n{chr(10).join(char_descriptions)}")
        
    # Story scenario
    if context.get("scenario"):
        context_parts.append(f"Story Scenario:\\n{context['scenario']}")
        
    # World setting
    if context.get("world_setting"):
        context_parts.append(f"World Setting:\\n{context['world_setting']}")

    prompt = f"""Based on these story elements:

{chr(10).join(context_parts)}

Generate a complete 5-point plot structure that weaves these characters' personal journeys into a compelling narrative arc. Each plot point should advance both the external story and the internal character development.

Plot Structure:

1. Opening Hook:
2. Inciting Incident:
3. Rising Action:
4. Climax:
5. Resolution:"""

    response = await improved_llm_service.generate(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt=system_prompt,
        max_tokens=800
    )
    
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

async def generate_single_plot_point(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
    """Generate a single plot point based on characters and scenario"""
    
    plot_point_names = [
        "Opening Hook", "Inciting Incident", "Rising Action", "Climax", "Resolution"
    ]
    
    index = context.get("plot_point_index", 0)
    point_name = plot_point_names[min(index, len(plot_point_names)-1)]
    
    system_prompt = f"""You are a master storyteller. Generate a compelling {point_name} that:
1. Is specifically tailored to the provided characters and their relationships
2. Builds naturally from the established scenario and world
3. Creates meaningful stakes for these specific characters
4. Advances character development and relationships
5. Matches the genre and tone perfectly
6. Sets up future plot developments organically

Write 2-3 sentences that feel like a natural part of this specific story with these specific characters."""

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
        context_parts.append(f"Main Characters:\\n{chr(10).join(char_descriptions)}")
        
    # Story scenario
    if context.get("scenario"):
        context_parts.append(f"Story Scenario:\\n{context['scenario']}")
        
    # World setting
    if context.get("world_setting"):
        context_parts.append(f"World Setting:\\n{context['world_setting']}")

    prompt = f"""Based on these story elements:

{chr(10).join(context_parts)}

Generate a compelling {point_name} that naturally incorporates these characters' personalities, relationships, and the established scenario. Focus on how this plot point specifically serves these characters' journeys and the unique aspects of this story.

{point_name}:"""

    return await improved_llm_service.generate(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt=system_prompt,
        max_tokens=200
    )

async def generate_choices(scene_content: str, context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> List[str]:
    """Generate choices for a scene"""
    
    system_prompt = """You are an interactive fiction choice generator. Create engaging story choices that:
1. Are meaningful and impact the story direction
2. Reflect different character approaches or personalities
3. Offer varied consequences and outcomes
4. Maintain consistency with the established story world
5. Give players agency in how they want to proceed
6. Are concise but descriptive (1-2 sentences each)

Generate exactly 4 choices. Each choice should feel distinct and meaningful."""

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

    prompt = f"""Based on this scene:

{scene_content[-800:]}  # Last 800 chars to avoid token limits

Story Context:
{chr(10).join(context_parts)}

Generate 4 meaningful choices for what happens next. Each choice should:
- Lead to different story outcomes
- Reflect different approaches to the situation
- Be engaging and make the reader want to see what happens

Choices:
1.
2.
3.
4."""

    response = await _collect_streaming_response(
        improved_llm_service.generate_stream(
            prompt=prompt,
            user_id=user_id,
            user_settings=user_settings,
            system_prompt=system_prompt,
            max_tokens=300
        )
    )
    
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

async def generate_scene_continuation(context: Dict[str, Any], user_id: int, user_settings: Dict[str, Any]) -> str:
    """Generate a scene continuation based on context"""
    
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

    return await improved_llm_service.generate(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt=system_prompt,
        max_tokens=400
    )

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

    async for chunk in improved_llm_service.generate_stream(
        prompt=prompt,
        user_id=user_id,
        user_settings=user_settings,
        system_prompt=system_prompt,
        max_tokens=400
    ):
        yield chunk