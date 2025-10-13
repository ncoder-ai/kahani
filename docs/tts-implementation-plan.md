# 🎙️ TTS (Text-to-Speech) Implementation Plan for Kahani

## Overview
Add OpenAI-compatible TTS narration capabilities to Kahani, allowing users to listen to their stories with customizable voices and settings.

## Test Configuration
- **Endpoint**: `http://172.16.23.80:4321/audio/speech`
- **Available Voice**: `Sara`
- **Max Chunk Size**: 280 characters

---

## 📋 Table of Contents
1. [Backend Architecture](#backend-architecture)
2. [Frontend Architecture](#frontend-architecture)
3. [Database Schema](#database-schema)
4. [API Endpoints](#api-endpoints)
5. [UI/UX Design](#uiux-design)
6. [Implementation Phases](#implementation-phases)
7. [Technical Specifications](#technical-specifications)

---

## 🏗️ Backend Architecture

### 1. New Models & Database Schema

#### TTS Settings Model (`backend/app/models/tts_settings.py`)
```python
class TTSSettings(Base):
    """User TTS configuration - Provider Agnostic"""
    __tablename__ = "tts_settings"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    
    # Provider Selection (Extensible!)
    tts_enabled = Column(Boolean, default=False)
    tts_provider_type = Column(String(50), default="openai-compatible")
    # Supported: openai-compatible, elevenlabs, google, azure, aws-polly
    
    # Provider Configuration
    tts_api_url = Column(String(500), default="")
    tts_api_key = Column(String(500), default="")
    tts_timeout = Column(Integer, default=30)
    tts_retry_attempts = Column(Integer, default=3)
    
    # Provider-Specific Settings (JSON for flexibility)
    tts_custom_headers = Column(JSON, default=None)  # Custom HTTP headers
    tts_extra_params = Column(JSON, default=None)    # Provider-specific params
    # Example: {"model_id": "eleven_monolingual_v1", "stability": 0.75}
    
    # Voice Settings
    default_voice = Column(String(100), default="Sara")
    speech_speed = Column(Float, default=1.0)  # 0.5 - 2.0
    audio_format = Column(String(10), default="mp3")  # mp3, aac, opus
    
    # Behavior Settings
    auto_narrate_new_scenes = Column(Boolean, default=False)
    chunk_size = Column(Integer, default=280)  # Max characters per chunk
    stream_audio = Column(Boolean, default=True)
    
    # Advanced Settings
    pause_between_paragraphs = Column(Integer, default=500)  # ms
    volume = Column(Float, default=1.0)  # 0.0 - 1.0
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", back_populates="tts_settings")
```

#### Voice Preset Model (`backend/app/models/tts_voice_preset.py`)
```python
class TTSVoicePreset(Base):
    """Custom voice presets per user"""
    __tablename__ = "tts_voice_presets"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    name = Column(String(100))  # e.g., "Narrator", "Character 1"
    voice_id = Column(String(100))  # e.g., "Sara", "John"
    speed = Column(Float, default=1.0)
    pitch = Column(Float, default=1.0)  # If supported by API
    is_default = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="tts_voice_presets")
```

#### Scene Audio Cache Model (`backend/app/models/scene_audio.py`)
```python
class SceneAudio(Base):
    """Cache generated TTS audio for scenes"""
    __tablename__ = "scene_audio"
    
    id = Column(Integer, primary_key=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # Audio file info
    audio_url = Column(String(500))  # Path to audio file
    audio_format = Column(String(10))  # mp3, aac
    file_size = Column(Integer)  # bytes
    duration = Column(Float)  # seconds
    
    # Generation metadata
    voice_used = Column(String(100))
    speed_used = Column(Float)
    chunk_count = Column(Integer)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    scene = relationship("Scene", back_populates="audio_cache")
    user = relationship("User")
```

### 2. New Service Layer (Extensible Provider Architecture)

**See detailed architecture in:** `docs/tts-provider-architecture.md`

#### TTS Provider System
The TTS system uses a **Strategy + Factory + Registry pattern** for extensibility:

- **Base Provider Interface** (`base.py`): Abstract class defining TTS operations
- **Provider Registry** (`registry.py`): Plugin system for provider registration
- **Provider Factory** (`factory.py`): Dynamic provider instantiation
- **Provider Implementations** (`providers/`): Concrete provider classes

```
backend/app/services/tts/
├── base.py                    # Abstract TTSProviderBase
├── registry.py                # TTSProviderRegistry
├── factory.py                 # TTSProviderFactory
├── service.py                 # Main TTS service (provider-agnostic)
├── chunker.py                 # Text chunking utilities
└── providers/
    ├── openai_compatible.py  # Default provider
    ├── elevenlabs.py          # ElevenLabs provider
    ├── google_tts.py          # Google Cloud TTS
    ├── azure_tts.py           # Azure Cognitive Services
    └── aws_polly.py           # AWS Polly
```

#### Adding New Providers (Zero Core Changes!)
```python
from ..base import TTSProviderBase
from ..registry import TTSProviderRegistry

@TTSProviderRegistry.register("my-provider")
class MyTTSProvider(TTSProviderBase):
    
    @property
    def provider_name(self) -> str:
        return "my-provider"
    
    # Implement required methods
    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        # Provider-specific implementation
        pass
    
    async def get_voices(self) -> List[Voice]:
        # Provider-specific voice list
        pass
```

#### TTS Service (Provider-Agnostic)
```python
class TTSService:
    """
    Main TTS service - delegates to appropriate provider.
    Handles business logic, caching, and chunking.
    """
    
    async def generate_scene_audio(
        self,
        scene_id: int,
        user_id: int,
        db: Session
    ) -> SceneAudio:
        """
        Generate audio using user's configured provider.
        Automatically handles chunking and caching.
        """
        # Get user settings
        settings = self._get_settings(user_id, db)
        
        # Create provider instance (could be OpenAI, ElevenLabs, etc.)
        provider = TTSProviderFactory.create_provider(settings)
        
        # Generate audio using provider
        # ...
        
    async def stream_scene_audio(
        self,
        scene_id: int,
        user_id: int,
        db: Session
    ):
        """Stream audio generation in real-time"""
        
    async def get_available_voices(
        self,
        user_id: int,
        db: Session
    ) -> List[Voice]:
        """Get voices from user's configured provider"""
```

#### Benefits of Extensible Architecture:
✅ **Add new providers without modifying core code**  
✅ **Each provider implements standard interface**  
✅ **Automatic provider discovery via registry**  
✅ **Provider-specific settings via JSON**  
✅ **Easy to test with mock providers**  
✅ **Third-party plugins supported**

### 3. Text Chunking Strategy

```python
class TextChunker:
    """Smart text chunking for TTS"""
    
    @staticmethod
    def chunk_by_paragraphs(text: str, max_size: int = 280) -> List[str]:
        """
        Split text into chunks, preferring paragraph boundaries.
        
        Priority:
        1. Split at paragraph breaks (\n\n)
        2. Split at sentence ends (. ! ?)
        3. Split at comma or space if necessary
        4. Never split mid-word
        """
        chunks = []
        paragraphs = text.split('\n\n')
        
        for para in paragraphs:
            if len(para) <= max_size:
                chunks.append(para)
            else:
                # Split long paragraphs by sentences
                sentences = re.split(r'([.!?]+\s+)', para)
                current_chunk = ""
                
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) <= max_size:
                        current_chunk += sentence
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sentence
                        
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    
        return chunks
```

---

## 🎨 Frontend Architecture

### 1. New Components

#### TTSPlayer Component (`frontend/src/components/TTSPlayer.tsx`)
```typescript
interface TTSPlayerProps {
  sceneId: number;
  sceneContent: string;
  autoPlay?: boolean;
  compact?: boolean;
}

// Features:
// - Play/Pause button
// - Progress bar
// - Speed control (0.5x - 2x)
// - Volume control
// - Download audio button
// - Loading/buffering states
// - Error handling
```

#### TTSSettingsPanel Component (`frontend/src/components/TTSSettingsPanel.tsx`)
```typescript
// Integrated into user settings
// Features:
// - Enable/Disable TTS
// - API URL configuration
// - Voice selection dropdown
// - Speech speed slider
// - Audio format selection
// - Auto-narrate toggle
// - Test TTS button with sample text
// - Voice preview player
```

#### SceneNarrationButton Component (`frontend/src/components/SceneNarrationButton.tsx`)
```typescript
interface SceneNarrationButtonProps {
  sceneId: number;
  sceneContent: string;
  compact?: boolean;
}

// Speaker icon button overlaid on scene
// States: idle, loading, playing, paused, error
```

### 2. Audio Management Hook

#### useTTS Hook (`frontend/src/hooks/useTTS.ts`)
```typescript
interface UseTTSReturn {
  isPlaying: boolean;
  isPaused: boolean;
  isLoading: boolean;
  progress: number; // 0-100
  duration: number; // seconds
  currentTime: number;
  error: string | null;
  
  play: (sceneId: number) => Promise<void>;
  pause: () => void;
  resume: () => void;
  stop: () => void;
  seek: (time: number) => void;
  setSpeed: (speed: number) => void;
  setVolume: (volume: number) => void;
  
  generateAudio: (text: string, voice?: string) => Promise<void>;
  prefetchAudio: (sceneId: number) => Promise<void>;
}

// Uses Web Audio API for playback control
// Handles audio caching
// Manages playback queue for multi-chunk scenes
```

### 3. Audio State Management

#### Add to Zustand Store (`frontend/src/store/index.ts`)
```typescript
interface TTSState {
  enabled: boolean;
  currentlyPlaying: number | null; // scene_id
  queue: number[]; // scene_ids
  settings: {
    voice: string;
    speed: number;
    autoNarrate: boolean;
    volume: number;
  };
  
  setEnabled: (enabled: boolean) => void;
  playScene: (sceneId: number) => void;
  stopPlayback: () => void;
  updateSettings: (settings: Partial<TTSState['settings']>) => void;
}
```

---

## 🗄️ Database Schema Changes

### Migration Script
```sql
-- Add TTS settings table (Provider-Agnostic Design)
CREATE TABLE tts_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    
    -- Provider selection (extensible!)
    tts_enabled BOOLEAN DEFAULT FALSE,
    tts_provider_type VARCHAR(50) DEFAULT 'openai-compatible',
    -- Supported: openai-compatible, elevenlabs, google, azure, aws-polly, etc.
    
    -- Provider configuration
    tts_api_url VARCHAR(500) DEFAULT '',
    tts_api_key VARCHAR(500) DEFAULT '',
    tts_timeout INTEGER DEFAULT 30,
    tts_retry_attempts INTEGER DEFAULT 3,
    
    -- Provider-specific settings (JSON for flexibility)
    tts_custom_headers JSON DEFAULT NULL,
    tts_extra_params JSON DEFAULT NULL,
    -- Example JSON: {"model_id": "eleven_monolingual_v1", "stability": 0.75}
    
    -- Voice settings
    default_voice VARCHAR(100) DEFAULT 'Sara',
    speech_speed FLOAT DEFAULT 1.0,
    audio_format VARCHAR(10) DEFAULT 'mp3',
    
    -- Behavior
    auto_narrate_new_scenes BOOLEAN DEFAULT FALSE,
    chunk_size INTEGER DEFAULT 280,
    stream_audio BOOLEAN DEFAULT TRUE,
    pause_between_paragraphs INTEGER DEFAULT 500,
    volume FLOAT DEFAULT 1.0,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Add voice presets table
CREATE TABLE tts_voice_presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    voice_id VARCHAR(100) NOT NULL,
    speed FLOAT DEFAULT 1.0,
    pitch FLOAT DEFAULT 1.0,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Add scene audio cache table
CREATE TABLE scene_audio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    audio_url VARCHAR(500) NOT NULL,
    audio_format VARCHAR(10) NOT NULL,
    file_size INTEGER NOT NULL,
    duration FLOAT NOT NULL,
    voice_used VARCHAR(100),
    speed_used FLOAT,
    chunk_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Add indexes
CREATE INDEX idx_scene_audio_scene ON scene_audio(scene_id);
CREATE INDEX idx_scene_audio_user ON scene_audio(user_id);
CREATE INDEX idx_tts_voice_presets_user ON tts_voice_presets(user_id);
```

---

## 🔌 Supported TTS Providers

### Built-in Providers

#### 1. OpenAI-Compatible (Default)
- **Use Cases**: Kokoro FastAPI, ChatterboxTTS, LM Studio TTS, OpenAI
- **Endpoint**: `/audio/speech`
- **Strengths**: Simple API, widely supported format
- **Example**: `http://172.16.23.80:4321` (Kokoro)

#### 2. ElevenLabs
- **Use Cases**: High-quality voices, voice cloning
- **Endpoint**: `/v1/text-to-speech/{voice_id}`
- **Strengths**: Best voice quality, emotion control
- **Example**: `https://api.elevenlabs.io`

#### 3. Google Cloud TTS
- **Use Cases**: Multi-language, WaveNet voices
- **Endpoint**: `/v1/text:synthesize`
- **Strengths**: 220+ voices, 40+ languages
- **Example**: `https://texttospeech.googleapis.com`

#### 4. Azure Cognitive Services
- **Use Cases**: Neural voices, SSML support
- **Endpoint**: `/cognitiveservices/v1`
- **Strengths**: Enterprise-ready, SSML
- **Example**: `https://{region}.tts.speech.microsoft.com`

#### 5. AWS Polly
- **Use Cases**: AWS integration, neural voices
- **Endpoint**: AWS API
- **Strengths**: Cost-effective, reliable
- **Example**: `https://polly.{region}.amazonaws.com`

### Adding Custom Providers

See `docs/tts-provider-architecture.md` for detailed guide on creating custom providers.

**Quick Example**:
```python
@TTSProviderRegistry.register("my-tts")
class MyTTSProvider(TTSProviderBase):
    # Implement required methods
    pass
```

---

## 🔌 API Endpoints

### TTS Settings Endpoints

```
GET    /api/tts/settings              - Get user TTS settings
PUT    /api/tts/settings              - Update TTS settings
POST   /api/tts/test                  - Test TTS with sample text
GET    /api/tts/voices                - Get available voices from API
```

### TTS Generation Endpoints

```
POST   /api/tts/generate/{scene_id}   - Generate audio for scene
GET    /api/tts/audio/{scene_id}      - Get cached audio for scene
DELETE /api/tts/audio/{scene_id}      - Delete cached audio
GET    /api/tts/stream/{scene_id}     - Stream audio generation (SSE)
POST   /api/tts/synthesize            - Generate audio from custom text
```

### Voice Presets Endpoints

```
GET    /api/tts/presets               - List user voice presets
POST   /api/tts/presets               - Create voice preset
PUT    /api/tts/presets/{id}          - Update voice preset
DELETE /api/tts/presets/{id}          - Delete voice preset
```

### Example Request/Response

```json
// POST /api/tts/generate/{scene_id}
Request:
{
  "voice": "Sara",
  "speed": 1.0,
  "format": "mp3"
}

Response:
{
  "audio_url": "/audio/scene_123_user_1.mp3",
  "duration": 45.5,
  "file_size": 720000,
  "chunk_count": 3,
  "format": "mp3"
}

// POST /api/tts/synthesize
Request:
{
  "text": "This is a test narration.",
  "voice": "Sara",
  "speed": 1.2,
  "format": "mp3"
}

Response: (binary audio data or audio URL)
```

---

## 🎨 UI/UX Design

### 1. Scene Display with TTS

```
┌─────────────────────────────────────────────────┐
│ Scene 1: The Beginning                      [🔊] │ ← Speaker button
├─────────────────────────────────────────────────┤
│                                                   │
│ The story begins on a dark and stormy night...   │
│                                                   │
│ [If TTS is playing for this scene:]              │
│ ┌───────────────────────────────────────────┐   │
│ │ 🔊 Playing...  [⏸️]  [■]  1.0x  🔊 ▁▂▃▅  │   │
│ │ ▰▰▰▰▰▰▰▰▱▱▱▱▱▱▱▱▱▱▱▱ 45% (0:23 / 0:52)  │   │
│ └───────────────────────────────────────────┘   │
│                                                   │
└─────────────────────────────────────────────────┘
```

### 2. TTS Settings Panel (in User Settings)

```
┌─────────────────────────────────────────────────┐
│ 🎙️ Text-to-Speech Settings                      │
├─────────────────────────────────────────────────┤
│                                                   │
│ ☑️ Enable TTS Narration                          │
│                                                   │
│ Provider Selection:                               │
│ ┌─────────────────────────────────────────────┐ │
│ │ ⚫ OpenAI-Compatible (Kokoro, ChatterboxTTS)│ │
│ │ ⚪ ElevenLabs                               │ │
│ │ ⚪ Google Cloud TTS                         │ │
│ │ ⚪ Azure Cognitive Services                 │ │
│ │ ⚪ AWS Polly                                │ │
│ └─────────────────────────────────────────────┘ │
│                                                   │
│ API Configuration:                                │
│ ┌─────────────────────────────────────────────┐ │
│ │ API URL: http://172.16.23.80:4321         ▼│ │
│ └─────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────┐ │
│ │ API Key: ********************************  │ │
│ └─────────────────────────────────────────────┘ │
│                                                   │
│ [Advanced Settings ▼]                             │
│ ┌─────────────────────────────────────────────┐ │
│ │ Timeout: 30 seconds                         │ │
│ │ Retry Attempts: 3                           │ │
│ │ Provider-Specific Settings:                 │ │
│ │ ┌─────────────────────────────────────────┐ │ │
│ │ │ {                                       │ │ │
│ │ │   "max_text_length": 280,               │ │ │
│ │ │   "voices": ["Sara", "John"]            │ │ │
│ │ │ }                                       │ │ │
│ │ └─────────────────────────────────────────┘ │ │
│ └─────────────────────────────────────────────┘ │
│                                                   │
│ Voice Settings:                                   │
│ ┌─────────────────────────────────────────────┐ │
│ │ Voice: Sara                  [Refresh List]▼│ │
│ └─────────────────────────────────────────────┘ │
│                                                   │
│ Speech Speed: 1.0x                                │
│ ┌────────────●──────────────────────────────┐   │
│ 0.5x                                      2.0x   │
│                                                   │
│ Audio Format: ⚫ MP3  ⚪ AAC  ⚪ Opus            │
│                                                   │
│ Behavior:                                         │
│ ☑️ Auto-narrate new scenes                        │
│ ☑️ Stream audio (faster start)                    │
│ ☐ Continue to next scene automatically           │
│                                                   │
│ Advanced:                                         │
│ Chunk Size: 280 characters                        │
│ Pause between paragraphs: 500ms                   │
│                                                   │
│ [Test TTS] [Save Settings]                       │
│                                                   │
└─────────────────────────────────────────────────┘
```

### 3. Scene Narration Button States

```
Idle:     [🔊]  - Gray, clickable
Loading:  [⏳]  - Spinning animation
Playing:  [⏸️]  - Blue/green, animated waves
Paused:   [▶️]  - Yellow
Error:    [❌]  - Red with tooltip
```

### 4. TTS Player Controls (Expanded)

```
┌─────────────────────────────────────────────────┐
│ 🎧 Scene Narration                                │
├─────────────────────────────────────────────────┤
│ Voice: Sara                        Speed: 1.0x   │
│                                                   │
│        [⏮️]  [▶️]  [⏸️]  [⏭️]                    │
│                                                   │
│ ▰▰▰▰▰▰▰▰▰▰▰▱▱▱▱▱▱▱▱▱ 55%                        │
│ 0:28 / 0:52                                       │
│                                                   │
│ Speed: [0.5x] [0.75x] [1.0x] [1.25x] [1.5x] [2x]│
│                                                   │
│ Volume: ┌────────●──────────┐ 80%                │
│                                                   │
│ [💾 Download] [🔄 Regenerate] [✕ Close]          │
└─────────────────────────────────────────────────┘
```

### 5. Auto-Narration Notification

```
┌─────────────────────────────────────────────────┐
│ 🔊 Auto-narrating new scene...                   │
│ [Disable Auto-Narrate] [✕]                       │
└─────────────────────────────────────────────────┘
```

---

## 🚀 Implementation Phases

### Phase 1: Backend Foundation (Week 1)
**Goal**: Basic TTS infrastructure

- [ ] Create database models (TTSSettings, SceneAudio)
- [ ] Create migration script
- [ ] Implement TTSClient for OpenAI-compatible APIs
- [ ] Create basic TTSService with text chunking
- [ ] Add TTS settings endpoints
- [ ] Test with http://172.16.23.80:4321 endpoint

**Deliverables**:
- Working TTS API integration
- Text chunking by paragraphs
- Basic audio generation endpoint

### Phase 2: Audio Generation & Caching (Week 1-2)
**Goal**: Generate and store audio files

- [ ] Implement audio file storage (backend/data/audio/)
- [ ] Add SceneAudio caching layer
- [ ] Create generate_scene_audio endpoint
- [ ] Add audio file serving endpoint
- [ ] Implement chunk concatenation for multi-part scenes
- [ ] Add cleanup for old cached audio

**Deliverables**:
- Cached audio files
- Efficient storage management
- Fast audio retrieval

### Phase 3: Frontend TTS Player (Week 2)
**Goal**: Basic playback UI

- [ ] Create TTSPlayer component
- [ ] Implement useTTS hook with Web Audio API
- [ ] Add play/pause/stop controls
- [ ] Create progress bar
- [ ] Add loading states
- [ ] Implement error handling

**Deliverables**:
- Working audio player
- Basic playback controls
- Progress tracking

### Phase 4: Scene Integration (Week 2-3)
**Goal**: TTS in scene display

- [ ] Add SceneNarrationButton to SceneDisplay
- [ ] Integrate TTSPlayer into scene view
- [ ] Add TTS state to Zustand store
- [ ] Implement auto-narration for new scenes
- [ ] Add narration queue for multiple scenes

**Deliverables**:
- Speaker button on each scene
- Auto-narration functionality
- Seamless scene-to-scene playback

### Phase 5: Advanced Controls (Week 3)
**Goal**: Full playback control

- [ ] Add speed control (0.5x - 2x)
- [ ] Add volume control
- [ ] Implement seek functionality
- [ ] Add keyboard shortcuts (Space, Arrow keys)
- [ ] Create download audio button
- [ ] Add regenerate audio option

**Deliverables**:
- Complete playback controls
- Keyboard navigation
- Audio export

### Phase 6: Settings & Configuration (Week 3-4)
**Goal**: User customization

- [ ] Create TTSSettingsPanel component
- [ ] Add TTS settings to user settings page
- [ ] Implement voice selection dropdown
- [ ] Add API configuration UI
- [ ] Create "Test TTS" functionality
- [ ] Add voice preview player

**Deliverables**:
- Complete settings UI
- Voice management
- API configuration

### Phase 7: Streaming & Performance (Week 4)
**Goal**: Real-time audio streaming

- [ ] Implement streaming TTS endpoint (SSE)
- [ ] Add client-side streaming playback
- [ ] Optimize chunk processing
- [ ] Add audio prefetching
- [ ] Implement progressive loading

**Deliverables**:
- Streaming audio generation
- Faster playback start
- Optimized performance

### Phase 8: Polish & Testing (Week 4-5)
**Goal**: Production-ready feature

- [ ] Add comprehensive error handling
- [ ] Implement retry logic for failed generations
- [ ] Add loading skeletons
- [ ] Create user documentation
- [ ] Add analytics/telemetry
- [ ] Performance testing
- [ ] Cross-browser testing
- [ ] Mobile optimization

**Deliverables**:
- Polished UI/UX
- Robust error handling
- Documentation

---

## 🔧 Technical Specifications

### Audio Format Specifications

```python
AUDIO_FORMATS = {
    "mp3": {
        "mime_type": "audio/mpeg",
        "bitrate": "128k",  # Good quality, reasonable size
        "extension": ".mp3"
    },
    "aac": {
        "mime_type": "audio/aac",
        "bitrate": "96k",  # Better compression than MP3
        "extension": ".aac"
    },
    "opus": {
        "mime_type": "audio/opus",
        "bitrate": "64k",  # Best compression for speech
        "extension": ".opus"
    }
}
```

### File Storage Structure

```
backend/data/audio/
├── user_1/
│   ├── scene_123_v1.mp3
│   ├── scene_123_v2.mp3  # Regenerated with different voice
│   ├── scene_124_v1.mp3
│   └── ...
├── user_2/
│   └── ...
└── temp/  # For streaming chunks
    └── ...
```

### Chunking Algorithm

```python
def chunk_text_smart(text: str, max_size: int = 280) -> List[str]:
    """
    Smart text chunking that respects:
    1. Paragraph boundaries (\n\n)
    2. Sentence boundaries (. ! ?)
    3. Clause boundaries (, ; :)
    4. Never splits words
    
    Returns list of chunks ready for TTS API
    """
    # Implementation prioritizes natural breaks
```

### OpenAI-Compatible TTS API Format

```python
# Request format
POST /audio/speech
Content-Type: application/json

{
    "input": "Text to synthesize (max 280 chars)",
    "voice": "Sara",
    "speed": 1.0,
    "response_format": "mp3"  # optional
}

# Response: binary audio data (audio/mpeg)
```

### Performance Targets

- **Initial playback start**: < 2 seconds (with streaming)
- **Cache hit response**: < 100ms
- **Audio generation**: < 5 seconds per chunk
- **File size**: ~100KB per minute of speech (MP3 128kbps)
- **Concurrent generations**: Up to 3 per user

### Error Handling

```typescript
enum TTSErrorType {
  API_UNREACHABLE = "API_UNREACHABLE",
  INVALID_VOICE = "INVALID_VOICE",
  TEXT_TOO_LONG = "TEXT_TOO_LONG",
  GENERATION_FAILED = "GENERATION_FAILED",
  PLAYBACK_ERROR = "PLAYBACK_ERROR",
  STORAGE_ERROR = "STORAGE_ERROR"
}

// User-friendly error messages
ERROR_MESSAGES = {
  API_UNREACHABLE: "Cannot connect to TTS service. Check your settings.",
  INVALID_VOICE: "Selected voice is not available.",
  TEXT_TOO_LONG: "Scene text is too long. Try breaking it into smaller parts.",
  // ...
}
```

---

## 📱 Mobile Considerations

### Responsive Design
- Compact player controls for mobile
- Touch-friendly buttons (min 44px)
- Swipe gestures for seek
- Background audio support (PWA)

### Performance
- Lazy-load audio player
- Preload only current + next scene
- Compress audio more aggressively for mobile
- Use native audio element on iOS for background play

---

## 🔐 Security Considerations

1. **API Key Storage**: Encrypt TTS API keys in database
2. **Rate Limiting**: Limit TTS generations per user per hour
3. **File Access Control**: Only serve audio files to scene owner
4. **Storage Quotas**: Implement per-user audio storage limits
5. **Validation**: Sanitize text input before sending to TTS API

---

## 📊 Analytics & Monitoring

Track:
- TTS usage per user
- Average audio generation time
- Cache hit rate
- Popular voices
- Error rates by type
- Storage usage

---

## 🎯 Success Metrics

- **Adoption**: 50% of active users enable TTS within 1 month
- **Performance**: 90% of audio starts playing within 2 seconds
- **Quality**: < 5% error rate on audio generation
- **Satisfaction**: User feedback rating > 4.0/5.0
- **Efficiency**: 80% cache hit rate for repeated scene plays

---

## 🔮 Future Enhancements (Post-MVP)

1. **Multi-Voice Support**: Different voices for different characters
2. **Emotional Tone Control**: Adjust voice emotion based on scene
3. **Background Music**: Add ambient music mixing
4. **Voice Cloning**: Custom user voice training
5. **STT Integration**: Voice commands and dictation (Whisper)
6. **Offline Mode**: Download entire story audio
7. **Podcast Export**: Export story as podcast episode
8. **Real-time Collaboration**: Live narration sessions
9. **Voice Profiles**: Character-specific voice assignments
10. **AI Voice Direction**: Auto-detect emotions and adjust tone

---

## 📝 Documentation Tasks

- [ ] User guide: "How to enable TTS"
- [ ] Admin guide: "Setting up TTS service"
- [ ] API documentation: TTS endpoints
- [ ] Developer guide: Extending TTS functionality
- [ ] Troubleshooting guide: Common TTS issues

---

## ✅ Testing Strategy

### Unit Tests
- Text chunking algorithm
- Audio file management
- TTS client API calls

### Integration Tests
- End-to-end audio generation
- Cache management
- Settings persistence

### E2E Tests
- User enables TTS and plays scene
- Auto-narration on new scene generation
- Settings update and playback

### Performance Tests
- Concurrent audio generation
- Large scene handling
- Cache efficiency

---

## 🎬 Demo Scenarios

### Scenario 1: First-Time TTS User
1. User opens settings
2. Enables TTS and configures API
3. Tests with sample text
4. Returns to story
5. Clicks speaker button on scene
6. Audio plays immediately (new generation)

### Scenario 2: Returning User with Auto-Narrate
1. User generates new scene
2. Auto-narration begins immediately
3. User continues writing while listening
4. Next scene auto-plays after completion

### Scenario 3: Voice Customization
1. User creates voice preset "Villain Voice"
2. Assigns to character
3. Plays scene with multiple characters
4. Different voices for different characters

---

## 📚 Dependencies

### Backend
```txt
# Add to requirements.txt
httpx>=0.24.0  # Async HTTP client
pydub>=0.25.1  # Audio manipulation
```

### Frontend
```json
// Add to package.json
{
  "dependencies": {
    "howler": "^2.2.3",  // Advanced audio library
    "wavesurfer.js": "^7.0.0"  // Audio visualization (optional)
  }
}
```

---

## 🎉 Conclusion

This comprehensive plan provides a structured approach to implementing TTS in Kahani. The phased implementation allows for iterative development and testing, ensuring a robust and user-friendly feature.

**Next Steps**:
1. Review and approve this plan
2. Begin Phase 1 implementation
3. Set up development environment with test TTS API
4. Create initial database migrations

**Estimated Total Timeline**: 4-5 weeks for full implementation
