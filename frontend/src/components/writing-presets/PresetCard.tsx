'use client';

import React from 'react';
import { WritingStylePreset } from '@/types/writing-presets';

interface PresetCardProps {
  preset: WritingStylePreset;
  onActivate: (preset: WritingStylePreset) => void;
  onEdit: (preset: WritingStylePreset) => void;
  onDuplicate: (preset: WritingStylePreset) => void;
  onDelete: (preset: WritingStylePreset) => void;
}

export default function PresetCard({
  preset,
  onActivate,
  onEdit,
  onDuplicate,
  onDelete,
}: PresetCardProps) {
  return (
    <div
      className={`
        relative rounded-lg border-2 p-4 transition-all
        ${preset.is_active
          ? 'border-blue-500 bg-blue-50 dark:bg-blue-950 shadow-lg'
          : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
        }
      `}
    >
      {/* Active Badge */}
      {preset.is_active && (
        <div className="absolute top-2 right-2 bg-blue-500 text-white text-xs px-2 py-1 rounded-full font-semibold">
          Active
        </div>
      )}

      {/* Preset Name & Description */}
      <div className="mb-3">
        <h3 className="text-lg font-bold text-gray-900 dark:text-white">
          {preset.name}
        </h3>
        {preset.description && (
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            {preset.description}
          </p>
        )}
      </div>

      {/* System Prompt Preview */}
      <div className="mb-4">
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">
          Writing Style:
        </p>
        <div className="bg-white dark:bg-gray-800 rounded p-2 text-xs text-gray-700 dark:text-gray-300 line-clamp-3">
          {preset.system_prompt}
        </div>
      </div>

      {/* Summary Override Indicator */}
      {preset.summary_system_prompt && (
        <div className="mb-4">
          <p className="text-xs text-green-600 dark:text-green-400 flex items-center">
            <svg className="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            Custom summary style
          </p>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex gap-2 flex-wrap">
        {!preset.is_active && (
          <button
            onClick={() => onActivate(preset)}
            className="flex-1 min-w-[100px] bg-blue-500 hover:bg-blue-600 text-white px-3 py-2 rounded text-sm font-medium transition-colors"
          >
            Activate
          </button>
        )}
        <button
          onClick={() => onEdit(preset)}
          className="flex-1 min-w-[80px] bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 px-3 py-2 rounded text-sm font-medium transition-colors"
        >
          Edit
        </button>
        <button
          onClick={() => onDuplicate(preset)}
          className="bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 px-3 py-2 rounded text-sm font-medium transition-colors"
          title="Duplicate preset"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
        </button>
        <button
          onClick={() => onDelete(preset)}
          className="bg-red-50 hover:bg-red-100 dark:bg-red-950 dark:hover:bg-red-900 text-red-600 dark:text-red-400 px-3 py-2 rounded text-sm font-medium transition-colors"
          title="Delete preset"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      </div>

      {/* Metadata */}
      <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Created {new Date(preset.created_at).toLocaleDateString()}
          {preset.updated_at && ` • Updated ${new Date(preset.updated_at).toLocaleDateString()}`}
        </p>
      </div>
    </div>
  );
}

