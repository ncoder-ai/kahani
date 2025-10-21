#!/bin/bash
# Simple script to watch semantic memory operations in real-time
#
# Just run this while your backend is running and generate a scene

echo "🔍 Watching Semantic Memory Operations"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "This will show all semantic operations when you generate a scene."
echo "Press Ctrl+C to stop."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Watch the log file with filtering
tail -f backend/logs/kahani.log | grep --line-buffered -E "(semantic|embedding|rerank|entity_state|ChromaDB|LLM|prompt|Generating|context)" --color=always


