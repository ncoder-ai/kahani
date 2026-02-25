'use client';

import { useState, useEffect } from 'react';
import { getApiBaseUrl } from '@/lib/api';
import { getThemeList, applyTheme } from '@/lib/themes';
import { UIPreferences } from '@/types/settings';
import { SettingsTabProps } from '../types';

interface InterfaceSettingsTabProps extends SettingsTabProps {
  uiSettings: UIPreferences;
  setUiSettings: (settings: UIPreferences) => void;
}

export default function InterfaceSettingsTab({
  token,
  showMessage,
  uiSettings,
  setUiSettings,
}: InterfaceSettingsTabProps) {
  const updateUIPreference = async (key: keyof UIPreferences, value: any) => {
    const newSettings = { ...uiSettings, [key]: value };
    setUiSettings(newSettings);

    // Apply theme immediately for instant feedback
    if (key === 'color_theme') {
      applyTheme(value);
    } else if (key === 'font_size') {
      const root = document.documentElement;
      root.classList.remove('text-small', 'text-medium', 'text-large');
      root.classList.add(`text-${value}`);
    }

    // Auto-save
    try {
      await fetch(`${await getApiBaseUrl()}/api/settings/`, {
        method: 'PUT',
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

      // Dispatch event for other components to listen to
      window.dispatchEvent(new CustomEvent('kahaniUISettingsChanged', {
        detail: newSettings
      }));
    } catch (error) {
      console.error('Failed to save setting:', error);
      showMessage('Failed to save setting', 'error');
    }
  };

  const saveAllSettings = async () => {
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          ui_preferences: uiSettings,
        }),
      });

      if (response.ok) {
        showMessage('Interface settings saved', 'success');
      } else {
        showMessage('Error saving settings', 'error');
      }
    } catch (error) {
      showMessage('Error saving settings', 'error');
    }
  };

  return (
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
            <p className="text-xs text-gray-400 mt-1">
              How scenes are visually displayed in the story
            </p>
          </div>

          {/* Scene Edit Mode */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">Scene Edit Mode</label>
            <select
              value={uiSettings.scene_edit_mode}
              onChange={(e) => updateUIPreference('scene_edit_mode', e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
            >
              <option value="textarea">Auto-expanding Textarea</option>
              <option value="contenteditable">ContentEditable (WYSIWYG)</option>
            </select>
            <p className="text-xs text-gray-400 mt-1">
              How scene editing works when you click to edit a scene. Textarea mode uses a resizable text box, ContentEditable mode preserves formatting.
            </p>
          </div>

          {/* Checkboxes */}
          <div className="space-y-3 pt-4 border-t border-gray-700">

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
                checked={uiSettings.show_scene_titles}
                onChange={(e) => updateUIPreference('show_scene_titles', e.target.checked)}
                className="w-4 h-4 rounded"
              />
              <span className="text-sm text-white">Show scene titles</span>
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
  );
}
