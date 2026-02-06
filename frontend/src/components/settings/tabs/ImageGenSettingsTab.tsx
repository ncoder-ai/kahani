'use client';

import { useState, useEffect } from 'react';
import { Image, Loader2, Check, AlertCircle, RefreshCw } from 'lucide-react';
import { getApiBaseUrl } from '@/lib/api';
import { imageGenerationApi } from '@/lib/api/index';
import type { ServerStatus, AvailableModels, StylePresetsResponse } from '@/lib/api/imageGeneration';
import { SettingsTabProps } from '../types';

export interface ImageGenSettings {
  enabled: boolean;
  comfyui_server_url: string;
  comfyui_api_key: string;
  comfyui_checkpoint: string;
  comfyui_model_type: string;
  width: number;
  height: number;
  steps: number;
  cfg_scale: number;
  default_style: string;
  use_extraction_llm_for_prompts: boolean;
}

interface ImageGenSettingsTabProps extends SettingsTabProps {
  imageGenSettings: ImageGenSettings;
  setImageGenSettings: React.Dispatch<React.SetStateAction<ImageGenSettings>>;
}

export default function ImageGenSettingsTab({
  token,
  showMessage,
  imageGenSettings,
  setImageGenSettings,
}: ImageGenSettingsTabProps) {
  // Server status
  const [serverStatus, setServerStatus] = useState<ServerStatus | null>(null);
  const [isCheckingServer, setIsCheckingServer] = useState(false);

  // Available models from ComfyUI
  const [availableModels, setAvailableModels] = useState<AvailableModels>({
    checkpoints: [],
    samplers: [],
    schedulers: [],
  });
  const [isLoadingModels, setIsLoadingModels] = useState(false);

  // Style presets
  const [stylePresets, setStylePresets] = useState<Record<string, { name: string; description: string }>>({});

  // Save state
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    loadStylePresets();
    // Auto-check server status and load models silently if URL is configured
    if (imageGenSettings.comfyui_server_url) {
      autoCheckServerAndLoadModels();
    }
  }, []);

  const loadStylePresets = async () => {
    try {
      const response = await imageGenerationApi.getStylePresets();
      const presets: Record<string, { name: string; description: string }> = {};
      for (const [key, preset] of Object.entries(response.presets || {})) {
        const typedPreset = preset as { name: string; description: string };
        presets[key] = { name: typedPreset.name, description: typedPreset.description };
      }
      setStylePresets(presets);
    } catch (error) {
      console.error('Failed to load style presets:', error);
    }
  };

  const autoCheckServerAndLoadModels = async () => {
    setIsCheckingServer(true);
    setServerStatus(null);
    try {
      const status = await imageGenerationApi.getServerStatus();
      setServerStatus(status);
      if (status.online) {
        // Silently load models
        setIsLoadingModels(true);
        try {
          const models = await imageGenerationApi.getAvailableModels();
          setAvailableModels(models);
        } catch (error) {
          // Silent failure
        } finally {
          setIsLoadingModels(false);
        }
      }
    } catch (error) {
      setServerStatus({ online: false, error: 'Connection failed', queue_running: 0, queue_pending: 0, gpu_memory: {} });
    } finally {
      setIsCheckingServer(false);
    }
  };

  const checkServerStatus = async () => {
    if (!imageGenSettings.comfyui_server_url) {
      showMessage('Please enter a ComfyUI server URL first', 'error');
      return;
    }

    setIsCheckingServer(true);
    setServerStatus(null);

    try {
      const status = await imageGenerationApi.getServerStatus();
      setServerStatus(status);

      if (status.online) {
        showMessage('ComfyUI server is online', 'success');
        // Load available models
        loadAvailableModels();
      } else {
        showMessage(status.error || 'Server is offline', 'error');
      }
    } catch (error) {
      console.error('Server check failed:', error);
      setServerStatus({ online: false, error: 'Connection failed', queue_running: 0, queue_pending: 0, gpu_memory: {} });
      showMessage('Failed to connect to ComfyUI server', 'error');
    } finally {
      setIsCheckingServer(false);
    }
  };

  const loadAvailableModels = async () => {
    setIsLoadingModels(true);
    try {
      const models = await imageGenerationApi.getAvailableModels();
      setAvailableModels(models);

      if (models.checkpoints.length > 0) {
        showMessage(`Found ${models.checkpoints.length} checkpoints`, 'success');
      }
    } catch (error) {
      console.error('Failed to load models:', error);
      showMessage('Failed to load available models', 'error');
    } finally {
      setIsLoadingModels(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          image_generation_settings: {
            enabled: imageGenSettings.enabled,
            comfyui_server_url: imageGenSettings.comfyui_server_url,
            comfyui_api_key: imageGenSettings.comfyui_api_key,
            comfyui_checkpoint: imageGenSettings.comfyui_checkpoint,
            comfyui_model_type: imageGenSettings.comfyui_model_type,
            width: imageGenSettings.width,
            height: imageGenSettings.height,
            steps: imageGenSettings.steps,
            cfg_scale: imageGenSettings.cfg_scale,
            default_style: imageGenSettings.default_style,
            use_extraction_llm_for_prompts: imageGenSettings.use_extraction_llm_for_prompts,
          },
        }),
      });

      if (response.ok) {
        showMessage('Image generation settings saved', 'success');
      } else {
        const error = await response.json().catch(() => ({ detail: 'Failed to save settings' }));
        showMessage(error.detail || 'Failed to save settings', 'error');
      }
    } catch (error) {
      showMessage('Failed to save settings', 'error');
    } finally {
      setIsSaving(false);
    }
  };

  // Detect model type from checkpoint name
  const detectModelType = (checkpointName: string): string => {
    const name = checkpointName.toLowerCase();
    if (name.includes('flux')) return 'flux';
    if (name.includes('sdxl') || name.includes('xl')) return 'sdxl';
    if (name.includes('sd15') || name.includes('sd1.5') || name.includes('v1-5')) return 'sd15';
    return 'sdxl'; // Default to SDXL
  };

  const handleCheckpointChange = (checkpoint: string) => {
    const modelType = detectModelType(checkpoint);
    setImageGenSettings(prev => ({
      ...prev,
      comfyui_checkpoint: checkpoint,
      comfyui_model_type: modelType,
    }));
  };

  return (
    <div className="space-y-6">
      {/* Enable Toggle */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Image className="w-5 h-5" />
          Image Generation
        </h3>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={imageGenSettings.enabled}
            onChange={(e) => setImageGenSettings(prev => ({ ...prev, enabled: e.target.checked }))}
            className="w-4 h-4 rounded"
          />
          <span className="text-sm text-white">Enable Image Generation</span>
        </label>
        <p className="text-xs text-gray-400">
          Generate character portraits and scene images using ComfyUI
        </p>
      </div>

      {imageGenSettings.enabled && (
        <>
          {/* ComfyUI Server Configuration */}
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-white mb-4">ComfyUI Server</h3>

            <div>
              <label className="block text-sm font-medium text-white mb-2">Server URL</label>
              <input
                type="url"
                value={imageGenSettings.comfyui_server_url}
                onChange={(e) => setImageGenSettings(prev => ({ ...prev, comfyui_server_url: e.target.value }))}
                placeholder="http://localhost:8188"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <p className="text-xs text-gray-400 mt-1">
                URL to your ComfyUI server (can be behind a reverse proxy)
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-white mb-2">API Key (Optional)</label>
              <input
                type="password"
                value={imageGenSettings.comfyui_api_key}
                onChange={(e) => setImageGenSettings(prev => ({ ...prev, comfyui_api_key: e.target.value }))}
                placeholder="Enter API key if required"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            {/* Server Status */}
            <div className="flex items-center gap-3">
              <button
                onClick={checkServerStatus}
                disabled={isCheckingServer || !imageGenSettings.comfyui_server_url}
                className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isCheckingServer ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Checking...</span>
                  </>
                ) : serverStatus?.online ? (
                  <>
                    <Check className="w-4 h-4 text-green-400" />
                    <span>Connected</span>
                  </>
                ) : serverStatus?.online === false ? (
                  <>
                    <AlertCircle className="w-4 h-4 text-red-400" />
                    <span>Offline</span>
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4" />
                    <span>Test Connection</span>
                  </>
                )}
              </button>

              {serverStatus?.online && (
                <span className="text-sm text-gray-400">
                  Queue: {serverStatus.queue_running} running, {serverStatus.queue_pending} pending
                </span>
              )}
            </div>
          </div>

          {/* Model Selection */}
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-white mb-4">Model Selection</h3>

            <div>
              <label className="block text-sm font-medium text-white mb-2">Checkpoint</label>
              <div className="flex gap-2">
                <select
                  value={imageGenSettings.comfyui_checkpoint}
                  onChange={(e) => handleCheckpointChange(e.target.value)}
                  disabled={isLoadingModels || availableModels.checkpoints.length === 0}
                  className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
                >
                  {availableModels.checkpoints.length === 0 ? (
                    <option value="">Connect to load checkpoints</option>
                  ) : (
                    <>
                      <option value="">Select a checkpoint...</option>
                      {availableModels.checkpoints.map((checkpoint) => (
                        <option key={checkpoint} value={checkpoint}>
                          {checkpoint}
                        </option>
                      ))}
                    </>
                  )}
                </select>
                <button
                  onClick={loadAvailableModels}
                  disabled={isLoadingModels || !serverStatus?.online}
                  className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors disabled:opacity-50"
                  title="Refresh models"
                >
                  <RefreshCw className={`w-4 h-4 ${isLoadingModels ? 'animate-spin' : ''}`} />
                </button>
              </div>
              <p className="text-xs text-gray-400 mt-1">
                Model type: {imageGenSettings.comfyui_model_type.toUpperCase() || 'Auto-detected'}
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-white mb-2">Default Style</label>
              <select
                value={imageGenSettings.default_style}
                onChange={(e) => setImageGenSettings(prev => ({ ...prev, default_style: e.target.value }))}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
              >
                {Object.entries(stylePresets).map(([key, preset]) => (
                  <option key={key} value={key}>
                    {preset.name} - {preset.description}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Generation Defaults */}
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-white mb-4">Generation Defaults</h3>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-white mb-2">Width</label>
                <input
                  type="number"
                  value={imageGenSettings.width}
                  onChange={(e) => setImageGenSettings(prev => ({ ...prev, width: parseInt(e.target.value) || 1024 }))}
                  min={256}
                  max={2048}
                  step={64}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-white mb-2">Height</label>
                <input
                  type="number"
                  value={imageGenSettings.height}
                  onChange={(e) => setImageGenSettings(prev => ({ ...prev, height: parseInt(e.target.value) || 1024 }))}
                  min={256}
                  max={2048}
                  step={64}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Steps: {imageGenSettings.steps}
              </label>
              <input
                type="range"
                min={1}
                max={50}
                value={imageGenSettings.steps}
                onChange={(e) => setImageGenSettings(prev => ({ ...prev, steps: parseInt(e.target.value) }))}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
              />
              <p className="text-xs text-gray-400 mt-1">
                Lower steps = faster (4-8 for lightning/turbo models)
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-white mb-2">
                CFG Scale: {imageGenSettings.cfg_scale.toFixed(1)}
              </label>
              <input
                type="range"
                min={1}
                max={20}
                step={0.5}
                value={imageGenSettings.cfg_scale}
                onChange={(e) => setImageGenSettings(prev => ({ ...prev, cfg_scale: parseFloat(e.target.value) }))}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
              />
              <p className="text-xs text-gray-400 mt-1">
                Lower CFG for lightning/turbo models (1-2)
              </p>
            </div>
          </div>

          {/* Advanced Settings */}
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-white mb-4">Advanced</h3>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={imageGenSettings.use_extraction_llm_for_prompts}
                onChange={(e) => setImageGenSettings(prev => ({ ...prev, use_extraction_llm_for_prompts: e.target.checked }))}
                className="w-4 h-4 rounded"
              />
              <span className="text-sm text-white">Use Extraction LLM for prompt generation</span>
            </label>
            <p className="text-xs text-gray-400">
              When enabled, uses the extraction model (if configured) instead of main LLM for converting scene/character descriptions to image prompts
            </p>
          </div>

          {/* Save Button */}
          <div className="flex items-center justify-end pt-6 border-t border-gray-700">
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="flex items-center gap-2 px-6 py-2 theme-btn-primary rounded-lg font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Saving...</span>
                </>
              ) : (
                <span>Save Image Generation Settings</span>
              )}
            </button>
          </div>
        </>
      )}

      {/* Save button for disabled state */}
      {!imageGenSettings.enabled && (
        <div className="flex items-center justify-end pt-6 border-t border-gray-700">
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="flex items-center gap-2 px-6 py-2 theme-btn-primary rounded-lg font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Saving...</span>
              </>
            ) : (
              <span>Save Settings</span>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
