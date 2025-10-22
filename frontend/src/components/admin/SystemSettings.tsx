'use client';

import { useState, useEffect } from 'react';
import { API_BASE_URL } from '@/lib/api';
import { useAuthStore } from '@/store';

interface SystemSettingsData {
  // Default permissions for new users
  default_allow_nsfw: boolean;
  default_can_change_llm_provider: boolean;
  default_can_change_tts_settings: boolean;
  default_can_use_stt: boolean;
  default_can_use_image_generation: boolean;
  default_can_export_stories: boolean;
  default_can_import_stories: boolean;
  // Default resource limits
  default_max_stories: number | null;
  default_max_images_per_story: number | null;
  default_max_stt_minutes_per_month: number | null;
  // Default LLM configuration
  default_llm_api_url: string | null;
  default_llm_api_key: string | null;
  default_llm_model_name: string | null;
  default_llm_temperature: number | null;
  // Registration settings
  registration_requires_approval: boolean;
}

export default function SystemSettings() {
  const { token } = useAuthStore();
  const [settings, setSettings] = useState<SystemSettingsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/api/admin/settings`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) throw new Error('Failed to fetch settings');
      
      const data = await response.json();
      setSettings(data.settings);
    } catch (error) {
      console.error('Error fetching settings:', error);
      showMessage('error', 'Failed to load system settings');
    } finally {
      setLoading(false);
    }
  };

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const saveSettings = async () => {
    if (!settings) return;

    try {
      setSaving(true);
      const response = await fetch(`${API_BASE_URL}/api/admin/settings`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(settings),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to update settings');
      }
      
      showMessage('success', 'Settings updated successfully');
      fetchSettings();
    } catch (error) {
      console.error('Error updating settings:', error);
      showMessage('error', error instanceof Error ? error.message : 'Failed to update settings');
    } finally {
      setSaving(false);
    }
  };

  const updateSetting = (key: keyof SystemSettingsData, value: any) => {
    if (!settings) return;
    setSettings({ ...settings, [key]: value });
  };

  if (loading) {
    return (
      <div className="text-center py-12">
        <div className="w-12 h-12 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
        <p className="text-white/70">Loading settings...</p>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="text-center py-12">
        <p className="text-red-400">Failed to load settings</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Message */}
      {message && (
        <div className={`p-4 rounded-lg border ${
          message.type === 'success'
            ? 'bg-green-500/20 border-green-400/30 text-green-100'
            : 'bg-red-500/20 border-red-400/30 text-red-100'
        }`}>
          {message.text}
        </div>
      )}

      {/* Registration Settings */}
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white">Registration Settings</h3>
        <div className="space-y-4 bg-white/5 rounded-lg p-6">
          <label className="flex items-center space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.registration_requires_approval}
              onChange={(e) => updateSetting('registration_requires_approval', e.target.checked)}
              className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-purple-500 focus:ring-purple-500"
            />
            <div>
              <span className="text-white font-medium">Require Admin Approval</span>
              <p className="text-white/60 text-sm">New users must be approved before accessing the app</p>
            </div>
          </label>
        </div>
      </div>

      {/* Default Permissions */}
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white">Default Permissions for New Users</h3>
        <div className="space-y-4 bg-white/5 rounded-lg p-6">
          
          <label className="flex items-center space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.default_allow_nsfw}
              onChange={(e) => updateSetting('default_allow_nsfw', e.target.checked)}
              className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-purple-500 focus:ring-purple-500"
            />
            <div>
              <span className="text-white font-medium">Allow NSFW Content</span>
              <p className="text-white/60 text-sm">Enable adult content for new users by default</p>
            </div>
          </label>

          <label className="flex items-center space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.default_can_change_llm_provider}
              onChange={(e) => updateSetting('default_can_change_llm_provider', e.target.checked)}
              className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-purple-500 focus:ring-purple-500"
            />
            <div>
              <span className="text-white font-medium">Can Change LLM Provider</span>
              <p className="text-white/60 text-sm">Allow LLM provider configuration changes</p>
            </div>
          </label>

          <label className="flex items-center space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.default_can_change_tts_settings}
              onChange={(e) => updateSetting('default_can_change_tts_settings', e.target.checked)}
              className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-purple-500 focus:ring-purple-500"
            />
            <div>
              <span className="text-white font-medium">Can Change TTS Settings</span>
              <p className="text-white/60 text-sm">Allow TTS provider configuration changes</p>
            </div>
          </label>

          <label className="flex items-center space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.default_can_use_stt}
              onChange={(e) => updateSetting('default_can_use_stt', e.target.checked)}
              className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-purple-500 focus:ring-purple-500"
            />
            <div>
              <span className="text-white font-medium">Can Use STT (Future)</span>
              <p className="text-white/60 text-sm">Enable speech-to-text functionality</p>
            </div>
          </label>

          <label className="flex items-center space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.default_can_use_image_generation}
              onChange={(e) => updateSetting('default_can_use_image_generation', e.target.checked)}
              className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-purple-500 focus:ring-purple-500"
            />
            <div>
              <span className="text-white font-medium">Can Use Image Generation (Future)</span>
              <p className="text-white/60 text-sm">Enable AI image generation features</p>
            </div>
          </label>

          <label className="flex items-center space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.default_can_export_stories}
              onChange={(e) => updateSetting('default_can_export_stories', e.target.checked)}
              className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-purple-500 focus:ring-purple-500"
            />
            <div>
              <span className="text-white font-medium">Can Export Stories</span>
              <p className="text-white/60 text-sm">Allow story export functionality</p>
            </div>
          </label>

          <label className="flex items-center space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.default_can_import_stories}
              onChange={(e) => updateSetting('default_can_import_stories', e.target.checked)}
              className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-purple-500 focus:ring-purple-500"
            />
            <div>
              <span className="text-white font-medium">Can Import Stories</span>
              <p className="text-white/60 text-sm">Allow story import functionality</p>
            </div>
          </label>
        </div>
      </div>

      {/* Default Resource Limits */}
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white">Default Resource Limits</h3>
        <div className="space-y-4 bg-white/5 rounded-lg p-6">
          
          <div>
            <label className="block text-white font-medium mb-2">Maximum Stories</label>
            <input
              type="number"
              value={settings.default_max_stories || ''}
              onChange={(e) => updateSetting('default_max_stories', e.target.value ? parseInt(e.target.value) : null)}
              placeholder="Unlimited"
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
            />
            <p className="text-white/60 text-sm mt-1">Leave empty for unlimited stories</p>
          </div>

          <div>
            <label className="block text-white font-medium mb-2">Maximum Images per Story (Future)</label>
            <input
              type="number"
              value={settings.default_max_images_per_story || ''}
              onChange={(e) => updateSetting('default_max_images_per_story', e.target.value ? parseInt(e.target.value) : null)}
              placeholder="Unlimited"
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
            />
            <p className="text-white/60 text-sm mt-1">For AI image generation features</p>
          </div>

          <div>
            <label className="block text-white font-medium mb-2">STT Minutes per Month (Future)</label>
            <input
              type="number"
              value={settings.default_max_stt_minutes_per_month || ''}
              onChange={(e) => updateSetting('default_max_stt_minutes_per_month', e.target.value ? parseInt(e.target.value) : null)}
              placeholder="Unlimited"
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
            />
            <p className="text-white/60 text-sm mt-1">For speech-to-text usage limits</p>
          </div>
        </div>
      </div>

      {/* Default LLM Configuration */}
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-white">Default LLM Configuration</h3>
        <div className="space-y-4 bg-white/5 rounded-lg p-6">
          
          <div>
            <label className="block text-white font-medium mb-2">Default API URL</label>
            <input
              type="url"
              value={settings.default_llm_api_url || ''}
              onChange={(e) => updateSetting('default_llm_api_url', e.target.value || null)}
              placeholder="e.g., http://localhost:11434/v1"
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
            />
            <p className="text-white/60 text-sm mt-1">Default LLM API endpoint for new users</p>
          </div>

          <div>
            <label className="block text-white font-medium mb-2">Default API Key</label>
            <input
              type="password"
              value={settings.default_llm_api_key || ''}
              onChange={(e) => updateSetting('default_llm_api_key', e.target.value || null)}
              placeholder="Leave empty if not required"
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
            />
            <p className="text-white/60 text-sm mt-1">Optional API key for authentication</p>
          </div>

          <div>
            <label className="block text-white font-medium mb-2">Default Model Name</label>
            <input
              type="text"
              value={settings.default_llm_model_name || ''}
              onChange={(e) => updateSetting('default_llm_model_name', e.target.value || null)}
              placeholder="e.g., llama3.2:latest"
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
            />
            <p className="text-white/60 text-sm mt-1">Default model for new users</p>
          </div>

          <div>
            <label className="block text-white font-medium mb-2">Default Temperature</label>
            <input
              type="number"
              step="0.1"
              min="0"
              max="2"
              value={settings.default_llm_temperature || ''}
              onChange={(e) => updateSetting('default_llm_temperature', e.target.value ? parseFloat(e.target.value) : null)}
              placeholder="0.7"
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
            />
            <p className="text-white/60 text-sm mt-1">Controls randomness (0.0 - 2.0)</p>
          </div>
        </div>
      </div>

      {/* Save Button */}
      <div className="flex justify-end pt-6 border-t border-white/20">
        <button
          onClick={saveSettings}
          disabled={saving}
          className="px-8 py-3 rounded-lg bg-gradient-to-r from-purple-500 to-pink-500 text-white hover:from-purple-600 hover:to-pink-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-semibold"
        >
          {saving ? (
            <div className="flex items-center space-x-2">
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
              <span>Saving...</span>
            </div>
          ) : (
            'Save Settings'
          )}
        </button>
      </div>
    </div>
  );
}

