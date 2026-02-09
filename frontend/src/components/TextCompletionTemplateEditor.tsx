'use client';

import React, { useState, useEffect } from 'react';
import api from '@/lib/api';

interface TemplateConfig {
  name?: string;
  description?: string;
  bos_token: string;
  eos_token: string;
  system_prefix: string;
  system_suffix: string;
  instruction_prefix: string;
  instruction_suffix: string;
  response_prefix: string;
}

interface PresetInfo {
  key: string;
  name: string;
  description: string;
  compatible_models: string[];
}

interface TextCompletionTemplateEditorProps {
  value: TemplateConfig | null;
  preset: string;
  onChange: (template: TemplateConfig, preset: string) => void;
}

export default function TextCompletionTemplateEditor({
  value,
  preset,
  onChange
}: TextCompletionTemplateEditorProps) {
  const [presets, setPresets] = useState<PresetInfo[]>([]);
  const [selectedPreset, setSelectedPreset] = useState<string>(preset || 'llama3');
  const [template, setTemplate] = useState<TemplateConfig>(value || {
    bos_token: '',
    eos_token: '',
    system_prefix: '',
    system_suffix: '',
    instruction_prefix: '',
    instruction_suffix: '',
    response_prefix: ''
  });
  const [previewPrompt, setPreviewPrompt] = useState<string>('');
  const [testResult, setTestResult] = useState<{ valid: boolean; error: string | null } | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showHelp, setShowHelp] = useState(false);

  // Load available presets on mount
  useEffect(() => {
    loadPresets();
  }, []);

  // Sync with preset prop changes
  useEffect(() => {
    if (preset && preset !== selectedPreset && preset !== 'custom') {
      loadPresetTemplate(preset);
    } else if (preset === 'custom' && value) {
      setTemplate(value);
      setSelectedPreset('custom');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset]);

  // Sync with value prop changes when in custom mode
  useEffect(() => {
    if (value && selectedPreset === 'custom') {
      setTemplate(value);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  // Update preview when template changes
  useEffect(() => {
    updatePreview();
  }, [template]);

  const loadPresets = async () => {
    try {
      const response = await api.getTextCompletionPresets();
      setPresets(response.presets);
    } catch (error) {
      console.error('Failed to load presets:', error);
    }
  };

  const loadPresetTemplate = async (presetKey: string) => {
    setIsLoading(true);
    try {
      const response = await api.getPresetTemplate(presetKey);
      const loadedTemplate = response.template;
      
      // Remove metadata fields before setting
      const { name, description, compatible_models, ...templateFields } = loadedTemplate;
      
      setTemplate(templateFields as TemplateConfig);
      setSelectedPreset(presetKey);
      onChange(templateFields as TemplateConfig, presetKey);
    } catch (error) {
      console.error('Failed to load preset template:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const updatePreview = () => {
    const exampleSystem = "You are a helpful assistant.";
    const exampleUser = "Hello, how are you?";
    
    const parts = [];
    if (template.bos_token) parts.push(template.bos_token);
    if (exampleSystem) {
      parts.push(template.system_prefix);
      parts.push(exampleSystem);
      parts.push(template.system_suffix);
    }
    parts.push(template.instruction_prefix);
    parts.push(exampleUser);
    parts.push(template.instruction_suffix);
    parts.push(template.response_prefix);
    
    setPreviewPrompt(parts.join(''));
  };

  const handleFieldChange = (field: keyof TemplateConfig, value: string) => {
    const newTemplate = { ...template, [field]: value };
    setTemplate(newTemplate);
    
    // Mark as custom if user modifies any field
    if (selectedPreset !== 'custom') {
      setSelectedPreset('custom');
    }
    
    onChange(newTemplate, 'custom');
  };

  const handleTestTemplate = async () => {
    setIsLoading(true);
    try {
      const result = await api.testTemplateRender(
        template,
        "You are a helpful assistant.",
        "Hello, how are you?"
      );
      setTestResult({ valid: result.valid, error: result.error });
    } catch (error) {
      setTestResult({ valid: false, error: 'Failed to test template' });
    } finally {
      setIsLoading(false);
    }
  };

  const handleResetToPreset = () => {
    if (selectedPreset && selectedPreset !== 'custom') {
      loadPresetTemplate(selectedPreset);
    }
  };

  return (
    <div className="text-completion-template-editor space-y-4">
      {/* Preset Selector */}
      <div className="preset-selector">
        <label className="block text-sm font-medium mb-2">
          Template Preset
        </label>
        <div className="flex gap-2">
          <select
            value={selectedPreset}
            onChange={(e) => {
              const newPreset = e.target.value;
              if (newPreset !== 'custom') {
                loadPresetTemplate(newPreset);
              }
              setSelectedPreset(newPreset);
            }}
            className="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-blue-500"
          >
            <option value="llama3">Llama 3 Instruct</option>
            <option value="mistral">Mistral Instruct</option>
            <option value="qwen">Qwen</option>
            <option value="glm">GLM</option>
            <option value="generic">Generic</option>
            <option value="custom">Custom</option>
          </select>
          {selectedPreset !== 'custom' && (
            <button
              onClick={() => loadPresetTemplate(selectedPreset)}
              disabled={isLoading}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white disabled:opacity-50"
            >
              Load Preset
            </button>
          )}
        </div>
        {presets.find(p => p.key === selectedPreset) && (
          <p className="text-sm text-gray-400 mt-1">
            {presets.find(p => p.key === selectedPreset)?.description}
          </p>
        )}
      </div>

      {/* Template Fields */}
      <div className="template-fields space-y-3">
        <h4 className="text-sm font-medium text-gray-300">Template Configuration</h4>
        
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            BOS Token <span className="text-xs">(Beginning of sequence)</span>
          </label>
          <input
            type="text"
            value={template.bos_token}
            onChange={(e) => handleFieldChange('bos_token', e.target.value)}
            placeholder="<|begin_of_text|>"
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-blue-500 font-mono text-sm"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">
            System Prefix
          </label>
          <input
            type="text"
            value={template.system_prefix}
            onChange={(e) => handleFieldChange('system_prefix', e.target.value)}
            placeholder="<|start_header_id|>system<|end_header_id|>\n\n"
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-blue-500 font-mono text-sm"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">
            System Suffix
          </label>
          <input
            type="text"
            value={template.system_suffix}
            onChange={(e) => handleFieldChange('system_suffix', e.target.value)}
            placeholder="<|eot_id|>"
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-blue-500 font-mono text-sm"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Instruction Prefix
          </label>
          <input
            type="text"
            value={template.instruction_prefix}
            onChange={(e) => handleFieldChange('instruction_prefix', e.target.value)}
            placeholder="<|start_header_id|>user<|end_header_id|>\n\n"
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-blue-500 font-mono text-sm"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Instruction Suffix
          </label>
          <input
            type="text"
            value={template.instruction_suffix}
            onChange={(e) => handleFieldChange('instruction_suffix', e.target.value)}
            placeholder="<|eot_id|>"
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-blue-500 font-mono text-sm"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Response Prefix
          </label>
          <input
            type="text"
            value={template.response_prefix}
            onChange={(e) => handleFieldChange('response_prefix', e.target.value)}
            placeholder="<|start_header_id|>assistant<|end_header_id|>\n\n"
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-blue-500 font-mono text-sm"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">
            EOS Token <span className="text-xs">(End of sequence)</span>
          </label>
          <input
            type="text"
            value={template.eos_token}
            onChange={(e) => handleFieldChange('eos_token', e.target.value)}
            placeholder="<|eot_id|>"
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-blue-500 font-mono text-sm"
          />
        </div>
      </div>

      {/* Preview */}
      <div className="template-preview">
        <h5 className="text-sm font-medium text-gray-300 mb-2">Preview</h5>
        <div className="bg-gray-800 border border-gray-700 rounded p-3 max-h-40 overflow-y-auto">
          <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono">
            {previewPrompt || 'Configure template fields to see preview...'}
          </pre>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="template-actions flex gap-2">
        <button
          onClick={handleTestTemplate}
          disabled={isLoading}
          className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded text-white disabled:opacity-50 text-sm"
        >
          {isLoading ? 'Testing...' : 'Test Template'}
        </button>
        {selectedPreset !== 'custom' && (
          <button
            onClick={handleResetToPreset}
            disabled={isLoading}
            className="px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded text-white disabled:opacity-50 text-sm"
          >
            Reset to Preset
          </button>
        )}
        <button
          onClick={() => setShowHelp(!showHelp)}
          className="px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded text-white text-sm"
        >
          {showHelp ? 'Hide Help' : 'Show Help'}
        </button>
      </div>

      {/* Test Result */}
      {testResult && (
        <div className={`p-3 rounded ${testResult.valid ? 'bg-green-900/30 border border-green-700' : 'bg-red-900/30 border border-red-700'}`}>
          <p className="text-sm">
            {testResult.valid ? '✓ Template is valid' : `✗ ${testResult.error}`}
          </p>
        </div>
      )}

      {/* Help Section */}
      {showHelp && (
        <div className="template-help bg-gray-800 border border-gray-700 rounded p-4 space-y-2">
          <h5 className="text-sm font-medium text-gray-300 mb-2">Template Variables & Help</h5>
          <div className="text-sm text-gray-400 space-y-1">
            <p><code className="bg-gray-700 px-1 rounded">{'{{system}}'}</code> - System prompt content</p>
            <p><code className="bg-gray-700 px-1 rounded">{'{{user_prompt}}'}</code> - User instruction content</p>
            <p><code className="bg-gray-700 px-1 rounded">{'{{bos}}'}</code> - Beginning of sequence token</p>
            <p><code className="bg-gray-700 px-1 rounded">{'{{eos}}'}</code> - End of sequence token</p>
          </div>
          <div className="mt-3 pt-3 border-t border-gray-700">
            <p className="text-sm text-gray-400">
              <strong>Note:</strong> Thinking tags (like &lt;think&gt;, &lt;reasoning&gt;) are automatically detected and removed from model responses.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

