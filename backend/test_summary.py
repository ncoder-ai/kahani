import asyncio
import sys
sys.path.insert(0, '/Users/nishant/apps/kahani/backend')

from app.services.llm.service import UnifiedLLMService
from app.services.llm.prompts import prompt_manager

async def test_summary():
    # Your scene content
    scene_content = """You quickened your pace as you descended into the heart of the ancient forest, the weight of the task ahead bearing down upon you like a physical force. The trees loomed closer, their branches grasping for you like skeletal fingers, but you pressed on, driven by the knowledge that time was running out.

The air grew thick with an otherworldly energy as you approached the clearing where the ritual was to take place. You could feel it coursing through your veins, urging you forward. The moon hung low in the sky, its pale light casting eerie shadows across the forest floor.

You stepped into the circle of stones, the center of which pulsed with an intense, blue-white light. Before you stood the sorcerer, his eyes blazing with an unnatural intensity as he began to chant. The air around him shimmered and rippled, like the surface of a pond disturbed by a thrown stone.

*This has to work*, you thought, your mind racing with the possibilities if the ritual failed. You raised your hands, feeling the familiar tingle of magic building within you. With a surge of power, you joined the sorcerer's incantation, the combined energy of your voices and wills sending a blast of magical force hurtling towards the sky.

The outcome hung in the balance as the world around you began to change, the very fabric of reality trembling under the pressure of what you had unleashed. Time seemed to slow, allowing you a fleeting glimpse of what might be on the horizon before the consequences of your actions took hold."""

    combined_text = f"Scene 1: Ritual in the Forest\n{scene_content}"
    
    story_context = "Title: Test Story, Genre: Fantasy, Total Scenes: 1"
    
    # Get prompts
    system_prompt = prompt_manager.get_prompt(
        template_key="story_summary",
        prompt_type="system",
        user_id=None,
        db=None
    )
    
    user_prompt = prompt_manager.get_prompt(
        template_key="story_summary",
        prompt_type="user",
        user_id=None,
        db=None,
        story_content=combined_text,
        story_context=story_context
    )
    
    max_tokens = prompt_manager.get_max_tokens("story_summary")
    
    print("="*80)
    print("SYSTEM PROMPT:")
    print("="*80)
    print(system_prompt)
    print("\n" + "="*80)
    print("USER PROMPT:")
    print("="*80)
    print(user_prompt)
    print("\n" + "="*80)
    print(f"MAX TOKENS: {max_tokens}")
    print("="*80)
    
    # Generate summary
    llm_service = UnifiedLLMService()
    
    user_settings = {
        "api_type": "lm_studio",
        "api_url": "http://localhost:1234/v1",
        "api_key": "lm-studio",
        "model_name": "qwen2.5-14b-instruct",
        "max_tokens": 2048,
        "temperature": 0.7,
        "top_p": 0.9
    }
    
    print("\nGenerating summary...")
    summary = await llm_service.generate(
        prompt=user_prompt,
        user_id=1,
        user_settings=user_settings,
        system_prompt=system_prompt,
        max_tokens=max_tokens
    )
    
    print("\n" + "="*80)
    print("GENERATED SUMMARY:")
    print("="*80)
    print(summary)
    print("="*80)

if __name__ == "__main__":
    asyncio.run(test_summary())
