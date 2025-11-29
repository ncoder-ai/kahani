'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useGlobalTTS } from '@/contexts/GlobalTTSContext';
import { audioContextManager } from '@/utils/audioContextManager';

export const TTSDebugPanel: React.FC = () => {
  const { currentSceneId, isPlaying, isGenerating, error, progress, chunksReceived, totalChunks } = useGlobalTTS();
  const [isVisible, setIsVisible] = useState(false);
  const [audioState, setAudioState] = useState<string>('unknown');
  const [isUnlocking, setIsUnlocking] = useState(false);
  
  // Update AudioContext state periodically
  useEffect(() => {
    const updateState = () => {
      setAudioState(audioContextManager.getState());
    };
    
    updateState();
    const interval = setInterval(updateState, 500);
    
    return () => clearInterval(interval);
  }, []);
  
  // Handle unlock button click
  const handleUnlock = useCallback(async () => {
    setIsUnlocking(true);
    console.log('[TTS Debug] Attempting to unlock AudioContext...');
    
    const success = await audioContextManager.unlock();
    
    if (success) {
      console.log('[TTS Debug] ✓ AudioContext unlocked');
      setAudioState(audioContextManager.getState());
    } else {
      console.error('[TTS Debug] ✗ Failed to unlock AudioContext');
    }
    
    setIsUnlocking(false);
  }, []);
  
  // Handle test audio button click
  const handleTestAudio = useCallback(async () => {
    console.log('[TTS Debug] Testing audio playback...');
    await audioContextManager.testAudio();
  }, []);
  
  // Only show on mobile devices
  if (typeof window === 'undefined' || !/iPhone|iPad|iPod|Android/i.test(navigator.userAgent)) {
    return null;
  }
  
  const isAudioReady = audioState === 'running';
  
  // Don't render anything if not visible
  if (!isVisible) {
    return (
      <button
        onClick={() => setIsVisible(true)}
        className="fixed bottom-4 right-4 bg-blue-600 hover:bg-blue-700 text-white p-2 rounded-full shadow-lg z-50 transition-all"
        title="Show TTS Debug Panel"
      >
        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M3 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd" />
        </svg>
      </button>
    );
  }
  
  return (
    <>
      {/* Close Button */}
      <button
        onClick={() => setIsVisible(false)}
        className="fixed bottom-4 right-4 bg-red-600 hover:bg-red-700 text-white p-2 rounded-full shadow-lg z-50 transition-all"
        title="Hide TTS Debug Panel"
      >
        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
        </svg>
      </button>
      
      {/* Debug Panel */}
      <div className="fixed bottom-16 right-4 bg-black/95 text-white p-4 rounded-lg text-xs max-w-md z-50 shadow-2xl border border-gray-700">
        <div className="flex items-center justify-between mb-3">
          <div className="font-bold text-sm">🔍 TTS Debug Panel</div>
          <div className={`px-2 py-0.5 rounded text-[10px] ${
            error ? 'bg-red-500' : isGenerating ? 'bg-blue-500' : isPlaying ? 'bg-green-500' : 'bg-gray-600'
          }`}>
            {error ? 'ERROR' : isGenerating ? 'GENERATING' : isPlaying ? 'PLAYING' : 'IDLE'}
          </div>
        </div>
        
        {/* AudioContext Status - Prominent */}
        <div className={`mb-3 p-2 rounded border ${
          isAudioReady 
            ? 'bg-green-500/20 border-green-500/50' 
            : 'bg-orange-500/20 border-orange-500/50'
        }`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${isAudioReady ? 'bg-green-400' : 'bg-orange-400 animate-pulse'}`}></span>
              <span className="text-[11px] font-semibold">
                AudioContext: <span className="font-mono">{audioState}</span>
              </span>
            </div>
            {!isAudioReady && (
              <button
                onClick={handleUnlock}
                disabled={isUnlocking}
                className="px-2 py-1 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-600 text-white text-[10px] rounded transition-colors"
              >
                {isUnlocking ? 'Unlocking...' : 'Tap to Unlock'}
              </button>
            )}
          </div>
          {!isAudioReady && (
            <p className="text-[10px] text-orange-300 mt-1">
              Audio is suspended. Tap the button above to enable TTS playback.
            </p>
          )}
        </div>
        
        {/* Status Info */}
        <div className="mb-3 space-y-1 text-[11px]">
          <div className="flex justify-between">
            <span className="text-gray-400">Scene:</span>
            <span className="font-mono">{currentSceneId || 'None'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Progress:</span>
            <span className="font-mono">{progress}%</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Chunks:</span>
            <span className="font-mono">{chunksReceived} / {totalChunks || '?'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Online:</span>
            <span className={navigator.onLine ? 'text-green-400' : 'text-red-400'}>
              {navigator.onLine ? '✓ Yes' : '✗ No'}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Auth:</span>
            <span className={localStorage.getItem('auth_token') ? 'text-green-400' : 'text-red-400'}>
              {localStorage.getItem('auth_token') ? '✓ Present' : '✗ Missing'}
            </span>
          </div>
        </div>
        
        {/* Error Display */}
        {error && (
          <div className="mb-3 p-2 bg-red-500/20 border border-red-500/50 rounded text-[11px]">
            <div className="font-semibold text-red-400 mb-1">Error:</div>
            <div className="text-red-300">{error}</div>
          </div>
        )}
        
        {/* Device Info */}
        <div className="pt-3 border-t border-gray-700 text-[10px] text-gray-500">
          <div>Device: {/iPhone|iPad|iPod/i.test(navigator.userAgent) ? 'iOS' : 
                        /Android/i.test(navigator.userAgent) ? 'Android' : 'Desktop'}</div>
          <div>Screen: {window.innerWidth}×{window.innerHeight}</div>
          <div>Playing: {audioContextManager.getIsPlaying() ? 'Yes' : 'No'}</div>
        </div>
        
        {/* Test Audio Button */}
        <div className="mt-3 pt-3 border-t border-gray-700">
          <button
            onClick={handleTestAudio}
            disabled={!isAudioReady}
            className={`w-full text-white text-xs py-2 px-3 rounded transition-colors ${
              isAudioReady 
                ? 'bg-yellow-600 hover:bg-yellow-700' 
                : 'bg-gray-600 cursor-not-allowed'
            }`}
          >
            🔊 Test Audio (Beep)
          </button>
          {!isAudioReady && (
            <p className="text-[10px] text-gray-500 mt-1 text-center">
              Unlock audio first to test
            </p>
          )}
        </div>
      </div>
    </>
  );
};
