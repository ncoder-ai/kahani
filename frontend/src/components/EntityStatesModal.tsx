'use client';

import { useState, useEffect } from 'react';
import { X, Trash2, Edit2, Check, XCircle, ChevronDown, ChevronRight, Users, MapPin, Package } from 'lucide-react';
import apiClient from '@/lib/api';

// Relationship can be a string or a nested object with type/status/change
type RelationshipValue = string | { type?: string; status?: string; change?: string; [key: string]: string | undefined };

interface CharacterState {
  id: number;
  character_id: number;
  character_name: string;
  story_id: number;
  last_updated_scene: number | null;
  current_location: string | null;
  physical_condition: string | null;
  appearance: string | null;
  possessions: string[];
  emotional_state: string | null;
  current_goal: string | null;
  active_conflicts: string[];
  knowledge: string[];
  secrets: string[];
  relationships: Record<string, RelationshipValue>;
  arc_stage: string | null;
  arc_progress: number | null;
  recent_decisions: string[];
  recent_actions: string[];
  updated_at: string | null;
}

interface LocationState {
  id: number;
  story_id: number;
  location_name: string;
  last_updated_scene: number | null;
  condition: string | null;
  atmosphere: string | null;
  notable_features: string[];
  current_occupants: string[];
  significant_events: string[];
  time_of_day: string | null;
  weather: string | null;
  updated_at: string | null;
}

interface ObjectState {
  id: number;
  story_id: number;
  object_name: string;
  last_updated_scene: number | null;
  condition: string | null;
  current_location: string | null;
  current_owner_id: number | null;
  current_owner_name: string | null;
  significance: string | null;
  object_type: string | null;
  powers: string[];
  limitations: string[];
  origin: string | null;
  previous_owners: string[];
  recent_events: string[];
  updated_at: string | null;
}

interface EntityStatesModalProps {
  isOpen: boolean;
  onClose: () => void;
  storyId: number;
  storyTitle: string;
}

type TabType = 'characters' | 'locations' | 'objects';

