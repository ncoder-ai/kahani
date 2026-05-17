'use client';

import { Trash2, CheckSquare, Square } from 'lucide-react';

interface BrainstormBulkActionsProps {
  selectMode: boolean;
  selectedCount: number;
  totalCount: number;
  isDeleting: boolean;
  onToggleSelectMode: () => void;
  onToggleSelectAll: () => void;
  onDeleteSelected: () => void;
  onCancel: () => void;
}

export default function BrainstormBulkActions({
  selectMode,
  selectedCount,
  totalCount,
  isDeleting,
  onToggleSelectMode,
  onToggleSelectAll,
  onDeleteSelected,
  onCancel,
}: BrainstormBulkActionsProps) {
  if (!selectMode) {
    return (
      <button
        onClick={onToggleSelectMode}
        className="text-white/70 hover:text-white px-3 py-1.5 rounded-lg hover:bg-white/10 transition-colors text-sm flex items-center gap-1.5"
      >
        <Trash2 className="w-4 h-4" />
        Manage
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={onToggleSelectAll}
        className="text-white/70 hover:text-white px-3 py-1.5 rounded-lg hover:bg-white/10 transition-colors text-sm flex items-center gap-1.5"
      >
        {selectedCount === totalCount ? (
          <CheckSquare className="w-4 h-4" />
        ) : (
          <Square className="w-4 h-4" />
        )}
        {selectedCount === totalCount ? 'Deselect All' : 'Select All'}
      </button>
      <button
        onClick={onDeleteSelected}
        disabled={selectedCount === 0 || isDeleting}
        className="bg-red-600 hover:bg-red-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white px-3 py-1.5 rounded-lg text-sm flex items-center gap-1.5 transition-colors"
      >
        <Trash2 className="w-4 h-4" />
        {isDeleting ? 'Deleting...' : `Delete (${selectedCount})`}
      </button>
      <button
        onClick={onCancel}
        className="text-white/70 hover:text-white px-3 py-1.5 rounded-lg hover:bg-white/10 transition-colors text-sm"
      >
        Cancel
      </button>
    </div>
  );
}
