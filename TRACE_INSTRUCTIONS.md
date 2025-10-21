# How to See Real Semantic Memory Prompts

## ✅ Step 1: Restart Backend (with DEBUG logging now enabled)

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 9876 &
cd ..
```

## ✅ Step 2: Watch the logs

```bash
./watch_semantic_trace.sh
```

Or manually:

```bash
tail -f backend/logs/kahani.log | grep -E "semantic|embedding|prompt"
```

## ✅ Step 3: Generate a scene

1. Open http://localhost:6789
2. Login (test@test.com / test)
3. Go to your story
4. **Generate a scene**

## ✅ Step 4: Watch the output!

You'll see output like:

```
2025-10-20 23:37:10 - semantic_context_manager - DEBUG - Building hybrid context
2025-10-20 23:37:13 - semantic_memory - DEBUG - Generating embedding for: "The iron doors..."
2025-10-20 23:37:17 - semantic_memory - DEBUG - Retrieved 8 candidates
2025-10-20 23:37:18 - semantic_memory - DEBUG - Reranker scores: [0.85, 0.72, 0.65...]
2025-10-20 23:37:18 - llm.prompts - DEBUG - System prompt: "You are a creative..."
2025-10-20 23:37:18 - llm.prompts - DEBUG - User prompt: [full context with 2800 tokens]
```

## 💾 To Save to File

```bash
tail -f backend/logs/kahani.log > my_trace_$(date +%H%M%S).log
```

Then generate a scene, press Ctrl+C, and check the file!

---

That's it! DEBUG logging is now permanently enabled in `backend/app/config.py`.


