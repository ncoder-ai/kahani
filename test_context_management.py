"""
Test script to demonstrate context management for long stories
"""

import asyncio
import sys
import os
sys.path.append('/Users/nishant/apps/kahani/backend')

from app.services.context_manager import ContextManager
from app.models.scene import Scene

async def test_context_management():
    """Test context management with a simulated long story"""
    
    context_manager = ContextManager()
    
    # Simulate a long story with many scenes
    mock_scenes = []
    
    scene_contents = [
        "The hero begins their journey in the small village of Millbrook, where rumors of a dark sorcerer spread fear among the townspeople.",
        "Setting out at dawn, our protagonist encounters a mysterious stranger who offers cryptic warnings about the path ahead.",
        "The first challenge appears: a bridge guarded by a troll who demands payment in riddles rather than gold.",
        "After solving the troll's riddles, the hero discovers an ancient map hidden beneath the bridge, revealing secret passages.",
        "The map leads to the Whispering Woods, where the trees themselves seem to murmur warnings of danger.",
        "In the heart of the forest, a wise hermit provides magical items and crucial information about the sorcerer's weakness.",
        "The journey continues to the Crystal Caves, where the hero must face their deepest fears made manifest.",
        "Inside the caves, a powerful crystal reveals visions of the past, showing how the sorcerer gained his dark powers.",
        "The hero emerges stronger, bearing a crystal fragment that will be essential in the final confrontation.",
        "Approaching the sorcerer's tower, the landscape itself seems twisted by dark magic, with reality bending in impossible ways.",
        "The tower's guardians are defeated through wit rather than strength, using lessons learned throughout the journey.",
        "Inside the tower, the hero discovers the sorcerer was once a defender of the realm, corrupted by good intentions gone wrong.",
        "The final battle is not one of swords but of understanding, as the hero must find a way to redeem rather than destroy.",
        "Using the crystal fragment and wisdom gained, the hero manages to purify the corruption, saving both sorcerer and realm.",
        "The story concludes with the hero returning to Millbrook, forever changed by their journey and ready for new adventures."
    ]
    
    for i, content in enumerate(scene_contents):
        scene = Scene()
        scene.sequence_number = i + 1
        scene.content = content
        mock_scenes.append(scene)
    
    print(f"Testing with {len(mock_scenes)} scenes")
    print(f"Max tokens: {context_manager.max_tokens}")
    print()
    
    # Test context building at different story lengths
    test_lengths = [3, 5, 8, 12, 15]
    
    for length in test_lengths:
        if length <= len(mock_scenes):
            print(f"=== Testing with {length} scenes ===")
            
            test_scenes = mock_scenes[:length]
            available_tokens = context_manager.max_tokens - 1000  # Reserve for other context
            
            scene_context = await context_manager._build_scene_context(test_scenes, available_tokens)
            
            print(f"Scene summary: {scene_context.get('scene_summary', 'None')}")
            print(f"Total scenes in context: {scene_context.get('total_scenes', 0)}")
            
            # Count tokens in the context
            prev_scenes = scene_context.get('previous_scenes', '')
            recent_scenes = scene_context.get('recent_scenes', '')
            
            prev_tokens = context_manager.count_tokens(prev_scenes)
            recent_tokens = context_manager.count_tokens(recent_scenes)
            total_context_tokens = prev_tokens + recent_tokens
            
            print(f"Previous scenes tokens: {prev_tokens}")
            print(f"Recent scenes tokens: {recent_tokens}")
            print(f"Total context tokens: {total_context_tokens}")
            print(f"Fits in budget: {total_context_tokens <= available_tokens}")
            
            if length >= 8:  # Show sample of context for longer stories
                print("\nSample context (first 200 chars):")
                print(f"Previous: {prev_scenes[:200]}...")
                print(f"Recent: {recent_scenes[:200]}...")
            
            print()

if __name__ == "__main__":
    asyncio.run(test_context_management())