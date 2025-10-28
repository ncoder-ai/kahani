# Real-time STT Test Implementation

This branch implements a standalone test page for real-time Speech-to-Text using Whisper models with both GPU and CPU support.

## Features

- **Real-time transcription** using RealtimeSTT + faster-whisper
- **GPU/CPU auto-detection** - tries GPU first, falls back to CPU
- **Performance metrics** - latency, accuracy, throughput
- **WebSocket streaming** - low-latency audio processing
- **Voice Activity Detection** - automatic speech detection
- **Test page** - comprehensive testing interface

## Quick Start

1. **Install dependencies:**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. **Start the backend:**
   ```bash
   cd backend
   python -m uvicorn app.main:app --reload --port 9876
   ```

3. **Start the frontend:**
   ```bash
   cd frontend
   npm run dev
   ```

4. **Access the test page:**
   ```
   http://localhost:6789/stt-test
   ```

## Configuration

Edit `backend/app/config.py` to adjust STT settings:

```python
# STT Configuration
stt_model: str = "small"  # base, small, medium
stt_device: str = "auto"  # auto, cuda, cpu
stt_compute_type: str = "int8"  # int8, int8_float16, float16
stt_language: str = "en"
stt_vad_enabled: bool = True
stt_vad_sensitivity: int = 3  # 0-3 (aggressive to permissive)
```

## Testing Performance

The test page provides:

- **Real-time metrics**: Current latency, average latency, transcription count
- **Device info**: Shows which device (GPU/CPU) and model is being used
- **Live transcription**: Partial (gray) and final (white) text updates
- **Performance tracking**: Duration, word count, error handling

## Expected Performance

### GPU (CUDA)
- **Latency**: 200-500ms
- **VRAM**: 1-2GB (whisper-small)
- **RTF**: <0.3 (processes faster than real-time)

### CPU
- **Latency**: 1-3 seconds
- **RAM**: 2-4GB
- **RTF**: 0.5-1.0 (still usable for record-then-transcribe)

## Troubleshooting

1. **CUDA not available**: The system will automatically fall back to CPU
2. **Microphone permissions**: Browser will prompt for microphone access
3. **WebSocket connection**: Check browser console for connection errors
4. **Model download**: First run will download the Whisper model (~1GB)

## Next Steps

After testing performance:

1. **If latency <500ms**: Ready for app integration
2. **If latency >500ms**: Consider Parakeet-0.6B or optimization
3. **If CPU performance is acceptable**: Can deploy without GPU

## Files Added

- `backend/app/services/stt_service.py` - STT service with RealtimeSTT
- `backend/app/services/stt_session_manager.py` - WebSocket session management
- `backend/app/api/stt_websocket.py` - WebSocket endpoints
- `frontend/src/app/stt-test/page.tsx` - Test page UI
- `frontend/src/hooks/useRealtimeSTT.ts` - React hook for STT
- `frontend/src/utils/audioRecorder.ts` - Audio recording utility
