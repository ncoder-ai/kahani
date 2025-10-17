#!/bin/bash

# Test Manual TTS Generation
# This script will:
# 1. Clear the log
# 2. Make a TTS request
# 3. Show step-by-step logs

echo "============================================"
echo "MANUAL TTS TEST"
echo "============================================"
echo ""

# Get scene ID (use first scene from your story)
STORY_ID=1
SCENE_ID=1

# Get your auth token from localStorage or login
# You'll need to replace this with your actual token
TOKEN="your-token-here"

echo "Step 1: Clearing backend logs..."
> backend/backend.log

echo ""
echo "Step 2: Making TTS generation request..."
echo "POST http://localhost:9876/api/tts/generate-ws/${SCENE_ID}"
echo ""

# Make the request (you'll need to add your token)
curl -X POST "http://localhost:9876/api/tts/generate-ws/${SCENE_ID}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -v

echo ""
echo ""
echo "Step 3: Checking backend logs..."
echo "============================================"
sleep 1
grep -E "\[MANUAL TTS\]|\[GEN\]" backend/backend.log | tail -50

echo ""
echo "============================================"
echo "If you see no [MANUAL TTS] or [GEN] logs,"
echo "then the endpoint is not being called."
echo "Check frontend console for errors."
echo "============================================"
