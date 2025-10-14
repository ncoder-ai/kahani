# Per-Provider TTS Settings Feature

## Overview
Users can now save separate TTS configurations for each provider (Chatterbox, Kokoro, OpenAI-compatible). When switching between providers, the system remembers each provider's settings instead of overwriting them.

## Changes Made

### Backend Changes

#### 1. New Database Model
**File**: `backend/app/models/tts_provider_config.py`
- Created `TTSProviderConfig` model to store per-provider configurations
- Each user can have one config per provider type
- Stores: api_url, api_key, voice_id, speed, timeout, extra_params
- Unique constraint on (user_id, provider_type)

#### 2. Database Migration
**File**: `backend/migrate_add_provider_configs.py`
- Migration script to create `tts_provider_configs` table
- Run with: `python migrate_add_provider_configs.py`
- ✅ Already executed successfully

#### 3. New API Endpoints
**File**: `backend/app/routers/tts.py`

Added three new endpoints:

1. **GET `/api/tts/provider-configs`**
   - Returns all saved provider configurations for the current user
   - Response: Array of TTSSettingsResponse objects

2. **GET `/api/tts/provider-configs/{provider_type}`**
   - Returns saved configuration for a specific provider
   - Returns 404 if no saved config exists
   - Response: TTSSettingsResponse object

3. **PUT `/api/tts/provider-configs/{provider_type}`**
   - Saves configuration for a specific provider
   - Creates new config if doesn't exist, updates if exists
   - Request body: TTSSettingsRequest
   - Response: TTSSettingsResponse object

### Frontend Changes

#### File: `frontend/src/components/TTSSettingsModal.tsx`

**State Management:**
- Added `providerConfigs` state to cache all saved provider configurations
- Loads on modal open via `loadAllProviderConfigs()`

**Provider Switching Logic:**
- `handleProviderChange()` now checks if saved config exists for the provider
- If config exists: loads saved settings (api_url, api_key, voice_id, speed, timeout, extra_params)
- If no config: uses default settings for that provider
- Provider-specific settings (Chatterbox params) are also restored

**Save Logic:**
- `handleSave()` now saves to two endpoints:
  1. `/api/tts/provider-configs/{provider_type}` - Saves provider-specific config
  2. `/api/tts/settings` - Updates global settings (for backward compatibility)
- Updates local `providerConfigs` cache after save

## User Experience

### Before
1. User configures Chatterbox with custom settings
2. User saves settings
3. User switches to Kokoro and configures it
4. User saves settings
5. **User switches back to Chatterbox → Settings are lost (default values)**

### After
1. User configures Chatterbox with custom settings
2. User saves settings
3. User switches to Kokoro and configures it
4. User saves settings
5. **User switches back to Chatterbox → Settings are restored! ✅**

## Testing

### Manual Testing Steps

1. **Setup Chatterbox:**
   - Open TTS Settings Modal
   - Select "Chatterbox" provider
   - Enter API URL: `http://localhost:8880/v1`
   - Test connection
   - Select a voice
   - Adjust Chatterbox settings (Exaggeration, Pace, Temperature)
   - Save settings

2. **Setup Kokoro:**
   - Switch to "Kokoro" provider
   - Enter API URL: `http://localhost:8188/v1`
   - Test connection
   - Select a voice
   - Save settings

3. **Verify Persistence:**
   - Switch back to "Chatterbox"
   - **Expected**: All Chatterbox settings are restored (URL, voice, Chatterbox params)
   - Switch to "Kokoro"
   - **Expected**: All Kokoro settings are restored

4. **Setup Third Provider:**
   - Switch to "OpenAI-compatible"
   - Configure settings
   - Save
   - Switch between all three providers
   - **Expected**: Each provider remembers its own settings

### API Testing

```bash
# Get all provider configs
curl -X GET "http://172.16.23.125:8000/api/tts/provider-configs" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get specific provider config
curl -X GET "http://172.16.23.125:8000/api/tts/provider-configs/chatterbox" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Save provider config
curl -X PUT "http://172.16.23.125:8000/api/tts/provider-configs/chatterbox" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider_type": "chatterbox",
    "api_url": "http://localhost:8880/v1",
    "api_key": "",
    "voice_id": "some_voice",
    "speed": 1.0,
    "timeout": 30,
    "extra_params": {
      "exaggeration": 0.5,
      "cfg_weight": 0.5,
      "temperature": 0.7
    }
  }'
```

## Database Schema

### Table: `tts_provider_configs`

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| user_id | INTEGER | Foreign key to users table |
| provider_type | STRING(50) | Provider identifier (chatterbox, kokoro, etc.) |
| api_url | STRING(500) | Provider API endpoint |
| api_key | STRING(500) | API key (if required) |
| timeout | INTEGER | Request timeout in seconds |
| voice_id | STRING(100) | Selected voice ID |
| speed | FLOAT | Speech speed (0.5-2.0) |
| extra_params | JSON | Provider-specific parameters |
| created_at | DATETIME | Creation timestamp |
| updated_at | DATETIME | Last update timestamp |

**Constraints:**
- UNIQUE (user_id, provider_type) - One config per user per provider

## Benefits

1. **Better UX**: Users don't lose their configurations when switching providers
2. **Experimentation**: Easy to compare different providers without reconfiguring
3. **Flexibility**: Each provider can have completely different settings
4. **Data Preservation**: Historical configurations are maintained
5. **Backward Compatible**: Existing code continues to work via global settings endpoint

## Future Enhancements

1. **Provider Config Management UI**: 
   - Show all saved configs in a list
   - Delete/reset individual provider configs
   - Duplicate config from one provider to another

2. **Named Profiles**:
   - Multiple configs per provider (e.g., "Fast", "Quality", "Dramatic")
   - Quick switching between profiles

3. **Import/Export**:
   - Export all configs as JSON
   - Import configs from file
   - Share configs with other users

4. **Default Templates**:
   - Pre-configured settings for common use cases
   - "Audiobook", "Character Dialogue", "Narration", etc.
