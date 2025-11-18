# TTS Settings Enhancements - Voice Persistence & Auto-Connection

## Summary of Changes

### 1. Voice Settings Persistence ✅
**Status**: Already working, verified in code

The `voice_id` is properly saved and restored with each provider configuration:
- Saved to database via `/api/tts/provider-configs/{provider_type}`
- Included in the `settings` object spread: `{...settings, extra_params}`
- Restored when switching providers via `savedConfig.voice_id`

### 2. Auto Health Check on Provider Switch ✅
**Status**: Newly implemented

When switching to a provider that has saved settings, the system now:
1. Automatically performs a health check
2. Fetches available voices
3. Pre-selects the saved voice if it exists in the list
4. Falls back to first available voice if saved voice not found

## Implementation Details

### Frontend Changes

#### File: `frontend/src/components/TTSSettingsModal.tsx`

**New Function: `autoTestConnection()`**
```typescript
const autoTestConnection = async (
  currentSettings: TTSSettings, 
  savedVoiceId?: string
) => {
  // Performs health check silently (no error dialogs)
  // Populates voices list
  // Pre-selects saved voice if available
}
```

**Updated Function: `handleProviderChange()`**
- Now `async` to support auto-testing
- Triggers `autoTestConnection()` after loading saved config
- Passes saved `voice_id` for pre-selection
- Uses 100ms delay to ensure state updates complete

**Updated Function: `handleTestConnection()`**
- Enhanced to preserve current voice selection when re-testing
- Only changes voice if current one is not in the new list
- Falls back to first voice if current voice unavailable

## User Experience Flow

### Scenario: Switching Between Configured Providers

**Before Enhancement:**
1. User selects "Chatterbox" from dropdown
2. Settings load (URL, API key, etc.)
3. Voice dropdown is empty
4. User must click "Test Connection"
5. Voices populate
6. User must manually select voice again

**After Enhancement:**
1. User selects "Chatterbox" from dropdown
2. Settings load (URL, API key, etc.)
3. ✨ **Health check runs automatically**
4. ✨ **Voices populate automatically**
5. ✨ **Saved voice is pre-selected automatically**
6. User can immediately continue or save

### Scenario: First Time Setup (No Saved Config)

**Behavior:**
1. User selects provider
2. Default URL loads
3. Voice dropdown remains empty (expected)
4. User enters API details
5. User clicks "Test Connection"
6. Voices populate
7. User selects voice and saves

## Technical Details

### Auto-Test Connection Logic

```typescript
// Triggered when switching to provider with saved config
if (savedConfig && savedConfig.api_url) {
  setTimeout(() => {
    autoTestConnection(newSettings, savedConfig.voice_id);
  }, 100);
}
```

**Why the 100ms delay?**
- Ensures React state updates complete
- Prevents race conditions with settings updates
- Allows UI to stabilize before API call

### Voice Pre-Selection Logic

```typescript
if (savedVoiceId && response.voices.some(v => v.id === savedVoiceId)) {
  // Saved voice exists, restore it
  setSettings(prev => ({ ...prev, voice_id: savedVoiceId }));
} else if (response.voices.length > 0 && !currentSettings.voice_id) {
  // No saved voice or not found, use first available
  setSettings(prev => ({ ...prev, voice_id: response.voices[0].id }));
}
```

### Error Handling

**Auto-test failures are handled gracefully:**
- No error dialogs shown (uses `console.warn` instead)
- Connection status set to "failed" (visual indicator)
- User can manually click "Test Connection" to retry
- Doesn't block user from entering/editing settings

**Manual test failures show errors:**
- Error dialog appears
- Connection status set to "failed"
- User informed of specific issue

## Database Schema

### Voice Storage

The `voice_id` is stored in the `tts_provider_configs` table:

```sql
CREATE TABLE tts_provider_configs (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,
  provider_type VARCHAR(50) NOT NULL,
  api_url VARCHAR(500) NOT NULL,
  api_key VARCHAR(500),
  voice_id VARCHAR(100),  -- ✅ Voice is stored here
  speed FLOAT DEFAULT 1.0,
  timeout INTEGER DEFAULT 30,
  extra_params JSON,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  UNIQUE(user_id, provider_type)
);
```

## Testing Instructions

### Test 1: Voice Persistence
1. Open TTS Settings Modal
2. Select "Chatterbox" provider
3. Enter API URL: `http://localhost:8880/v1`
4. Click "Test Connection"
5. Select voice: "female_01"
6. Adjust other settings
7. Click "Save"
8. Switch to "Kokoro" provider
9. Configure and save with voice "af_bella"
10. **Switch back to Chatterbox**
11. ✅ Verify: Voice "female_01" is pre-selected
12. **Switch to Kokoro**
13. ✅ Verify: Voice "af_bella" is pre-selected

