/**
 * Reusable UI components for settings and forms.
 *
 * These components reduce boilerplate in settings modals and forms
 * by providing consistent styling and behavior for common form elements.
 *
 * Example usage:
 *
 * ```tsx
 * import { SettingsSlider, SettingsInput, SettingsSelect, SettingsToggle } from '@/components/ui';
 *
 * // Slider for range values
 * <SettingsSlider
 *   label="Temperature"
 *   value={temperature}
 *   onChange={setTemperature}
 *   min={0}
 *   max={2}
 *   step={0.05}
 *   parseAsFloat
 *   description="Controls randomness (0=focused, 2=creative)"
 * />
 *
 * // Input for text/number values
 * <SettingsInput
 *   label="API URL"
 *   value={apiUrl}
 *   onChange={setApiUrl}
 *   type="url"
 *   placeholder="https://api.example.com"
 *   description="The URL of your LLM API endpoint"
 * />
 *
 * // Select dropdown
 * <SettingsSelect
 *   label="Model"
 *   value={selectedModel}
 *   onChange={setSelectedModel}
 *   options={[
 *     { value: 'gpt-4', label: 'GPT-4' },
 *     { value: 'gpt-3.5', label: 'GPT-3.5' },
 *   ]}
 *   description="Choose the AI model for generation"
 * />
 *
 * // Toggle/checkbox
 * <SettingsToggle
 *   label="Enable streaming"
 *   checked={enableStreaming}
 *   onChange={setEnableStreaming}
 *   switchStyle
 *   description="Stream responses in real-time"
 * />
 * ```
 */

export { default as SettingsSlider } from './SettingsSlider';
export { default as SettingsInput } from './SettingsInput';
export { default as SettingsSelect } from './SettingsSelect';
export { default as SettingsToggle } from './SettingsToggle';
