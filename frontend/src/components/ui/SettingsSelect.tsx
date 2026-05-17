'use client';

import { useId } from 'react';

interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface SettingsSelectProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  description?: string;
  placeholder?: string;
  /** Additional className for the container */
  className?: string;
  /** Additional className for the select */
  selectClassName?: string;
  /** Disable the select */
  disabled?: boolean;
  /** Required field */
  required?: boolean;
}

/**
 * Reusable settings select component with label and optional description.
 * Reduces boilerplate for dropdown selects in settings forms.
 */
export default function SettingsSelect({
  label,
  value,
  onChange,
  options,
  description,
  placeholder,
  className = '',
  selectClassName = '',
  disabled = false,
  required = false,
}: SettingsSelectProps) {
  const id = useId();

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onChange(e.target.value);
  };

  const baseSelectClass = 'w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500';
  const disabledClass = disabled ? 'opacity-50 cursor-not-allowed' : '';

  return (
    <div className={className}>
      <label htmlFor={id} className="block text-xs sm:text-sm font-medium text-white mb-1 sm:mb-2">
        {label}
        {required && <span className="text-red-400 ml-1">*</span>}
      </label>
      <select
        id={id}
        value={value}
        onChange={handleChange}
        disabled={disabled}
        required={required}
        className={`${baseSelectClass} ${disabledClass} ${selectClassName}`}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((option) => (
          <option
            key={option.value}
            value={option.value}
            disabled={option.disabled}
          >
            {option.label}
          </option>
        ))}
      </select>
      {description && (
        <p className="text-[10px] sm:text-xs text-gray-400 mt-1">{description}</p>
      )}
    </div>
  );
}
