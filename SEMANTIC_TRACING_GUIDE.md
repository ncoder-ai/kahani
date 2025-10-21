# Semantic Memory Tracing Guide

This guide shows you how to capture **real** prompts, embeddings, and model interactions when generating a scene.

## Quick Start

### 1. Enable Tracing

```bash
cd /Users/user/apps/kahani
export ENABLE_SEMANTIC_TRACING=true
mkdir -p backend/traces
```

### 2. Set Log Level to DEBUG

Edit `backend/app/config.py` and temporarily change:

```python
# Change from INFO to DEBUG
logging.basicConfig(
    level=logging.DEBUG,  # <-- Change this
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### 3. Restart Backend

```bash
# Kill existing backend
pkill -f "uvicorn app.main:app"

# Start with tracing enabled
cd backend
ENABLE_SEMANTIC_TRACING=true uvicorn app.main:app --reload --host 0.0.0.0 --port 9876
```

### 4. Generate a Scene

1. Open http://localhost:6789
2. Go to your story
3. Generate a new scene
4. Watch the terminal output for detailed logs

### 5. Check the Trace Output

The backend logs will now show:

```
[SEMANTIC TRACE] Step 1: Context Assembly
[SEMANTIC TRACE] Step 2: Embedding Query  
[SEMANTIC TRACE] Step 3: Semantic Search Results
[SEMANTIC TRACE] Step 4: Cross-Encoder Reranking
[SEMANTIC TRACE] Step 5: LLM Prompt (Scene Generation)
[SEMANTIC TRACE] Step 6: Entity Extraction Prompt
[SEMANTIC TRACE] Step 7: Final Context Sent to LLM
```

---

## What You'll See

### Example Output (from actual scene generation):

```
2025-10-20 23:37:10 - semantic_context_manager - INFO - Building hybrid context for story 2
2025-10-20 23:37:10 - semantic_context_manager - DEBUG - Base context: {genre: "fantasy", tone: "dark", characters: [...]}
2025-10-20 23:37:10 - semantic_context_manager - DEBUG - Recent scenes tokens: 1200
2025-10-20 23:37:10 - semantic_context_manager - DEBUG - Token allocation: semantic=900, character=400, entity=400, summary=300

2025-10-20 23:37:10 - semantic_memory - INFO - Generating embedding for query
2025-10-20 23:37:10 - semantic_memory - DEBUG - Query text (first 200 chars): "The iron doors to the throne room groan open with an echo that reverberates through..."
2025-10-20 23:37:13 - semantic_memory - INFO - Embedding generated: dimension=384

2025-10-20 23:37:13 - semantic_memory - INFO - Searching ChromaDB for similar scenes
2025-10-20 23:37:13 - semantic_memory - DEBUG - Query embedding shape: (384,)
2025-10-20 23:37:13 - semantic_memory - DEBUG - Retrieving top 15 candidates for reranking
2025-10-20 23:37:17 - semantic_memory - INFO - Found 8 candidates

2025-10-20 23:37:17 - semantic_memory - INFO - Reranking with Cross-Encoder
2025-10-20 23:37:17 - semantic_memory - DEBUG - Reranking pairs:
  - Pair 1: ["current scene text...", "candidate scene 1..."]
  - Pair 2: ["current scene text...", "candidate scene 2..."]
2025-10-20 23:37:18 - semantic_memory - DEBUG - Reranker scores: [0.85, 0.72, 0.65, 0.42, ...]
2025-10-20 23:37:18 - semantic_memory - INFO - Top 5 after reranking: [scene_45, scene_23, scene_12, ...]

2025-10-20 23:37:18 - semantic_context_manager - DEBUG - Final context assembly:
  Story Summary (300 tokens)
  Entity States (400 tokens)  
  Semantic Scenes (900 tokens)
  Recent Scenes (1200 tokens)
  Total: 2800 tokens

2025-10-20 23:37:18 - llm.service - INFO - Generating scene with hybrid context
2025-10-20 23:37:18 - llm.prompts - DEBUG - System prompt: "You are a creative storytelling AI..."
2025-10-20 23:37:18 - llm.prompts - DEBUG - User prompt includes:
  - Genre: fantasy
  - Tone: dark
  - Context: [2800 tokens of story history]
  - Current situation: [recent scenes]

2025-10-20 23:37:22 - entity_state_service - INFO - Extracting entity states from new scene
2025-10-20 23:37:22 - entity_state_service - DEBUG - LLM prompt for entity extraction:
{
  "system": "You are an expert at analyzing narrative text...",
  "user": "Extract character states, locations, and objects from: [scene content]"
}
```

---

## Alternative: Save to File

If you want everything saved to a file instead of terminal:

```bash
cd backend
ENABLE_SEMANTIC_TRACING=true uvicorn app.main:app --reload --host 0.0.0.0 --port 9876 2>&1 | tee traces/live_trace_$(date +%Y%m%d_%H%M%S).log
```

This will:
- Show output in terminal (live)
- Save everything to `backend/traces/live_trace_YYYYMMDD_HHMMSS.log`

---

## Filtering the Output

To see only semantic memory operations:

```bash
tail -f backend/logs/kahani.log | grep -E "(semantic|embedding|rerank|entity_state|ChromaDB)"
```

To see only LLM prompts:

```bash
tail -f backend/logs/kahani.log | grep -E "(llm\.|prompts\.|Generating)"
```

---

##Current Log Locations

Your system already logs to:
- `backend/logs/kahani.log` - Main application log
- `backend/backend.log` - Uvicorn output

Just set the log level to DEBUG and all the prompts and operations will appear there!

---

## Quick Test

```bash
# 1. Enable debug logging
sed -i '' 's/level=logging.INFO/level=logging.DEBUG/' backend/app/config.py

# 2. Restart backend
pkill -f uvicorn
cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 9876 &

# 3. Follow the logs
tail -f logs/kahani.log
```

Now generate a scene and watch the magic! 🎭✨

---

## What Gets Logged

### 1. **Context Assembly**
- Base story info (genre, tone, characters)
- Token budget allocation
- Which context strategy is used (linear vs hybrid)

### 2. **Semantic Search**
- Query text sent to embedding model  
- Embedding vector shape
- ChromaDB query parameters
- Number of candidates retrieved

### 3. **Cross-Encoder Reranking**
- Input pairs (query + each candidate)
- Bi-encoder scores vs reranker scores
- Final similarity rankings

### 4. **Entity State Extraction**
- Full LLM prompt for entity extraction
- Extracted character states, locations, objects
- Relationship updates

### 5. **Scene Generation Prompt**
- Complete system prompt
- Complete user prompt with full context
- Generation parameters (temperature, top_k, etc.)
- Token counts

### 6. **Generated Output**
- Generated scene content
- Choices generated
- Semantic processing results

---

## Tips

- **For shorter output**: Use `grep` to filter specific components
- **For structured output**: Set `LOG_FORMAT=json` in `.env`
- **For real-time monitoring**: Use `tail -f` with grep patterns
- **For analysis**: Save to file and use tools like `jq` for JSON logs

---

## Example Commands

```bash
# Watch semantic search only
tail -f backend/logs/kahani.log | grep semantic_memory

# Watch LLM prompts only  
tail -f backend/logs/kahani.log | grep "llm\.(service|prompts)"

# Watch entity extraction
tail -f backend/logs/kahani.log | grep entity_state

# Save everything to file
tail -f backend/logs/kahani.log > /tmp/semantic_trace.log
```

Generate a scene, then open the log file to see **exactly** what prompts were sent!


