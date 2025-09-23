# Context Manager: How It Works

## 📊 **Detailed Flow Explanation**

The Context Manager is the brain of Kahani's long story handling. Here's exactly how it works:

## 🔄 **Main Flow**

```
1. API Request → build_scene_generation_context()
2. Context Manager → build_story_context()
3. Token Budget Calculation
4. Smart Scene Selection Strategy
5. LLM Generation with Optimized Context
```

## 🧮 **Token Budget Calculation**

```python
# Configuration (from settings)
max_tokens = 4000           # Total budget for LLM request
keep_recent_scenes = 3      # Always preserve these recent scenes
summary_threshold = 5       # Start summarizing when story exceeds this

# Runtime calculation
base_context_tokens = calculate_base_context()  # Story info + characters
safety_buffer = 500                             # Reserve for LLM response
available_for_scenes = max_tokens - base_context_tokens - safety_buffer
```

**Example:**
- Total budget: 4000 tokens
- Base context (story + characters): 800 tokens  
- Safety buffer: 500 tokens
- Available for scenes: **2700 tokens**

## 🎯 **Decision Tree**

```
Story Length Check
├── ≤ 5 scenes (Short Story)
│   ├── All scenes fit in budget? → Include everything
│   ├── Recent scenes fit? → Recent scenes + summary of older
│   └── Emergency → Last scene only
│
└── > 5 scenes (Long Story)  
    ├── Recent scenes fit? → Recent scenes + progressive summary
    ├── Recent scenes too big? → Emergency fallback (last scene)
    └── No space for summary? → Recent scenes only with truncation note
```

## 📝 **Scene Selection Examples**

### **Scenario 1: Short Story (3 scenes, all fit)**
```
Input: 3 scenes, 500 tokens total
Available: 2700 tokens
Decision: Include all scenes completely
Result: Full context preservation
```

### **Scenario 2: Medium Story (8 scenes, needs optimization)**
```
Input: 8 scenes, 2000 tokens total  
Available: 2700 tokens
Decision: Recent 3 scenes (800 tokens) + summary of older 5 scenes (300 tokens)
Result: 1100 tokens used, fits in budget
```

### **Scenario 3: Long Story (20 scenes, needs aggressive summarization)**
```
Input: 20 scenes, 8000 tokens total
Available: 2700 tokens  
Recent 3 scenes: 900 tokens
Older 17 scenes: Need summarization
Decision: Progressive summary (600 tokens) + recent scenes (900 tokens)
Result: 1500 tokens used, maintains continuity
```

### **Scenario 4: Emergency (Recent scenes don't fit)**
```
Input: Recent 3 scenes = 3000 tokens
Available: 2700 tokens
Decision: Last scene only (800 tokens) + emergency note
Result: Minimal context but story continues
```

## 🔄 **Progressive Summarization Strategy**

For very long stories, the context manager creates **layered summaries**:

```python
# Example: 20-scene story
scenes_1_to_7   → "Story Opening Summary"    (150 tokens)
scenes_8_to_17  → "Story Development Summary" (200 tokens)  
scenes_18_to_20 → Full content (recent scenes) (900 tokens)

Total context: 1250 tokens (fits in 2700 token budget)
```

## 📊 **Token Counting**

The system uses **tiktoken** (GPT-4's tokenizer) for accurate counting:

```python
def count_tokens(self, text: str) -> int:
    if self.use_tiktoken:
        return len(self.encoding.encode(text))  # Accurate
    else:
        return len(text) // 4  # Fallback: ~4 chars per token
```

**Why this matters:**
- "Hello world" = 2 tokens (not 11 characters ÷ 4 = 2.75)
- Accurate counting prevents context overflow
- Fallback ensures system works even without tiktoken

## 🎭 **Context Structure Sent to LLM**

```json
{
  "genre": "fantasy",
  "tone": "epic", 
  "world_setting": "Medieval realm with magic",
  "characters": [
    {
      "name": "Lyra",
      "role": "protagonist", 
      "description": "Young mage discovering her powers",
      "personality": "Brave but impulsive"
    }
  ],
  "previous_scenes": "Story Opening (Scenes 1-5): Lyra discovers she has magical abilities when her village is attacked...\n\nStory Development (Scenes 6-15): She trains with a mentor and faces increasingly difficult challenges...",
  "recent_scenes": "Scene 16: Lyra confronts the dark sorcerer...\n\nScene 17: The battle intensifies...\n\nScene 18: A crucial revelation changes everything...",
  "scene_summary": "Progressive summary of 15 scenes + 3 recent scenes",
  "total_scenes": 18
}
```

## 🧠 **LLM Instructions**

The enhanced generation method tells the LLM:

```python
system_prompt = """You are a creative storytelling assistant...

Important: If you see a scene summary, treat it as established story history.
Pay attention to the total scene count to understand story progression.
Reference important previous events when relevant.
Show character growth and relationship development."""
```

## ⚡ **Performance Optimizations**

1. **Smart Caching**: Base context tokens calculated once per story
2. **Lazy Summarization**: Only summarize when needed
3. **Graceful Degradation**: Multiple fallback strategies
4. **Token Pre-calculation**: Avoid generating content that won't fit

## 🔍 **Monitoring & Debugging**

The `/stories/{story_id}/context-info` endpoint shows:

```json
{
  "context_management": {
    "max_tokens": 4000,
    "base_context_tokens": 800,
    "total_story_tokens": 12000,
    "needs_summarization": true,
    "context_type": "summarized"
  },
  "summary_used": true,
  "recent_scenes_included": 3
}
```

## 🛡️ **Error Handling**

Multiple fallback layers ensure the system never fails:

1. **Summarization fails** → Use truncated content
2. **Token counting fails** → Use character-based estimation  
3. **Recent scenes too big** → Use last scene only
4. **No scenes fit** → Generate from story premise only

## 🎯 **Key Benefits**

- **Consistency**: Characters and plot threads preserved across any story length
- **Performance**: Always fits within LLM token limits
- **Quality**: Better context = better story continuity
- **Scalability**: Handles stories from 1 to 1000+ scenes
- **Transparency**: Full visibility into decisions made

This system ensures that whether your story is 3 scenes or 300 scenes, the AI always has the right amount of relevant context to generate coherent, consistent content! 🚀