### Test 2: Auto Health Check
1. Complete Test 1 (have saved configs)
2. Close TTS Settings Modal
3. Reopen TTS Settings Modal
4. Note: Modal opens with last used provider
5. **Select "Chatterbox" from dropdown**
6. ✅ Verify: Loading spinner appears briefly
7. ✅ Verify: Voices populate automatically
8. ✅ Verify: Saved voice is pre-selected
9. ✅ Verify: Connection status shows success (green checkmark)

### Test 3: Offline Provider Handling
1. Stop Chatterbox service (simulate offline)
2. Open TTS Settings Modal
3. Select "Chatterbox" provider
4. ✅ Verify: Auto-test fails silently
5. ✅ Verify: Connection status shows failed (red X)
6. ✅ Verify: No error dialog appears
7. ✅ Verify: Settings still populate from saved config
8. ✅ Verify: User can edit settings
9. Click "Test Connection" manually
10. ✅ Verify: Now error message appears

### Test 4: Voice Not Available
1. Configure Chatterbox with voice "female_01"
2. Save settings
3. (Simulate: provider now only has "male_01" available)
4. Switch to another provider and back
5. ✅ Verify: Auto-test runs
6. ✅ Verify: First available voice selected (since saved one missing)
7. ✅ Verify: No errors shown

## Benefits

### For Users
1. **Faster workflow**: No need to repeatedly test connections
2. **Seamless switching**: Instant access to saved configurations
3. **Better UX**: Voice selections preserved across sessions
4. **Less clicking**: Auto-population reduces manual steps
5. **Non-disruptive**: Silent failures don't interrupt workflow

### For Developers
1. **Cleaner state management**: Voice IDs properly tracked
2. **Robust error handling**: Graceful degradation on failures
3. **Consistent behavior**: Same logic for manual and auto tests
4. **Maintainable code**: Clear separation of concerns

## Configuration

No configuration needed. Features are automatic based on:
- Saved provider configs in database
- Valid API URLs in settings
- Available network connectivity

## Known Limitations

1. **100ms delay**: Small delay before auto-test (acceptable tradeoff)
2. **Network dependency**: Requires provider to be online
3. **No retry logic**: Failed auto-tests don't retry automatically
4. **Silent failures**: User must manually test if auto-test fails

## Future Enhancements

### Potential Improvements
1. **Retry logic**: Auto-retry failed health checks (with backoff)
2. **Cache voices**: Store voice list locally to reduce API calls
3. **Background refresh**: Update voices in background periodically
4. **Smart caching**: Remember last successful voice list per provider
5. **Offline mode**: Allow editing settings without connection
6. **Voice preview cache**: Cache audio samples for faster previews

### Advanced Features
1. **Voice recommendations**: Suggest voices based on story genre
2. **Bulk testing**: Test all saved providers at once
3. **Health monitoring**: Background monitoring of provider status
4. **Auto-fallback**: Switch to working provider if current fails
5. **Voice comparison**: Side-by-side comparison of different voices

## Troubleshooting

### Issue: Auto-test doesn't run
**Causes:**
- No saved config for provider
- Empty API URL in saved config
- React state update timing

**Solutions:**
- Manually test connection once and save
- Verify API URL is not empty
- Refresh modal by closing and reopening

### Issue: Wrong voice selected
**Causes:**
- Saved voice no longer available
- Voice ID changed on provider side
- Database contains stale data

**Solutions:**
- Manually select correct voice and save again
- Click "Test Connection" to refresh voice list
- Verify provider is returning expected voices

### Issue: Connection status shows failed
**Causes:**
- Provider is offline
- Invalid API URL or key
- Network connectivity issues
- Timeout too short

**Solutions:**
- Verify provider service is running
- Check API URL and key are correct
- Test network connectivity
- Increase timeout in settings

## API Endpoints Used

### Provider Configuration
- **GET** `/api/tts/provider-configs` - Load all saved configs
- **GET** `/api/tts/provider-configs/{type}` - Load specific provider config
- **PUT** `/api/tts/provider-configs/{type}` - Save provider config

### Health Check
- **POST** `/api/tts/test-connection` - Test provider connection & get voices

### Legacy Support
- **GET** `/api/tts/settings` - Get global TTS settings
- **PUT** `/api/tts/settings` - Update global TTS settings
- **GET** `/api/tts/voices` - Get voices from current provider

## Conclusion

These enhancements significantly improve the TTS configuration experience by:
1. ✅ **Persisting voice selections** per provider
2. ✅ **Auto-testing connections** on provider switch
3. ✅ **Pre-selecting voices** from saved settings
4. ✅ **Providing smooth UX** with graceful error handling

Users can now seamlessly switch between providers without losing their carefully chosen voice configurations!