export default function EntityStatesModal({
  isOpen,
  onClose,
  storyId,
  storyTitle
}: EntityStatesModalProps) {
  const [activeTab, setActiveTab] = useState<TabType>('characters');
  const [characterStates, setCharacterStates] = useState<CharacterState[]>([]);
  const [locationStates, setLocationStates] = useState<LocationState[]>([]);
  const [objectStates, setObjectStates] = useState<ObjectState[]>([]);
  const [loading, setLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editData, setEditData] = useState<Record<string, unknown>>({});
  const [counts, setCounts] = useState({ characters: 0, locations: 0, objects: 0 });

  useEffect(() => {
    if (isOpen) {
      loadEntityStates();
    }
  }, [isOpen, storyId]);

  const loadEntityStates = async () => {
    setLoading(true);
    try {
      const result = await apiClient.getEntityStates(storyId);
      setCharacterStates(result.character_states);
      setLocationStates(result.location_states);
      setObjectStates(result.object_states);
      setCounts(result.counts);
    } catch (err) {
      console.error('Failed to load entity states:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (type: TabType, stateId: number) => {
    if (deletingId) return;

    setDeletingId(stateId);
    try {
      await apiClient.deleteEntityState(storyId, type, stateId);
      // Remove from local state
      if (type === 'characters') {
        setCharacterStates(prev => prev.filter(s => s.id !== stateId));
        setCounts(prev => ({ ...prev, characters: prev.characters - 1 }));
      } else if (type === 'locations') {
        setLocationStates(prev => prev.filter(s => s.id !== stateId));
        setCounts(prev => ({ ...prev, locations: prev.locations - 1 }));
      } else {
        setObjectStates(prev => prev.filter(s => s.id !== stateId));
        setCounts(prev => ({ ...prev, objects: prev.objects - 1 }));
      }
    } catch (err) {
      console.error('Failed to delete state:', err);
    } finally {
      setDeletingId(null);
    }
  };

  const toggleExpanded = (id: number) => {
    setExpandedIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  const startEdit = (id: number, data: CharacterState | LocationState | ObjectState) => {
    setEditingId(id);
    setEditData({ ...data } as Record<string, unknown>);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditData({});
  };

  const saveEdit = async () => {
    if (!editingId) return;

    try {
      if (activeTab === 'characters') {
        await apiClient.updateCharacterState(storyId, editingId, editData as Parameters<typeof apiClient.updateCharacterState>[2]);
        setCharacterStates(prev => prev.map(s => s.id === editingId ? { ...s, ...editData } as CharacterState : s));
      } else if (activeTab === 'locations') {
        await apiClient.updateLocationState(storyId, editingId, editData as Parameters<typeof apiClient.updateLocationState>[2]);
        setLocationStates(prev => prev.map(s => s.id === editingId ? { ...s, ...editData } as LocationState : s));
      } else {
        await apiClient.updateObjectState(storyId, editingId, editData as Parameters<typeof apiClient.updateObjectState>[2]);
        setObjectStates(prev => prev.map(s => s.id === editingId ? { ...s, ...editData } as ObjectState : s));
      }
      setEditingId(null);
      setEditData({});
    } catch (err) {
      console.error('Failed to save state:', err);
    }
  };

  const renderStringField = (label: string, field: string, value: string | null) => {
    const isEditing = editingId !== null;
    return (
      <div className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-2 py-1">
        <span className="text-gray-300 text-xs sm:text-sm sm:w-32 shrink-0 font-medium">{label}:</span>
        {isEditing ? (
          <input
            type="text"
            value={(editData[field] as string) ?? value ?? ''}
            onChange={(e) => setEditData(prev => ({ ...prev, [field]: e.target.value || null }))}
            className="w-full sm:flex-1 bg-slate-700 border border-slate-500 rounded px-2 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
          />
        ) : (
          <span className="text-white text-sm">{value || <span className="text-gray-400 italic">Not set</span>}</span>
        )}
      </div>
    );
  };

  const renderArrayField = (label: string, field: string, values: string[]) => {
    const isEditing = editingId !== null;
    const currentValues = (editData[field] as string[]) ?? values;

    return (
      <div className="py-1">
        <span className="text-gray-300 text-xs sm:text-sm font-medium">{label}:</span>
        {isEditing ? (
          <div className="mt-1.5 space-y-1.5">
            {currentValues.map((v, i) => (
              <div key={i} className="flex items-center gap-1.5">
                <input
                  type="text"
                  value={v}
                  onChange={(e) => {
                    const newValues = [...currentValues];
                    newValues[i] = e.target.value;
                    setEditData(prev => ({ ...prev, [field]: newValues }));
                  }}
                  className="flex-1 min-w-0 bg-slate-700 border border-slate-500 rounded px-2 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
                />
                <button
                  onClick={() => {
                    const newValues = currentValues.filter((_, idx) => idx !== i);
                    setEditData(prev => ({ ...prev, [field]: newValues }));
                  }}
                  className="text-red-400 active:text-red-300 p-1.5 rounded hover:bg-red-900/30"
                >
                  <XCircle className="w-4 h-4" />
                </button>
              </div>
            ))}
            <button
              onClick={() => setEditData(prev => ({ ...prev, [field]: [...currentValues, ''] }))}
              className="text-blue-400 active:text-blue-300 text-sm py-1"
            >
              + Add item
            </button>
          </div>
        ) : values.length > 0 ? (
          <ul className="mt-1 ml-4 list-disc text-white text-sm space-y-0.5">
            {values.map((v, i) => (
              <li key={i}>{v}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-gray-400 text-sm italic">None</p>
        )}
      </div>
    );
  };

  // Helper to convert relationship value to string for display/editing
  const relToString = (rel: RelationshipValue): string => {
    if (typeof rel === 'string') return rel;
    if (typeof rel === 'object' && rel !== null) {
      return rel.type || rel.status || JSON.stringify(rel);
    }
    return String(rel);
  };

  const renderRelationshipsField = (relationships: Record<string, RelationshipValue>) => {
    const isEditing = editingId !== null;
    const currentRelationships = (editData.relationships as Record<string, RelationshipValue>) ?? relationships ?? {};
    const entries = Object.entries(currentRelationships);

    return (
      <div className="py-1">
        <span className="text-gray-300 text-xs sm:text-sm font-medium">Relationships:</span>
        {isEditing ? (
          <div className="mt-1.5 space-y-2">
            {entries.map(([name, rel], i) => (
              <div key={i} className="flex flex-col sm:flex-row gap-1.5 sm:items-center p-2 bg-slate-800/50 rounded-lg">
                <input
                  type="text"
                  value={name}
                  placeholder="Character"
                  onChange={(e) => {
                    const newRels = { ...currentRelationships };
                    delete newRels[name];
                    newRels[e.target.value] = rel;
                    setEditData(prev => ({ ...prev, relationships: newRels }));
                  }}
                  className="w-full sm:w-28 bg-slate-700 border border-slate-500 rounded px-2 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
                />
                <span className="text-gray-400 text-center hidden sm:block">→</span>
                <input
                  type="text"
                  value={relToString(rel)}
                  placeholder="Relationship"
                  onChange={(e) => {
                    const newRels = { ...currentRelationships, [name]: e.target.value };
                    setEditData(prev => ({ ...prev, relationships: newRels }));
                  }}
                  className="flex-1 min-w-0 bg-slate-700 border border-slate-500 rounded px-2 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
                />
                <button
                  onClick={() => {
                    const newRels = { ...currentRelationships };
                    delete newRels[name];
                    setEditData(prev => ({ ...prev, relationships: newRels }));
                  }}
                  className="text-red-400 active:text-red-300 p-1.5 rounded hover:bg-red-900/30 self-end sm:self-auto"
                >
                  <XCircle className="w-4 h-4" />
                </button>
              </div>
            ))}
            <button
              onClick={() => setEditData(prev => ({ ...prev, relationships: { ...currentRelationships, '': '' } }))}
              className="text-blue-400 active:text-blue-300 text-sm py-1"
            >
              + Add relationship
            </button>
          </div>
        ) : entries.length > 0 ? (
          <ul className="mt-1 ml-4 list-disc text-white text-sm space-y-0.5">
            {entries.map(([name, rel]) => (
              <li key={name}><span className="text-purple-400">{name}</span>: {relToString(rel)}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-gray-400 text-sm italic">None</p>
        )}
      </div>
    );
  };

  const renderCharacterCard = (state: CharacterState) => {
    const isExpanded = expandedIds.has(state.id);
    const isEditing = editingId === state.id;

    return (
      <div key={state.id} className="bg-slate-900/50 rounded-lg border border-slate-700/50 overflow-hidden">
        {/* Header */}
        <div
          className="flex items-center justify-between p-3 sm:p-4 cursor-pointer hover:bg-slate-800/50 active:bg-slate-800/70"
          onClick={() => toggleExpanded(state.id)}
        >
          <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1">
            {isExpanded ? <ChevronDown className="w-4 h-4 text-gray-300 flex-shrink-0" /> : <ChevronRight className="w-4 h-4 text-gray-300 flex-shrink-0" />}
            <div className="min-w-0">
              <h3 className="text-base sm:text-lg font-medium text-white truncate">{state.character_name}</h3>
              <p className="text-xs sm:text-sm text-gray-300 truncate">
                {state.current_location && <span className="text-blue-400">{state.current_location}</span>}
                {state.current_location && state.emotional_state && ' • '}
                {state.emotional_state && <span className="text-purple-400">{state.emotional_state}</span>}
                {(state.current_location || state.emotional_state) && state.last_updated_scene && ' • '}
                {state.last_updated_scene && <span>Scene {state.last_updated_scene}</span>}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
            {isEditing ? (
              <>
                <button onClick={saveEdit} className="p-2 sm:p-1.5 hover:bg-green-900/50 active:bg-green-900/70 rounded text-green-400" title="Save">
                  <Check className="w-4 h-4" />
                </button>
                <button onClick={cancelEdit} className="p-2 sm:p-1.5 hover:bg-slate-700 active:bg-slate-600 rounded text-gray-300" title="Cancel">
                  <XCircle className="w-4 h-4" />
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => startEdit(state.id, state)}
                  className="p-2 sm:p-1.5 hover:bg-slate-700 active:bg-slate-600 rounded text-gray-300 hover:text-blue-400"
                  title="Edit"
                >
                  <Edit2 className="w-4 h-4" />
                </button>
                <button
                  onClick={() => handleDelete('characters', state.id)}
                  disabled={deletingId === state.id}
                  className="p-2 sm:p-1.5 hover:bg-red-900/50 active:bg-red-900/70 rounded text-gray-400 hover:text-red-400 disabled:opacity-50"
                  title="Delete"
                >
                  <Trash2 className={`w-4 h-4 ${deletingId === state.id ? 'animate-pulse' : ''}`} />
                </button>
              </>
            )}
          </div>
        </div>

        {/* Expanded Content */}
        {isExpanded && (
          <div className="px-3 sm:px-4 pb-3 sm:pb-4 border-t border-slate-700/50 pt-3 space-y-3">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 sm:gap-4">
              <div className="space-y-1">
                {renderStringField('Location', 'current_location', state.current_location)}
                {renderStringField('Emotional State', 'emotional_state', state.emotional_state)}
                {renderStringField('Physical Condition', 'physical_condition', state.physical_condition)}
                {renderStringField('Appearance', 'appearance', state.appearance)}
                {renderStringField('Current Goal', 'current_goal', state.current_goal)}
                {renderStringField('Arc Stage', 'arc_stage', state.arc_stage)}
              </div>
              <div className="space-y-1">
                {renderArrayField('Possessions', 'possessions', state.possessions)}
                {renderArrayField('Knowledge', 'knowledge', state.knowledge)}
                {renderArrayField('Secrets', 'secrets', state.secrets)}
              </div>
            </div>
            <div className="border-t border-slate-700/30 pt-2 mt-2">
              {renderRelationshipsField(state.relationships)}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4 border-t border-slate-700/30 pt-2">
              <div className="space-y-1">
                {renderArrayField('Active Conflicts', 'active_conflicts', state.active_conflicts)}
                {renderArrayField('Recent Decisions', 'recent_decisions', state.recent_decisions)}
              </div>
              <div className="space-y-1">
                {renderArrayField('Recent Actions', 'recent_actions', state.recent_actions)}
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderLocationCard = (state: LocationState) => {
    const isExpanded = expandedIds.has(state.id + 10000); // Offset to avoid ID collision
    const isEditing = editingId === state.id;

    return (
      <div key={state.id} className="bg-slate-900/50 rounded-lg border border-slate-700/50 overflow-hidden">
        <div
          className="flex items-center justify-between p-3 sm:p-4 cursor-pointer hover:bg-slate-800/50 active:bg-slate-800/70"
          onClick={() => toggleExpanded(state.id + 10000)}
        >
          <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1">
            {isExpanded ? <ChevronDown className="w-4 h-4 text-gray-300 flex-shrink-0" /> : <ChevronRight className="w-4 h-4 text-gray-300 flex-shrink-0" />}
            <div className="min-w-0">
              <h3 className="text-base sm:text-lg font-medium text-white truncate">{state.location_name}</h3>
              <p className="text-xs sm:text-sm text-gray-300 truncate">
                {state.atmosphere && <span className="text-green-400">{state.atmosphere}</span>}
                {state.atmosphere && state.condition && ' • '}
                {state.condition && <span className="text-yellow-400">{state.condition}</span>}
                {(state.atmosphere || state.condition) && state.last_updated_scene && ' • '}
                {state.last_updated_scene && <span>Scene {state.last_updated_scene}</span>}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
            {isEditing ? (
              <>
                <button onClick={saveEdit} className="p-2 sm:p-1.5 hover:bg-green-900/50 active:bg-green-900/70 rounded text-green-400" title="Save">
                  <Check className="w-4 h-4" />
                </button>
                <button onClick={cancelEdit} className="p-2 sm:p-1.5 hover:bg-slate-700 active:bg-slate-600 rounded text-gray-300" title="Cancel">
                  <XCircle className="w-4 h-4" />
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => startEdit(state.id, state)}
                  className="p-2 sm:p-1.5 hover:bg-slate-700 active:bg-slate-600 rounded text-gray-300 hover:text-blue-400"
                  title="Edit"
                >
                  <Edit2 className="w-4 h-4" />
                </button>
                <button
                  onClick={() => handleDelete('locations', state.id)}
                  disabled={deletingId === state.id}
                  className="p-2 sm:p-1.5 hover:bg-red-900/50 active:bg-red-900/70 rounded text-gray-400 hover:text-red-400 disabled:opacity-50"
                  title="Delete"
                >
                  <Trash2 className={`w-4 h-4 ${deletingId === state.id ? 'animate-pulse' : ''}`} />
                </button>
              </>
            )}
          </div>
        </div>

        {isExpanded && (
          <div className="px-3 sm:px-4 pb-3 sm:pb-4 border-t border-slate-700/50 pt-3 space-y-3">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 sm:gap-4">
              <div className="space-y-1">
                {renderStringField('Condition', 'condition', state.condition)}
                {renderStringField('Atmosphere', 'atmosphere', state.atmosphere)}
                {renderStringField('Time of Day', 'time_of_day', state.time_of_day)}
                {renderStringField('Weather', 'weather', state.weather)}
              </div>
              <div className="space-y-1">
                {renderArrayField('Current Occupants', 'current_occupants', state.current_occupants)}
                {renderArrayField('Notable Features', 'notable_features', state.notable_features)}
                {renderArrayField('Significant Events', 'significant_events', state.significant_events)}
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderObjectCard = (state: ObjectState) => {
    const isExpanded = expandedIds.has(state.id + 20000); // Offset to avoid ID collision
    const isEditing = editingId === state.id;

    return (
      <div key={state.id} className="bg-slate-900/50 rounded-lg border border-slate-700/50 overflow-hidden">
        <div
          className="flex items-center justify-between p-3 sm:p-4 cursor-pointer hover:bg-slate-800/50 active:bg-slate-800/70"
          onClick={() => toggleExpanded(state.id + 20000)}
        >
          <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1">
            {isExpanded ? <ChevronDown className="w-4 h-4 text-gray-300 flex-shrink-0" /> : <ChevronRight className="w-4 h-4 text-gray-300 flex-shrink-0" />}
            <div className="min-w-0">
              <h3 className="text-base sm:text-lg font-medium text-white truncate">{state.object_name}</h3>
              <p className="text-xs sm:text-sm text-gray-300 truncate">
                {state.object_type && <span className="text-orange-400">{state.object_type}</span>}
                {state.object_type && state.current_owner_name && ' • '}
                {state.current_owner_name && <span>Owned by <span className="text-purple-400">{state.current_owner_name}</span></span>}
                {(state.object_type || state.current_owner_name) && state.last_updated_scene && ' • '}
                {state.last_updated_scene && <span>Scene {state.last_updated_scene}</span>}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
            {isEditing ? (
              <>
                <button onClick={saveEdit} className="p-2 sm:p-1.5 hover:bg-green-900/50 active:bg-green-900/70 rounded text-green-400" title="Save">
                  <Check className="w-4 h-4" />
                </button>
                <button onClick={cancelEdit} className="p-2 sm:p-1.5 hover:bg-slate-700 active:bg-slate-600 rounded text-gray-300" title="Cancel">
                  <XCircle className="w-4 h-4" />
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => startEdit(state.id, state)}
                  className="p-2 sm:p-1.5 hover:bg-slate-700 active:bg-slate-600 rounded text-gray-300 hover:text-blue-400"
                  title="Edit"
                >
                  <Edit2 className="w-4 h-4" />
                </button>
                <button
                  onClick={() => handleDelete('objects', state.id)}
                  disabled={deletingId === state.id}
                  className="p-2 sm:p-1.5 hover:bg-red-900/50 active:bg-red-900/70 rounded text-gray-400 hover:text-red-400 disabled:opacity-50"
                  title="Delete"
                >
                  <Trash2 className={`w-4 h-4 ${deletingId === state.id ? 'animate-pulse' : ''}`} />
                </button>
              </>
            )}
          </div>
        </div>

        {isExpanded && (
          <div className="px-3 sm:px-4 pb-3 sm:pb-4 border-t border-slate-700/50 pt-3 space-y-3">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 sm:gap-4">
              <div className="space-y-1">
                {renderStringField('Object Type', 'object_type', state.object_type)}
                {renderStringField('Condition', 'condition', state.condition)}
                {renderStringField('Current Location', 'current_location', state.current_location)}
                {renderStringField('Significance', 'significance', state.significance)}
                {renderStringField('Origin', 'origin', state.origin)}
              </div>
              <div className="space-y-1">
                {renderArrayField('Powers', 'powers', state.powers)}
                {renderArrayField('Limitations', 'limitations', state.limitations)}
                {renderArrayField('Previous Owners', 'previous_owners', state.previous_owners)}
                {renderArrayField('Recent Events', 'recent_events', state.recent_events)}
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4">
        <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-2xl w-full max-w-5xl max-h-[95vh] sm:max-h-[90vh] overflow-hidden flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between p-3 sm:p-6 border-b border-slate-700 bg-gradient-to-r from-emerald-900/50 to-teal-900/50">
            <div className="flex items-center gap-2 sm:gap-3 min-w-0">
              <Package className="w-5 h-5 sm:w-6 sm:h-6 text-emerald-400 flex-shrink-0" />
              <div className="min-w-0">
                <h2 className="text-lg sm:text-2xl font-bold text-white">Entity States</h2>
                <p className="text-xs sm:text-sm text-gray-300 truncate">{storyTitle}</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-2 hover:bg-slate-700 rounded-lg transition-colors flex-shrink-0"
            >
              <X className="w-5 h-5 text-gray-300" />
            </button>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-slate-700 overflow-x-auto">
            <button
              onClick={() => setActiveTab('characters')}
              className={`flex items-center gap-1.5 sm:gap-2 px-3 sm:px-6 py-2.5 sm:py-3 text-xs sm:text-sm font-medium transition-colors whitespace-nowrap ${
                activeTab === 'characters'
                  ? 'text-white border-b-2 border-purple-500 bg-slate-700/30'
                  : 'text-gray-300 hover:text-white hover:bg-slate-700/20'
              }`}
            >
              <Users className="w-4 h-4" />
              <span className="hidden xs:inline">Characters</span> ({counts.characters})
            </button>
            <button
              onClick={() => setActiveTab('locations')}
              className={`flex items-center gap-1.5 sm:gap-2 px-3 sm:px-6 py-2.5 sm:py-3 text-xs sm:text-sm font-medium transition-colors whitespace-nowrap ${
                activeTab === 'locations'
                  ? 'text-white border-b-2 border-green-500 bg-slate-700/30'
                  : 'text-gray-300 hover:text-white hover:bg-slate-700/20'
              }`}
            >
              <MapPin className="w-4 h-4" />
              <span className="hidden xs:inline">Locations</span> ({counts.locations})
            </button>
            <button
              onClick={() => setActiveTab('objects')}
              className={`flex items-center gap-1.5 sm:gap-2 px-3 sm:px-6 py-2.5 sm:py-3 text-xs sm:text-sm font-medium transition-colors whitespace-nowrap ${
                activeTab === 'objects'
                  ? 'text-white border-b-2 border-orange-500 bg-slate-700/30'
                  : 'text-gray-300 hover:text-white hover:bg-slate-700/20'
              }`}
            >
              <Package className="w-4 h-4" />
              <span className="hidden xs:inline">Objects</span> ({counts.objects})
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-3 sm:p-6">
            {loading ? (
              <div className="text-center py-12 text-gray-400">Loading entity states...</div>
            ) : (
              <div className="space-y-4">
                {activeTab === 'characters' && (
                  characterStates.length === 0 ? (
                    <div className="text-center py-12">
                      <p className="text-gray-400 mb-2">No character states tracked yet.</p>
                      <p className="text-sm text-gray-500">Character states are extracted automatically during scene generation.</p>
                    </div>
                  ) : (
                    characterStates.map(renderCharacterCard)
                  )
                )}
                {activeTab === 'locations' && (
                  locationStates.length === 0 ? (
                    <div className="text-center py-12">
                      <p className="text-gray-400 mb-2">No location states tracked yet.</p>
                      <p className="text-sm text-gray-500">Location states are extracted automatically during scene generation.</p>
                    </div>
                  ) : (
                    locationStates.map(renderLocationCard)
                  )
                )}
                {activeTab === 'objects' && (
                  objectStates.length === 0 ? (
                    <div className="text-center py-12">
                      <p className="text-gray-400 mb-2">No object states tracked yet.</p>
                      <p className="text-sm text-gray-500">Object states are extracted automatically during scene generation.</p>
                    </div>
                  ) : (
                    objectStates.map(renderObjectCard)
                  )
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

