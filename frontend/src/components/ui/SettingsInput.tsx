'use client';

import { useId } from 'react';

interface SettingsInputProps {
  label: string;
  value: string | number;
  onChange: (value: string | number) => void;
  type?: 'text' | 'number' | 'password' | 'url';
  placeholder?: string;
  description?: string;
  /** For number inputs */
  min?: number;
  max?: number;
  step?: number;
  /** Additional className for the container */
  className?: string;
  /** Additional className for the input */
  inputClassName?: string;
  /** Disable the input */
  disabled?: boolean;
  /** Required field */
  required?: boolean;
  /** Auto-focus on mount */
  autoFocus?: boolean;
}

/**
 * Reusable settings input component with label and optional description.
 * Supports text, number, password, and url input types.
 */
export default function SettingsInput({
  label,
  value,
  onChange,
  type = 'text',
  placeholder,
  description,
  min,
  max,
  step,
  className = '',
  inputClassName = '',
  disabled = false,
  required = false,
  autoFocus = false,
}: SettingsInputProps) {
  const id = useId();

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = type === 'number'
      ? (e.target.value === '' ? '' : parseFloat(e.target.value))
      : e.target.value;
    onChange(newValue);
  };

  const baseInputClass = 'w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500';
  const disabledClass = disabled ? 'opacity-50 cursor-not-allowed' : '';

  return (
    <div className={className}>
      <label htmlFor={id} className="block text-xs sm:text-sm font-medium text-white mb-1 sm:mb-2">
        {label}
        {required && <span className="text-red-400 ml-1">*</span>}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={handleChange}
        placeholder={placeholder}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        required={required}
        autoFocus={autoFocus}
        className={`${baseInputClass} ${disabledClass} ${inputClassName}`}
      />
      {description && (
        <p className="text-[10px] sm:text-xs text-gray-400 mt-1">{description}</p>
      )}
    </div>
  );
}
