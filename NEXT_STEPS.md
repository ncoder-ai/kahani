# Next Steps - Semantic Memory System

## ✅ Implementation Complete!

The semantic memory system has been fully implemented on the `advanced_context` branch.

---

## What Was Built

### 🎯 Core Features
1. **Vector Database Integration** - ChromaDB with persistent storage
2. **Semantic Context Manager** - Hybrid retrieval (recent + relevant scenes)
3. **Character Memory System** - Auto-tracking of character development
4. **Plot Thread Tracking** - Automatic event extraction and thread management
5. **Semantic Search API** - Query scenes, characters, and plot events
6. **Database Models** - CharacterMemory, PlotEvent, SceneEmbedding tables
7. **Migration Tools** - Script to embed existing stories

### 📊 Files Summary
- **15 files changed**
- **4,630 lines added**
- **8 new services/models created**
- **5 existing files enhanced**

---

## Setup & Testing

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

This will install:
- `chromadb==0.4.22` - Vector database
- `sentence-transformers==2.2.2` - Embedding model
- `tiktoken==0.5.2` - Token counting

### 2. Run Database Migration

```bash
cd backend
alembic upgrade head
```

This creates the new tables:
- `character_memories`
- `plot_events`
- `scene_embeddings`

### 3. Start the Application

```bash
# From project root
./start-backend.sh
```

The semantic memory service will initialize automatically on startup.

### 4. Verify Installation

Check the logs for:
```
INFO - Loading embedding model: sentence-transformers/all-MiniLM-L6-v2
INFO - ChromaDB collections initialized successfully
INFO - Semantic memory service initialized successfully
INFO - Application startup complete
```

### 5. Test with New Story

Create a new story and generate 10+ scenes. The system will:
1. **Automatically embed** each scene in ChromaDB
2. **Extract character moments** using LLM
3. **Extract plot events** using LLM
4. **Build hybrid context** for future scenes

### 6. Check Semantic Stats

```bash
curl http://localhost:9876/api/stories/{story_id}/semantic-stats
```

Expected response:
```json
{
  "story_id": 123,
  "semantic_memory": {
    "enabled": true,
    "scene_embeddings": 10,
    "character_moments": 15,
    "plot_events": 8,
    "unresolved_threads": 5
  }
}
```

---

## Optional: Migrate Existing Stories

If you have existing stories, you can migrate them:

```bash
cd backend

# Dry run (see what would happen)
python migrate_existing_stories_to_semantic.py --dry-run

# Migrate all stories
python migrate_existing_stories_to_semantic.py

# Migrate specific story
python migrate_existing_stories_to_semantic.py --story-id 123

# Skip character/plot extraction (faster, only scene embeddings)
python migrate_existing_stories_to_semantic.py --skip-extraction
```

**Note**: Migration can take time for large stories (LLM extraction is slow).

---

## Testing the Features

### Test 1: Semantic Search

```bash
curl -X POST http://localhost:9876/api/stories/{story_id}/semantic-search \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What happened when the hero faced the villain?",
    "context_type": "all",
    "top_k": 5
  }'
```

### Test 2: Character Arc

```bash
curl http://localhost:9876/api/stories/{story_id}/characters/{char_id}/arc \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Test 3: Plot Threads

```bash
curl http://localhost:9876/api/stories/{story_id}/plot-threads \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Test 4: Verify Context Quality

Generate scene 20+ in a story and check that:
- **Recent scenes** are included
- **Relevant past scenes** are retrieved (not just sequential)
- **Character consistency** is maintained
- **Plot continuity** is preserved

---

## Configuration Options

### Disable Semantic Features (Fallback)

In `backend/app/config.py`:
```python
enable_semantic_memory = False  # Use linear context only
```

### Adjust Context Strategy

```python
context_strategy = "linear"  # or "hybrid" (default)
```

### Tune Extraction

```python
# Higher = fewer, better quality extractions
extraction_confidence_threshold = 70  # 0-100

# Disable auto-extraction
auto_extract_character_moments = False
auto_extract_plot_events = False
```

### Adjust Token Allocation

```python
semantic_scenes_in_context = 5  # Number of semantically relevant scenes
character_moments_in_context = 3  # Number of character moments
context_max_tokens = 4000  # Total context budget
```

