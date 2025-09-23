# Kahani User Settings System

## Overview

The Kahani user settings system allows users to customize their storytelling experience by configuring LLM parameters, context management, generation preferences, and UI options.

## Features

### 🤖 LLM Settings
- **Temperature** (0.0 - 2.0): Controls creativity vs focus
- **Top P** (0.0 - 1.0): Nucleus sampling for word diversity
- **Top K** (1 - 100): Limits vocabulary to top K words
- **Repetition Penalty** (1.0 - 2.0): Reduces repetitive text
- **Max Tokens** (100 - 4096): Maximum tokens per generation

### 🧠 Context Management
- **Context Budget** (1000 - 8000 tokens): Total context sent to LLM
- **Keep Recent Scenes**: Always preserve N recent scenes
- **Summary Threshold**: Start summarizing after N scenes
- **Enable Summarization**: Smart context compression for long stories

### ✨ Generation Preferences
- **Default Genre**: Pre-fill genre for new stories
- **Default Tone**: Pre-fill tone for new stories  
- **Scene Length**: Short/Medium/Long scene preferences
- **Auto Choices**: Automatically generate choices after scenes
- **Choices Count** (2-6): Number of choices to generate

### 🎨 Interface Preferences
- **Theme**: Dark/Light/Auto theme selection
- **Font Size**: Small/Medium/Large text sizing
- **Show Token Info**: Display token usage information
- **Show Context Info**: Show context management details
- **Notifications**: Enable/disable system notifications

## Quick Setup Presets

### Creative Writer
- High temperature (1.2)
- High top-p (0.95)
- Lower repetition penalty (1.05)
- Emphasizes creativity and variety

### Focused Storyteller  
- Low temperature (0.4)
- Lower top-p (0.8)
- Higher top-k (40)
- Emphasizes consistency and coherence

### Balanced Author
- Medium temperature (0.7)
- Balanced parameters
- Good for general storytelling

### Experimental
- High temperature (1.5)
- Very high top-p (1.0)
- Low top-k (20)
- For unpredictable, experimental narratives

## Technical Implementation

### Backend Architecture

```
/api/v1/settings/
├── GET     - Retrieve user settings
├── PUT     - Update user settings
├── POST    - Reset to defaults
└── /presets
    └── GET - Get available presets
```

### Database Schema

```sql
-- UserSettings table
CREATE TABLE user_settings (
    id INTEGER PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES users(id),
    
    -- LLM Settings
    llm_temperature REAL DEFAULT 0.7,
    llm_top_p REAL DEFAULT 1.0,
    llm_top_k INTEGER DEFAULT 50,
    llm_repetition_penalty REAL DEFAULT 1.1,
    llm_max_tokens INTEGER DEFAULT 2048,
    
    -- Context Management
    context_max_tokens INTEGER DEFAULT 4000,
    context_keep_recent_scenes INTEGER DEFAULT 3,
    context_summary_threshold INTEGER DEFAULT 10,
    context_enable_summarization BOOLEAN DEFAULT true,
    
    -- Generation Preferences
    generation_default_genre VARCHAR(100),
    generation_default_tone VARCHAR(100),
    generation_scene_length VARCHAR(20) DEFAULT 'medium',
    generation_auto_choices BOOLEAN DEFAULT false,
    generation_choices_count INTEGER DEFAULT 3,
    
    -- UI Preferences
    ui_theme VARCHAR(20) DEFAULT 'dark',
    ui_font_size VARCHAR(20) DEFAULT 'medium',
    ui_show_token_info BOOLEAN DEFAULT false,
    ui_show_context_info BOOLEAN DEFAULT false,
    ui_notifications BOOLEAN DEFAULT true,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Integration Points

1. **Context Manager Integration**
   - Uses user's context budget and summarization preferences
   - Respects keep_recent_scenes setting
   - Applies summary_threshold configuration

2. **LLM Service Integration**
   - Passes user's temperature, top_p, top_k, repetition_penalty to LM Studio
   - Uses user's max_tokens setting for generation limits
   - Applies user preferences in all generation calls

3. **Story Generation Integration**
   - Scene generation uses user's LLM settings
   - Choice generation respects auto_choices and choices_count
   - Context management uses user's budget and thresholds

## Frontend Components

### Settings Page (`/settings`)
- Tabbed interface for different setting categories
- Real-time preview of current settings
- Quick preset application
- Save/Reset functionality

### API Integration
```typescript
// Get user settings
const response = await fetch('/api/settings/', {
  headers: { 'Authorization': `Bearer ${token}` }
});

// Update settings
await fetch('/api/settings/', {
  method: 'PUT',
  headers: { 
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}` 
  },
  body: JSON.stringify(settings)
});
```

## Usage Examples

### 1. Setting up Creative Writing
```python
# User sets high creativity parameters
settings = {
    "llm_settings": {
        "temperature": 1.2,
        "top_p": 0.95,
        "repetition_penalty": 1.05
    }
}
```

### 2. Configuring Long Story Management
```python
# User optimizes for long stories
settings = {
    "context_settings": {
        "max_tokens": 6000,
        "keep_recent_scenes": 5,
        "summary_threshold": 8,
        "enable_summarization": True
    }
}
```

### 3. Customizing Generation Experience
```python
# User sets up automatic choices
settings = {
    "generation_preferences": {
        "auto_choices": True,
        "choices_count": 4,
        "scene_length": "long"
    }
}
```

## Migration Guide

If you're upgrading from a previous version:

1. **Run the table creation script:**
   ```bash
   cd backend
   python create_user_settings_table.py
   ```

2. **Restart the backend server** to load the new API endpoints

3. **Access settings** at `http://localhost:3000/settings`

## Default Values

All settings have sensible defaults:
- Temperature: 0.7 (balanced creativity)
- Context Budget: 4000 tokens (good for most stories)
- Keep Recent Scenes: 3 (maintains story continuity)
- Theme: Dark (easier on eyes)
- Auto Choices: Disabled (manual control)

## Best Practices

### For New Users
- Start with default settings
- Try different presets to find your style
- Gradually adjust individual parameters

### For Long Stories
- Increase context budget to 6000-8000 tokens
- Enable summarization
- Keep 4-5 recent scenes for continuity

### For Creative Writing
- Increase temperature to 1.0-1.2
- Raise top_p to 0.9-0.95
- Lower repetition penalty to 1.05

### For Consistent Narratives
- Lower temperature to 0.4-0.6
- Use moderate top_p (0.8)
- Keep default repetition penalty (1.1)

## Troubleshooting

### Settings Not Saving
- Check authentication token
- Verify network connectivity
- Check browser console for errors

### Unexpected Generation Behavior
- Review LLM settings (especially temperature)
- Check context budget isn't too low
- Verify LM Studio is running and accessible

### Performance Issues
- Reduce context budget if generation is slow
- Lower max_tokens for faster responses
- Disable auto-choices if not needed

## Future Enhancements

- **Advanced Presets**: Genre-specific presets
- **Collaborative Settings**: Shared settings for team stories
- **A/B Testing**: Compare different parameter sets
- **Analytics**: Track which settings work best for you
- **Import/Export**: Share settings configurations