'use client';

import React, { useState, useEffect } from 'react';
import { StoryArc, ArcPhase } from '@/lib/api';

interface StoryArcEditorProps {
  arc: StoryArc | null;
  onArcChange: (arc: StoryArc) => void;
  onGenerate: (structureType: string) => Promise<void>;
  onConfirm: () => void;
  isGenerating: boolean;
  storyTitle?: string;
}

const STRUCTURE_TYPES = [
  { 
    id: 'three_act', 
    name: 'Three-Act Structure', 
    description: 'Classic Setup, Confrontation, Resolution',
    icon: '📖'
  },
  { 
    id: 'five_act', 
    name: 'Five-Act Structure', 
    description: 'Shakespearean dramatic structure',
    icon: '🎭'
  },
  { 
    id: 'hero_journey', 
    name: "Hero's Journey", 
    description: "Campbell's 12-stage monomyth",
    icon: '⚔️'
  }
];

export default function StoryArcEditor({
  arc,
  onArcChange,
  onGenerate,
  onConfirm,
  isGenerating,
  storyTitle
}: StoryArcEditorProps) {
  const [selectedStructure, setSelectedStructure] = useState<string>(arc?.structure_type || 'three_act');
  const [editingPhase, setEditingPhase] = useState<string | null>(null);
  const [editedPhase, setEditedPhase] = useState<ArcPhase | null>(null);

  useEffect(() => {
    if (arc?.structure_type) {
      setSelectedStructure(arc.structure_type);
    }
  }, [arc]);

  const handleGenerateArc = async () => {
    await onGenerate(selectedStructure);
  };

  const handlePhaseEdit = (phase: ArcPhase) => {
    setEditingPhase(phase.id);
    setEditedPhase({ ...phase });
  };

  const handlePhaseSave = () => {
    if (!arc || !editedPhase) return;
    
    const updatedPhases = arc.phases.map(p => 
      p.id === editedPhase.id ? editedPhase : p
    );
    
    onArcChange({
      ...arc,
      phases: updatedPhases,
      last_modified_at: new Date().toISOString()
    });
    
    setEditingPhase(null);
    setEditedPhase(null);
  };

  const handlePhaseCancel = () => {
    setEditingPhase(null);
    setEditedPhase(null);
  };

  const handleKeyEventChange = (index: number, value: string) => {
    if (!editedPhase) return;
    const newEvents = [...editedPhase.key_events];
    newEvents[index] = value;
    setEditedPhase({ ...editedPhase, key_events: newEvents });
  };

  const addKeyEvent = () => {
    if (!editedPhase) return;
    setEditedPhase({ 
      ...editedPhase, 
      key_events: [...editedPhase.key_events, ''] 
    });
  };

  const removeKeyEvent = (index: number) => {
    if (!editedPhase) return;
    setEditedPhase({ 
      ...editedPhase, 
      key_events: editedPhase.key_events.filter((_, i) => i !== index) 
    });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">
            Story Arc Generator
          </h1>
          {storyTitle && (
            <p className="text-purple-300">
              Creating narrative structure for &ldquo;{storyTitle}&rdquo;
            </p>
          )}
        </div>

        {/* Structure Type Selection */}
        {!arc && (
          <div className="mb-8">
            <h2 className="text-xl font-semibold text-white mb-4">
              Choose Your Story Structure
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {STRUCTURE_TYPES.map((structure) => (
                <button
                  key={structure.id}
                  onClick={() => setSelectedStructure(structure.id)}
                  className={`p-4 rounded-xl border-2 transition-all text-left ${
                    selectedStructure === structure.id
                      ? 'border-purple-500 bg-purple-500/20'
                      : 'border-white/20 bg-white/5 hover:border-purple-400/50'
                  }`}
                >
                  <span className="text-2xl mb-2 block">{structure.icon}</span>
                  <h3 className="text-white font-semibold">{structure.name}</h3>
                  <p className="text-white/60 text-sm mt-1">{structure.description}</p>
                </button>
              ))}
            </div>

            <div className="mt-6 text-center">
              <button
                onClick={handleGenerateArc}
                disabled={isGenerating}
                className="px-8 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold rounded-xl hover:from-purple-500 hover:to-pink-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {isGenerating ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Generating Arc...
                  </span>
                ) : (
                  '✨ Generate Story Arc'
                )}
              </button>
            </div>
          </div>
        )}

        {/* Arc Display & Editor */}
        {arc && (
          <div className="space-y-6">
            {/* Arc Header */}
            <div className="flex items-center justify-between bg-white/5 rounded-xl p-4">
              <div>
                <h2 className="text-xl font-semibold text-white">
                  {STRUCTURE_TYPES.find(s => s.id === arc.structure_type)?.name || 'Story Arc'}
                </h2>
                <p className="text-white/60 text-sm">
                  {arc.phases.length} phases • Click any phase to edit
                </p>
              </div>
              <button
                onClick={() => onArcChange({ ...arc, phases: [] })}
                className="text-white/60 hover:text-white text-sm"
              >
                Regenerate
              </button>
            </div>

            {/* Timeline Visualization */}
            <div className="relative">
              <div className="absolute left-8 top-0 bottom-0 w-0.5 bg-gradient-to-b from-purple-500 via-pink-500 to-purple-500" />
              
              <div className="space-y-4">
                {arc.phases.map((phase, index) => (
                  <div key={phase.id} className="relative pl-16">
                    {/* Timeline Node */}
                    <div className="absolute left-6 top-4 w-4 h-4 rounded-full bg-gradient-to-r from-purple-500 to-pink-500 border-2 border-white" />
                    
                    {editingPhase === phase.id ? (
                      /* Edit Mode */
                      <div className="bg-white/10 backdrop-blur-sm rounded-xl p-4 border border-purple-500">
                        <input
                          type="text"
                          value={editedPhase?.name ?? ''}
                          onChange={(e) => setEditedPhase(prev => prev ? { ...prev, name: e.target.value } : null)}
                          className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white mb-3"
                          placeholder="Phase name"
                        />

                        <textarea
                          value={editedPhase?.description ?? ''}
                          onChange={(e) => setEditedPhase(prev => prev ? { ...prev, description: e.target.value } : null)}
                          className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white mb-3 min-h-[80px]"
                          placeholder="Phase description"
                        />

                        <div className="mb-3">
                          <label className="text-white/80 text-sm block mb-2">Key Events:</label>
                          {editedPhase?.key_events.map((event, i) => (
                            <div key={i} className="flex gap-2 mb-2">
                              <input
                                type="text"
                                value={event}
                                onChange={(e) => handleKeyEventChange(i, e.target.value)}
                                className="flex-1 bg-white/10 border border-white/20 rounded-lg px-3 py-1 text-white text-sm"
                              />
                              <button
                                onClick={() => removeKeyEvent(i)}
                                className="text-red-400 hover:text-red-300 px-2"
                              >
                                ×
                              </button>
                            </div>
                          ))}
                          <button
                            onClick={addKeyEvent}
                            className="text-purple-400 hover:text-purple-300 text-sm"
                          >
                            + Add Event
                          </button>
                        </div>

                        <div className="flex gap-2 justify-end">
                          <button
                            onClick={handlePhaseCancel}
                            className="px-4 py-2 text-white/60 hover:text-white"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={handlePhaseSave}
                            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-500"
                          >
                            Save
                          </button>
                        </div>
                      </div>
                    ) : (
                      /* View Mode */
                      <div 
                        onClick={() => handlePhaseEdit(phase)}
                        className="bg-white/5 backdrop-blur-sm rounded-xl p-4 cursor-pointer hover:bg-white/10 transition-all group"
                      >
                        <div className="flex items-start justify-between">
                          <div>
                            <span className="text-purple-400 text-sm font-medium">
                              Phase {index + 1}
                            </span>
                            <h3 className="text-white font-semibold text-lg">
                              {phase.name}
                            </h3>
                          </div>
                          <span className="text-white/40 group-hover:text-white/60 text-sm">
                            ~{phase.estimated_chapters} chapters
                          </span>
                        </div>
                        
                        <p className="text-white/70 mt-2">
                          {phase.description}
                        </p>
                        
                        {phase.key_events.length > 0 && (
                          <div className="mt-3">
                            <span className="text-white/50 text-sm">Key Events:</span>
                            <ul className="mt-1 space-y-1">
                              {phase.key_events.map((event, i) => (
                                <li key={i} className="text-white/60 text-sm flex items-start gap-2">
                                  <span className="text-purple-400">•</span>
                                  {event}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {phase.characters_involved.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {phase.characters_involved.map((char, i) => (
                              <span 
                                key={i}
                                className="px-2 py-1 bg-white/10 rounded-full text-xs text-white/70"
                              >
                                {char}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Confirm Button */}
            <div className="text-center pt-6">
              <button
                onClick={onConfirm}
                className="px-8 py-3 bg-gradient-to-r from-green-600 to-emerald-600 text-white font-semibold rounded-xl hover:from-green-500 hover:to-emerald-500 transition-all"
              >
                ✓ Confirm Story Arc & Continue
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

