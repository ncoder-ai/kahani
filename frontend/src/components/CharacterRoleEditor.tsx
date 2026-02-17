'use client';

import { useState, useEffect } from 'react';
import { X, UserCog, Check, Loader2 } from 'lucide-react';
import apiClient from '@/lib/api';
import { CHARACTER_ROLES, isCustomRole, getRoleInfo as sharedGetRoleInfo } from '@/components/RoleSelector';

interface StoryCharacter {
  id: number;
  character_id: number;
  story_id: number;
  role: string | null;
  name: string;
  description: string | null;
}

interface CharacterRoleEditorProps {
  isOpen: boolean;
  onClose: () => void;
  storyId: number;
  branchId?: number;
  onSaved?: () => void;
}

export default function CharacterRoleEditor({ isOpen, onClose, storyId, branchId, onSaved }: CharacterRoleEditorProps) {
  const [characters, setCharacters] = useState<StoryCharacter[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingCharacterId, setSavingCharacterId] = useState<number | null>(null);
  const [pendingRoles, setPendingRoles] = useState<Record<number, string>>({});
  const [customRoles, setCustomRoles] = useState<Record<number, string>>({});

  useEffect(() => {
    if (isOpen && storyId) {
      loadCharacters();
    }
  }, [isOpen, storyId, branchId]);

  const loadCharacters = async () => {
    setLoading(true);
    setError(null);
    try {
      // If branchId is not provided, fetch the story to get its current_branch_id
      let effectiveBranchId = branchId;
      if (effectiveBranchId === undefined) {
        try {
          const story = await apiClient.getStory(storyId);
          effectiveBranchId = story.current_branch_id;
        } catch (err) {
          console.warn('[CharacterRoleEditor] Failed to get story, proceeding without branch filter');
        }
      }

      const storyCharacters = await apiClient.getStoryCharacters(storyId, effectiveBranchId);
      setCharacters(storyCharacters);
      // Initialize pending roles with current roles
      const initialRoles: Record<number, string> = {};
      const initialCustomRoles: Record<number, string> = {};
      storyCharacters.forEach(char => {
        if (char.role) {
          // If the role is a custom role (not in predefined list), set it as custom
          if (isCustomRole(char.role)) {
            initialRoles[char.id] = 'other';
            initialCustomRoles[char.id] = char.role;
          } else {
            initialRoles[char.id] = char.role;
          }
        }
      });
      setPendingRoles(initialRoles);
      setCustomRoles(initialCustomRoles);
    } catch (err) {
      console.error('Failed to load story characters:', err);
      setError(err instanceof Error ? err.message : 'Failed to load characters');
    } finally {
      setLoading(false);
    }
  };

  const handleRoleChange = (storyCharacterId: number, role: string) => {
    setPendingRoles(prev => ({
      ...prev,
      [storyCharacterId]: role
    }));
    // Clear custom role if switching away from "other"
    if (role !== 'other') {
      setCustomRoles(prev => {
        const updated = { ...prev };
        delete updated[storyCharacterId];
        return updated;
      });
    }
  };

  const handleCustomRoleChange = (storyCharacterId: number, customRole: string) => {
    setCustomRoles(prev => ({
      ...prev,
      [storyCharacterId]: customRole
    }));
  };

  const saveRole = async (storyCharacterId: number) => {
    const pendingRole = pendingRoles[storyCharacterId];
    if (!pendingRole) return;

    // If "other" is selected, use the custom role text instead
    const roleToSave = pendingRole === 'other' && customRoles[storyCharacterId]
      ? customRoles[storyCharacterId]
      : pendingRole;

    setSavingCharacterId(storyCharacterId);
    try {
      await apiClient.updateStoryCharacterRole(storyId, storyCharacterId, roleToSave);
      // Update local state
      setCharacters(prev => prev.map(char => 
        char.id === storyCharacterId ? { ...char, role: roleToSave } : char
      ));
      if (onSaved) {
        onSaved();
      }
    } catch (err) {
      console.error('Failed to update character role:', err);
      setError(err instanceof Error ? err.message : 'Failed to update role');
    } finally {
      setSavingCharacterId(null);
    }
  };

  const getRoleInfo = (roleId: string | null) => {
    return sharedGetRoleInfo(roleId);
  };

  const hasUnsavedChanges = (storyCharacterId: number, currentRole: string | null) => {
    const pendingRole = pendingRoles[storyCharacterId];
    const customRole = customRoles[storyCharacterId];
    
    // If "other" is selected, compare the custom role text
    if (pendingRole === 'other') {
      // If current role is a custom role, compare with the custom role text
      if (isCustomRole(currentRole)) {
        return customRole !== currentRole;
      }
      // If current role is not custom, we have changes if custom role text is set
      return !!customRole;
    }
    
    // For predefined roles, compare directly
    return pendingRole && pendingRole !== currentRole;
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
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-slate-700 bg-gradient-to-r from-amber-900/50 to-orange-900/50">
            <div className="flex items-center gap-3">
              <UserCog className="w-6 h-6 text-amber-400" />
              <h2 className="text-2xl font-bold text-white">Edit Character Roles</h2>
            </div>
            <button
              onClick={onClose}
              className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-gray-400" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-6">
            {loading ? (
              <div className="text-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-amber-400 mx-auto mb-3" />
                <div className="text-gray-400">Loading characters...</div>
              </div>
            ) : error ? (
              <div className="bg-red-900/50 border border-red-700 rounded-lg p-4 text-red-200">
                {error}
              </div>
            ) : characters.length === 0 ? (
              <div className="text-center py-12">
                <div className="text-gray-400 mb-2">No characters in this story yet.</div>
                <div className="text-sm text-gray-500">Add characters to your story to assign roles.</div>
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-sm text-gray-400 mb-4">
                  Assign roles to characters in your story. Roles help the AI understand each character's function in the narrative.
                </p>
                
                {characters.map(character => {
                  const currentRole = character.role;
                  const selectedRole = pendingRoles[character.id] || (isCustomRole(currentRole) ? 'other' : currentRole) || '';
                  const customRole = customRoles[character.id];
                  // For display, show custom role text if "other" is selected
                  const displayRole = selectedRole === 'other' && customRole ? customRole : selectedRole;
                  const roleInfo = getRoleInfo(displayRole);
                  const hasChanges = hasUnsavedChanges(character.id, currentRole);
                  const isSaving = savingCharacterId === character.id;

                  return (
                    <div 
                      key={character.id}
                      className="bg-slate-700/50 border border-slate-600 rounded-lg p-4"
                    >
                      <div className="flex items-start justify-between gap-4 mb-3">
                        <div className="flex-1">
                          <h3 className="text-lg font-semibold text-white">{character.name}</h3>
                          {character.description && (
                            <p className="text-sm text-gray-400 line-clamp-2 mt-1">{character.description}</p>
                          )}
                        </div>
                        {roleInfo && (
                          <div className={`px-3 py-1 rounded-full bg-gradient-to-r ${roleInfo.color} text-white text-sm font-medium flex items-center gap-1.5`}>
                            <span>{roleInfo.icon}</span>
                            <span>{roleInfo.name}</span>
                          </div>
                        )}
                      </div>

                      {/* Role Selection Grid */}
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
                        {CHARACTER_ROLES.map(role => {
                          const isSelected = selectedRole === role.id;
                          return (
                            <button
                              key={role.id}
                              type="button"
                              onClick={() => handleRoleChange(character.id, role.id)}
                              className={`p-2 rounded-lg border-2 transition-all text-center ${
                                isSelected
                                  ? 'border-amber-500 bg-amber-500/20'
                                  : 'border-slate-600 hover:border-slate-500 bg-slate-700/50'
                              }`}
                            >
                              <div className={`w-8 h-8 rounded-full bg-gradient-to-r ${role.color} flex items-center justify-center text-white text-lg mb-1 mx-auto`}>
                                {role.icon}
                              </div>
                              <div className={`text-xs font-medium ${isSelected ? 'text-amber-400' : 'text-gray-300'}`}>
                                {role.name}
                              </div>
                            </button>
                          );
                        })}
                      </div>

                      {/* Custom Role Input - shown when "Other" is selected */}
                      {selectedRole === 'other' && (
                        <div className="mb-3">
                          <label className="block text-sm text-gray-400 mb-1">
                            Specify custom role:
                          </label>
                          <input
                            type="text"
                            value={customRoles[character.id] ?? ''}
                            onChange={(e) => handleCustomRoleChange(character.id, e.target.value)}
                            placeholder="e.g., Sidekick, Rival, Guardian, Trickster..."
                            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                          />
                          <p className="text-xs text-gray-500 mt-1">
                            Enter a custom role that best describes this character's function in your story.
                          </p>
                        </div>
                      )}

                      {/* Save Button */}
                      {hasChanges && (
                        <div className="flex justify-end">
                          <button
                            onClick={() => saveRole(character.id)}
                            disabled={isSaving}
                            className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-amber-800 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
                          >
                            {isSaving ? (
                              <>
                                <Loader2 className="w-4 h-4 animate-spin" />
                                Saving...
                              </>
                            ) : (
                              <>
                                <Check className="w-4 h-4" />
                                Save Role
                              </>
                            )}
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex justify-end gap-3 p-6 border-t border-slate-700">
            <button
              onClick={onClose}
              className="px-6 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

