#!/bin/bash
# One-command semantic memory tracing
# 
# Usage: ./trace_semantic_memory.sh
# 
# This will:
# 1. Set log level to DEBUG
# 2. Restart backend
# 3. Tail logs with semantic filtering
# 4. Generate a scene in your story
# 5. Watch the real prompts and operations!

set -e

echo "🔍 Semantic Memory Tracer"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Create trace file
TRACE_FILE="semantic_trace_$(date +%Y%m%d_%H%M%S).log"

echo "📝 Trace will be saved to: $TRACE_FILE"
echo ""

# Stop existing backend
echo "🛑 Stopping existing backend..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 2

# Start backend with DEBUG logging
echo "🚀 Starting backend with DEBUG logging..."
cd backend
KAHANI_LOG_LEVEL=DEBUG uvicorn app.main:app --reload --host 0.0.0.0 --port 9876 > "../$TRACE_FILE" 2>&1 &
BACKEND_PID=$!

echo "✅ Backend started (PID: $BACKEND_PID)"
echo ""

# Wait for backend to be ready
echo "⏳ Waiting for backend to be ready..."
sleep 5

# Check if backend is running
if ! curl -s http://localhost:9876/health > /dev/null; then
    echo "❌ Backend not responding!"
    exit 1
fi

echo "✅ Backend is ready!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📖 Open your story: http://localhost:6789"
echo "🎬 Generate a scene now!"
echo ""
echo "📊 Watching for semantic operations..."
echo "   (Press Ctrl+C to stop)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Tail and filter the trace file
tail -f "$TRACE_FILE" | grep --line-buffered -E "(semantic|embedding|rerank|entity_state|ChromaDB|llm\.|context_manager|Generating|prompt)" --color=always

# Cleanup on exit
trap "echo ''; echo '✅ Trace saved to: $TRACE_FILE'; kill $BACKEND_PID 2>/dev/null" EXIT


