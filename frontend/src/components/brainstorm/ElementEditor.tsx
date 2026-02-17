'use client';

import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';

interface ElementEditorProps {
  title: string;
  value: any;
  onSave: (value: any) => void;
  onCancel: () => void;
  type: 'text' | 'textarea' | 'list' | 'select';
  options?: string[];
}

export default function ElementEditor({ 
  title, 
  value, 
  onSave, 
  onCancel, 
  type,
  options = []
}: ElementEditorProps) {
  const [editedValue, setEditedValue] = useState(value);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    console.log('[ElementEditor] Mounted with title:', title, 'type:', type, 'value:', value);
    return () => {
      console.log('[ElementEditor] Unmounting');
    };
  }, [title, type, value]);

  const handleSave = () => {
    console.log('[ElementEditor] Saving value:', editedValue);
    onSave(editedValue);
  };

  const renderEditor = () => {
    switch (type) {
      case 'text':
        return (
          <input
            type="text"
            value={editedValue ?? ''}
            onChange={(e) => setEditedValue(e.target.value)}
            className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
            autoFocus
          />
        );

      case 'textarea':
        return (
          <textarea
            value={editedValue ?? ''}
            onChange={(e) => setEditedValue(e.target.value)}
            rows={4}
            className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
            autoFocus
          />
        );

      case 'select':
        return (
          <select
            value={editedValue ?? ''}
            onChange={(e) => setEditedValue(e.target.value)}
            className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
            autoFocus
          >
            <option value="">Select...</option>
            {options.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
        );
      
      case 'list':
        const listValue = Array.isArray(editedValue) ? editedValue : [];
        return (
          <div className="space-y-2">
            {listValue.length > 0 ? (
              listValue.map((item, index) => (
                <div key={index} className="flex items-center space-x-2">
                  <input
                    type="text"
                    value={item}
                    onChange={(e) => {
                      const newList = [...listValue];
                      newList[index] = e.target.value;
                      setEditedValue(newList);
                    }}
                    className="flex-1 p-2 bg-white/10 border border-white/30 rounded text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                  <button
                    onClick={() => {
                      const newList = listValue.filter((_: any, i: number) => i !== index);
                      setEditedValue(newList);
                    }}
                    className="text-red-400 hover:text-red-300 p-1"
                    title="Remove item"
                  >
                    ✕
                  </button>
                </div>
              ))
            ) : (
              <p className="text-white/50 text-sm italic">No items yet. Click "Add Item" to start.</p>
            )}
            <button
              onClick={() => setEditedValue([...listValue, ''])}
              className="px-3 py-2 bg-white/10 text-white rounded hover:bg-white/20 transition-colors text-sm"
            >
              + Add Item
            </button>
          </div>
        );
      
      default:
        return null;
    }
  };

  if (!mounted) return null;

  const modalContent = (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-[100] p-4" onClick={(e) => {
      // Close on backdrop click
      if (e.target === e.currentTarget) {
        onCancel();
      }
    }}>
      <div className="bg-gradient-to-br from-gray-900 to-gray-800 rounded-xl max-w-2xl w-full border border-white/20 p-6 shadow-2xl">
        <h3 className="text-xl font-bold text-white mb-4">Edit {title}</h3>
        
        <div className="mb-6">
          {renderEditor()}
        </div>

        <div className="flex justify-end space-x-3">
          <button
            onClick={onCancel}
            className="px-6 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-6 py-2 theme-btn-primary rounded-lg transition-colors"
          >
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );

  // Use portal to render at document body level
  return createPortal(modalContent, document.body);
}

