'use client';

import { getApiBaseUrl } from '@/lib/api';
import { GenerationPreferences } from '@/types/settings';
import { SettingsTabProps, ContextSettings, ExtractionModelSettings } from '../types';

interface ContextSettingsTabProps extends SettingsTabProps {
  contextSettings: ContextSettings;
  setContextSettings: (settings: ContextSettings) => void;
  generationPrefs: GenerationPreferences;
  setGenerationPrefs: (prefs: GenerationPreferences) => void;
  extractionModelSettings: ExtractionModelSettings;
}

export default function ContextSettingsTab({
  token,
  showMessage,
  contextSettings,
  setContextSettings,
  generationPrefs,
  setGenerationPrefs,
  extractionModelSettings,
}: ContextSettingsTabProps) {
  const saveSettings = async () => {
    try {
      const response = await fetch(`${await getApiBaseUrl()}/api/settings/`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          context_settings: contextSettings,
          generation_preferences: generationPrefs,
          extraction_model_settings: extractionModelSettings,
        }),
      });
      if (response.ok) {
        showMessage('Settings saved!', 'success');
      } else {
        showMessage('Failed to save settings', 'error');
      }
    } catch (error) {
      showMessage('Error saving settings', 'error');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">Generation & Context</h3>
        <p className="text-sm text-gray-400 mb-6">
          Configure context management and generation preferences
        </p>

        {/* Generation Preferences */}
        <div className="space-y-4 mb-8">
          <h4 className="text-md font-semibold text-white mb-3">Generation Preferences</h4>

          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Preferred Scene Length
            </label>
            <select
              value={generationPrefs.scene_length}
              onChange={(e) => setGenerationPrefs({ ...generationPrefs, scene_length: e.target.value })}
              className="w-full px-3 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:outline-none"
            >
              <option value="short">Short (100-150 words)</option>
              <option value="medium">Medium (200-300 words)</option>
              <option value="long">Long (400-500 words)</option>
            </select>
            <p className="text-xs text-gray-400 mt-1">Target length for generated scenes</p>
          </div>

          <div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={generationPrefs.separate_choice_generation || false}
                onChange={(e) => setGenerationPrefs({ ...generationPrefs, separate_choice_generation: e.target.checked })}
                className="w-4 h-4 rounded"
              />
              <span className="text-sm text-white">Generate choices separately (higher quality)</span>
            </label>
            <p className="text-xs text-gray-400 mt-1">
              Generate choices in a separate LLM call after scene generation for better quality choices
            </p>
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={generationPrefs.auto_choices}
              onChange={(e) => setGenerationPrefs({ ...generationPrefs, auto_choices: e.target.checked })}
              className="w-4 h-4 rounded"
            />
            <span className="text-sm text-white">Auto-generate choices after each scene</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={generationPrefs.enable_streaming !== false}
              onChange={(e) => setGenerationPrefs({ ...generationPrefs, enable_streaming: e.target.checked })}
              className="w-4 h-4 rounded"
            />
            <span className="text-sm text-white">Enable streaming generation</span>
            <span className="text-xs text-gray-400">(Shows content as it's generated)</span>
          </label>

          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Number of Choices: {generationPrefs.choices_count}
            </label>
            <input
              type="range"
              min="2"
              max="6"
              step="1"
              value={generationPrefs.choices_count}
              onChange={(e) => setGenerationPrefs({ ...generationPrefs, choices_count: parseInt(e.target.value) })}
              className="w-full"
            />
            <p className="text-xs text-gray-400 mt-1">Number of choices to generate</p>
          </div>

          {/* Use Extraction LLM for Summary */}
          {extractionModelSettings.enabled && (
            <div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={generationPrefs.use_extraction_llm_for_summary || false}
                  onChange={(e) => setGenerationPrefs({ ...generationPrefs, use_extraction_llm_for_summary: e.target.checked })}
                  className="w-4 h-4 rounded"
                />
                <span className="text-sm text-white">Use Extraction LLM for Summary</span>
              </label>
              <p className="text-xs text-gray-400 mt-1">
                Generate summaries using the extraction model instead of the main LLM
              </p>
            </div>
          )}
        </div>

        {/* Chapter Plot Tracking */}
        <div className="space-y-4 mb-8 pt-6 border-t border-gray-700">
          <h4 className="text-md font-semibold text-white mb-3">Chapter Plot Tracking</h4>

          <div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={(generationPrefs as any).enable_chapter_plot_tracking ?? true}
                onChange={(e) => setGenerationPrefs({ ...generationPrefs, enable_chapter_plot_tracking: e.target.checked } as any)}
                className="w-4 h-4 rounded"
              />
              <span className="text-sm text-white">Enable plot progress tracking</span>
            </label>
            <p className="text-xs text-gray-400 mt-1">
              Track which chapter events have occurred and guide the AI toward remaining plot points.
            </p>
          </div>
        </div>

        {/* Context Management */}
        <div className="space-y-6 mb-8 pt-6 border-t border-gray-700">
          <h4 className="text-md font-semibold text-white mb-3">Context Management</h4>

          {/* Enable Summarization */}
          <div>
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={contextSettings.enable_summarization || false}
                onChange={(e) => setContextSettings({ ...contextSettings, enable_summarization: e.target.checked })}
                className="mr-2"
              />
              <span className="text-sm text-white">Enable intelligent context summarization</span>
            </label>
            <div className="text-xs text-gray-400 mt-1">
              Automatically summarize older scenes for long stories
            </div>
          </div>

          {/* Max Tokens */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Context Budget: {(contextSettings.max_tokens || 4000).toLocaleString()} tokens
            </label>
            <input
              type="number"
              min="1000"
              max="1000000"
              step="8"
              value={contextSettings.max_tokens || 4000}
              onChange={(e) => {
                const value = parseInt(e.target.value) || 4000;
                setContextSettings({ ...contextSettings, max_tokens: value });
              }}
              onBlur={(e) => {
                const value = parseInt(e.target.value) || 4000;
                const rounded = Math.round(value / 8) * 8;
                if (value !== rounded) {
                  setContextSettings({ ...contextSettings, max_tokens: rounded });
                }
              }}
              className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white mb-2"
            />
            <input
              type="range"
              min="1000"
              max="100000"
              step="8"
              value={Math.min(contextSettings.max_tokens || 4000, 100000)}
              onChange={(e) => setContextSettings({ ...contextSettings, max_tokens: parseInt(e.target.value) })}
              className="w-full"
            />
            <div className="text-xs text-gray-400 mt-1">
              Total context budget sent to LLM (1K - 1M tokens)
            </div>
          </div>

          {/* Number of Recent Batches */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Number of Recent Batches: {contextSettings.keep_recent_scenes || 2}
            </label>
            <input
              type="range"
              min="1"
              max="10"
              step="1"
              value={contextSettings.keep_recent_scenes || 2}
              onChange={(e) => setContextSettings({ ...contextSettings, keep_recent_scenes: parseInt(e.target.value) })}
              className="w-full"
            />
            <div className="text-xs text-gray-400 mt-1">
              Complete scene batches to include (improves LLM cache hits)
            </div>
          </div>

          {/* Fill Remaining Context Toggle */}
          <div className="flex items-center justify-between py-2">
            <div>
              <label className="block text-sm font-medium text-white">
                Fill Remaining Context
              </label>
              <div className="text-xs text-gray-400">
                Fill context window with older scenes. Disable for weaker LLMs.
              </div>
            </div>
            <button
              onClick={() => setContextSettings({ ...contextSettings, fill_remaining_context: !contextSettings.fill_remaining_context })}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                contextSettings.fill_remaining_context ? 'bg-blue-600' : 'bg-gray-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  contextSettings.fill_remaining_context ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          {/* Summary Threshold */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Summary Threshold: {contextSettings.summary_threshold || 5} scenes
            </label>
            <input
              type="range"
              min="3"
              max="50"
              step="1"
              value={contextSettings.summary_threshold || 5}
              onChange={(e) => setContextSettings({ ...contextSettings, summary_threshold: parseInt(e.target.value) })}
              className="w-full"
            />
            <div className="text-xs text-gray-400 mt-1">
              Start summarizing when story exceeds this many scenes
            </div>
          </div>

          {/* Character Extraction Threshold */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Character Extraction Threshold: {contextSettings.character_extraction_threshold || 5} scenes
            </label>
            <input
              type="range"
              min="3"
              max="50"
              step="1"
              value={contextSettings.character_extraction_threshold || 5}
              onChange={(e) => setContextSettings({ ...contextSettings, character_extraction_threshold: parseInt(e.target.value) })}
              className="w-full"
            />
            <div className="text-xs text-gray-400 mt-1">
              Run character/NPC extraction after this many scenes
            </div>
          </div>

          {/* Plot Event Extraction Threshold */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Plot Event Extraction Threshold: {contextSettings.plot_event_extraction_threshold || 5} scenes
            </label>
            <input
              type="range"
              min="1"
              max="50"
              step="1"
              value={contextSettings.plot_event_extraction_threshold || 5}
              onChange={(e) => setContextSettings({ ...contextSettings, plot_event_extraction_threshold: parseInt(e.target.value) })}
              className="w-full"
            />
            <div className="text-xs text-gray-400 mt-1">
              Run plot event extraction after this many scenes
            </div>
          </div>

          {/* Scene Batch Size */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Scene Batch Size: {contextSettings.scene_batch_size || 10} scenes
            </label>
            <input
              type="range"
              min="3"
              max="50"
              step="1"
              value={contextSettings.scene_batch_size || 10}
              onChange={(e) => setContextSettings({ ...contextSettings, scene_batch_size: parseInt(e.target.value) })}
              className="w-full"
            />
            <div className="text-xs text-gray-400 mt-1">
              Scenes are grouped into batches for better LLM cache hit rates
            </div>
          </div>

          {/* Summary Threshold Tokens */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Token Threshold: {(contextSettings.summary_threshold_tokens || 8000).toLocaleString()} tokens
            </label>
            <input
              type="number"
              min="1000"
              max="50000"
              step="8"
              value={contextSettings.summary_threshold_tokens || 8000}
              onChange={(e) => {
                const value = parseInt(e.target.value) || 8000;
                setContextSettings({ ...contextSettings, summary_threshold_tokens: value });
              }}
              onBlur={(e) => {
                const value = parseInt(e.target.value) || 8000;
                const rounded = Math.round(value / 8) * 8;
                if (value !== rounded) {
                  setContextSettings({ ...contextSettings, summary_threshold_tokens: rounded });
                }
              }}
              className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white mb-2"
            />
            <input
              type="range"
              min="1000"
              max="50000"
              step="8"
              value={contextSettings.summary_threshold_tokens || 8000}
              onChange={(e) => setContextSettings({ ...contextSettings, summary_threshold_tokens: parseInt(e.target.value) })}
              className="w-full"
            />
            <div className="text-xs text-gray-400 mt-1">
              Start summarizing when total token count exceeds this threshold
            </div>
          </div>

          {/* Alert on High Context */}
          <div>
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={generationPrefs.alert_on_high_context !== false}
                onChange={(e) => setGenerationPrefs({ ...generationPrefs, alert_on_high_context: e.target.checked })}
                className="mr-2"
              />
              <span className="text-sm text-white">Alert when context usage is high</span>
            </label>
            <div className="text-xs text-gray-400 mt-1">
              Show a warning when chapter context reaches 80%
            </div>
          </div>

          {/* Semantic Memory Section */}
          <div className="border-t border-gray-700 pt-6 mt-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
              🧠 Semantic Memory
              <span className="ml-2 px-2 py-1 text-xs bg-purple-600 rounded">Experimental</span>
            </h3>

            <div className="mb-4">
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={contextSettings.enable_semantic_memory !== false}
                  onChange={(e) => setContextSettings({ ...contextSettings, enable_semantic_memory: e.target.checked })}
                  className="mr-2"
                />
                <span className="text-sm text-white">Enable Semantic Memory</span>
              </label>
              <div className="text-xs text-gray-400 mt-1">
                Use vector embeddings to find semantically relevant past scenes
              </div>
            </div>

            {contextSettings.enable_semantic_memory !== false && (
              <div className="space-y-4 ml-4 pl-4 border-l-2 border-purple-600">
                {/* Context Strategy */}
                <div>
                  <label className="block text-sm font-medium text-white mb-2">Context Strategy</label>
                  <select
                    value={contextSettings.context_strategy || 'hybrid'}
                    onChange={(e) => setContextSettings({ ...contextSettings, context_strategy: e.target.value })}
                    className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                  >
                    <option value="linear">Linear (Recent scenes only)</option>
                    <option value="hybrid">Hybrid (Recent + Semantic)</option>
                  </select>
                </div>

                {contextSettings.context_strategy !== 'linear' && (
                  <>
                    {/* Semantic Scenes */}
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        Semantic Scenes: {contextSettings.semantic_scenes_in_context || 5}
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="10"
                        step="1"
                        value={contextSettings.semantic_scenes_in_context || 5}
                        onChange={(e) => setContextSettings({ ...contextSettings, semantic_scenes_in_context: parseInt(e.target.value) })}
                        className="w-full"
                      />
                    </div>

                    {/* Semantic Search Top K */}
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        Search Results: {contextSettings.semantic_search_top_k || 5}
                      </label>
                      <input
                        type="range"
                        min="1"
                        max="20"
                        step="1"
                        value={contextSettings.semantic_search_top_k || 5}
                        onChange={(e) => setContextSettings({ ...contextSettings, semantic_search_top_k: parseInt(e.target.value) })}
                        className="w-full"
                      />
                    </div>

                    {/* Semantic Context Weight */}
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        Semantic Weight: {((contextSettings.semantic_context_weight || 0.4) * 100).toFixed(0)}%
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.1"
                        value={contextSettings.semantic_context_weight || 0.4}
                        onChange={(e) => setContextSettings({ ...contextSettings, semantic_context_weight: parseFloat(e.target.value) })}
                        className="w-full"
                      />
                    </div>

                    {/* Character Moments */}
                    <div>
                      <label className="block text-sm font-medium text-white mb-2">
                        Character Moments: {contextSettings.character_moments_in_context || 3}
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="10"
                        step="1"
                        value={contextSettings.character_moments_in_context || 3}
                        onChange={(e) => setContextSettings({ ...contextSettings, character_moments_in_context: parseInt(e.target.value) })}
                        className="w-full"
                      />
                    </div>
                  </>
                )}

                {/* Auto-extraction Settings */}
                <div className="pt-2 space-y-3">
                  <div>
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={contextSettings.auto_extract_character_moments !== false}
                        onChange={(e) => setContextSettings({ ...contextSettings, auto_extract_character_moments: e.target.checked })}
                        className="mr-2"
                      />
                      <span className="text-sm text-white">Auto-extract character moments</span>
                    </label>
                  </div>

                  <div>
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={contextSettings.auto_extract_plot_events !== false}
                        onChange={(e) => setContextSettings({ ...contextSettings, auto_extract_plot_events: e.target.checked })}
                        className="mr-2"
                      />
                      <span className="text-sm text-white">Auto-extract plot events</span>
                    </label>
                  </div>

                  {/* Extraction Confidence Threshold */}
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Confidence Threshold: {contextSettings.extraction_confidence_threshold || 70}%
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      step="5"
                      value={contextSettings.extraction_confidence_threshold || 70}
                      onChange={(e) => setContextSettings({ ...contextSettings, extraction_confidence_threshold: parseInt(e.target.value) })}
                      className="w-full"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Memory & Continuity Section */}
          <div className="border-t border-gray-700 pt-6 mt-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
              🧠 Memory & Continuity
              <span className="ml-2 px-2 py-1 text-xs bg-blue-600 rounded">New</span>
            </h3>

            <div className="space-y-4">
              {/* Enable Working Memory */}
              <div>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={contextSettings.enable_working_memory !== false}
                    onChange={(e) => setContextSettings({ ...contextSettings, enable_working_memory: e.target.checked })}
                    className="mr-2"
                  />
                  <span className="text-sm text-white">Enable Working Memory</span>
                </label>
                <div className="text-xs text-gray-400 mt-1">
                  Track scene-to-scene focus, pending items, and character spotlight for better continuity
                </div>
              </div>

              {/* Enable Contradiction Detection */}
              <div>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={contextSettings.enable_contradiction_detection !== false}
                    onChange={(e) => setContextSettings({ ...contextSettings, enable_contradiction_detection: e.target.checked })}
                    className="mr-2"
                  />
                  <span className="text-sm text-white">Enable Contradiction Detection</span>
                </label>
                <div className="text-xs text-gray-400 mt-1">
                  Detect continuity errors like location jumps and state regressions
                </div>
              </div>

              {/* Contradiction Severity Threshold & Injection Settings */}
              {contextSettings.enable_contradiction_detection !== false && (
                <div className="ml-4 pl-4 border-l-2 border-blue-600 space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">
                      Minimum Severity to Log
                    </label>
                    <select
                      value={contextSettings.contradiction_severity_threshold || 'info'}
                      onChange={(e) => setContextSettings({ ...contextSettings, contradiction_severity_threshold: e.target.value })}
                      className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white"
                    >
                      <option value="info">Info (all contradictions)</option>
                      <option value="warning">Warning (moderate+)</option>
                      <option value="error">Error (severe only)</option>
                    </select>
                    <div className="text-xs text-gray-400 mt-1">
                      Filter which contradictions are logged based on severity
                    </div>
                  </div>

                  {/* Inject warnings into prompt */}
                  <div>
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={contextSettings.enable_contradiction_injection !== false}
                        onChange={(e) => setContextSettings({ ...contextSettings, enable_contradiction_injection: e.target.checked })}
                        className="mr-2"
                      />
                      <span className="text-sm text-white">Inject continuity warnings into prompt</span>
                    </label>
                    <div className="text-xs text-gray-400 mt-1">
                      Informs the LLM about existing contradictions so it avoids repeating them
                    </div>
                  </div>

                  {/* Inline contradiction check */}
                  <div>
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={contextSettings.enable_inline_contradiction_check === true}
                        onChange={(e) => setContextSettings({ ...contextSettings, enable_inline_contradiction_check: e.target.checked })}
                        className="mr-2"
                      />
                      <span className="text-sm text-white">Check for contradictions after each scene</span>
                    </label>
                    <div className="text-xs text-gray-400 mt-1">
                      Runs entity extraction every scene — uses extraction LLM, adds a few seconds after scene completes
                    </div>
                  </div>

                  {/* Auto-regenerate on contradiction (nested under inline check) */}
                  {contextSettings.enable_inline_contradiction_check === true && (
                    <div className="ml-4 pl-4 border-l-2 border-amber-600">
                      <label className="flex items-center">
                        <input
                          type="checkbox"
                          checked={contextSettings.auto_regenerate_on_contradiction === true}
                          onChange={(e) => setContextSettings({ ...contextSettings, auto_regenerate_on_contradiction: e.target.checked })}
                          className="mr-2"
                        />
                        <span className="text-sm text-white">Auto-regenerate scene if contradictions found</span>
                      </label>
                      <div className="text-xs text-gray-400 mt-1">
                        Regenerates the scene once to fix the issue — requires inline check enabled
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex justify-end pt-4 border-t border-gray-700">
          <button
            onClick={saveSettings}
            className="px-6 py-2 theme-btn-primary rounded-lg font-semibold"
          >
            Save Settings
          </button>
        </div>
      </div>
    </div>
  );
}
