import React, { useState, useEffect } from 'react';
import { X, ChevronLeft, ChevronRight, User, Sparkles, CheckCircle, AlertCircle } from 'lucide-react';
import apiClient from '../lib/api';

interface CharacterSuggestion {
  name: string;
  mention_count: number;
  importance_score: number;
  first_appearance_scene: number;
  last_appearance_scene: number;
  is_in_library: boolean;
  preview: string;
  scenes: number[];
}

interface CharacterDetails {
  name: string;
  description: string;
  personality_traits: string[];
  background: string;
  goals: string;
  fears: string;
  appearance: string;
  suggested_role: string;
  confidence: number;
  scenes_analyzed: number[];
}

interface CharacterWizardProps {
  storyId: number;
  chapterId?: number;
  onCharacterCreated: (character: any) => void;
  onClose: () => void;
}

const CHARACTER_ROLES = [
  { id: 'protagonist', name: 'Main Character', icon: '⭐', color: 'from-yellow-400 to-orange-500' },
  { id: 'antagonist', name: 'Antagonist', icon: '⚔️', color: 'from-red-500 to-red-700' },
  { id: 'ally', name: 'Ally/Friend', icon: '🤝', color: 'from-green-400 to-green-600' },
  { id: 'mentor', name: 'Mentor', icon: '🎓', color: 'from-blue-400 to-blue-600' },
  { id: 'love_interest', name: 'Love Interest', icon: '💕', color: 'from-pink-400 to-pink-600' },
  { id: 'comic_relief', name: 'Comic Relief', icon: '😄', color: 'from-purple-400 to-purple-600' },
  { id: 'mysterious', name: 'Mysterious Figure', icon: '🎭', color: 'from-gray-500 to-gray-700' },
  { id: 'other', name: 'Other', icon: '👤', color: 'from-indigo-400 to-indigo-600' }
];

