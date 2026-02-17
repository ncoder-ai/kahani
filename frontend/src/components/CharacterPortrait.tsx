'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { imageGenerationApi } from '@/lib/api/index';
import type { ImageGenServerStatus, ImageGenAvailableModels, StylePreset } from '@/lib/api/index';

interface CharacterPortraitProps {
  characterId?: number;
  appearance?: string;
  portraitImageId?: number | null;
  onPortraitChange?: (imageId: number | null) => void;
  mode?: 'create' | 'edit' | 'view';
  disabled?: boolean;
}

interface GenerationProgress {
  status: 'idle' | 'connecting' | 'generating' | 'complete' | 'error';
  progress?: number;
  message?: string;
}

export default function CharacterPortrait({
  characterId,
  appearance = '',
  portraitImageId,
  onPortraitChange,
  mode = 'view',
  disabled = false
}: CharacterPortraitProps) {
  // State
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [serverStatus, setServerStatus] = useState<ImageGenServerStatus | null>(null);
  const [availableModels, setAvailableModels] = useState<ImageGenAvailableModels | null>(null);
  const [stylePresets, setStylePresets] = useState<Record<string, StylePreset>>({});
  const [selectedCheckpoint, setSelectedCheckpoint] = useState<string>('');
  const [selectedStyle, setSelectedStyle] = useState<string>('illustrated');
  const [generationProgress, setGenerationProgress] = useState<GenerationProgress>({ status: 'idle' });
  const [showOptions, setShowOptions] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load server status and available models
  useEffect(() => {
    const loadServerInfo = async () => {
      try {
        const [status, models, presetsResponse] = await Promise.all([
          imageGenerationApi.getServerStatus().catch(() => null),
          imageGenerationApi.getAvailableModels().catch(() => null),
          imageGenerationApi.getStylePresets().catch(() => ({ presets: {} }))
        ]);

        setServerStatus(status);
        setAvailableModels(models);
        setStylePresets(presetsResponse?.presets || {});

        // Set default checkpoint if available
        if (models?.checkpoints && models.checkpoints.length > 0) {
          setSelectedCheckpoint(models.checkpoints[0]);
        }
      } catch (err) {
        console.error('Failed to load image generation info:', err);
      }
    };

    loadServerInfo();
  }, []);

  // Load existing portrait image
  useEffect(() => {
    if (portraitImageId) {
      loadPortraitImage(portraitImageId);
    } else {
      setImageUrl(null);
    }
  }, [portraitImageId]);

  const loadPortraitImage = async (imageId: number) => {
    try {
      setLoading(true);
      const image = await imageGenerationApi.getImage(imageId);
      if (image.file_path) {
        // Get full URL including backend base URL for <img src>
        const fullUrl = await imageGenerationApi.getImageFileUrl(imageId);
        setImageUrl(fullUrl);
      }
    } catch (err) {
      console.error('Failed to load portrait image:', err);
      setError('Failed to load portrait');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = useCallback(async () => {
    if (!characterId) {
      setError('Please save the character first before generating a portrait');
      return;
    }

    if (!appearance?.trim()) {
      setError('Please add an appearance description to generate a portrait');
      return;
    }

    if (!serverStatus?.online) {
      setError('Image generation server is not available');
      return;
    }

    try {
      setError(null);
      setGenerationProgress({ status: 'connecting', message: 'Connecting to server...' });

      const result = await imageGenerationApi.generateCharacterPortrait(characterId, {
        style: selectedStyle,
        checkpoint: selectedCheckpoint || undefined
      });

      // Check if generation completed synchronously (current backend behavior)
      if (result.status === 'completed' && result.image_id) {
        setGenerationProgress({ status: 'complete', message: 'Portrait generated!' });
        const fullUrl = await imageGenerationApi.getImageFileUrl(result.image_id);
        setImageUrl(fullUrl);
        onPortraitChange?.(result.image_id);
        setTimeout(() => setGenerationProgress({ status: 'idle' }), 2000);
        return;
      }

      // If not completed immediately, poll for completion
      setGenerationProgress({ status: 'generating', message: 'Generating portrait...' });

      let attempts = 0;
      const maxAttempts = 60; // 2 minutes with 2s intervals

      while (attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 2000));

        try {
          const status = await imageGenerationApi.getJobStatus(result.job_id);

          if (status.status === 'completed' && status.image_id) {
            setGenerationProgress({ status: 'complete', message: 'Portrait generated!' });
            const fullUrl = await imageGenerationApi.getImageFileUrl(status.image_id);
            setImageUrl(fullUrl);
            onPortraitChange?.(status.image_id);
            setTimeout(() => setGenerationProgress({ status: 'idle' }), 2000);
            return;
          } else if (status.status === 'failed') {
            throw new Error(status.error || 'Generation failed');
          }

          // Update progress if available
          if (status.progress !== undefined) {
            setGenerationProgress({
              status: 'generating',
              progress: status.progress,
              message: `Generating... ${Math.round(status.progress * 100)}%`
            });
          }
        } catch (pollError: any) {
          // If job not found, it may have completed before we started polling
          if (pollError.message?.includes('not found')) {
            // Re-check the original result in case it completed
            if (result.image_id) {
              setGenerationProgress({ status: 'complete', message: 'Portrait generated!' });
              const fullUrl = await imageGenerationApi.getImageFileUrl(result.image_id);
              setImageUrl(fullUrl);
              onPortraitChange?.(result.image_id);
              setTimeout(() => setGenerationProgress({ status: 'idle' }), 2000);
              return;
            }
          }
          // Continue polling on transient errors
          console.warn('Poll error:', pollError);
        }

        attempts++;
      }

      throw new Error('Generation timed out');
    } catch (err: any) {
      console.error('Portrait generation failed:', err);
      setError(err.message || 'Failed to generate portrait');
      setGenerationProgress({ status: 'error', message: err.message || 'Generation failed' });
      setTimeout(() => setGenerationProgress({ status: 'idle' }), 3000);
    }
  }, [characterId, appearance, serverStatus, selectedStyle, selectedCheckpoint, onPortraitChange]);

  const handleUpload = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !characterId) return;

    // Validate file type
    if (!file.type.startsWith('image/')) {
      setError('Please select an image file');
      return;
    }

    // Validate file size (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
      setError('Image must be less than 10MB');
      return;
    }

    try {
      setError(null);
      setLoading(true);

      const result = await imageGenerationApi.uploadCharacterPortrait(characterId, file);

      if (result.id) {
        const fullUrl = await imageGenerationApi.getImageFileUrl(result.id);
        setImageUrl(fullUrl);
        onPortraitChange?.(result.id);
      }
    } catch (err: any) {
      console.error('Portrait upload failed:', err);
      setError(err.message || 'Failed to upload portrait');
    } finally {
      setLoading(false);
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  }, [characterId, onPortraitChange]);

  const handleRemove = useCallback(async () => {
    if (!characterId || !portraitImageId) return;

    if (!confirm('Are you sure you want to remove this portrait?')) return;

    try {
      setError(null);
      setLoading(true);

      await imageGenerationApi.deleteCharacterPortrait(characterId);

      setImageUrl(null);
      onPortraitChange?.(null);
    } catch (err: any) {
      console.error('Portrait removal failed:', err);
      setError(err.message || 'Failed to remove portrait');
    } finally {
      setLoading(false);
    }
  }, [characterId, portraitImageId, onPortraitChange]);

  const isGenerating = generationProgress.status === 'connecting' || generationProgress.status === 'generating';
  const canGenerate = characterId && appearance?.trim() && serverStatus?.online && !isGenerating && !loading && !disabled;
  const canUpload = characterId && !isGenerating && !loading && !disabled;

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-4">
        {/* Portrait Display */}
        <div className="relative w-32 h-32 flex-shrink-0">
          {loading ? (
            <div className="w-full h-full rounded-xl bg-white/10 flex items-center justify-center">
              <div className="animate-spin w-8 h-8 border-2 border-white/30 border-t-white rounded-full" />
            </div>
          ) : imageUrl ? (
            <div className="relative w-full h-full group">
              <img
                src={imageUrl}
                alt="Character portrait"
                className="w-full h-full object-cover rounded-xl"
              />
              {mode !== 'view' && !disabled && (
                <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity rounded-xl flex items-center justify-center">
                  <button
                    onClick={handleRemove}
                    className="text-white/80 hover:text-white p-2"
                    title="Remove portrait"
                  >
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="w-full h-full rounded-xl bg-white/10 border-2 border-dashed border-white/30 flex flex-col items-center justify-center text-white/50">
              <svg className="w-10 h-10 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
              <span className="text-xs">No portrait</span>
            </div>
          )}

          {/* Generation Progress Overlay */}
          {isGenerating && (
            <div className="absolute inset-0 bg-black/70 rounded-xl flex flex-col items-center justify-center">
              <div className="animate-spin w-8 h-8 border-2 border-white/30 border-t-white rounded-full mb-2" />
              <span className="text-xs text-white/80 text-center px-2">
                {generationProgress.message}
              </span>
              {generationProgress.progress !== undefined && (
                <div className="w-20 h-1 bg-white/20 rounded-full mt-2 overflow-hidden">
                  <div
                    className="h-full bg-white/80 transition-all duration-300"
                    style={{ width: `${generationProgress.progress * 100}%` }}
                  />
                </div>
              )}
            </div>
          )}
        </div>

        {/* Controls */}
        {mode !== 'view' && (
          <div className="flex-1 space-y-3">
            {/* Action Buttons */}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={handleGenerate}
                disabled={!canGenerate}
                className="px-3 py-1.5 text-sm theme-btn-primary rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Generate
              </button>

              <button
                type="button"
                onClick={handleUpload}
                disabled={!canUpload}
                className="px-3 py-1.5 text-sm bg-white/20 text-white rounded-lg hover:bg-white/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
                Upload
              </button>

              {imageUrl && (
                <button
                  type="button"
                  onClick={handleRemove}
                  disabled={loading || isGenerating || disabled}
                  className="px-3 py-1.5 text-sm bg-red-500/20 text-red-300 rounded-lg hover:bg-red-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                  Remove
                </button>
              )}
            </div>

            {/* Options Toggle */}
            <button
              type="button"
              onClick={() => setShowOptions(!showOptions)}
              className="text-xs text-white/60 hover:text-white flex items-center gap-1"
            >
              <svg
                className={`w-3 h-3 transition-transform ${showOptions ? 'rotate-90' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              Generation options
            </button>

            {/* Generation Options */}
            {showOptions && (
              <div className="space-y-3 p-3 bg-white/5 rounded-lg border border-white/10">
                {/* Model Selection */}
                <div>
                  <label className="block text-xs font-medium text-white/70 mb-1">
                    Model
                  </label>
                  <select
                    value={selectedCheckpoint}
                    onChange={(e) => setSelectedCheckpoint(e.target.value)}
                    disabled={!availableModels?.checkpoints?.length}
                    className="w-full p-2 text-sm bg-gray-800 border border-white/20 rounded-lg text-white focus:outline-none theme-focus-ring [&>option]:bg-gray-800"
                  >
                    {availableModels?.checkpoints?.length ? (
                      availableModels.checkpoints.map((cp: string) => (
                        <option key={cp} value={cp}>{cp}</option>
                      ))
                    ) : (
                      <option value="">No models available</option>
                    )}
                  </select>
                </div>

                {/* Style Selection */}
                <div>
                  <label className="block text-xs font-medium text-white/70 mb-1">
                    Style
                  </label>
                  <select
                    value={selectedStyle}
                    onChange={(e) => setSelectedStyle(e.target.value)}
                    className="w-full p-2 text-sm bg-gray-800 border border-white/20 rounded-lg text-white focus:outline-none theme-focus-ring [&>option]:bg-gray-800"
                  >
                    {Object.entries(stylePresets).map(([id, preset]) => (
                      <option key={id} value={id}>{preset.name}</option>
                    ))}
                    {Object.keys(stylePresets).length === 0 && (
                      <>
                        <option value="illustrated">Illustrated</option>
                        <option value="semi_realistic">Semi-Realistic</option>
                        <option value="anime">Anime</option>
                        <option value="photorealistic">Photorealistic</option>
                      </>
                    )}
                  </select>
                </div>

                {/* Server Status */}
                <div className="flex items-center gap-2 text-xs">
                  <div className={`w-2 h-2 rounded-full ${serverStatus?.online ? 'bg-green-500' : 'bg-red-500'}`} />
                  <span className="text-white/60">
                    {serverStatus?.online ? 'Server connected' : 'Server offline'}
                  </span>
                </div>
              </div>
            )}

            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleFileChange}
              className="hidden"
            />
          </div>
        )}
      </div>

      {/* Error Message */}
      {error && (
        <div className="flex items-center gap-2 text-sm text-red-400 bg-red-500/10 px-3 py-2 rounded-lg">
          <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            className="ml-auto text-red-400/60 hover:text-red-400"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* Help Text */}
      {mode !== 'view' && !characterId && (
        <p className="text-xs text-white/50">
          Save the character first to enable portrait generation
        </p>
      )}

      {mode !== 'view' && characterId && !appearance?.trim() && (
        <p className="text-xs text-white/50">
          Add an appearance description above to generate a portrait
        </p>
      )}
    </div>
  );
}
