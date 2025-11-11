'use client';

import { useState, useEffect } from 'react';
import { X, Plus, Check, MapPin, Clock, FileText } from 'lucide-react';
import apiClient from '@/lib/api';
import CharacterQuickAdd from '@/components/CharacterQuickAdd';

interface Character {
  id: number;
  name: string;
  role: string | null;
  description: string | null;
  story_character_id?: number;
}

interface ChapterWizardProps {
  storyId: number;
  chapterNumber?: number;
  initialData?: {
    title?: string;
    description?: string;
    characters?: Character[];
    location_name?: string;
    time_period?: string;
    scenario?: string;
    continues_from_previous?: boolean;
  };
  onComplete: (data: {
    title?: string;
    description?: string;
    story_character_ids: number[];
    location_name?: string;
    time_period?: string;
    scenario?: string;
    continues_from_previous?: boolean;
  }) => void;
  onCancel: () => void;
}

export default function ChapterWizard({
  storyId,
  chapterNumber,
  initialData,
  onComplete,
  onCancel
}: ChapterWizardProps) {
  const [title, setTitle] = useState(initialData?.title || `Chapter ${chapterNumber || 1}`);
  const [description, setDescription] = useState(initialData?.description || '');
  const [selectedCharacterIds, setSelectedCharacterIds] = useState<number[]>(
    initialData?.characters?.map(c => c.id) || []
  );
  const [availableCharacters, setAvailableCharacters] = useState<Character[]>([]);
  const [locationName, setLocationName] = useState(initialData?.location_name || '');
  const [availableLocations, setAvailableLocations] = useState<string[]>([]);
  const [timePeriod, setTimePeriod] = useState(initialData?.time_period || '');
  const [scenario, setScenario] = useState(initialData?.scenario || '');
  const [continuesFromPrevious, setContinuesFromPrevious] = useState(
    initialData?.continues_from_previous !== undefined ? initialData.continues_from_previous : true
  );
  const [showCharacterQuickAdd, setShowCharacterQuickAdd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingData, setLoadingData] = useState(true);

  useEffect(() => {
    loadAvailableData();
  }, [storyId]);

  const loadAvailableData = async () => {
    try {
      setLoadingData(true);
      const [charsResponse, locsResponse] = await Promise.all([
        apiClient.getAvailableCharacters(storyId),
        apiClient.getAvailableLocations(storyId)
      ]);
      
      setAvailableCharacters(charsResponse.characters.map(c => ({
        id: c.character_id,
        name: c.name,
        role: c.role,
        description: c.description,
        story_character_id: c.story_character_id
      })));
      setAvailableLocations(locsResponse.locations);
    } catch (error) {
      console.error('Failed to load available data:', error);
    } finally {
      setLoadingData(false);
    }
  };

  const handleCharacterToggle = (characterId: number) => {
    setSelectedCharacterIds(prev => {
      if (prev.includes(characterId)) {
        return prev.filter(id => id !== characterId);
      } else {
        return [...prev, characterId];
      }
    });
  };

  const handleCharacterAdd = async (character: { id?: number; name: string; role: string; description: string }) => {
    // Character is added to story via CharacterQuickAdd
    // Now we need to add it to the chapter selection
    if (character.id) {
      // Find the story_character_id for this character
      const storyChar = availableCharacters.find(c => c.id === character.id);
      if (storyChar) {
        setSelectedCharacterIds(prev => {
          if (!prev.includes(character.id!)) {
            return [...prev, character.id!];
          }
          return prev;
        });
      } else {
        // Character was just created, reload available characters
        await loadAvailableData();
        // Try to find it again
        const updatedChars = await apiClient.getAvailableCharacters(storyId);
        const newChar = updatedChars.characters.find(c => c.character_id === character.id);
        if (newChar) {
          setSelectedCharacterIds(prev => {
            if (!prev.includes(character.id!)) {
              return [...prev, character.id!];
            }
            return prev;
          });
        }
      }
    }
    setShowCharacterQuickAdd(false);
  };

  const handleSubmit = () => {
    // Get story_character_ids for selected characters
    const storyCharacterIds = availableCharacters
      .filter(c => selectedCharacterIds.includes(c.id))
      .map(c => c.story_character_id)
      .filter((id): id is number => id !== undefined && id !== null);

    onComplete({
      title: title.trim() || undefined,
      description: description.trim() || undefined,
      story_character_ids: storyCharacterIds,
      location_name: locationName.trim() || undefined,
      time_period: timePeriod.trim() || undefined,
      scenario: scenario.trim() || undefined,
      continues_from_previous: continuesFromPrevious
    });
  };

  if (loadingData) {
    return (
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
        <div className="bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 p-8">
          <div className="w-16 h-16 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-white/80 text-center">Loading chapter setup...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 p-8 max-w-3xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-white">
            {chapterNumber ? `Chapter ${chapterNumber} Setup` : 'Chapter Setup'}
          </h2>
          <button
            onClick={onCancel}
            className="text-white/60 hover:text-white transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <div className="space-y-6">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-white/80 mb-2">
              Chapter Title (optional)
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-pink-500"
              placeholder={`Chapter ${chapterNumber || 1}`}
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-white/80 mb-2">
              Description (optional)
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-pink-500 resize-none"
              placeholder="Brief description of this chapter..."
            />
          </div>

          {/* Characters */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-white/80">
                Characters (select characters active in this chapter)
              </label>
              <button
                onClick={() => setShowCharacterQuickAdd(true)}
                className="flex items-center space-x-1 px-3 py-1 bg-pink-600 hover:bg-pink-700 text-white rounded-lg text-sm transition-colors"
              >
                <Plus className="w-4 h-4" />
                <span>Add Character</span>
              </button>
            </div>
            <div className="bg-white/5 rounded-lg p-4 border border-white/10">
              {availableCharacters.length === 0 ? (
                <p className="text-white/60 text-sm">No characters available. Add characters to your story first.</p>
              ) : (
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {availableCharacters.map((char) => (
                    <label
                      key={char.id}
                      className="flex items-start space-x-3 p-2 rounded hover:bg-white/5 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={selectedCharacterIds.includes(char.id)}
                        onChange={() => handleCharacterToggle(char.id)}
                        className="mt-1 w-4 h-4 text-pink-600 bg-white/10 border-white/20 rounded focus:ring-pink-500"
                      />
                      <div className="flex-1">
                        <div className="text-white font-medium">{char.name}</div>
                        {char.role && (
                          <div className="text-white/60 text-sm">{char.role}</div>
                        )}
                        {char.description && (
                          <div className="text-white/50 text-xs mt-1">{char.description}</div>
                        )}
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>
            {selectedCharacterIds.length > 0 && (
              <p className="mt-2 text-white/60 text-sm">
                {selectedCharacterIds.length} character{selectedCharacterIds.length !== 1 ? 's' : ''} selected
              </p>
            )}
          </div>

          {/* Location */}
          <div>
            <label className="block text-sm font-medium text-white/80 mb-2 flex items-center space-x-2">
              <MapPin className="w-4 h-4" />
              <span>Location (optional)</span>
            </label>
            <div className="flex space-x-2">
              {availableLocations.length > 0 && (
                <select
                  value={locationName}
                  onChange={(e) => setLocationName(e.target.value)}
                  className="flex-1 px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-pink-500"
                >
                  <option value="">Select or type new location...</option>
                  {availableLocations.map((loc) => (
                    <option key={loc} value={loc} className="bg-gray-800">
                      {loc}
                    </option>
                  ))}
                </select>
              )}
              <input
                type="text"
                value={locationName}
                onChange={(e) => setLocationName(e.target.value)}
                placeholder={availableLocations.length > 0 ? "Or type new location..." : "Enter location..."}
                className="flex-1 px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-pink-500"
              />
            </div>
          </div>

          {/* Time Period */}
          <div>
            <label className="block text-sm font-medium text-white/80 mb-2 flex items-center space-x-2">
              <Clock className="w-4 h-4" />
              <span>Time Period (optional)</span>
            </label>
            <input
              type="text"
              value={timePeriod}
              onChange={(e) => setTimePeriod(e.target.value)}
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-pink-500"
              placeholder="e.g., Morning, Evening, 1920s, Future..."
            />
          </div>

          {/* Scenario */}
          <div>
            <label className="block text-sm font-medium text-white/80 mb-2 flex items-center space-x-2">
              <FileText className="w-4 h-4" />
              <span>Chapter Scenario (optional)</span>
            </label>
            <textarea
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              rows={4}
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-pink-500 resize-none"
              placeholder="Describe the scenario or situation for this chapter..."
            />
          </div>

          {/* Continues from Previous Chapter */}
          <div>
            <label className="flex items-center space-x-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition-colors">
              <input
                type="checkbox"
                checked={continuesFromPrevious}
                onChange={(e) => setContinuesFromPrevious(e.target.checked)}
                className="w-5 h-5 text-pink-600 bg-white/10 border-white/20 rounded focus:ring-pink-500"
              />
              <div className="flex-1">
                <div className="text-white font-medium">Chapter directly follows previous chapter?</div>
                <div className="text-white/60 text-sm mt-1">
                  If enabled, recent scenes from the previous chapter will be included in context for continuity.
                </div>
              </div>
            </label>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end space-x-4 mt-8">
          <button
            onClick={onCancel}
            className="px-6 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-6 py-2 bg-pink-600 hover:bg-pink-700 disabled:bg-pink-800 disabled:opacity-50 text-white rounded-lg transition-colors flex items-center space-x-2"
          >
            {loading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                <span>Creating...</span>
              </>
            ) : (
              <>
                <Check className="w-4 h-4" />
                <span>Continue</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Character Quick Add Modal */}
      {showCharacterQuickAdd && (
        <CharacterQuickAdd
          onCharacterAdd={handleCharacterAdd}
          onClose={() => setShowCharacterQuickAdd(false)}
          existingCharacters={availableCharacters.map(c => ({
            id: c.id,
            name: c.name,
            role: c.role || '',
            description: c.description || ''
          }))}
          storyId={storyId}
        />
      )}
    </div>
  );
}

