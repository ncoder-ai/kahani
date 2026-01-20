'use client';

import { useId } from 'react';

interface SettingsToggleProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  description?: string;
  /** Additional className for the container */
  className?: string;
  /** Disable the toggle */
  disabled?: boolean;
  /** Use a switch-style toggle instead of checkbox */
  switchStyle?: boolean;
}

/**
 * Reusable settings toggle/checkbox component with label and optional description.
 * Supports both standard checkbox and switch-style toggle.
 */
export default function SettingsToggle({
  label,
  checked,
  onChange,
  description,
  className = '',
  disabled = false,
  switchStyle = false,
}: SettingsToggleProps) {
  const id = useId();

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.checked);
  };

  if (switchStyle) {
    return (
      <div className={`flex items-center justify-between ${className}`}>
        <div>
          <label htmlFor={id} className="text-sm font-medium text-white cursor-pointer">
            {label}
          </label>
          {description && (
            <p className="text-xs text-gray-400 mt-1">{description}</p>
          )}
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          onClick={() => !disabled && onChange(!checked)}
          disabled={disabled}
          className={`
            relative inline-flex h-6 w-11 items-center rounded-full transition-colors
            ${checked ? 'bg-blue-600' : 'bg-gray-600'}
            ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          `}
        >
          <span
            className={`
              inline-block h-4 w-4 transform rounded-full bg-white transition-transform
              ${checked ? 'translate-x-6' : 'translate-x-1'}
            `}
          />
        </button>
      </div>
    );
  }

  // Standard checkbox style
  return (
    <div className={`flex items-start gap-3 ${className}`}>
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={handleChange}
        disabled={disabled}
        className={`
          mt-1 h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600
          focus:ring-2 focus:ring-blue-500 focus:ring-offset-gray-800
          ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
        `}
      />
      <div>
        <label htmlFor={id} className={`text-sm font-medium text-white ${disabled ? '' : 'cursor-pointer'}`}>
          {label}
        </label>
        {description && (
          <p className="text-xs text-gray-400 mt-1">{description}</p>
        )}
      </div>
    </div>
  );
}
