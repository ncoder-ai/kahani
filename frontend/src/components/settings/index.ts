/**
 * Settings Components
 *
 * Modular settings UI components for the Settings Modal.
 */

// Types
export * from './types';

// Tab Components
export { default as InterfaceSettingsTab } from './tabs/InterfaceSettingsTab';
export { default as WritingSettingsTab } from './tabs/WritingSettingsTab';
export { default as LLMSettingsTab } from './tabs/LLMSettingsTab';
export { default as ContextSettingsTab } from './tabs/ContextSettingsTab';
export { default as VoiceSettingsTab } from './tabs/VoiceSettingsTab';
export { default as ImageGenSettingsTab } from './tabs/ImageGenSettingsTab';
export type { ImageGenSettings } from './tabs/ImageGenSettingsTab';
