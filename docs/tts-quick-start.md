# TTS Implementation - Quick Start Guide

## 🎯 Overview
Adding OpenAI-compatible Text-to-Speech narration to Kahani with the following key features:

## ✨ Core Features
1. ✅ User-configurable TTS API settings (URL, API key, voice, speed)
2. ✅ Smart text chunking (280 char max, paragraph-aware)
3. ✅ Streaming audio generation for fast playback
4. ✅ Auto-narration for newly generated scenes
5. ✅ Enable/disable TTS globally
6. ✅ Per-scene speaker buttons for on-demand narration
7. ✅ MP3/AAC format support for efficient storage

## 🧪 Test Configuration
- **Endpoint**: `http://172.16.23.80:4321/audio/speech`
- **Voice**: `Sara`
- **Max Chunk**: 280 characters

## 🏗️ Architecture Overview

### Backend
```
backend/
├── app/
│   ├── models/
│   │   ├── tts_settings.py      # User TTS configuration
│   │   ├── tts_voice_preset.py  # Custom voice presets
│   │   └── scene_audio.py       # Audio cache
│   ├── services/
│   │   └── tts/
│   │       ├── client.py        # OpenAI-compatible API client
│   │       ├── service.py       # TTS business logic
│   │       └── chunker.py       # Smart text chunking
│   └── api/
│       └── tts.py               # TTS endpoints
└── data/
    └── audio/                   # Audio file storage
        └── user_{id}/
            └── scene_{id}_v{n}.mp3
```

### Frontend
```
frontend/src/
├── components/
│   ├── TTSPlayer.tsx            # Main audio player
│   ├── TTSSettingsPanel.tsx     # Settings UI
│   └── SceneNarrationButton.tsx # Per-scene speaker button
├── hooks/
│   └── useTTS.ts                # Audio playback hook
└── store/
    └── ttsStore.ts              # TTS state management
```

## 📋 Database Schema

### tts_settings
- user_id, tts_enabled, tts_api_url, tts_api_key
- default_voice, speech_speed, audio_format
- auto_narrate_new_scenes, chunk_size, stream_audio

### scene_audio (cache)
- scene_id, user_id, audio_url, audio_format
- file_size, duration, voice_used, speed_used

## 🔌 Key API Endpoints

```bash
# Settings
GET    /api/tts/settings
PUT    /api/tts/settings
POST   /api/tts/test

# Audio Generation
POST   /api/tts/generate/{scene_id}
GET    /api/tts/audio/{scene_id}
GET    /api/tts/stream/{scene_id}   # Streaming
DELETE /api/tts/audio/{scene_id}

# Voices
GET    /api/tts/voices
```

## 🎨 UI Components

### 1. Scene with TTS Button
```
┌────────────────────────────────┐
│ Scene 1: Title          [🔊]   │
│ Scene content...                │
│ [Playing: ▰▰▰▱▱ 60% 0:12/0:20] │
└────────────────────────────────┘
```

### 2. TTS Settings
- Enable/Disable toggle
- API URL & Key configuration
- Voice selector
- Speed slider (0.5x - 2.0x)
- Format selection (MP3/AAC)
- Auto-narrate toggle
- Test button

### 3. Audio Player
- Play/Pause/Stop
- Progress bar with seek
- Speed control
- Volume control
- Download button

## 🚀 Implementation Phases

### Phase 1: Backend Core (Week 1)
- Database models & migrations
- TTS client for OpenAI API
- Text chunking algorithm
- Basic generate endpoint

### Phase 2: Audio Management (Week 1-2)
- File storage system
- Audio caching layer
- Serve audio endpoint
- Cleanup old audio

### Phase 3: Frontend Player (Week 2)
- TTSPlayer component
- useTTS hook
- Basic playback controls
- Loading states

### Phase 4: Scene Integration (Week 2-3)
- Speaker button on scenes
- Auto-narration for new scenes
- TTS state management
- Scene playback queue

### Phase 5: Advanced Features (Week 3-4)
- Speed/volume controls
- Streaming audio
- Settings UI
- Voice management
- Performance optimization

## 💡 Key Technical Decisions

### Text Chunking Strategy
```python
# Priority order:
1. Split at paragraph breaks (\n\n)
2. Split at sentence ends (. ! ?)
3. Split at commas if needed
4. Never split mid-word
5. Max 280 chars per chunk
```

### Audio Format
- **Primary**: MP3 @ 128kbps (~100KB/min)
- **Alternative**: AAC @ 96kbps (better compression)
- **Future**: Opus @ 64kbps (best for speech)

### Caching Strategy
- Cache audio files per user/scene/voice combination
- Auto-cleanup audio older than 30 days
- Regenerate if voice/speed changes
- Serve from cache when available (<100ms response)

### Streaming Approach
- Generate and stream first chunk immediately
- Generate remaining chunks in background
- Progressive playback with seamless chunk transitions
- Prefetch next scene audio when near end

## 🔐 Security

1. **Encrypt API keys** in database
2. **Rate limit** TTS generations (e.g., 50/hour per user)
3. **Validate** text input before sending to API
4. **Restrict** audio file access to owner only
5. **Quota** storage limits per user

## 📊 Success Metrics

- **Adoption**: 50% of users enable TTS
- **Performance**: Audio starts in < 2 seconds
- **Quality**: < 5% generation error rate
- **Cache efficiency**: 80% cache hit rate

## 🎯 Testing Plan

1. **Unit**: Chunking algorithm, API client
2. **Integration**: End-to-end audio generation
3. **E2E**: User workflow from settings to playback
4. **Performance**: Concurrent generations, large scenes
5. **Mobile**: Touch controls, background audio

## 📝 Documentation Needed

- [ ] User guide: Enabling and using TTS
- [ ] Admin guide: TTS service setup
- [ ] API docs: TTS endpoints
- [ ] Troubleshooting: Common issues

## 🔮 Future Enhancements

- Multiple voices for different characters
- Emotional tone control
- Background music mixing
- Podcast export
- STT integration (Whisper)
- Offline audio download

## 🎬 Quick Demo Flow

1. User opens Settings → TTS
2. Enables TTS, enters API URL: `http://172.16.23.80:4321`
3. Selects voice: `Sara`, speed: `1.0x`
4. Clicks "Test TTS" - hears sample
5. Enables "Auto-narrate new scenes"
6. Returns to story, generates new scene
7. Audio begins playing automatically
8. User clicks speaker button on previous scene
9. Previous scene plays immediately (from cache)

## 📦 Dependencies to Add

```txt
# Backend (requirements.txt)
httpx>=0.24.0
pydub>=0.25.1

# Frontend (package.json)
"howler": "^2.2.3"
```

## ✅ Ready to Start!

See full details in: `/docs/tts-implementation-plan.md`

**First Task**: Create database migration for `tts_settings` table
