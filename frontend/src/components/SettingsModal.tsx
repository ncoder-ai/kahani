'use client';

import { useState, useEffect } from 'react';
import { X, Settings as SettingsIcon, Check, AlertCircle } from 'lucide-react';
import apiClient, { getApiBaseUrl } from '@/lib/api';
import { getThemeList } from '@/lib/themes';
import { useAuthStore } from '@/store';

interface UIPreferences {
  color_theme: string;
  font_size: string;
  show_token_info: boolean;
  show_context_info: boolean;
  notifications: boolean;
  scene_display_format: string;
  scene_container_style: string;
  auto_open_last_story: boolean;
}

interface WritingPreset {
  id?: number;
  name: string;
  system_prompt: string;
  summary_prompt: string;
}

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const { user, token } = useAuthStore();
  const [activeTab, setActiveTab] = useState<'interface' | 'writing' | 'llm' | 'context' | 'tts'>('interface');
  
  // UI Settings
  const [uiSettings, setUiSettings] = useState<UIPreferences>({
    color_theme: 'pure-dark',
    font_size: 'medium',
    show_token_info: false,
    show_context_info: false,
    notifications: true,
    scene_display_format: 'default',
    scene_container_style: 'lines',
    auto_open_last_story: false,
  });

  // Writing Styles
  const [systemPrompt, setSystemPrompt] = useState('');
  const [summaryPrompt, setSummaryPrompt] = useState('');
  const [loadingPrompts, setLoadingPrompts] = useState(false);
  const [savingPrompts, setSavingPrompts] = useState(false);
  
  // Messages
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState<'success' | 'error'>('success');

  // Load settings on mount
  useEffect(() => {
    if (isOpen) {
      loadUISettings();
      if (activeTab === 'writing') {
        loadWritingPrompts();
      }
    }
  }, [isOpen, activeTab]);

  const loadUISettings = async () => {
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/settings/`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.settings?.ui_preferences) {
          setUiSettings({
            color_theme: data.settings.ui_preferences.color_theme || 'pure-dark',
            font_size: data.settings.ui_preferences.font_size || 'medium',
            show_token_info: data.settings.ui_preferences.show_token_info || false,
            show_context_info: data.settings.ui_preferences.show_context_info || false,
            notifications: data.settings.ui_preferences.notifications !== false,
            scene_display_format: data.settings.ui_preferences.scene_display_format || 'default',
            scene_container_style: data.settings.ui_preferences.scene_container_style || 'lines',
            auto_open_last_story: data.settings.ui_preferences.auto_open_last_story || false,
          });
        }
      }
    } catch (error) {
      console.error('Failed to load UI settings:', error);
    }
  };

  const loadWritingPrompts = async () => {
    setLoadingPrompts(true);
    try {
      // Get the active writing preset
      const response = await fetch(`${getApiBaseUrl()}/api/writing-presets/active`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const preset = await response.json();
        setSystemPrompt(preset.system_prompt || '');
        setSummaryPrompt(preset.summary_prompt || '');
      } else {
        // If no active preset, load defaults
        setSystemPrompt('You are a creative storytelling assistant. Write engaging, immersive narrative prose.');
        setSummaryPrompt('Summarize the key events and character developments concisely.');
      }
    } catch (error) {
      console.error('Failed to load writing prompts:', error);
      showMessage('Failed to load writing prompts', 'error');
    } finally {
      setLoadingPrompts(false);
    }
  };

  const updateUIPreference = async (key: keyof UIPreferences, value: any) => {
    const newSettings = { ...uiSettings, [key]: value };
    setUiSettings(newSettings);

    // Auto-save
    try {
      await fetch(`${getApiBaseUrl()}/api/settings/`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          ui_preferences: {
            [key]: value,
          },
        }),
      });
      
      showMessage('Settings saved', 'success');
      
      // Reload page to apply theme changes
      if (key === 'color_theme' || key === 'font_size') {
        setTimeout(() => window.location.reload(), 500);
      }
    } catch (error) {
      console.error('Failed to save setting:', error);
      showMessage('Failed to save setting', 'error');
    }
  };

  const saveWritingPrompts = async () => {
    setSavingPrompts(true);
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/writing-presets/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: 'Custom Preset',
          system_prompt: systemPrompt,
          summary_prompt: summaryPrompt,
          is_active: true,
        }),
      });

      if (response.ok) {
        showMessage('Writing styles saved successfully', 'success');
      } else {
        showMessage('Failed to save writing styles', 'error');
      }
    } catch (error) {
      console.error('Failed to save writing prompts:', error);
      showMessage('Failed to save writing styles', 'error');
    } finally {
      setSavingPrompts(false);
    }
  };

  const showMessage = (msg: string, type: 'success' | 'error') => {
    setMessage(msg);
    setMessageType(type);
    setTimeout(() => setMessage(''), 3000);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-4">
      <div className="theme-card rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden border border-gray-700">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-700 theme-banner">
          <div className="flex items-center gap-3">
            <SettingsIcon className="w-6 h-6 text-white" />
            <h2 className="text-xl font-bold text-white">Settings</h2>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-gray-700 bg-gray-800/50 overflow-x-auto">
          {[
            { id: 'interface', name: 'Interface' },
            { id: 'writing', name: 'Writing Styles' },
            { id: 'llm', name: 'LLM Settings' },
            { id: 'context', name: 'Generation & Context' },
            { id: 'tts', name: 'Text-to-Speech' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex-1 py-3 px-4 text-sm font-medium transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'theme-btn-primary border-b-2 theme-border-accent'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              {tab.name}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-180px)]">
          {/* Messages */}
          {message && (
            <div className={`mb-4 p-4 rounded-lg flex items-start gap-3 ${
              messageType === 'success' 
                ? 'bg-green-500/10 border border-green-500/50' 
                : 'bg-red-500/10 border border-red-500/50'
            }`}>
              {messageType === 'success' ? (
                <Check className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              )}
              <p className={`text-sm ${messageType === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                {message}
              </p>
            </div>
          )}

          {/* Interface Tab */}
          {activeTab === 'interface' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-white mb-4">Interface Preferences</h3>
                
                <div className="space-y-4">
                  {/* Color Theme */}
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">Color Theme</label>
                    <select
                      value={uiSettings.color_theme}
                      onChange={(e) => updateUIPreference('color_theme', e.target.value)}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                    >
                      {getThemeList().map(theme => (
                        <option key={theme.value} value={theme.value}>
                          {theme.label} - {theme.description}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-gray-400 mt-1">
                      Choose your preferred color scheme for the entire app
                    </p>
                  </div>

                  {/* Font Size */}
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">Font Size</label>
                    <select
                      value={uiSettings.font_size}
                      onChange={(e) => updateUIPreference('font_size', e.target.value)}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                    >
                      <option value="small">Small</option>
                      <option value="medium">Medium</option>
                      <option value="large">Large</option>
                    </select>
                  </div>

                  {/* Scene Container Style */}
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">Scene Container Style</label>
                    <select
                      value={uiSettings.scene_container_style}
                      onChange={(e) => updateUIPreference('scene_container_style', e.target.value)}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                    >
                      <option value="lines">Simple Lines (Clean, Mobile-friendly)</option>
                      <option value="cards">Cards/Bubbles (Rich, Desktop style)</option>
                    </select>
                    <p className="text-sm text-gray-400 mt-1">
                      Choose between minimal line separators or rich card containers for scenes
                    </p>
                  </div>

                  {/* Scene Display Format */}
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">Scene Display Format</label>
                    <select
                      value={uiSettings.scene_display_format}
                      onChange={(e) => updateUIPreference('scene_display_format', e.target.value)}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                    >
                      <option value="default">Default</option>
                      <option value="bubble">Bubble</option>
                      <option value="card">Card</option>
                      <option value="minimal">Minimal</option>
                    </select>
                    <p className="text-sm text-gray-400 mt-1">
                      Choose how story scenes are displayed (when using Cards container style)
                    </p>
                  </div>

                  {/* Checkboxes */}
                  <div className="space-y-3 pt-4 border-t border-gray-700">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={uiSettings.show_token_info}
                        onChange={(e) => updateUIPreference('show_token_info', e.target.checked)}
                        className="w-4 h-4 rounded"
                      />
                      <span className="text-sm text-white">Show token usage information</span>
                    </label>

                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={uiSettings.show_context_info}
                        onChange={(e) => updateUIPreference('show_context_info', e.target.checked)}
                        className="w-4 h-4 rounded"
                      />
                      <span className="text-sm text-white">Show context management details</span>
                    </label>

                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={uiSettings.notifications}
                        onChange={(e) => updateUIPreference('notifications', e.target.checked)}
                        className="w-4 h-4 rounded"
                      />
                      <span className="text-sm text-white">Enable notifications</span>
                    </label>

                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={uiSettings.auto_open_last_story}
                        onChange={(e) => updateUIPreference('auto_open_last_story', e.target.checked)}
                        className="w-4 h-4 rounded"
                      />
                      <span className="text-sm text-white">Auto-open last story on login</span>
                    </label>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Writing Styles Tab */}
          {activeTab === 'writing' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-white mb-2">Writing Styles</h3>
                <p className="text-sm text-gray-400 mb-4">
                  Customize how the AI writes and summarizes your stories
                </p>

                {loadingPrompts ? (
                  <div className="text-center py-8 text-gray-400">Loading prompts...</div>
                ) : (
                  <div className="space-y-6">
                    {/* System Prompt */}
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        System Prompt
                      </label>
                      <p className="text-xs text-gray-400 mb-2">
                        This defines how the AI writes (tone, style, NSFW settings)
                      </p>
                      <textarea
                        value={systemPrompt}
                        onChange={(e) => setSystemPrompt(e.target.value)}
                        rows={8}
                        className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white font-mono text-sm"
                        placeholder="Enter your system prompt..."
                      />
                    </div>

                    {/* Summary Prompt */}
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        Summary Prompt
                      </label>
                      <p className="text-xs text-gray-400 mb-2">
                        This defines how the AI creates summaries
                      </p>
                      <textarea
                        value={summaryPrompt}
                        onChange={(e) => setSummaryPrompt(e.target.value)}
                        rows={8}
                        className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white font-mono text-sm"
                        placeholder="Enter your summary prompt..."
                      />
                    </div>

                    {/* Save Button */}
                    <button
                      onClick={saveWritingPrompts}
                      disabled={savingPrompts}
                      className="theme-btn-primary px-6 py-3 rounded-lg font-semibold disabled:opacity-50"
                    >
                      {savingPrompts ? 'Saving...' : 'Save Writing Styles'}
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Placeholder Tabs */}
          {(activeTab === 'llm' || activeTab === 'context' || activeTab === 'tts') && (
            <div className="text-center py-12">
              <div className="text-6xl mb-4">🚧</div>
              <h3 className="text-xl font-semibold text-white mb-2">Coming Soon</h3>
              <p className="text-gray-400">
                {activeTab === 'llm' && 'LLM configuration settings will be available here.'}
                {activeTab === 'context' && 'Generation and context management settings will be available here.'}
                {activeTab === 'tts' && 'Text-to-speech settings will be available here. For now, use TTS Settings from the main menu.'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

