# How to Trace Semantic Memory (See Real Prompts!)

## ⚡ Quick Start (Easiest Way)

Run this **ONE command**:

```bash
./trace_semantic_memory.sh
```

This will:
1. ✅ Stop existing backend
2. ✅ Start backend with DEBUG logging
3. ✅ Save all output to a timestamped file
4. ✅ Show you filtered, colored output in real-time
5. ✅ Automatically clean up when you're done (Ctrl+C)

Then:
1. Open http://localhost:6789
2. Go to your story
3. **Generate a scene**
4. Watch the terminal show all semantic operations!

The complete trace is automatically saved to: `semantic_trace_YYYYMMDD_HHMMSS.log`

---

## 🎯 What You'll See

When you generate a scene, you'll see output like this (real example):

```
2025-10-20 23:37:10 - semantic_context_manager - DEBUG - Building hybrid context for story 2
2025-10-20 23:37:10 - semantic_context_manager - DEBUG - Token allocation: semantic=900, character=400, entity=400, summary=300

2025-10-20 23:37:13 - semantic_memory - INFO - Loading embedding model: sentence-transformers/all-MiniLM-L6-v2
2025-10-20 23:37:17 - semantic_memory - INFO - Embedding model loaded successfully. Dimension: 384

2025-10-20 23:37:17 - semantic_memory - DEBUG - Query text (first 200 chars): "The iron doors to the throne room..."
2025-10-20 23:37:17 - semantic_memory - DEBUG - Generating embedding for semantic search

2025-10-20 23:37:17 - semantic_memory - INFO - Searching ChromaDB for similar scenes
2025-10-20 23:37:17 - semantic_memory - DEBUG - Retrieved 8 candidates for reranking

2025-10-20 23:37:18 - semantic_memory - INFO - Reranking with Cross-Encoder
2025-10-20 23:37:18 - semantic_memory - DEBUG - Bi-encoder scores: [0.65, 0.58, 0.52, ...]
2025-10-20 23:37:18 - semantic_memory - DEBUG - Reranker scores: [0.85, 0.72, 0.65, ...]
2025-10-20 23:37:18 - semantic_memory - INFO - Top 5 after reranking: scenes [45, 23, 12, 8, 3]

2025-10-20 23:37:18 - llm.prompts - DEBUG - System prompt: "You are a creative storytelling AI..."
2025-10-20 23:37:18 - llm.prompts - DEBUG - User prompt includes: [2800 tokens of context]

2025-10-20 23:37:22 - entity_state_service - DEBUG - Extracting entity states from scene
2025-10-20 23:37:22 - entity_state_service - DEBUG - LLM prompt: {"system": "Extract character states...", ...}
```

---

## 📁 Alternative: Manual Tracing

If you want more control:

### Step 1: Set Environment Variable

```bash
export KAHANI_LOG_LEVEL=DEBUG
```

### Step 2: Restart Backend

```bash
cd backend
KAHANI_LOG_LEVEL=DEBUG uvicorn app.main:app --reload --host 0.0.0.0 --port 9876
```

### Step 3: Watch Logs

In another terminal:

```bash
tail -f backend/logs/kahani.log | grep -E "(semantic|embedding|rerank|entity)"
```

---

## 🔍 Filtering Options

### See Everything (Full Trace)
```bash
tail -f backend/logs/kahani.log
```

### See Only Semantic Operations
```bash
tail -f backend/logs/kahani.log | grep semantic
```

### See Only LLM Prompts
```bash
tail -f backend/logs/kahani.log | grep -E "(llm\.|prompts\.|Generating)"
```

### See Only Entity Extraction
```bash
tail -f backend/logs/kahani.log | grep entity_state
```

### See Only Embeddings & Search
```bash
tail -f backend/logs/kahani.log | grep -E "(embedding|ChromaDB|rerank)"
```

---

## 💾 Save Everything to File

### Option 1: Use the trace script (recommended)
```bash
./trace_semantic_memory.sh
# Automatically saves to semantic_trace_YYYYMMDD_HHMMSS.log
```