export default function CharacterWizard({ storyId, chapterId, onCharacterCreated, onClose }: CharacterWizardProps) {
  const [currentStep, setCurrentStep] = useState(1);
  const [suggestions, setSuggestions] = useState<CharacterSuggestion[]>([]);
  const [selectedCharacter, setSelectedCharacter] = useState<CharacterSuggestion | null>(null);
  const [characterDetails, setCharacterDetails] = useState<CharacterDetails | null>(null);
  const [selectedRole, setSelectedRole] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 1: Load character suggestions
  useEffect(() => {
    if (currentStep === 1) {
      loadSuggestions();
    }
  }, [currentStep]);

  const loadSuggestions = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await apiClient.getCharacterSuggestions(storyId, chapterId);
      setSuggestions(response.suggestions);
    } catch (err) {
      setError('Failed to load character suggestions');
      console.error('Error loading suggestions:', err);
    } finally {
      setLoading(false);
    }
  };

  const analyzeCharacter = async (character: CharacterSuggestion) => {
    try {
      setLoading(true);
      setError(null);
      const details = await apiClient.analyzeCharacterDetails(storyId, character.name);
      setCharacterDetails(details);
      setSelectedRole(details.suggested_role);
      setCurrentStep(3); // Skip to role selection
    } catch (err) {
      setError('Failed to analyze character details');
      console.error('Error analyzing character:', err);
    } finally {
      setLoading(false);
    }
  };

  const createCharacter = async () => {
    if (!selectedCharacter || !characterDetails || !selectedRole) return;

    try {
      setLoading(true);
      setError(null);
      
      const characterData = {
        name: characterDetails.name,
        description: characterDetails.description,
        personality_traits: characterDetails.personality_traits,
        background: characterDetails.background,
        goals: characterDetails.goals,
        fears: characterDetails.fears,
        appearance: characterDetails.appearance,
        role: selectedRole
      };

      const createdCharacter = await apiClient.createCharacterFromSuggestion(
        storyId,
        selectedCharacter.name,
        characterData
      );

      onCharacterCreated(createdCharacter);
      onClose();
    } catch (err) {
      setError('Failed to create character');
      console.error('Error creating character:', err);
    } finally {
      setLoading(false);
    }
  };

  const getRoleInfo = (roleId: string) => {
    return CHARACTER_ROLES.find(role => role.id === roleId) || CHARACTER_ROLES[CHARACTER_ROLES.length - 1];
  };

  const renderStep1 = () => (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-white mb-2">Discover Characters</h2>
        <p className="text-white/70">Analyzing your story for new characters...</p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2"
               style={{ borderColor: 'var(--color-accentPrimary)' } as React.CSSProperties}>
          </div>
        </div>
      ) : error ? (
        <div className="text-center py-8">
          <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <p className="text-red-400 mb-4">{error}</p>
          <button
            onClick={loadSuggestions}
            className="px-4 py-2 theme-btn-primary rounded-lg"
          >
            Try Again
          </button>
        </div>
      ) : suggestions.length === 0 ? (
        <div className="text-center py-8">
          <User className="h-12 w-12 text-white/40 mx-auto mb-4" />
          <p className="text-white/60">No new characters found in this chapter.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {suggestions.map((suggestion, index) => (
            <div
              key={index}
              className="bg-white/5 rounded-lg p-4 border border-white/10 hover:bg-white/10 transition-colors cursor-pointer"
              onClick={() => {
                setSelectedCharacter(suggestion);
                analyzeCharacter(suggestion);
              }}
            >
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-2">
                    <h3 className="text-lg font-semibold text-white">{suggestion.name}</h3>
                    <div className="flex items-center space-x-2">
                      <span className="px-2 py-1 text-xs rounded"
                            style={{ backgroundColor: 'var(--color-accentPrimary)', opacity: 0.2, color: 'var(--color-accentPrimary)' } as React.CSSProperties}>
                        {suggestion.importance_score}% important
                      </span>
                      <span className="px-2 py-1 bg-blue-500/20 text-blue-300 text-xs rounded">
                        {suggestion.mention_count} mentions
                      </span>
                    </div>
                  </div>
                  <p className="text-white/70 text-sm mb-2">{suggestion.preview}</p>
                  <p className="text-white/50 text-xs">
                    Appears in scenes {suggestion.first_appearance_scene}-{suggestion.last_appearance_scene}
                  </p>
                </div>
                <ChevronRight className="h-5 w-5 text-white/40" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const renderStep2 = () => (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-white mb-2">Analyzing Character</h2>
        <p className="text-white/70">Extracting detailed information about {selectedCharacter?.name}...</p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2"
               style={{ borderColor: 'var(--color-accentPrimary)' } as React.CSSProperties}>
          </div>
        </div>
      ) : error ? (
        <div className="text-center py-8">
          <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <p className="text-red-400 mb-4">{error}</p>
          <button
            onClick={() => setCurrentStep(1)}
            className="px-4 py-2 theme-btn-primary rounded-lg"
          >
            Back to Characters
          </button>
        </div>
      ) : null}
    </div>
  );

  const renderStep3 = () => (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-white mb-2">Character Details</h2>
        <p className="text-white/70">Review and edit the extracted information for {characterDetails?.name}</p>
      </div>

      {characterDetails && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-white/80 mb-2">Name</label>
              <input
                type="text"
                value={characterDetails.name}
                onChange={(e) => setCharacterDetails({...characterDetails, name: e.target.value})}
                className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-white/80 mb-2">Confidence</label>
              <div className="flex items-center space-x-2">
                <div className="flex-1 bg-white/10 rounded-full h-2">
                  <div 
                    className="h-2 rounded-full"
                    style={{ 
                      backgroundColor: 'var(--color-accentPrimary)',
                      width: `${characterDetails.confidence * 100}%`
                    } as React.CSSProperties}
                  ></div>
                </div>
                <span className="text-white/70 text-sm">{Math.round(characterDetails.confidence * 100)}%</span>
              </div>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-white/80 mb-2">Description</label>
            <textarea
              value={characterDetails.description}
              onChange={(e) => setCharacterDetails({...characterDetails, description: e.target.value})}
              rows={3}
              className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-white/80 mb-2">Personality Traits</label>
            <input
              type="text"
              value={characterDetails.personality_traits.join(', ')}
              onChange={(e) => setCharacterDetails({
                ...characterDetails, 
                personality_traits: e.target.value.split(',').map(t => t.trim()).filter(t => t)
              })}
              placeholder="brave, loyal, determined"
              className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-white/80 mb-2">Background</label>
              <textarea
                value={characterDetails.background}
                onChange={(e) => setCharacterDetails({...characterDetails, background: e.target.value})}
                rows={3}
                className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-white/80 mb-2">Goals</label>
              <textarea
                value={characterDetails.goals}
                onChange={(e) => setCharacterDetails({...characterDetails, goals: e.target.value})}
                rows={3}
                className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-white/80 mb-2">Fears</label>
              <textarea
                value={characterDetails.fears}
                onChange={(e) => setCharacterDetails({...characterDetails, fears: e.target.value})}
                rows={3}
                className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-white/80 mb-2">Appearance</label>
              <textarea
                value={characterDetails.appearance}
                onChange={(e) => setCharacterDetails({...characterDetails, appearance: e.target.value})}
                rows={3}
                className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-white/80 mb-2">Character Role</label>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {CHARACTER_ROLES.map((role) => {
                const isSelected = selectedRole === role.id;
                return (
                  <button
                    key={role.id}
                    onClick={() => setSelectedRole(role.id)}
                    className={`p-3 rounded-lg border-2 transition-all ${
                      isSelected
                        ? 'border-2'
                        : 'border-white/20 hover:border-white/40'
                    }`}
                    style={isSelected ? {
                      borderColor: 'var(--color-accentPrimary)',
                      backgroundColor: 'var(--color-accentPrimary)',
                      opacity: 0.2
                    } as React.CSSProperties : {}}
                  >
                    <div className={`w-8 h-8 rounded-full bg-gradient-to-r ${role.color} flex items-center justify-center text-white text-lg mb-2 mx-auto`}>
                      {role.icon}
                    </div>
                    <div className="text-white text-sm font-medium">{role.name}</div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );

  const renderStep4 = () => (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-white mb-2">Confirm Character</h2>
        <p className="text-white/70">Review the character before adding to your library</p>
      </div>

      {characterDetails && selectedRole && (
        <div className="bg-white/5 rounded-lg p-6 border border-white/10">
          <div className="flex items-center space-x-4 mb-4">
            <div className={`w-12 h-12 rounded-full bg-gradient-to-r ${getRoleInfo(selectedRole).color} flex items-center justify-center text-white text-xl`}>
              {getRoleInfo(selectedRole).icon}
            </div>
            <div>
              <h3 className="text-xl font-semibold text-white">{characterDetails.name}</h3>
              <p className="text-white/70">{getRoleInfo(selectedRole).name}</p>
            </div>
          </div>
          
          <div className="space-y-3">
            <div>
              <h4 className="text-sm font-medium text-white/80 mb-1">Description</h4>
              <p className="text-white/70 text-sm">{characterDetails.description}</p>
            </div>
            
            <div>
              <h4 className="text-sm font-medium text-white/80 mb-1">Personality</h4>
              <p className="text-white/70 text-sm">{characterDetails.personality_traits.join(', ')}</p>
            </div>
            
            <div>
              <h4 className="text-sm font-medium text-white/80 mb-1">Background</h4>
              <p className="text-white/70 text-sm">{characterDetails.background}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 rounded-xl max-w-4xl w-full max-h-[90vh] overflow-hidden">
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <div className="flex items-center space-x-4">
            <div className="flex space-x-2">
              {[1, 2, 3, 4].map((step) => (
                <div
                  key={step}
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                    step <= currentStep
                      ? 'text-white'
                      : 'bg-white/10 text-white/50'
                  }`}
                  style={step <= currentStep ? {
                    backgroundColor: 'var(--color-accentPrimary)'
                  } as React.CSSProperties : {}}
                >
                  {step}
                </div>
              ))}
            </div>
            <div className="text-white/70 text-sm">
              Step {currentStep} of 4
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="h-5 w-5 text-white/70" />
          </button>
        </div>

        <div className="p-6 overflow-y-auto max-h-[calc(90vh-120px)]">
          {currentStep === 1 && renderStep1()}
          {currentStep === 2 && renderStep2()}
          {currentStep === 3 && renderStep3()}
          {currentStep === 4 && renderStep4()}
        </div>

        <div className="flex items-center justify-between p-6 border-t border-white/10">
          <button
            onClick={() => setCurrentStep(Math.max(1, currentStep - 1))}
            disabled={currentStep === 1}
            className="flex items-center space-x-2 px-4 py-2 text-white/70 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronLeft className="h-4 w-4" />
            <span>Back</span>
          </button>

          <div className="flex space-x-3">
            {currentStep === 1 && (
              <button
                onClick={onClose}
                className="px-4 py-2 text-white/70 hover:text-white"
              >
                Cancel
              </button>
            )}
            
            {currentStep === 3 && (
              <button
                onClick={() => setCurrentStep(4)}
                disabled={!selectedRole}
                className="flex items-center space-x-2 px-6 py-2 theme-btn-primary rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <span>Continue</span>
                <ChevronRight className="h-4 w-4" />
              </button>
            )}
            
            {currentStep === 4 && (
              <button
                onClick={createCharacter}
                disabled={loading || !characterDetails || !selectedRole}
                className="flex items-center space-x-2 px-6 py-2 bg-green-500 hover:bg-green-600 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                ) : (
                  <CheckCircle className="h-4 w-4" />
                )}
                <span>Create Character</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
