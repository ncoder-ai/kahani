'use client';

import { useId } from 'react';

interface SettingsSliderProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step?: number;
  description?: string;
  /** Format function for displaying the value (defaults to showing raw value) */
  formatValue?: (value: number) => string;
  /** Whether to parse as int (default) or float */
  parseAsFloat?: boolean;
  /** Additional className for the container */
  className?: string;
  /** Disable the slider */
  disabled?: boolean;
}

/**
 * Reusable settings slider component with label and optional description.
 * Reduces boilerplate for range inputs in settings forms.
 */
export default function SettingsSlider({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  description,
  formatValue,
  parseAsFloat = false,
  className = '',
  disabled = false,
}: SettingsSliderProps) {
  const id = useId();

  const displayValue = formatValue ? formatValue(value) : value;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = parseAsFloat
      ? parseFloat(e.target.value)
      : parseInt(e.target.value, 10);
    onChange(newValue);
  };

  return (
    <div className={className}>
      <label htmlFor={id} className="block text-xs sm:text-sm font-medium text-white mb-1 sm:mb-2">
        {label}: <span className="text-blue-400">{displayValue}</span>
      </label>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={handleChange}
        disabled={disabled}
        className={`w-full ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      />
      {description && (
        <p className="text-[10px] sm:text-xs text-gray-400 mt-1">{description}</p>
      )}
    </div>
  );
}