### Option 2: Manual save
```bash
# Start backend and save output
cd backend
KAHANI_LOG_LEVEL=DEBUG uvicorn app.main:app --reload --host 0.0.0.0 --port 9876 2>&1 | tee ../my_trace.log
```

### Option 3: Save from existing logs
```bash
tail -f backend/logs/kahani.log > my_semantic_trace.log
```

---

## 📖 What Gets Logged

The DEBUG logs will show you:

### 1. **Context Assembly**
- Base story metadata (genre, tone, characters)
- Token budget and allocation
- Strategy selection (linear vs hybrid)

### 2. **Embedding Generation**
- Text being embedded (truncated)
- Model used (sentence-transformers/all-MiniLM-L6-v2)
- Embedding dimension (384)
- Processing time

### 3. **Semantic Search**
- Query text
- Number of candidates retrieved
- ChromaDB query parameters
- Distance scores

### 4. **Cross-Encoder Reranking**
- Number of candidates
- Bi-encoder scores (before reranking)
- Reranker scores (after reranking)
- Final top-k selection

### 5. **Entity State Extraction**
- Full LLM prompt for extraction
- Scene content sent to LLM
- Extracted states (characters, locations, objects)
- Relationships and knowledge updates

### 6. **Scene Generation**
- Complete system prompt
- Complete user prompt with all context
- Token counts
- Generation parameters
- LLM model being used

### 7. **Semantic Processing Results**
- Scene embedding created
- Character moments extracted
- Plot events extracted
- Entity states updated

---

## 🎬 Complete Workflow

```bash
# 1. Run the trace script
./trace_semantic_memory.sh

# 2. In another terminal, watch specific operations
tail -f semantic_trace_*.log | grep "LLM prompt"

# 3. Generate a scene in your story (http://localhost:6789)

# 4. Watch the terminal see all operations in real-time!

# 5. When done, press Ctrl+C
#    The trace file is automatically saved

# 6. Review the full trace
cat semantic_trace_*.log | less
```

---

## 🚨 Troubleshooting

### Backend won't start
```bash
# Kill any existing backend
pkill -f uvicorn
# Wait a moment
sleep 2
# Try again
./trace_semantic_memory.sh
```

### Not seeing DEBUG logs
```bash
# Check environment variable
echo $KAHANI_LOG_LEVEL
# Should output: DEBUG

# If not, export it:
export KAHANI_LOG_LEVEL=DEBUG
```

### Want to reset to normal logging
```bash
# Unset the environment variable
unset KAHANI_LOG_LEVEL

# Restart backend normally
./start-backend.sh
```

---

## 📚 Example Use Cases

### "Show me the exact prompt sent to the LLM"
```bash
./trace_semantic_memory.sh
# Generate a scene
# Then grep for prompts:
cat semantic_trace_*.log | grep -A 50 "System prompt"
```

### "What scenes were semantically retrieved?"
```bash
./trace_semantic_memory.sh
# Generate a scene
# Then grep for semantic search:
cat semantic_trace_*.log | grep -A 20 "Searching ChromaDB"
```

### "How did reranking change the results?"
```bash
./trace_semantic_memory.sh
# Generate a scene  
# Then compare scores:
cat semantic_trace_*.log | grep -E "(Bi-encoder scores|Reranker scores)"
```

### "What entity states were extracted?"
```bash
./trace_semantic_memory.sh
# Generate a scene
# Then check extraction:
cat semantic_trace_*.log | grep -A 30 "Extracting entity states"
```

---

## ✨ Pro Tips

1. **Generate multiple scenes** in one trace session to compare operations
2. **Use grep -C 10** to see 10 lines of context around matches
3. **Save different traces** for different stories to compare
4. **Use `less +F`** instead of `tail -f` for better navigation (Ctrl+C to stop following, / to search, Shift+F to resume)
5. **Compare traces** before and after enabling semantic memory to see the difference!

---

That's it! Just run `./trace_semantic_memory.sh` and start generating scenes to see everything! 🎉


