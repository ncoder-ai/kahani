import { useState, useEffect, useRef, useCallback } from 'react';
import api from '@/lib/api';

interface UseTTSOptions {
  sceneId: number;
  onPlaybackStart?: () => void;
  onPlaybackEnd?: () => void;
  onError?: (error: string) => void;
}

interface AudioInfo {
  progressive: boolean;
  chunk_count: number;
  duration: number;
  format: string;
}

export const useTTS = ({ sceneId, onPlaybackStart, onPlaybackEnd, onError }: UseTTSOptions) => {
  const [isGenerating, setIsGenerating] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [hasAudio, setHasAudio] = useState(false);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [currentChunk, setCurrentChunk] = useState(0);
  const [totalChunks, setTotalChunks] = useState(1);
  
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const progressIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const audioInfoRef = useRef<AudioInfo | null>(null);
  const chunkStartTimeRef = useRef<number>(0);
  const totalDurationRef = useRef<number>(0);
  const currentChunkRef = useRef<number>(0); // Track current chunk with ref to avoid closure issues

  // Check if audio already exists
  useEffect(() => {
    const checkAudio = async () => {
      try {
        await api.get(`/api/tts/audio/${sceneId}`);
        setHasAudio(true);
      } catch (err) {
        // Audio doesn't exist yet, that's fine
        setHasAudio(false);
      }
    };
    
    checkAudio();
  }, [sceneId]);

  // Update progress while playing
  const startProgressTracking = useCallback(() => {
    if (progressIntervalRef.current) {
      clearInterval(progressIntervalRef.current);
    }

    progressIntervalRef.current = setInterval(() => {
      if (audioRef.current && totalDurationRef.current > 0) {
        // Calculate progress based on chunk progress + previous chunks
        const currentChunkProgress = audioRef.current.currentTime;
        const totalProgress = chunkStartTimeRef.current + currentChunkProgress;
        const progressPercent = (totalProgress / totalDurationRef.current) * 100;
        setProgress(Math.min(100, isNaN(progressPercent) ? 0 : progressPercent));
      }
    }, 100);
  }, []);

  const stopProgressTracking = useCallback(() => {
    if (progressIntervalRef.current) {
      clearInterval(progressIntervalRef.current);
      progressIntervalRef.current = null;
    }
  }, []);

  // Generate TTS audio - always force regenerate (no caching)
  const generate = useCallback(async () => {
    setIsGenerating(true);
    setError(null);

    try {
      const data = await api.post(`/api/tts/generate/${sceneId}`, {
        force_regenerate: true  // Always regenerate, no caching
      }) as AudioInfo;
      
      setHasAudio(true);
      audioInfoRef.current = data;
      setTotalChunks(data.chunk_count || 1);
      totalDurationRef.current = data.duration || 0;
      setDuration(data.duration || 0);
      return data;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to generate audio';
      setError(errorMessage);
      onError?.(errorMessage);
      throw err;
    } finally {
      setIsGenerating(false);
    }
  }, [sceneId, onError]);

  // Play a specific chunk with smart retry logic
  const playChunk = useCallback(async (chunkNumber: number, retryCount = 0) => {
    const MAX_RETRIES = 15; // Allow more retries for slow generation
    const BASE_DELAY_MS = 500; // Start with shorter delay
    const MAX_DELAY_MS = 3000; // Cap maximum delay
    
    try {
      const audioInfo = audioInfoRef.current;
      if (!audioInfo) {
        throw new Error('Audio info not available');
      }

      if (!audioRef.current) {
        throw new Error('Audio element not initialized - call play() first');
      }

      console.log(`[useTTS] Playing chunk ${chunkNumber}/${audioInfo.chunk_count} (attempt ${retryCount + 1})`);

      // Fetch audio chunk with authentication
      const { getApiBaseUrl } = await import('@/lib/apiUrl');
      const apiBaseUrl = getApiBaseUrl();
      const url = audioInfo.progressive 
        ? `${apiBaseUrl}/api/tts/audio/${sceneId}/chunk/${chunkNumber}`
        : `${apiBaseUrl}/api/tts/audio/${sceneId}`;

      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
        }
      });

      // If chunk not found and we haven't exceeded retries, wait and retry with smart backoff
      if (response.status === 404 && retryCount < MAX_RETRIES) {
        // Smart backoff: increases gradually but caps at MAX_DELAY_MS
        // Formula: min(BASE * (1 + retryCount * 0.3), MAX_DELAY)
        // Results: 500ms, 650ms, 800ms, 950ms, 1100ms... up to 3000ms
        const delay = Math.min(
          BASE_DELAY_MS * (1 + retryCount * 0.3),
          MAX_DELAY_MS
        );
        
        console.log(`[useTTS] Chunk ${chunkNumber} not ready yet, retrying in ${Math.round(delay)}ms (attempt ${retryCount + 1}/${MAX_RETRIES})`);
        
        // Wait before retrying
        await new Promise(resolve => setTimeout(resolve, delay));
        
        // Check generation status before retrying (optional optimization)
        try {
          const { getApiBaseUrl } = await import('@/lib/apiUrl');
          const statusResponse = await fetch(
            `${getApiBaseUrl()}/api/tts/audio/${sceneId}/status`,
            {
              headers: {
                'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
              }
            }
          );
          
          if (statusResponse.ok) {
            const status = await statusResponse.json();
            console.log(`[useTTS] Generation status: ${status.chunks_ready}/${status.total_chunks} chunks ready`);
          }
        } catch (statusErr) {
          // Status check failed, but continue with retry anyway
          console.warn('[useTTS] Failed to check generation status:', statusErr);
        }
        
        return await playChunk(chunkNumber, retryCount + 1);
      }

      if (!response.ok) {
        throw new Error(`Failed to fetch audio chunk ${chunkNumber}: ${response.statusText}`);
      }

      // Create blob URL from audio data
      const audioBlob = await response.blob();
      const audioUrl = URL.createObjectURL(audioBlob);

      // Clean up old blob URL if exists
      if (audioRef.current.src && audioRef.current.src.startsWith('blob:')) {
        URL.revokeObjectURL(audioRef.current.src);
      }

      // Set audio source and play
      audioRef.current.src = audioUrl;
      await audioRef.current.play();
      
      console.log(`[useTTS] Successfully playing chunk ${chunkNumber}`);
      
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : `Failed to play chunk ${chunkNumber}`;
      console.error('[useTTS] Play chunk error:', err);
      setError(errorMessage);
      setIsPlaying(false);
      onError?.(errorMessage);
    }
  }, [sceneId, onError]);

  // Play audio (start from beginning)
  const play = useCallback(async () => {
    try {
      // Create Audio element NOW during user interaction to avoid autoplay policy issues
      if (!audioRef.current) {
        audioRef.current = new Audio();
        
        // Set up all event listeners now
        audioRef.current.addEventListener('loadedmetadata', () => {
          const audioInfo = audioInfoRef.current;
          if (audioRef.current && audioInfo && !audioInfo.progressive) {
            setDuration(audioRef.current.duration);
            totalDurationRef.current = audioRef.current.duration;
          }
        });

        audioRef.current.addEventListener('play', () => {
          setIsPlaying(true);
          startProgressTracking();
          if (currentChunkRef.current === 0) {
            onPlaybackStart?.();
          }
        });

        audioRef.current.addEventListener('pause', () => {
          setIsPlaying(false);
          stopProgressTracking();
        });

        audioRef.current.addEventListener('ended', async () => {
          const audioInfo = audioInfoRef.current;
          const chunkNumber = currentChunkRef.current; // Use ref to get current value
          console.log(`[useTTS] Chunk ${chunkNumber} ended`);
          
          // Clean up current blob URL
          if (audioRef.current?.src) {
            URL.revokeObjectURL(audioRef.current.src);
          }

          // If progressive, play next chunk
          if (audioInfo?.progressive && chunkNumber < audioInfo.chunk_count - 1) {
            // Update chunk start time for progress calculation
            const chunkDuration = audioRef.current?.duration || 0;
            chunkStartTimeRef.current += chunkDuration;
            const nextChunk = chunkNumber + 1;
            currentChunkRef.current = nextChunk; // Update ref
            setCurrentChunk(nextChunk); // Update state for UI
            
            console.log(`[useTTS] Moving to chunk ${nextChunk}`);
            
            // Play next chunk
            await playChunk(nextChunk);
          } else {
            // All chunks finished
            setIsPlaying(false);
            setProgress(100);
            currentChunkRef.current = 0; // Reset ref
            setCurrentChunk(0); // Reset state
            chunkStartTimeRef.current = 0;
            stopProgressTracking();
            onPlaybackEnd?.();
            console.log('[useTTS] Playback complete');
            
            // Cleanup chunks on backend if progressive
            if (audioInfo?.progressive) {
              try {
                await api.delete(`/api/tts/audio/${sceneId}/chunks`);
                console.log('[useTTS] Cleaned up audio chunks on backend');
              } catch (err) {
                console.warn('[useTTS] Failed to cleanup chunks:', err);
              }
            }
          }
        });

        audioRef.current.addEventListener('error', (e) => {
          const errorMessage = `Failed to play audio: ${audioRef.current?.error?.message || 'Unknown error'}`;
          console.error('[useTTS] Audio error:', e, audioRef.current?.error);
          setError(errorMessage);
          setIsPlaying(false);
          stopProgressTracking();
          onError?.(errorMessage);
        });
      }
      
      // Always generate fresh audio (no caching)
      const audioInfo = await generate();
      
      // Reset state and ref
      currentChunkRef.current = 0; // Reset ref
      setCurrentChunk(0); // Reset state for UI
      chunkStartTimeRef.current = 0;
      setProgress(0);

      console.log(`[useTTS] Starting playback: progressive=${audioInfo.progressive}, chunks=${audioInfo.chunk_count}`);

      // Start playing from chunk 0
      await playChunk(0);
      
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to play audio';
      console.error('[useTTS] Play error:', err);
      setError(errorMessage);
      onError?.(errorMessage);
    }
  }, [generate, playChunk, onError, startProgressTracking, stopProgressTracking, onPlaybackStart, onPlaybackEnd, sceneId, currentChunk]);

  // Pause audio
  const pause = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
    }
  }, []);

  // Toggle play/pause
  const togglePlayback = useCallback(() => {
    if (isPlaying) {
      pause();
    } else {
      play();
    }
  }, [isPlaying, play, pause]);

  // Seek to position (0-100)
  const seek = useCallback((percentage: number) => {
    if (audioRef.current && duration > 0) {
      audioRef.current.currentTime = (percentage / 100) * duration;
      setProgress(percentage);
    }
  }, [duration]);

  // Cleanup
  useEffect(() => {
    return () => {
      stopProgressTracking();
      if (audioRef.current) {
        audioRef.current.pause();
        // Clean up blob URL
        if (audioRef.current.src && audioRef.current.src.startsWith('blob:')) {
          URL.revokeObjectURL(audioRef.current.src);
        }
        audioRef.current.src = '';
      }
    };
  }, [stopProgressTracking]);

  return {
    // State
    isGenerating,
    isPlaying,
    hasAudio,
    progress,
    duration,
    error,
    currentChunk,
    totalChunks,
    
    // Actions
    generate,
    play,
    pause,
    togglePlayback,
    seek,
  };
};
