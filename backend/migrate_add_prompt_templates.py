#!/usr/bin/env python3
"""
Database migration: Add prompt_templates table and default prompts
"""

import sqlite3
import sys
import os
from datetime import datetime

def main():
    print("🔧 Adding prompt_templates table and default prompts...")
    
    # Database path - relative to backend directory
    db_path = "data/kahani.db"
    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        return 1
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prompt_templates'")
        if cursor.fetchone():
            print("prompt_templates table already exists")
        else:
            # Create prompt_templates table
            cursor.execute("""
                CREATE TABLE prompt_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    template_key VARCHAR(100) NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    description TEXT,
                    category VARCHAR(50) NOT NULL,
                    system_prompt TEXT NOT NULL,
                    user_prompt_template TEXT,
                    is_default BOOLEAN DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    max_tokens INTEGER DEFAULT 2048,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            # Create index on template_key
            cursor.execute("CREATE INDEX ix_prompt_templates_template_key ON prompt_templates (template_key)")
            
            print("✅ Created prompt_templates table")
        
        # Get first user ID to assign default templates (or create system user)
        cursor.execute("SELECT id FROM users ORDER BY id LIMIT 1")
        user_row = cursor.fetchone()
        
        if not user_row:
            print("❌ No users found - creating system user for default prompts")
            cursor.execute("""
                INSERT INTO users (email, username, display_name, hashed_password, is_admin)
                VALUES ('system@kahani.ai', 'system', 'System', 'system_hash', 1)
            """)
            system_user_id = cursor.lastrowid
        else:
            system_user_id = user_row[0]
        
        # Default prompt templates
        default_prompts = [
            {
                "template_key": "scene_generation",
                "name": "Scene Generation",
                "description": "Generate new story scenes with narrative continuity",
                "category": "generation",
                "system_prompt": """You are a creative storytelling assistant. Generate engaging narrative scenes that:

1. Maintain narrative consistency and continuity
2. Match the established tone, style, and genre
3. Develop characters naturally and authentically  
4. Create compelling conflict and tension
5. Advance the plot meaningfully
6. Use vivid, immersive descriptions
7. Include realistic dialogue when appropriate
8. End with a natural stopping point or cliffhanger

Keep scenes focused and substantial but not overly long. Write in third person narrative style.""",
                "user_prompt_template": """Story Context:
Title: {title}
Genre: {genre}
Tone: {tone}
Setting: {world_setting}

Previous scenes:
{previous_scenes}

{custom_instruction}

Continue the story naturally from where it left off.""",
                "max_tokens": 2048
            },
            {
                "template_key": "story_summary",
                "name": "Story Summary",
                "description": "Generate comprehensive summaries of story content",
                "category": "analysis",
                "system_prompt": """You are a skilled story analyst and summarizer. Create comprehensive, engaging summaries that:

1. Capture the main plot points and story arc
2. Highlight key character developments and relationships
3. Identify major themes and motifs
4. Describe the setting and atmosphere
5. Note significant conflicts and their resolutions
6. Maintain the story's tone and style in the summary
7. Provide context for where the story currently stands
8. Make it engaging for someone who hasn't read the full story

Write in an engaging, narrative style that makes the reader want to continue the story.""",
                "user_prompt_template": """Please provide a comprehensive summary of this story:

Title: {title}
Genre: {genre}
Total Scenes: {scene_count}

Story Content:
{story_content}

Create a detailed summary that captures the essence of the story, key plot points, character development, and current situation.""",
                "max_tokens": 1000
            },
            {
                "template_key": "choice_generation",
                "name": "Choice Generation", 
                "description": "Generate narrative choices for interactive storytelling",
                "category": "generation",
                "system_prompt": """You are a creative storytelling assistant. Generate exactly 4 compelling narrative choices that:

1. Offer meaningfully different story directions
2. Match the current scene's tone and context
3. Present both safe and risky options
4. Include character-driven and action-driven choices
5. Avoid repetitive or similar options
6. Create interesting consequences and opportunities
7. Maintain story consistency and logic
8. Give the reader agency in the narrative

Each choice should be 1-2 sentences and clearly distinct from the others.""",
                "user_prompt_template": """Current scene context:
{scene_content}

Generate 4 distinct narrative choices for what happens next.""",
                "max_tokens": 500
            }
        ]
        
        # Insert default prompts if they don't exist
        for prompt in default_prompts:
            cursor.execute("""
                SELECT COUNT(*) FROM prompt_templates 
                WHERE template_key = ? AND is_default = 1
            """, (prompt["template_key"],))
            
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO prompt_templates (
                        user_id, template_key, name, description, category,
                        system_prompt, user_prompt_template, is_default, 
                        is_active, max_tokens
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?)
                """, (
                    system_user_id,
                    prompt["template_key"],
                    prompt["name"],
                    prompt["description"],
                    prompt["category"],
                    prompt["system_prompt"],
                    prompt["user_prompt_template"],
                    prompt["max_tokens"]
                ))
                print(f"✅ Added default prompt: {prompt['name']}")
        
        conn.commit()
        conn.close()
        
        print("\n✅ Migration completed successfully!")
        print("\nNew prompt templates added:")
        print("- Scene Generation: For generating new story scenes")
        print("- Story Summary: For creating comprehensive story summaries")
        print("- Choice Generation: For generating narrative choices")
        
        return 0
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return 1

if __name__ == "__main__":
    sys.exit(main())