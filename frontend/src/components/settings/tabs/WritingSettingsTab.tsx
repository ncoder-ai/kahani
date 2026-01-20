'use client';

import { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import { getApiBaseUrl } from '@/lib/api';
import { ProseStyleDefinition } from '@/types/writing-presets';
import { SettingsTabProps, WritingPreset } from '../types';

interface WritingSettingsTabProps extends SettingsTabProps {
  onLoad?: () => void;
}

export default function WritingSettingsTab({
  token,
  showMessage,
  onLoad,
}: WritingSettingsTabProps) {
  const [writingPresets, setWritingPresets] = useState<WritingPreset[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<number | null>(null);
  const [systemPrompt, setSystemPrompt] = useState('');
  const [summaryPrompt, setSummaryPrompt] = useState('');
  const [presetName, setPresetName] = useState('');
  const [pov, setPov] = useState<'first' | 'second' | 'third'>('third');
  const [proseStyle, setProseStyle] = useState<string>('balanced');
  const [proseStyles, setProseStyles] = useState<ProseStyleDefinition[]>([]);
  const [loadingProseStyles, setLoadingProseStyles] = useState(false);
  const [expandedProseStyle, setExpandedProseStyle] = useState<string | null>(null);
  const [showPromptInfo, setShowPromptInfo] = useState(false);
  const [loadingPrompts, setLoadingPrompts] = useState(false);
  const [savingPrompts, setSavingPrompts] = useState(false);

  useEffect(() => {
    loadWritingPrompts();
  }, []);

  const loadWritingPrompts = async () => {
    setLoadingPrompts(true);
    setLoadingProseStyles(true);
    try {
      // Load prose styles from API
      const proseStylesResponse = await fetch(`${await getApiBaseUrl()}/api/writing-presets/prose-styles`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (proseStylesResponse.ok) {
        const styles = await proseStylesResponse.json();
        setProseStyles(styles);
      }

      // Load all presets
      const presetsResponse = await fetch(`${await getApiBaseUrl()}/api/writing-presets/`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (presetsResponse.ok) {
        const presets = await presetsResponse.json();
        setWritingPresets(presets);

        // Find and load the active preset
        const activePreset = presets.find((p: WritingPreset) => p.is_active);
        if (activePreset) {
          setSelectedPresetId(activePreset.id || null);
          setSystemPrompt(activePreset.system_prompt || '');
          setSummaryPrompt(activePreset.summary_system_prompt || '');
          setPresetName(activePreset.name || '');
          setPov((activePreset.pov as 'first' | 'second' | 'third') || 'third');
          setProseStyle(activePreset.prose_style || 'balanced');
        } else if (presets.length > 0) {
          // If no active, load first preset
          setSelectedPresetId(presets[0].id || null);
          setSystemPrompt(presets[0].system_prompt || '');
          setSummaryPrompt(presets[0].summary_system_prompt || '');
          setPresetName(presets[0].name || '');
          setPov((presets[0].pov as 'first' | 'second' | 'third') || 'third');
          setProseStyle(presets[0].prose_style || 'balanced');
        } else {
          await loadDefaultPrompts();
        }
      }
      onLoad?.();
    } catch (error) {
      console.error('Failed to load writing prompts:', error);
      showMessage('Failed to load writing prompts', 'error');
    } finally {
      setLoadingPrompts(false);
      setLoadingProseStyles(false);
    }
  };

  const loadDefaultPrompts = async () => {
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/writing-presets/default/template`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setSystemPrompt(data.system_prompt || 'You are a creative storytelling assistant. Write engaging, immersive narrative prose.');
        setSummaryPrompt(data.summary_system_prompt || 'Summarize the key events and character developments concisely.');
        setPresetName('Default');
        setPov((data.pov as 'first' | 'second' | 'third') || 'third');
        setProseStyle(data.prose_style || 'balanced');
      } else {
        setSystemPrompt('You are a creative storytelling assistant. Write engaging, immersive narrative prose.');
        setSummaryPrompt('Summarize the key events and character developments concisely.');
        setPresetName('Default');
        setPov('third');
      }
    } catch (error) {
      console.error('Failed to load default prompts:', error);
      setSystemPrompt('You are a creative storytelling assistant. Write engaging, immersive narrative prose.');
      setSummaryPrompt('Summarize the key events and character developments concisely.');
      setPov('third');
      setPresetName('Default');
    }
  };

  const loadPreset = (presetId: number) => {
    const preset = writingPresets.find(p => p.id === presetId);
    if (preset) {
      setSelectedPresetId(presetId);
      setSystemPrompt(preset.system_prompt);
      setSummaryPrompt(preset.summary_system_prompt);
      setPresetName(preset.name);
      setPov((preset.pov as 'first' | 'second' | 'third') || 'third');
      setProseStyle(preset.prose_style || 'balanced');
    }
  };

  const deletePreset = async (presetId: number) => {
    if (!confirm('Are you sure you want to delete this preset?')) return;

    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/writing-presets/${presetId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        showMessage('Preset deleted', 'success');
        loadWritingPrompts();
      } else {
        showMessage('Failed to delete preset', 'error');
      }
    } catch (error) {
      console.error('Failed to delete preset:', error);
      showMessage('Failed to delete preset', 'error');
    }
  };

  const saveWritingPrompts = async (makeActive: boolean = false) => {
    if (!presetName.trim()) {
      showMessage('Please enter a preset name', 'error');
      return;
    }

    if (!selectedPresetId) {
      await createNewPreset(presetName, makeActive);
      return;
    }

    setSavingPrompts(true);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/writing-presets/${selectedPresetId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: presetName,
          system_prompt: systemPrompt,
          summary_system_prompt: summaryPrompt,
          pov: pov,
          prose_style: proseStyle,
          is_active: makeActive,
        }),
      });

      if (response.ok) {
        showMessage(`Preset "${presetName}" updated successfully`, 'success');
        loadWritingPrompts();
      } else {
        showMessage('Failed to update preset', 'error');
      }
    } catch (error) {
      console.error('Failed to update preset:', error);
      showMessage('Failed to update preset', 'error');
    } finally {
      setSavingPrompts(false);
    }
  };

  const createNewPreset = async (name: string, makeActive: boolean = false) => {
    if (!name.trim()) {
      showMessage('Please enter a preset name', 'error');
      return;
    }

    setSavingPrompts(true);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/writing-presets/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: name.trim(),
          system_prompt: systemPrompt,
          summary_system_prompt: summaryPrompt,
          pov: pov,
          prose_style: proseStyle,
          is_active: makeActive,
        }),
      });

      if (response.ok) {
        const newPreset = await response.json();
        showMessage(`Preset "${name}" created successfully`, 'success');
        loadWritingPrompts();
        setSelectedPresetId(newPreset.id);
      } else {
        showMessage('Failed to create preset', 'error');
      }
    } catch (error) {
      console.error('Failed to create preset:', error);
      showMessage('Failed to create preset', 'error');
    } finally {
      setSavingPrompts(false);
    }
  };

  const saveAsNewPreset = async () => {
    const newName = prompt('Enter a name for the new preset:', presetName + ' (Copy)');
    if (!newName || !newName.trim()) return;

    setSavingPrompts(true);
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/writing-presets/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: newName.trim(),
          system_prompt: systemPrompt,
          summary_system_prompt: summaryPrompt,
          pov: pov,
          prose_style: proseStyle,
          is_active: false,
        }),
      });

      if (response.ok) {
        const newPreset = await response.json();
        showMessage(`New preset "${newName}" created successfully`, 'success');
        loadWritingPrompts();
        setSelectedPresetId(newPreset.id);
        setPresetName(newName.trim());
      } else {
        showMessage('Failed to create new preset', 'error');
      }
    } catch (error) {
      console.error('Failed to create new preset:', error);
      showMessage('Failed to create new preset', 'error');
    } finally {
      setSavingPrompts(false);
    }
  };

  const setActivePreset = async (presetId: number) => {
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/writing-presets/${presetId}/activate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        showMessage('Preset activated', 'success');
        loadWritingPrompts();
      } else {
        showMessage('Failed to activate preset', 'error');
      }
    } catch (error) {
      console.error('Failed to activate preset:', error);
      showMessage('Failed to activate preset', 'error');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">Writing Styles</h3>
        <p className="text-sm text-gray-400 mb-4">
          Create and manage multiple writing style presets
        </p>

        {loadingPrompts ? (
          <div className="text-center py-8 text-gray-400">Loading presets...</div>
        ) : (
          <div className="space-y-6">
            {/* Preset Selector */}
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="block text-sm font-medium text-white mb-2">
                  Select Preset
                </label>
                <select
                  value={selectedPresetId || 'default'}
                  onChange={(e) => {
                    if (e.target.value === 'new') {
                      setSelectedPresetId(null);
                      setPresetName('');
                      setSystemPrompt('');
                      setSummaryPrompt('');
                      setPov('third');
                    } else if (e.target.value === 'default') {
                      setSelectedPresetId(null);
                      loadDefaultPrompts();
                    } else if (e.target.value) {
                      loadPreset(Number(e.target.value));
                    }
                  }}
                  className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                >
                  <option value="default">📄 Default (from prompts.yaml)</option>
                  <option value="new">+ Create New Preset</option>
                  {writingPresets.map((preset) => (
                    <option key={preset.id} value={preset.id}>
                      {preset.name} {preset.is_active ? '⭐ (Active)' : ''}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-end gap-2">
                {selectedPresetId && (
                  <>
                    <button
                      onClick={() => setActivePreset(selectedPresetId)}
                      className="px-4 py-2 theme-btn-primary rounded-md font-medium"
                      title="Set as active preset"
                    >
                      ✓ Set Active
                    </button>
                    <button
                      onClick={() => deletePreset(selectedPresetId)}
                      className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md font-medium"
                      title="Delete preset"
                    >
                      🗑️
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Preset Name */}
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Preset Name
              </label>
              <input
                type="text"
                value={presetName}
                onChange={(e) => setPresetName(e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                placeholder="e.g., NSFW Adventure, Family Friendly, Poetic Style"
              />
            </div>

            {/* Prompt Construction Info */}
            <div className="bg-blue-900/20 border border-blue-700/30 rounded-lg p-4">
              <button
                type="button"
                onClick={() => setShowPromptInfo(!showPromptInfo)}
                className="w-full flex items-center justify-between text-left"
              >
                <span className="text-sm font-semibold text-blue-200">
                  ℹ️ How prompts are constructed
                </span>
                <svg
                  className={`w-5 h-5 text-blue-400 transition-transform ${showPromptInfo ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {showPromptInfo && (
                <div className="mt-4 text-sm text-blue-200 space-y-2">
                  <p className="font-medium text-white">Your writing style prompt is combined with technical requirements:</p>
                  <div className="bg-gray-800 rounded p-3 space-y-1 text-xs">
                    <div className="flex items-start gap-2">
                      <span className="font-semibold text-green-400">✓ Your Style:</span>
                      <span className="text-gray-300">The writing style prompt you define below (tone, pacing, character development, etc.)</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="font-semibold text-blue-400">+ POV:</span>
                      <span className="text-gray-300">Point of view selection (First/Second/Third person) - see below</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="font-semibold text-purple-400">+ Formatting Rules:</span>
                      <span className="text-gray-300">Automatically added from system defaults (dialogue format, structure, etc.)</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="font-semibold text-orange-400">+ Choices Rules:</span>
                      <span className="text-gray-300">Automatically added from system defaults (JSON format, marker placement, etc.)</span>
                    </div>
                  </div>
                  <p className="text-xs italic text-gray-300">You only need to customize the writing style - technical requirements are handled automatically.</p>
                </div>
              )}
            </div>

            {/* Point of View Selection */}
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Point of View
              </label>
              <p className="text-xs text-gray-400 mb-2">
                Choose the narrative perspective for your stories
              </p>
              <div className="grid grid-cols-3 gap-3">
                <button
                  type="button"
                  onClick={() => setPov('first')}
                  className={`px-4 py-3 rounded-lg border-2 transition-all ${
                    pov === 'first'
                      ? 'border-blue-500 bg-blue-600/20 text-blue-200'
                      : 'border-gray-600 bg-gray-700 text-gray-300 hover:border-gray-500'
                  }`}
                >
                  <div className="font-semibold">First Person</div>
                  <div className="text-xs mt-1 opacity-75">I, me, my</div>
                </button>
                <button
                  type="button"
                  onClick={() => setPov('second')}
                  className={`px-4 py-3 rounded-lg border-2 transition-all ${
                    pov === 'second'
                      ? 'border-blue-500 bg-blue-600/20 text-blue-200'
                      : 'border-gray-600 bg-gray-700 text-gray-300 hover:border-gray-500'
                  }`}
                >
                  <div className="font-semibold">Second Person</div>
                  <div className="text-xs mt-1 opacity-75">You, your</div>
                </button>
                <button
                  type="button"
                  onClick={() => setPov('third')}
                  className={`px-4 py-3 rounded-lg border-2 transition-all ${
                    pov === 'third'
                      ? 'border-blue-500 bg-blue-600/20 text-blue-200'
                      : 'border-gray-600 bg-gray-700 text-gray-300 hover:border-gray-500'
                  }`}
                >
                  <div className="font-semibold">Third Person</div>
                  <div className="text-xs mt-1 opacity-75">He, she, they</div>
                </button>
              </div>
            </div>

            {/* Prose Style Selection */}
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                Prose Style
              </label>
              <p className="text-xs text-gray-400 mb-3">
                Choose how the AI structures its writing. Click any style to see an example.
              </p>
              {loadingProseStyles ? (
                <div className="flex items-center justify-center py-8 text-gray-400">
                  <Loader2 className="w-5 h-5 animate-spin mr-2" />
                  Loading prose styles...
                </div>
              ) : proseStyles.length === 0 ? (
                <div className="text-gray-400 text-sm py-4">
                  No prose styles available. Check backend configuration.
                </div>
              ) : (
                <div className="space-y-2 max-h-80 overflow-y-auto pr-2">
                  {proseStyles.map((style) => (
                    <div
                      key={style.key}
                      className={`rounded-lg border-2 transition-all ${
                        proseStyle === style.key
                          ? 'border-blue-500 bg-blue-600/20'
                          : 'border-gray-600 bg-gray-700 hover:border-gray-500'
                      }`}
                    >
                      {/* Style Header */}
                      <div className="flex items-center gap-3 p-3">
                        <button
                          type="button"
                          onClick={() => setProseStyle(style.key)}
                          className="flex-1 text-left"
                        >
                          <div className="flex items-center gap-2">
                            <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                              proseStyle === style.key
                                ? 'border-blue-500 bg-blue-500'
                                : 'border-gray-400'
                            }`}>
                              {proseStyle === style.key && (
                                <svg className="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 20 20">
                                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                </svg>
                              )}
                            </div>
                            <span className={`font-medium ${
                              proseStyle === style.key ? 'text-blue-200' : 'text-white'
                            }`}>
                              {style.name}
                            </span>
                          </div>
                          <p className={`text-xs mt-1 ml-6 ${
                            proseStyle === style.key ? 'text-blue-300' : 'text-gray-400'
                          }`}>
                            {style.description}
                          </p>
                        </button>

                        {/* Toggle Example Button */}
                        <button
                          type="button"
                          onClick={() => setExpandedProseStyle(expandedProseStyle === style.key ? null : style.key)}
                          className={`px-2 py-1 text-xs rounded transition-colors ${
                            expandedProseStyle === style.key
                              ? 'bg-blue-600 text-blue-100'
                              : 'bg-gray-600 text-gray-300 hover:bg-gray-500'
                          }`}
                        >
                          {expandedProseStyle === style.key ? 'Hide' : 'Example'}
                        </button>
                      </div>

                      {/* Expandable Example */}
                      {expandedProseStyle === style.key && (
                        <div className="px-3 pb-3">
                          <div className="bg-gray-800 rounded-lg p-3 text-sm text-gray-300 whitespace-pre-wrap font-serif italic border border-gray-600">
                            {style.example}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

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

            {/* Action Buttons */}
            <div className="flex gap-3">
              <button
                onClick={() => saveWritingPrompts(false)}
                disabled={savingPrompts}
                className="flex-1 theme-btn-primary px-6 py-3 rounded-lg font-semibold disabled:opacity-50"
              >
                {savingPrompts ? 'Saving...' : selectedPresetId ? 'Update Preset' : 'Save Preset'}
              </button>
              <button
                onClick={saveAsNewPreset}
                className="px-6 py-3 theme-btn-secondary rounded-lg font-semibold"
              >
                💾 Save As New
              </button>
              {selectedPresetId && (
                <button
                  onClick={() => saveWritingPrompts(true)}
                  disabled={savingPrompts}
                  className="px-6 py-3 theme-btn-primary rounded-lg font-semibold disabled:opacity-50"
                >
                  Save & Activate
                </button>
              )}
            </div>

            <div className="text-xs text-gray-400 bg-blue-900/20 border border-blue-700/30 rounded-lg p-3">
              💡 <strong>Tip:</strong> Create multiple presets for different writing styles.
              The active preset will be used for all story generation.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
