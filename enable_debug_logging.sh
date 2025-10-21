#!/bin/bash
# Enable DEBUG logging to see all semantic memory operations

echo "🔍 Enabling DEBUG logging for semantic memory tracing"
echo ""

# Set environment variable
export KAHANI_LOG_LEVEL=DEBUG
export ENABLE_SEMANTIC_TRACING=true

echo "✅ Debug logging enabled!"
echo ""
echo "Now restart your backend:"
echo "  1. Stop current backend: Ctrl+C or pkill -f uvicorn"
echo "  2. Run: cd backend && KAHANI_LOG_LEVEL=DEBUG uvicorn app.main:app --reload --host 0.0.0.0 --port 9876"
echo ""
echo "Or use the start script with DEBUG:"
echo "  KAHANI_LOG_LEVEL=DEBUG ./start-backend.sh"
echo ""
echo "📊 To watch the logs in real-time:"
echo "  tail -f backend/logs/kahani.log"
echo ""
echo "📝 To filter semantic operations only:"
echo "  tail -f backend/logs/kahani.log | grep -E '(semantic|embedding|rerank|entity)'"
echo ""
echo "💾 To save to a trace file:"
echo "  tail -f backend/logs/kahani.log > semantic_trace_\$(date +%Y%m%d_%H%M%S).log"


