# Context Management System

## Overview

Kahani implements a sophisticated context management system to handle long stories that exceed LLM token limits. This ensures that story generation remains coherent and consistent even for very long narratives.

## The Problem

Interactive stories can grow very long over time, with dozens or hundreds of scenes. Modern LLMs have token limits (typically 4K-8K tokens), which means we can't send the entire story context for every generation request. Without proper context management, the LLM would:

- Lose track of early story events
- Forget character development
- Break story continuity
- Generate inconsistent content

## Our Solution

### 1. Smart Context Truncation

The `ContextManager` class implements a multi-layered strategy:

```python
# Configuration (from settings)
context_max_tokens: int = 4000  # Maximum tokens to send to LLM
context_keep_recent_scenes: int = 3  # Always keep recent scenes
context_summary_threshold: int = 5  # Summarize when story has more scenes
```

### 2. Progressive Summarization

**For Short Stories (≤ 5 scenes):**
- Try to include complete context
- Fall back to recent scenes + summary if needed

**For Long Stories (> 5 scenes):**
- Always preserve the most recent 3 scenes (immediate context)
- Create progressive summaries of older content
- Use layered summarization for very long stories

### 3. Token Counting

Accurate token counting using `tiktoken` library:
```python
def count_tokens(self, text: str) -> int:
    """Count tokens using tiktoken or fallback estimation"""
    if self.use_tiktoken:
        return len(self.encoding.encode(text))
    # Fallback: ~4 characters per token
    return len(text) // 4
```

## Context Building Strategy

### Base Context (Always Included)
- Story metadata (genre, tone, setting)
- Character information (optimized for token limits)
- Current story status

### Scene Context (Smart Truncation)

1. **Recent Scenes**: Always keep last 3 scenes for immediate continuity
2. **Progressive Summary**: Older scenes are summarized in narrative chunks:
   - Story Opening (first quarter of scenes)
   - Story Development (middle sections)
3. **Emergency Fallback**: If even recent scenes don't fit, keep only the last scene

### Example Context Structure

```json
{
  "genre": "fantasy",
  "tone": "epic",
  "world_setting": "Medieval fantasy realm",
  "characters": [...],
  "previous_scenes": "Story Opening (Scenes 1-5): The hero begins their journey...\n\nStory Development (Scenes 6-15): Major conflicts arise...",
  "recent_scenes": "Scene 16: The current situation...\n\nScene 17: Recent events...",
  "scene_summary": "Progressive summary of 15 scenes + 3 recent scenes",
  "total_scenes": 18
}
```

## API Enhancements

### Enhanced Scene Generation

The `/stories/{story_id}/scenes` endpoint now:
- Uses `ContextManager` to build optimized context
- Provides context info in response
- Handles long stories gracefully

```python
# Response includes context information
{
  "id": 123,
  "content": "Generated scene content...",
  "sequence_number": 18,
  "choices": [...],
  "context_info": {
    "total_scenes": 18,
    "context_type": "summarized"  # or "full"
  }
}
```

### Context Analysis Endpoint

New endpoint `/stories/{story_id}/context-info` provides:
- Token usage analysis
- Context management status
- Performance metrics

```json
{
  "story_id": 123,
  "total_scenes": 18,
  "context_management": {
    "max_tokens": 4000,
    "base_context_tokens": 500,
    "total_story_tokens": 12000,
    "needs_summarization": true,
    "context_type": "summarized"
  },
  "characters": 3,
  "recent_scenes_included": 3,
  "summary_used": true
}
```

## LLM Integration

### Enhanced Generation Methods

New `generate_scene_with_context_management()` method:
- Handles optimized context from `ContextManager`
- Understands scene summaries
- Maintains story continuity instructions

```python
system_prompt = """You are a creative storytelling assistant...

Important: If you see a scene summary, treat it as established story history.
Pay attention to the total scene count to understand story progression."""
```

### Context-Aware Prompting

The system now provides better context to the LLM:
- Clear distinction between summary and full scenes
- Story progression indicators
- Character state information

## Benefits

### For Users
- **Consistent Characters**: Character development is preserved across long stories
- **Story Continuity**: Plot threads and past events remain relevant
- **Performance**: Fast generation even for very long stories
- **Quality**: Better narrative coherence and fewer contradictions

### For Developers
- **Scalable**: Handles stories of any length
- **Configurable**: Adjustable token limits and summarization thresholds
- **Transparent**: Context info endpoint for debugging and monitoring
- **Robust**: Graceful fallbacks when summarization fails

## Configuration Options

```python
# In config.py
class Settings(BaseSettings):
    # Context Management
    context_max_tokens: int = 4000
    context_keep_recent_scenes: int = 3
    context_summary_threshold: int = 5
```

### Tuning Guidelines

- **context_max_tokens**: Set based on your LLM's context window (leave room for response)
- **context_keep_recent_scenes**: More scenes = better immediate context but uses more tokens
- **context_summary_threshold**: Lower = more aggressive summarization for token efficiency

## Future Enhancements

### Planned Features
1. **Character-Specific Summaries**: Track individual character arcs
2. **Plot Thread Tracking**: Identify and preserve important story threads
3. **Adaptive Summarization**: Adjust strategy based on story genre/style
4. **Context Caching**: Cache summaries to improve performance
5. **User Preferences**: Let users choose context management aggressiveness

### Advanced Strategies
1. **Semantic Chunking**: Group related scenes for better summaries
2. **Importance Scoring**: Prioritize key scenes for inclusion
3. **Dynamic Token Allocation**: Adjust context distribution based on story needs
4. **Multi-Model Support**: Use different models for summarization vs generation

## Error Handling

The system includes robust error handling:
- Graceful fallbacks when summarization fails
- Token counting fallbacks when tiktoken unavailable
- Context size validation and emergency truncation
- Comprehensive logging for debugging

## Testing & Monitoring

Use the context info endpoint to monitor:
- When summarization is triggered
- Token usage patterns
- Context efficiency
- Story length trends

This helps optimize the system and understand user story-writing patterns.