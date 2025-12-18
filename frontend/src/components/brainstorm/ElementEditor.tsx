'use client';

import { useState } from 'react';

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

  const handleSave = () => {
    onSave(editedValue);
  };

  const renderEditor = () => {
    switch (type) {
      case 'text':
        return (
          <input
            type="text"
            value={editedValue || ''}
            onChange={(e) => setEditedValue(e.target.value)}
            className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
            autoFocus
          />
        );
      
      case 'textarea':
        return (
          <textarea
            value={editedValue || ''}
            onChange={(e) => setEditedValue(e.target.value)}
            rows={4}
            className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
            autoFocus
          />
        );
      
      case 'select':
        return (
          <select
            value={editedValue || ''}
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
        return (
          <div className="space-y-2">
            {Array.isArray(editedValue) && editedValue.map((item, index) => (
              <div key={index} className="flex items-center space-x-2">
                <input
                  type="text"
                  value={item}
                  onChange={(e) => {
                    const newList = [...editedValue];
                    newList[index] = e.target.value;
                    setEditedValue(newList);
                  }}
                  className="flex-1 p-2 bg-white/10 border border-white/30 rounded text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <button
                  onClick={() => {
                    const newList = editedValue.filter((_: any, i: number) => i !== index);
                    setEditedValue(newList);
                  }}
                  className="text-red-400 hover:text-red-300"
                >
                  ✕
                </button>
              </div>
            ))}
            <button
              onClick={() => setEditedValue([...(editedValue || []), ''])}
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

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-gradient-to-br from-gray-900 to-gray-800 rounded-xl max-w-2xl w-full border border-white/20 p-6">
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
}

