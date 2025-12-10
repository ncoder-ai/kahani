# Testing VibeVoice TTS Integration

## Quick Test Guide

### Step 1: Install Dependencies

First, make sure the websockets dependency is installed in your Kahani backend:

```bash
cd /Users/nishant/apps/kahani
pip install websockets==12.0
```

Or if using Docker, rebuild the backend:
```bash
docker-compose build backend
```

### Step 2: Start VibeVoice Service (Choose One Option)

#### Option A: Baremetal (Easiest for Testing)

1. **Navigate to VibeVoice directory:**
   ```bash
   cd /Users/nishant/apps/VibeVoice-main
   ```

2. **Install VibeVoice dependencies** (if not already done):
   ```bash
   pip install -e .
   ```
   
   Or install dependencies manually:
   ```bash
   pip install torch accelerate transformers==4.51.3 diffusers librosa fastapi uvicorn websockets
   ```

3. **Run VibeVoice service:**
   ```bash
   python demo/vibevoice_realtime_demo.py \
     --model_path microsoft/VibeVoice-Realtime-0.5B \
     --device cpu \
     --port 3000
   ```
   
   **Note:** 
   - First run will download the model (~500MB) - this may take a few minutes
   - Use `--device cuda` if you have GPU
   - Use `--device mps` for Apple Silicon Macs

4. **Verify it's running:**
   Open another terminal and test:
   ```bash
   curl http://localhost:3000/config
   ```
   
   You should see JSON with available voices.

#### Option B: Docker (For Production-like Testing)

1. **Set environment variables** (create `.env.vibevoice` or export):
   ```bash
   export VIBEVOICE_MODEL_PATH=microsoft/VibeVoice-Realtime-0.5B
   export VIBEVOICE_DEVICE=cpu  # or "cuda" for GPU
   export VIBEVOICE_PORT=3000
   ```

2. **Build and run:**
   ```bash
   cd /Users/nishant/apps/kahani
   docker-compose -f docker-compose.vibevoice.yml up -d
   ```

3. **Check logs:**
   ```bash
   docker logs vibevoice-tts
   ```

4. **Verify it's running:**
   ```bash
   curl http://localhost:3000/config
   ```

### Step 3: Start Kahani Backend

Make sure your Kahani backend is running:

```bash
# If using Docker
docker-compose up -d backend

# If using baremetal
cd /Users/nishant/apps/kahani/backend
python -m uvicorn app.main:app --reload --port 9876
```

### Step 4: Test Provider Connection

Test that Kahani can connect to VibeVoice:

```bash
# Test voice discovery
curl http://localhost:9876/api/tts/voices?provider_type=vibevoice \
  -H "Authorization: Bearer YOUR_TOKEN"

# Or test via Python
python3 << EOF
import requests
import json

# Get your auth token from Kahani login
token = "YOUR_AUTH_TOKEN"

# Test getting voices
response = requests.get(
    "http://localhost:9876/api/tts/voices",
    params={"provider_type": "vibevoice"},
    headers={"Authorization": f"Bearer {token}"}
)
print("Voices:", json.dumps(response.json(), indent=2))
EOF
```

### Step 5: Configure in Kahani UI

1. **Start Kahani frontend** (if not already running):
   ```bash
   # Docker
   docker-compose up -d frontend
   
   # Or baremetal
   cd /Users/nishant/apps/kahani/frontend
   npm run dev
   ```

2. **Open Kahani in browser:**
   - Navigate to `http://localhost:6789` (or your frontend URL)
   - Log in to your account

3. **Configure TTS:**
   - Click **Settings** (gear icon)
   - Go to **TTS** tab
   - Select **Provider**: `VibeVoice`
   - Set **API URL**: `http://localhost:3000`
   - Leave **API Key** empty (VibeVoice doesn't require auth)
   - Click **"Load Voices"** or wait for voices to auto-load
   - Select a voice (e.g., `en-Emma_woman`)

4. **Test TTS:**
   - Click **"Test TTS"** button
   - You should hear: "This is a test of the text-to-speech system."
   - If you hear audio, the integration is working! ✅

### Step 6: Test Full TTS Workflow

1. **Create or open a story** in Kahani
2. **Generate a new scene** (or use existing scene)
3. **Click the speaker icon** (🔊) on a scene
4. **Audio should start playing** - this tests the full integration!

### Troubleshooting

#### VibeVoice Service Issues

**Port 3000 already in use:**
```bash
# Find what's using port 3000
lsof -i :3000

# Kill it or use a different port
# Change --port 3001 in VibeVoice command
# Update API URL in Kahani to http://localhost:3001
```

**Model download fails:**
- Check internet connection
- Try downloading manually from HuggingFace
- Check disk space (model is ~500MB)

**Service crashes on startup:**
- Check logs: `docker logs vibevoice-tts` or terminal output
- Verify PyTorch is installed correctly
- Try CPU mode if GPU fails: `--device cpu`

#### Kahani Connection Issues

**"Provider not found" error:**
- Make sure you've restarted the Kahani backend after adding websockets
- Check that `vibevoice.py` is in `backend/app/services/tts/providers/`
- Verify imports in `__init__.py` files

**"Connection refused" or "WebSocket error":**
- Verify VibeVoice is running: `curl http://localhost:3000/config`
- Check firewall settings
- Verify API URL in settings matches VibeVoice port

**No voices available:**
- Check VibeVoice logs for errors
- Verify `/config` endpoint works: `curl http://localhost:3000/config`
- Check Kahani backend logs for errors

**Audio doesn't play:**
- Check browser console for errors
- Verify audio format (should be WAV)
- Test with a different voice
- Check Kahani backend logs for WebSocket errors

### Quick Verification Checklist

- [ ] VibeVoice service is running (`curl http://localhost:3000/config` works)
- [ ] Kahani backend has websockets installed
- [ ] Kahani backend is running
- [ ] VibeVoice appears in provider dropdown
- [ ] Voices load successfully
- [ ] Test TTS button works
- [ ] Scene narration works

### Expected Behavior

When everything works correctly:
1. VibeVoice service starts and loads model (~30-60 seconds first time)
2. Kahani can discover VibeVoice voices via `/config` endpoint
3. Test TTS generates audio successfully
4. Scene narration plays audio when clicking speaker icon
5. Audio quality is clear and natural

### Next Steps After Testing

Once testing is successful:
1. Consider setting up GPU support for faster generation
2. Configure voice presets if you have custom voices
3. Adjust `cfg_scale` and `inference_steps` for quality/speed balance
4. Set up as a production service with proper resource limits
