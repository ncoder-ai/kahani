'use client';

import { useState, useEffect } from 'react';
import { useAuthStore } from '@/store';
import { useUISettings } from '@/hooks/useUISettings';
import { useNotifications } from '@/hooks/useNotifications';
import WritingPresetsManager from '@/components/writing-presets/WritingPresetsManager';
import { API_BASE_URL } from '@/lib/api';
import { X, Settings, Save, TestTube } from 'lucide-react';

interface LLMSettings {
  temperature: number;
  top_p: number;
  top_k: number;
  repetition_penalty: number;
  max_tokens: number;
  // API Configuration
  api_url: string;
  api_key: string;
  api_type: string;
  model_name: string;
}

interface ContextSettings {
  max_tokens: number;
  keep_recent_scenes: number;
  summary_threshold: number;
  summary_threshold_tokens: number;
  enable_summarization: boolean;
  // Semantic Memory Settings
  enable_semantic_memory?: boolean;
  context_strategy?: string;
  semantic_search_top_k?: number;
  semantic_scenes_in_context?: number;
  semantic_context_weight?: number;
  character_moments_in_context?: number;
  auto_extract_character_moments?: boolean;
  auto_extract_plot_events?: boolean;
}

interface GenerationPreferences {
  default_genre: string;
  default_tone: string;
  default_perspective: string;
  default_length: string;
}

interface UIPreferences {
  theme: string;
  font_size: string;
  sidebar_collapsed: boolean;
  show_advanced_options: boolean;
}

interface SettingsPreset {
  id: string;
  name: string;
  description: string;
  settings: Partial<LLMSettings> & Partial<ContextSettings> & Partial<GenerationPreferences>;
}

interface UserSettings {
  llm_settings: LLMSettings;
  context_settings: ContextSettings;
  generation_preferences: GenerationPreferences;
  ui_preferences: UIPreferences;
  writing_presets: Record<string, SettingsPreset>;
}

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

