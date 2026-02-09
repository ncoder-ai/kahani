'use client';

import { useState } from 'react';
import { X, Volume2, Loader2, Play, Pause, Check } from 'lucide-react';
import apiClient from '@/lib/api';

interface Voice {
  id: string;
  name: string;
  language?: string;
  description?: string;
}

interface VoiceBrowserModalProps {
  isOpen: boolean;
  onClose: () => void;
  voices: Voice[];
  selectedVoiceId: string;
  onSelectVoice: (voiceId: string) => void;
  providerSettings: {
    provider_type: string;
    api_url: string;
    api_key?: string;
    speed: number;
  };
}

export default function VoiceBrowserModal({
  isOpen,
  onClose,
  voices,
  selectedVoiceId,
  onSelectVoice,
  providerSettings,
}: VoiceBrowserModalProps) {
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);
  const [loadingVoiceId, setLoadingVoiceId] = useState<string | null>(null);
  const [currentAudio, setCurrentAudio] = useState<HTMLAudioElement | null>(null);
  const [error, setError] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');

  const filteredVoices = voices.filter(voice => 
    voice.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    voice.language?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    voice.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handlePlayVoice = async (voice: Voice) => {
    setError('');
    
    // Stop currently playing audio
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
      setPlayingVoiceId(null);
    }

    // If clicking the same voice that's playing, just stop
    if (playingVoiceId === voice.id) {
      setPlayingVoiceId(null);
      return;
    }

    setLoadingVoiceId(voice.id);

    try {
      const testText = `Hello, I'm ${voice.name}. This is how I sound.`;
      
      // Use test-voice endpoint with full settings
      const response = await fetch(`${apiClient.getBaseURL()}/api/tts/test-voice?text=${encodeURIComponent(testText)}&voice_id=${encodeURIComponent(voice.id)}&speed=${providerSettings.speed}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiClient.getToken()}`,
        },
        body: JSON.stringify({
          provider_type: providerSettings.provider_type,
          api_url: providerSettings.api_url,
          api_key: providerSettings.api_key || '',
          voice_id: voice.id,
          speed: providerSettings.speed,
          timeout: 30,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errorData.detail || 'Failed to generate preview');
      }

      const audioBlob = await response.blob();
      const audioUrl = URL.createObjectURL(audioBlob);
      
      const audio = new Audio(audioUrl);
      setCurrentAudio(audio);
      setPlayingVoiceId(voice.id);

      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
        setPlayingVoiceId(null);
        setLoadingVoiceId(null);
      };

      audio.onerror = () => {
        URL.revokeObjectURL(audioUrl);
        setError(`Failed to play ${voice.name}`);
        setPlayingVoiceId(null);
        setLoadingVoiceId(null);
      };

      await audio.play();
      setLoadingVoiceId(null);

    } catch (err: any) {
      setError(`Preview failed: ${err.message}`);
      setPlayingVoiceId(null);
      setLoadingVoiceId(null);
    }
  };

  const handleStopAudio = () => {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
    }
    setPlayingVoiceId(null);
  };

  const handleSelectVoice = (voiceId: string) => {
    handleStopAudio();
    onSelectVoice(voiceId);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-4">
      <div className="bg-gray-900 rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <Volume2 className="w-6 h-6 text-purple-400" />
            <div>
              <h2 className="text-xl font-bold text-white">Voice Browser</h2>
              <p className="text-sm text-gray-400">{voices.length} voices available</p>
            </div>
          </div>
          <button
            onClick={() => {
              handleStopAudio();
              onClose();
            }}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Search */}
        <div className="p-4 border-b border-gray-800">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search voices by name, language, or description..."
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>

        {/* Error Message */}
        {error && (
          <div className="mx-6 mt-4 bg-red-500/10 border border-red-500/50 rounded-lg p-3">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        {/* Voice List */}
        <div className="flex-1 overflow-y-auto p-6 space-y-2">
          {filteredVoices.length === 0 ? (
            <div className="text-center text-gray-400 py-12">
              <Volume2 className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>No voices found</p>
            </div>
          ) : (
            filteredVoices.map((voice) => (
              <div
                key={voice.id}
                className={`flex items-center gap-4 p-4 rounded-lg border transition-all ${
                  selectedVoiceId === voice.id
                    ? 'bg-purple-600/20 border-purple-500/50'
                    : 'bg-gray-800 border-gray-700 hover:border-gray-600'
                }`}
              >
                {/* Voice Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium text-white truncate">{voice.name}</h3>
                    {selectedVoiceId === voice.id && (
                      <Check className="w-4 h-4 text-purple-400 flex-shrink-0" />
                    )}
                  </div>
                  {voice.language && (
                    <p className="text-sm text-gray-400">{voice.language}</p>
                  )}
                  {voice.description && (
                    <p className="text-xs text-gray-500 mt-1 line-clamp-2">{voice.description}</p>
                  )}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2">
                  {/* Play/Pause Button */}
                  <button
                    onClick={() => handlePlayVoice(voice)}
                    disabled={loadingVoiceId === voice.id}
                    className="p-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Preview voice"
                  >
                    {loadingVoiceId === voice.id ? (
                      <Loader2 className="w-5 h-5 animate-spin" />
                    ) : playingVoiceId === voice.id ? (
                      <Pause className="w-5 h-5" />
                    ) : (
                      <Play className="w-5 h-5" />
                    )}
                  </button>

                  {/* Select Button */}
                  {selectedVoiceId !== voice.id && (
                    <button
                      onClick={() => handleSelectVoice(voice.id)}
                      className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors text-sm"
                    >
                      Select
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-gray-800 bg-gray-900/50">
          <p className="text-sm text-gray-400">
            {filteredVoices.length} of {voices.length} voices shown
          </p>
          <button
            onClick={() => {
              handleStopAudio();
              onClose();
            }}
            className="px-6 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
