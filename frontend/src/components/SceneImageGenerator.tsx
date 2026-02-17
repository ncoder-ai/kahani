'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Sparkles, ChevronDown, ChevronLeft, ChevronRight, Download, Trash2, RefreshCw, X, User } from 'lucide-react';
import { imageGenerationApi } from '@/lib/api/index';
import type { ImageGenServerStatus, ImageGenAvailableModels, StylePreset } from '@/lib/api/index';
import apiClient from '@/lib/api';

interface SceneImage {
  id: number;
  prompt?: string;
  created_at: string;
}

interface SceneImageGeneratorProps {
  sceneId: number;
  storyId: number;
  sceneContent?: string;
  onImageGenerated?: (imageId: number) => void;
  forceShow?: boolean;  // When true, always show the component even without images
  onClose?: () => void; // Callback when user closes the generator
  defaultCheckpoint?: string; // User's preferred checkpoint from settings
  defaultStyle?: string; // User's preferred style from settings
  defaultSteps?: number; // User's preferred steps from settings
  defaultCfgScale?: number; // User's preferred cfg_scale from settings
}

interface GenerationProgress {
  status: 'idle' | 'connecting' | 'generating' | 'complete' | 'error';
  progress?: number;
  message?: string;
}

export default function SceneImageGenerator({
  sceneId,
  storyId,
  sceneContent = '',
  onImageGenerated,
  forceShow = false,
  onClose,
  defaultCheckpoint = '',
  defaultStyle = 'illustrated',
  defaultSteps,
  defaultCfgScale,
}: SceneImageGeneratorProps) {
  const [images, setImages] = useState<SceneImage[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [currentImageUrl, setCurrentImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [serverStatus, setServerStatus] = useState<ImageGenServerStatus | null>(null);
  const [availableModels, setAvailableModels] = useState<ImageGenAvailableModels | null>(null);
  const [stylePresets, setStylePresets] = useState<Record<string, StylePreset>>({});
  const [selectedCheckpoint, setSelectedCheckpoint] = useState<string>(defaultCheckpoint);
  const [selectedStyle, setSelectedStyle] = useState<string>(defaultStyle);
  const [customPrompt, setCustomPrompt] = useState<string>('');
  const [generationProgress, setGenerationProgress] = useState<GenerationProgress>({ status: 'idle' });
  const [showOptions, setShowOptions] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const confirmingDeleteRef = useRef(false);
  const [collapsed, setCollapsed] = useState(false);
  const promptFocusHandledRef = useRef(false);
  const [subjectType, setSubjectType] = useState<'scene' | 'character'>('scene');
  const [selectedCharacterId, setSelectedCharacterId] = useState<number | null>(null);
  const [storyCharacters, setStoryCharacters] = useState<{character_id: number; name: string}[]>([]);

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

        // Only set checkpoint if user doesn't have a default selected
        // or if their default isn't in the available models
        if (models?.checkpoints && models.checkpoints.length > 0) {
          if (!defaultCheckpoint || !models.checkpoints.includes(defaultCheckpoint)) {
            setSelectedCheckpoint(models.checkpoints[0]);
          }
        }
      } catch (err) {
        console.error('Failed to load image generation info:', err);
      }
    };

    loadServerInfo();
  }, [defaultCheckpoint]);

  // Load story characters when switching to character mode
  useEffect(() => {
    if (subjectType !== 'character' || !storyId) return;
    if (storyCharacters.length > 0) return; // already loaded

    const loadCharacters = async () => {
      try {
        const chars = await apiClient.getStoryCharacters(storyId);
        setStoryCharacters(chars);
        if (chars.length > 0 && !selectedCharacterId) {
          setSelectedCharacterId(chars[0].character_id);
        }
      } catch (err) {
        console.error('Failed to load story characters:', err);
      }
    };
    loadCharacters();
  }, [subjectType, storyId, storyCharacters.length, selectedCharacterId]);

  // Load existing images for this scene
  useEffect(() => {
    const loadSceneImages = async () => {
      if (!sceneId || !storyId) return;

      try {
        setLoading(true);
        const sceneImages = await imageGenerationApi.getStoryImages(storyId, { scene_id: sceneId });

        if (sceneImages && sceneImages.length > 0) {
          // Sort by created_at desc (newest first)
          const sorted = [...sceneImages].sort((a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
          );
          setImages(sorted);
          setCurrentIndex(0);

          // Load the first image
          const fullUrl = await imageGenerationApi.getImageFileUrl(sorted[0].id);
          setCurrentImageUrl(fullUrl);
        } else {
          setImages([]);
          setCurrentImageUrl(null);
        }
      } catch (err) {
        console.error('Failed to fetch scene images:', err);
        setImages([]);
        setCurrentImageUrl(null);
      } finally {
        setLoading(false);
      }
    };

    loadSceneImages();
  }, [sceneId, storyId]);

  // Load image when index changes
  useEffect(() => {
    const loadCurrentImage = async () => {
      if (images.length === 0 || currentIndex >= images.length) {
        setCurrentImageUrl(null);
        return;
      }

      try {
        const fullUrl = await imageGenerationApi.getImageFileUrl(images[currentIndex].id);
        setCurrentImageUrl(fullUrl);
      } catch (err) {
        console.error('Failed to load image:', err);
      }
    };

    loadCurrentImage();
  }, [currentIndex, images]);

  const handleGenerate = useCallback(async () => {
    if (!serverStatus?.online) {
      setError('Image generation server is not available');
      return;
    }

    try {
      setError(null);
      setGenerationProgress({ status: 'connecting', message: 'Connecting to server...' });

      const result = subjectType === 'character' && selectedCharacterId
        ? await imageGenerationApi.generateCharacterImage(sceneId, {
            character_id: selectedCharacterId,
            style: selectedStyle,
            checkpoint: selectedCheckpoint || undefined,
            steps: defaultSteps,
            cfg_scale: defaultCfgScale,
            custom_prompt: customPrompt || undefined,
          })
        : await imageGenerationApi.generateSceneImage(sceneId, {
            style: selectedStyle,
            checkpoint: selectedCheckpoint || undefined,
            steps: defaultSteps,
            cfg_scale: defaultCfgScale,
            custom_prompt: customPrompt || undefined,
          });

      if (result.status === 'completed' && result.image_id) {
        setGenerationProgress({ status: 'complete', message: 'Image generated!' });

        // Show the prompt that was actually used for generation
        if (result.prompt) {
          setCustomPrompt(result.prompt);
        }

        // Add new image to the list and select it
        const newImage: SceneImage = {
          id: result.image_id,
          prompt: result.prompt || customPrompt,
          created_at: new Date().toISOString(),
        };
        setImages(prev => [newImage, ...prev]);
        setCurrentIndex(0);

        const fullUrl = await imageGenerationApi.getImageFileUrl(result.image_id);
        setCurrentImageUrl(fullUrl);
        onImageGenerated?.(result.image_id);
        setTimeout(() => setGenerationProgress({ status: 'idle' }), 2000);
        return;
      }

      // Poll for completion if not done immediately
      setGenerationProgress({ status: 'generating', message: 'Generating image...' });

      let attempts = 0;
      const maxAttempts = 60;

      while (attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 2000));

        try {
          const status = await imageGenerationApi.getJobStatus(result.job_id);

          if (status.status === 'completed' && status.image_id) {
            setGenerationProgress({ status: 'complete', message: 'Image generated!' });

            const newImage: SceneImage = {
              id: status.image_id,
              prompt: customPrompt,
              created_at: new Date().toISOString(),
            };
            setImages(prev => [newImage, ...prev]);
            setCurrentIndex(0);

            const fullUrl = await imageGenerationApi.getImageFileUrl(status.image_id);
            setCurrentImageUrl(fullUrl);
            onImageGenerated?.(status.image_id);
            setTimeout(() => setGenerationProgress({ status: 'idle' }), 2000);
            return;
          } else if (status.status === 'failed') {
            throw new Error(status.error || 'Generation failed');
          }

          if (status.progress !== undefined) {
            setGenerationProgress({
              status: 'generating',
              progress: status.progress,
              message: `Generating... ${Math.round(status.progress * 100)}%`
            });
          }
        } catch (pollError: any) {
          if (pollError.message?.includes('not found') && result.image_id) {
            setGenerationProgress({ status: 'complete', message: 'Image generated!' });

            const newImage: SceneImage = {
              id: result.image_id,
              prompt: customPrompt,
              created_at: new Date().toISOString(),
            };
            setImages(prev => [newImage, ...prev]);
            setCurrentIndex(0);

            const fullUrl = await imageGenerationApi.getImageFileUrl(result.image_id);
            setCurrentImageUrl(fullUrl);
            onImageGenerated?.(result.image_id);
            setTimeout(() => setGenerationProgress({ status: 'idle' }), 2000);
            return;
          }
          console.warn('Poll error:', pollError);
        }

        attempts++;
      }

      throw new Error('Generation timed out');
    } catch (err: any) {
      console.error('Scene image generation failed:', err);
      setError(err.message || 'Failed to generate image');
      setGenerationProgress({ status: 'error', message: err.message || 'Generation failed' });
      setTimeout(() => setGenerationProgress({ status: 'idle' }), 3000);
    }
  }, [sceneId, serverStatus, selectedStyle, selectedCheckpoint, customPrompt, onImageGenerated, subjectType, selectedCharacterId, defaultSteps, defaultCfgScale]);

  const handleDelete = useCallback(async () => {
    if (images.length === 0) return;

    const currentImage = images[currentIndex];
    if (!currentImage) return;

    // First tap: show confirmation state
    if (!confirmingDeleteRef.current) {
      confirmingDeleteRef.current = true;
      setConfirmingDelete(true);
      // Auto-reset after 3 seconds if not confirmed
      setTimeout(() => {
        confirmingDeleteRef.current = false;
        setConfirmingDelete(false);
      }, 3000);
      return;
    }

    // Second tap: actually delete
    confirmingDeleteRef.current = false;
    setConfirmingDelete(false);

    try {
      setLoading(true);
      await imageGenerationApi.deleteImage(currentImage.id);

      // Remove from list
      const newImages = images.filter((_, i) => i !== currentIndex);
      setImages(newImages);

      // Adjust index
      if (newImages.length === 0) {
        setCurrentIndex(0);
        setCurrentImageUrl(null);
      } else if (currentIndex >= newImages.length) {
        setCurrentIndex(newImages.length - 1);
      }
    } catch (err: any) {
      console.error('Failed to delete image:', err);
      setError(err.message || 'Failed to delete image');
    } finally {
      setLoading(false);
    }
  }, [images, currentIndex]);

  const handleDownload = useCallback(async () => {
    if (!currentImageUrl) return;

    try {
      const response = await fetch(currentImageUrl);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `scene_${sceneId}_image_${currentIndex + 1}.png`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to download image:', err);
    }
  }, [currentImageUrl, sceneId, currentIndex]);

  const navigatePrev = () => {
    if (currentIndex < images.length - 1) {
      setCurrentIndex(currentIndex + 1);
      confirmingDeleteRef.current = false;
      setConfirmingDelete(false);
    }
  };

  const navigateNext = () => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
      confirmingDeleteRef.current = false;
      setConfirmingDelete(false);
    }
  };

  const isGenerating = generationProgress.status === 'connecting' || generationProgress.status === 'generating';
  const canGenerate = serverStatus?.online && !isGenerating && !loading
    && (subjectType === 'scene' || selectedCharacterId !== null);
  const hasImages = images.length > 0;
  const canNavigatePrev = currentIndex < images.length - 1;
  const canNavigateNext = currentIndex > 0;

  // Don't render anything if no images and not currently generating
  // Unless forceShow is true (user clicked to open the generator)
  if (!hasImages && !isGenerating && !loading && !forceShow) {
    return null;
  }

  return (
    <div className="mt-4 pt-4 border-t border-white/10">
      {/* Header with collapse toggle and close button */}
      <div className="flex items-center justify-between mb-3">
        {hasImages && (
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="flex items-center gap-1.5 text-sm font-medium text-white/70 hover:text-white/90 transition-colors"
            title={collapsed ? 'Show image' : 'Hide image'}
          >
            <ChevronRight className={`w-3.5 h-3.5 transition-transform duration-200 ${collapsed ? '' : 'rotate-90'}`} />
            <span>Scene Image</span>
            {images.length > 1 && <span className="text-xs text-white/40">({images.length})</span>}
          </button>
        )}
        {!hasImages && forceShow && (
          <span className="text-sm font-medium text-white/70">Scene Image</span>
        )}
        {forceShow && onClose && (
          <button
            onClick={onClose}
            className="p-1 text-white/50 hover:text-white/80 rounded"
            title="Close"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Image Display */}
      {hasImages && currentImageUrl && !collapsed && (
        <div className="relative mb-3">
          <img
            src={currentImageUrl}
            alt="Scene image"
            className="w-full rounded-lg"
          />

          {/* Generation overlay */}
          {isGenerating && (
            <div className="absolute inset-0 bg-black/60 flex items-center justify-center rounded-lg">
              <div className="text-center">
                <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-2" />
                <span className="text-sm text-white">{generationProgress.message}</span>
              </div>
            </div>
          )}

          {/* Image navigation and actions */}
          <div className="absolute bottom-2 left-2 right-2 z-10 flex items-center justify-between">
            {/* Navigation */}
            <div className="flex items-center gap-1 bg-black/60 rounded-lg px-2 py-1">
              <button
                onClick={navigatePrev}
                disabled={!canNavigatePrev}
                className="p-2 min-w-[36px] min-h-[36px] flex items-center justify-center text-white/70 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
                title="Older image"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-xs text-white/70">
                {images.length - currentIndex} / {images.length}
              </span>
              <button
                onClick={navigateNext}
                disabled={!canNavigateNext}
                className="p-2 min-w-[36px] min-h-[36px] flex items-center justify-center text-white/70 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
                title="Newer image"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-1 bg-black/60 rounded-lg px-2 py-1">
              <button
                onClick={handleDownload}
                className="p-2 min-w-[36px] min-h-[36px] flex items-center justify-center text-white/70 hover:text-white"
                title="Download"
              >
                <Download className="w-4 h-4" />
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); handleDelete(); }}
                className={`p-2 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation ${
                  confirmingDelete
                    ? 'text-red-400 bg-red-900/50 rounded'
                    : 'text-white/70 hover:text-red-400'
                }`}
                title={confirmingDelete ? 'Tap again to delete' : 'Delete'}
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Generating placeholder when no existing images */}
      {!hasImages && isGenerating && (
        <div className="mb-3 p-6 bg-white/5 rounded-lg text-center">
          <div className="w-8 h-8 border-2 border-purple-400/30 border-t-purple-400 rounded-full animate-spin mx-auto mb-2" />
          <p className="text-sm text-white/70">{generationProgress.message}</p>
        </div>
      )}

      {/* Prompt to generate when forceShow but no images */}
      {!hasImages && !isGenerating && forceShow && (
        <div className="mb-3 p-4 bg-white/5 rounded-lg text-center">
          <Sparkles className="w-6 h-6 text-purple-400/70 mx-auto mb-2" />
          <p className="text-sm text-white/60">Click Generate to create an image for this scene</p>
        </div>
      )}

      {/* Controls - hidden when collapsed */}
      {!collapsed && <div className="flex items-center gap-2">
        <button
          onClick={handleGenerate}
          disabled={!canGenerate}
          className="flex items-center gap-2 px-3 py-1.5 bg-purple-500/20 text-purple-300 rounded-lg hover:bg-purple-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm"
        >
          {isGenerating ? (
            <>
              <div className="w-3.5 h-3.5 border-2 border-purple-300/30 border-t-purple-300 rounded-full animate-spin" />
              <span>Generating...</span>
            </>
          ) : (
            <>
              {hasImages ? <RefreshCw className="w-3.5 h-3.5" /> : <Sparkles className="w-3.5 h-3.5" />}
              <span>{hasImages ? 'Regenerate' : 'Generate'}</span>
            </>
          )}
        </button>

        <button
          onClick={() => setShowOptions(!showOptions)}
          className="flex items-center gap-1 px-2 py-1.5 text-white/60 hover:text-white/80 text-sm"
        >
          <span>Options</span>
          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showOptions ? 'rotate-180' : ''}`} />
        </button>

        {/* Server status indicator */}
        <div className="ml-auto flex items-center gap-1.5 text-xs text-white/40">
          <div className={`w-1.5 h-1.5 rounded-full ${serverStatus?.online ? 'bg-green-500' : 'bg-red-500'}`} />
          <span>{serverStatus?.online ? 'Connected' : 'Offline'}</span>
        </div>
      </div>}

      {/* Options Panel */}
      {!collapsed && showOptions && (
        <div className="mt-3 space-y-3 p-3 bg-white/5 rounded-lg border border-white/10">
          {/* Subject Type */}
          <div>
            <label className="block text-xs font-medium text-white/70 mb-1">Subject</label>
            <div className="flex gap-1">
              <button
                onClick={() => { setSubjectType('scene'); setCustomPrompt(''); }}
                className={`flex-1 px-3 py-1.5 text-xs rounded transition-colors ${
                  subjectType === 'scene'
                    ? 'bg-purple-500/30 text-purple-300 border border-purple-500/50'
                    : 'bg-white/5 text-white/60 border border-white/10 hover:bg-white/10'
                }`}
              >
                Scene
              </button>
              <button
                onClick={() => { setSubjectType('character'); setCustomPrompt(''); }}
                className={`flex-1 flex items-center justify-center gap-1 px-3 py-1.5 text-xs rounded transition-colors ${
                  subjectType === 'character'
                    ? 'bg-purple-500/30 text-purple-300 border border-purple-500/50'
                    : 'bg-white/5 text-white/60 border border-white/10 hover:bg-white/10'
                }`}
              >
                <User className="w-3 h-3" />
                Character
              </button>
            </div>
          </div>

          {/* Character Selection (only when character mode) */}
          {subjectType === 'character' && (
            <div>
              <label className="block text-xs font-medium text-white/70 mb-1">Character</label>
              <select
                value={selectedCharacterId ?? ''}
                onChange={(e) => { setSelectedCharacterId(Number(e.target.value)); setCustomPrompt(''); }}
                className="w-full p-1.5 text-xs bg-gray-800 border border-white/20 rounded text-white focus:outline-none focus:ring-1 focus:ring-purple-500 [&>option]:bg-gray-800"
              >
                {storyCharacters.length === 0 && (
                  <option value="">Loading characters...</option>
                )}
                {storyCharacters.map((sc) => (
                  <option key={sc.character_id} value={sc.character_id}>{sc.name}</option>
                ))}
              </select>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            {/* Model Selection */}
            <div>
              <label className="block text-xs font-medium text-white/70 mb-1">Model</label>
              <select
                value={selectedCheckpoint}
                onChange={(e) => setSelectedCheckpoint(e.target.value)}
                disabled={!availableModels?.checkpoints?.length}
                className="w-full p-1.5 text-xs bg-gray-800 border border-white/20 rounded text-white focus:outline-none focus:ring-1 focus:ring-purple-500 [&>option]:bg-gray-800"
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
              <label className="block text-xs font-medium text-white/70 mb-1">Style</label>
              <select
                value={selectedStyle}
                onChange={(e) => setSelectedStyle(e.target.value)}
                className="w-full p-1.5 text-xs bg-gray-800 border border-white/20 rounded text-white focus:outline-none focus:ring-1 focus:ring-purple-500 [&>option]:bg-gray-800"
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
          </div>

          {/* Custom Prompt */}
          <div>
            <label className="block text-xs font-medium text-white/70 mb-1">Prompt</label>
            <textarea
              value={customPrompt}
              onChange={(e) => setCustomPrompt(e.target.value)}
              onFocus={(e) => {
                // Prevent browser from scrolling the parent scene list when focusing
                // Same pattern as choice editing in SceneVariantDisplay
                if (promptFocusHandledRef.current) {
                  promptFocusHandledRef.current = false;
                  return;
                }
                promptFocusHandledRef.current = true;
                const el = e.target;
                el.blur();
                requestAnimationFrame(() => {
                  el.focus({ preventScroll: true });
                });
              }}
              placeholder={subjectType === 'character' ? 'Leave empty for AI-generated prompt from character state' : 'Leave empty for AI-generated prompt from scene content'}
              className="w-full p-2 text-xs bg-gray-800 border border-white/20 rounded text-white placeholder-white/40 focus:outline-none focus:ring-1 focus:ring-purple-500 resize-none"
              rows={3}
            />
          </div>
        </div>
      )}

      {/* Error Message */}
      {!collapsed && error && (
        <div className="mt-2 text-xs text-red-400 bg-red-500/10 px-3 py-2 rounded">
          {error}
        </div>
      )}
    </div>
  );
}