export default function SettingsModal({ isOpen, onClose, onSaved }: SettingsModalProps) {
  const { user, token } = useAuthStore();
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [presets, setPresets] = useState<Record<string, SettingsPreset>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('writing');
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState<'success' | 'error' | 'info'>('success');
  const { addNotification } = useNotifications();

  // Permission checks
  const canChangeLLMProvider = user?.can_change_llm_provider ?? true;
  const canChangeTTSSettings = user?.can_change_tts_settings ?? true;

  // Model management state
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [currentModel, setCurrentModel] = useState<string>('');
  const [loadingModels, setLoadingModels] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);

  // Prompt templates state
  const [promptTemplates, setPromptTemplates] = useState<any[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<any>(null);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState(false);

  // Apply UI settings when they change
  useUISettings(settings?.ui_preferences || null);

  useEffect(() => {
    if (isOpen && user) {
      loadSettings();
      loadPresets();
      if (activeTab === 'prompts') {
        loadPromptTemplates();
      }
    }
  }, [isOpen, user, activeTab]);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/api/settings/`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to load settings');
      }

      const data = await response.json();
      // The API returns { settings: { ... } }, so we need to extract the settings object
      setSettings(data.settings || data);
    } catch (error) {
      console.error('Error loading settings:', error);
      setMessage('Failed to load settings');
      setMessageType('error');
    } finally {
      setLoading(false);
    }
  };

  const loadPresets = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/writing-presets/`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setPresets(data);
      }
    } catch (error) {
      console.error('Error loading presets:', error);
    }
  };

  const loadPromptTemplates = async () => {
    try {
      setLoadingTemplates(true);
      const response = await fetch(`${API_BASE_URL}/api/prompt-templates/`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setPromptTemplates(data);
      }
    } catch (error) {
      console.error('Error loading prompt templates:', error);
    } finally {
      setLoadingTemplates(false);
    }
  };

  const saveSettings = async () => {
    if (!settings) return;

    try {
      setSaving(true);
      const response = await fetch(`${API_BASE_URL}/api/settings/`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ settings }),
      });

      if (!response.ok) {
        throw new Error('Failed to save settings');
      }

      setMessage('Settings saved successfully');
      setMessageType('success');
      addNotification('Settings saved successfully', 'success');
      
      if (onSaved) {
        onSaved();
      }
    } catch (error) {
      console.error('Error saving settings:', error);
      setMessage('Failed to save settings');
      setMessageType('error');
      addNotification('Failed to save settings', 'error');
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async () => {
    if (!settings?.llm_settings) return;

    try {
      setTestingConnection(true);
      const response = await fetch(`${API_BASE_URL}/api/settings/test-connection`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ settings: { llm_settings: settings.llm_settings } }),
      });

      if (response.ok) {
        setMessage('Connection test successful');
        setMessageType('success');
        addNotification('LLM connection test successful', 'success');
      } else {
        const error = await response.json();
        setMessage(`Connection test failed: ${error.detail || 'Unknown error'}`);
        setMessageType('error');
        addNotification('LLM connection test failed', 'error');
      }
    } catch (error) {
      console.error('Connection test error:', error);
      setMessage('Connection test failed');
      setMessageType('error');
      addNotification('LLM connection test failed', 'error');
    } finally {
      setTestingConnection(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-start justify-center z-[80] p-4 pt-24">
      <div className="bg-gray-900 rounded-lg shadow-xl max-w-4xl w-full max-h-[calc(100vh-10rem)] overflow-y-auto mt-8">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <Settings className="w-6 h-6 text-purple-400" />
            <h2 className="text-xl font-bold text-white">Settings</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-700 rounded transition-colors"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex space-x-1 bg-gray-800 p-1 m-4 rounded-lg overflow-x-auto">
          {[
            { id: 'writing', name: 'Writing Styles' },
            { id: 'llm', name: 'LLM Settings' },
            { id: 'context', name: 'Context Management' },
            { id: 'generation', name: 'Generation' },
            { id: 'prompts', name: '👁️ Prompt Inspector' },
            { id: 'ui', name: 'Interface' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700'
              }`}
            >
              {tab.name}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-6">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
              <span className="ml-2 text-gray-400">Loading settings...</span>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Writing Styles Tab */}
              {activeTab === 'writing' && (
                <div>
                  <h3 className="text-lg font-semibold text-white mb-4">Writing Style Presets</h3>
                  <WritingPresetsManager />
                </div>
              )}

              {/* LLM Settings Tab */}
              {activeTab === 'llm' && settings && settings.llm_settings && (
                <div className="space-y-6">
                  <h3 className="text-lg font-semibold text-white">LLM Configuration</h3>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        API URL
                      </label>
                      <input
                        type="url"
                        value={settings.llm_settings?.api_url || ''}
                        onChange={(e) => setSettings(prev => prev ? {
                          ...prev,
                          llm_settings: { ...prev.llm_settings, api_url: e.target.value }
                        } : null)}
                        className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                        placeholder="http://localhost:1234/v1"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        API Key
                      </label>
                      <input
                        type="password"
                        value={settings.llm_settings?.api_key || ''}
                        onChange={(e) => setSettings(prev => prev ? {
                          ...prev,
                          llm_settings: { ...prev.llm_settings, api_key: e.target.value }
                        } : null)}
                        className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                        placeholder="Optional API key"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        Model Name
                      </label>
                      <input
                        type="text"
                        value={settings.llm_settings?.model_name || ''}
                        onChange={(e) => setSettings(prev => prev ? {
                          ...prev,
                          llm_settings: { ...prev.llm_settings, model_name: e.target.value }
                        } : null)}
                        className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                        placeholder="llama-3.1-8b-instruct"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        Temperature: {settings.llm_settings?.temperature || 0.7}
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="2"
                        step="0.1"
                        value={settings.llm_settings?.temperature || 0.7}
                        onChange={(e) => setSettings(prev => prev ? {
                          ...prev,
                          llm_settings: { ...prev.llm_settings, temperature: parseFloat(e.target.value) }
                        } : null)}
                        className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
                      />
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={testConnection}
                      disabled={testingConnection}
                      className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors disabled:opacity-50"
                    >
                      <TestTube className="w-4 h-4" />
                      {testingConnection ? 'Testing...' : 'Test Connection'}
                    </button>
                  </div>
                </div>
              )}

              {/* Context Management Tab */}
              {activeTab === 'context' && settings && settings.context_settings && (
                <div className="space-y-6">
                  <h3 className="text-lg font-semibold text-white">Context Management</h3>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        Max Context Tokens: {settings.context_settings?.max_tokens || 8000}
                      </label>
                      <input
                        type="range"
                        min="1000"
                        max="32000"
                        step="1000"
                        value={settings.context_settings?.max_tokens || 8000}
                        onChange={(e) => setSettings(prev => prev ? {
                          ...prev,
                          context_settings: { ...prev.context_settings, max_tokens: parseInt(e.target.value) }
                        } : null)}
                        className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        Keep Recent Scenes: {settings.context_settings?.keep_recent_scenes || 5}
                      </label>
                      <input
                        type="range"
                        min="1"
                        max="20"
                        step="1"
                        value={settings.context_settings?.keep_recent_scenes || 5}
                        onChange={(e) => setSettings(prev => prev ? {
                          ...prev,
                          context_settings: { ...prev.context_settings, keep_recent_scenes: parseInt(e.target.value) }
                        } : null)}
                        className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
                      />
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="enable_summarization"
                      checked={settings.context_settings?.enable_summarization || false}
                      onChange={(e) => setSettings(prev => prev ? {
                        ...prev,
                        context_settings: { ...prev.context_settings, enable_summarization: e.target.checked }
                      } : null)}
                      className="w-4 h-4 text-purple-600 bg-gray-800 border-gray-700 rounded focus:ring-purple-500"
                    />
                    <label htmlFor="enable_summarization" className="text-sm text-gray-300">
                      Enable automatic summarization
                    </label>
                  </div>
                </div>
              )}

              {/* Generation Tab */}
              {activeTab === 'generation' && settings && settings.generation_preferences && (
                <div className="space-y-6">
                  <h3 className="text-lg font-semibold text-white">Generation Preferences</h3>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        Default Genre
                      </label>
                      <select
                        value={settings.generation_preferences?.default_genre || 'fantasy'}
                        onChange={(e) => setSettings(prev => prev ? {
                          ...prev,
                          generation_preferences: { ...prev.generation_preferences, default_genre: e.target.value }
                        } : null)}
                        className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      >
                        <option value="fantasy">Fantasy</option>
                        <option value="sci-fi">Science Fiction</option>
                        <option value="mystery">Mystery</option>
                        <option value="romance">Romance</option>
                        <option value="horror">Horror</option>
                        <option value="drama">Drama</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        Default Tone
                      </label>
                      <select
                        value={settings.generation_preferences?.default_tone || 'serious'}
                        onChange={(e) => setSettings(prev => prev ? {
                          ...prev,
                          generation_preferences: { ...prev.generation_preferences, default_tone: e.target.value }
                        } : null)}
                        className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      >
                        <option value="serious">Serious</option>
                        <option value="humorous">Humorous</option>
                        <option value="dark">Dark</option>
                        <option value="light">Light</option>
                        <option value="dramatic">Dramatic</option>
                      </select>
                    </div>
                  </div>
                </div>
              )}

              {/* UI Tab */}
              {activeTab === 'ui' && settings && settings.ui_preferences && (
                <div className="space-y-6">
                  <h3 className="text-lg font-semibold text-white">Interface Preferences</h3>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        Theme
                      </label>
                      <select
                        value={settings.ui_preferences?.theme || 'dark'}
                        onChange={(e) => setSettings(prev => prev ? {
                          ...prev,
                          ui_preferences: { ...prev.ui_preferences, theme: e.target.value }
                        } : null)}
                        className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      >
                        <option value="dark">Dark</option>
                        <option value="light">Light</option>
                        <option value="auto">Auto</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        Font Size
                      </label>
                      <select
                        value={settings.ui_preferences?.font_size || 'medium'}
                        onChange={(e) => setSettings(prev => prev ? {
                          ...prev,
                          ui_preferences: { ...prev.ui_preferences, font_size: e.target.value }
                        } : null)}
                        className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      >
                        <option value="small">Small</option>
                        <option value="medium">Medium</option>
                        <option value="large">Large</option>
                      </select>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        id="sidebar_collapsed"
                        checked={settings.ui_preferences?.sidebar_collapsed || false}
                        onChange={(e) => setSettings(prev => prev ? {
                          ...prev,
                          ui_preferences: { ...prev.ui_preferences, sidebar_collapsed: e.target.checked }
                        } : null)}
                        className="w-4 h-4 text-purple-600 bg-gray-800 border-gray-700 rounded focus:ring-purple-500"
                      />
                      <label htmlFor="sidebar_collapsed" className="text-sm text-gray-300">
                        Collapse sidebar by default
                      </label>
                    </div>

                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        id="show_advanced_options"
                        checked={settings.ui_preferences?.show_advanced_options || false}
                        onChange={(e) => setSettings(prev => prev ? {
                          ...prev,
                          ui_preferences: { ...prev.ui_preferences, show_advanced_options: e.target.checked }
                        } : null)}
                        className="w-4 h-4 text-purple-600 bg-gray-800 border-gray-700 rounded focus:ring-purple-500"
                      />
                      <label htmlFor="show_advanced_options" className="text-sm text-gray-300">
                        Show advanced options
                      </label>
                    </div>
                  </div>
                </div>
              )}

              {/* Prompt Inspector Tab */}
              {activeTab === 'prompts' && (
                <div className="space-y-6">
                  <h3 className="text-lg font-semibold text-white">Prompt Inspector</h3>
                  <p className="text-gray-400">Prompt template management coming soon...</p>
                </div>
              )}
            </div>
          )}

          {/* Message */}
          {message && (
            <div className={`mt-4 p-3 rounded-md ${
              messageType === 'success' ? 'bg-green-900/20 text-green-400' :
              messageType === 'error' ? 'bg-red-900/20 text-red-400' :
              'bg-blue-900/20 text-blue-400'
            }`}>
              {message}
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex justify-end gap-3 pt-6 border-t border-gray-800">
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={saveSettings}
              disabled={saving || !settings}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-md transition-colors disabled:opacity-50"
            >
              <Save className="w-4 h-4" />
              {saving ? 'Saving...' : 'Save Settings'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
