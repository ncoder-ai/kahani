"""
Database model for configurable prompt templates
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database import Base

class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Template identification
    template_key = Column(String(100), nullable=False, index=True)  # e.g., "scene_generation", "story_summary"
    name = Column(String(200), nullable=False)  # Human-readable name
    description = Column(Text)  # What this prompt does
    category = Column(String(50), nullable=False)  # e.g., "generation", "analysis", "choices"
    
    # Prompt content
    system_prompt = Column(Text, nullable=False)
    user_prompt_template = Column(Text)  # Template with placeholders like {story_content}
    
    # Settings
    is_default = Column(Boolean, default=False)  # Is this a default system template
    is_active = Column(Boolean, default=True)    # Is this template currently active
    max_tokens = Column(Integer, default=2048)   # Recommended max tokens for this prompt
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="prompt_templates")
    
    def to_dict(self):
        return {
            "id": self.id,
            "template_key": self.template_key,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "system_prompt": self.system_prompt,
            "user_prompt_template": self.user_prompt_template,
            "is_default": self.is_default,
            "is_active": self.is_active,
            "max_tokens": self.max_tokens,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    @classmethod
    def get_default_templates(cls):
        """Return default prompt templates"""
        return [
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
            },
            {
                "template_key": "title_generation",
                "name": "Title Generation",
                "description": "Generate compelling story titles",
                "category": "generation", 
                "system_prompt": """You are a creative title generator for interactive stories. Generate 5 compelling story titles that:

1. Capture the essence and mood of the story
2. Are intriguing and memorable
3. Fit the specified genre and tone
4. Are neither too vague nor too specific
5. Have commercial appeal
6. Avoid clichés when possible
7. Are suitable for the target audience

Provide titles only, one per line.""",
                "user_prompt_template": """Generate 5 compelling titles for this story concept:

Genre: {genre}
Tone: {tone}  
Theme: {theme}
Setting: {setting}
Key elements: {key_elements}

Story concept: {concept}""",
                "max_tokens": 150
            }
        ]