---

## Performance Monitoring

### Check Collection Sizes

From Python:
```python
from app.services.semantic_memory import get_semantic_memory_service

service = get_semantic_memory_service()
stats = service.get_collection_stats()
print(stats)
# {'scenes': 150, 'character_moments': 230, 'plot_events': 180}
```

### Monitor Generation Time

Watch logs for:
```
INFO - Semantic processing results: {
  'scene_embedding': True,
  'character_moments': True,
  'plot_events': True
}
```

Typical times:
- Scene embedding: 100ms
- Character extraction: 2-3s
- Plot extraction: 2-3s
- **Total: ~5s** (async, non-blocking)

### Database Size

ChromaDB storage:
```bash
du -sh backend/data/chromadb
# Expect: ~10MB per 100 scenes
```

---

## Troubleshooting

### Issue: "Semantic memory service not initialized"

**Solution 1**: Check config
```python
enable_semantic_memory = True  # in config.py
```

**Solution 2**: Check startup logs
```bash
grep "semantic" backend/logs/kahani.log
```

**Solution 3**: Check ChromaDB directory permissions
```bash
ls -la backend/data/chromadb
# Should be writable by app user
```

### Issue: No character moments extracted

**Possible causes**:
1. No characters defined in story
2. Confidence threshold too high (lower it to 50-60)
3. LLM not responding properly (check logs)

**Solution**:
```python
extraction_confidence_threshold = 60  # Lower threshold
```

### Issue: Slow scene generation

**Note**: Semantic processing runs **async** and shouldn't block responses.

**Check**:
1. Verify async execution (logs should show "Semantic processing results" AFTER scene is returned)
2. Consider disabling auto-extraction for faster generation:
   ```python
   auto_extract_character_moments = False
   auto_extract_plot_events = False
   ```

### Issue: Migration fails

**Solution**: Use `--skip-extraction` for faster migration:
```bash
python migrate_existing_stories_to_semantic.py --skip-extraction
```

---

## Future Enhancements

### Phase 2 (Recommended)

1. **Frontend Integration**
   - UI for viewing character arcs
   - Plot thread visualization
   - Semantic search interface

2. **User Settings**
   - Per-user semantic configuration
   - Context strategy preference
   - Extraction settings

3. **Performance Optimization**
   - Cache frequent embeddings
   - Batch processing for migrations
   - Parallel extraction

### Advanced Features

1. **Relationship Graphs** - Character relationship tracking
2. **Multi-Modal Embeddings** - Include TTS voice features
3. **Adaptive Retrieval** - ML-based context optimization
4. **Cross-Story Memory** - Shared universe tracking

---

## Documentation

- **`SEMANTIC_MEMORY_IMPLEMENTATION.md`** - Complete technical documentation
- **`ARCHITECTURE.md`** - System architecture overview
- **Code Comments** - Inline documentation in all services

---

## Support & Questions

### Key Files to Understand

1. `backend/app/services/semantic_memory.py` - Core vector DB service
2. `backend/app/services/semantic_context_manager.py` - Context building
3. `backend/app/services/semantic_integration.py` - Integration helpers
4. `backend/app/api/semantic_search.py` - Search API

### Debugging

Enable debug logging:
```python
# In main.py
logging.basicConfig(level=logging.DEBUG)
```

Check specific services:
```python
logger = logging.getLogger("app.services.semantic_memory")
logger.setLevel(logging.DEBUG)
```

---

## Merging to Main

Once tested and verified:

```bash
# Switch to main branch
git checkout main

# Merge advanced_context
git merge advanced_context

# Push to remote
git push origin main
```

**Recommendation**: Test thoroughly on `advanced_context` branch first!

---

## Success Criteria

✅ **System is working if**:
1. New scenes automatically create embeddings
2. Semantic search returns relevant results
3. Character arcs show chronological development
4. Plot threads are detected and tracked
5. Story quality improves for 50+ scene narratives
6. No breaking changes to existing functionality

---

## Questions?

Review the implementation docs:
- `SEMANTIC_MEMORY_IMPLEMENTATION.md` - Technical details
- `ARCHITECTURE.md` - System overview

Happy storytelling with semantic memory! 🚀📚

