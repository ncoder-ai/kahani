#!/usr/bin/env python3
"""
Test script for event extraction prompt.
Run this to see how the new stricter prompt performs.
"""
import asyncio
import json
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import httpx


# Load the prompts - handle both host and container paths
import yaml
prompts_paths = ['backend/prompts.yml', 'prompts.yml', '/app/prompts.yml']
prompts = None
for prompts_path in prompts_paths:
    try:
        with open(prompts_path, 'r') as f:
            prompts = yaml.safe_load(f)
            break
    except FileNotFoundError:
        continue

if not prompts:
    raise FileNotFoundError(f"Could not find prompts.yml in any of: {prompts_paths}")

# Database connection - using the postgres container
# In container: postgres hostname; On host: localhost
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://kahani:kahani@postgres:5432/kahani")

# Extraction model settings (adjust as needed)
EXTRACTION_URL = os.environ.get("EXTRACTION_URL", "http://172.16.23.80:5001/v1")
EXTRACTION_MODEL = "openai/behemothx"


def get_event_extraction_prompt():
    """Get the event extraction prompts."""
    system = prompts['chapter_progress']['event_extraction']['system']
    user = prompts['chapter_progress']['event_extraction']['user']
    return system, user


async def call_llm(system_prompt: str, user_prompt: str) -> str:
    """Call the LLM API."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{EXTRACTION_URL}/chat/completions",
            json={
                "model": EXTRACTION_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 1000
            }
        )
        response.raise_for_status()
        data = response.json()
        return data['choices'][0]['message']['content']


def clean_json(json_str: str) -> str:
    """Clean common LLM JSON formatting issues."""
    json_str = json_str.strip()
    if json_str.startswith("```json"):
        json_str = json_str[7:]
    if json_str.startswith("```"):
        json_str = json_str[3:]
    if json_str.endswith("```"):
        json_str = json_str[:-3]
    return json_str.strip()


async def test_event_extraction():
    """Test event extraction on recent scenes."""
    
    # Connect to database
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Get the last 10 scenes from story 5 (chapter 24)
        scenes_query = text("""
            SELECT s.id, s.chapter_id, sv.content 
            FROM scenes s 
            JOIN scene_variants sv ON s.id = sv.scene_id 
            WHERE s.story_id = 5 
              AND s.is_deleted = false 
              AND sv.is_original = true
            ORDER BY s.id DESC 
            LIMIT 10
        """)
        scenes = session.execute(scenes_query).fetchall()
        
        # Get chapter 24 key_events
        chapter_query = text("""
            SELECT id, chapter_number, chapter_plot, plot_progress 
            FROM chapters 
            WHERE story_id = 5 AND chapter_number = 5
        """)
        chapter = session.execute(chapter_query).fetchone()
        
        if not chapter:
            print("Chapter 24 not found!")
            return
        
        chapter_plot = chapter.chapter_plot
        key_events = chapter_plot.get('key_events', [])
        completed_events = chapter.plot_progress.get('completed_events', []) if chapter.plot_progress else []
        
        print("=" * 80)
        print("KEY EVENTS FOR CHAPTER:")
        print("=" * 80)
        for i, event in enumerate(key_events, 1):
            status = "✓ COMPLETED" if event in completed_events else "○ PENDING"
            print(f"{i}. [{status}] {event}")
        
        print("\n" + "=" * 80)
        print(f"TESTING EVENT EXTRACTION ON {len(scenes)} SCENES")
        print("=" * 80)
        
        # Get prompt templates
        system_prompt, user_template = get_event_extraction_prompt()
        
        print("\n--- SYSTEM PROMPT ---")
        print(system_prompt)
        print("--- END SYSTEM PROMPT ---\n")
        
        for scene in scenes:
            scene_id = scene.id
            scene_content = scene.content
            
            # Skip if scene content is too short
            if not scene_content or len(scene_content) < 100:
                continue
            
            print(f"\n{'='*80}")
            print(f"SCENE {scene_id} (Chapter {scene.chapter_id})")
            print("="*80)
            print(f"Content Preview: {scene_content[:300]}...")
            print("-"*40)
            
            # Format user prompt
            user_prompt = user_template.format(
                scene_content=scene_content,
                key_events=json.dumps(key_events, indent=2)
            )
            
            # Call LLM
            try:
                response = await call_llm(system_prompt, user_prompt)
                print(f"\nLLM Response:")
                print(response)
                
                # Parse response
                try:
                    cleaned = clean_json(response)
                    completed = json.loads(cleaned)
                    if isinstance(completed, list) and completed:
                        print(f"\n✓ EVENTS DETECTED: {len(completed)}")
                        for event in completed:
                            print(f"  - {event[:80]}...")
                    else:
                        print(f"\n○ NO EVENTS DETECTED")
                except json.JSONDecodeError as e:
                    print(f"\n✗ JSON Parse Error: {e}")
            except Exception as e:
                print(f"\n✗ LLM Error: {e}")
            
            print("-"*80)
    
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(test_event_extraction())

