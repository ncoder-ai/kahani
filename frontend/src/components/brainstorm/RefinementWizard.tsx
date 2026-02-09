'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Check, X } from 'lucide-react';
import IdeaCard from './IdeaCard';
import ElementEditor from './ElementEditor';
import apiClient from '@/lib/api';

interface ExtractedElements {
  genre: string;
  tone: string;
  characters: Array<{
    name: string;
    role: string;
    description: string;
    personality_traits?: string[];
  }>;
  scenario: string;
  world_setting: string;
  suggested_titles: string[];
  description: string;
  plot_points: string[];
  themes: string[];
  conflicts: string[];
  selectedTitle?: string;
  useScenarioForChapter?: boolean;
}

interface RefinementWizardProps {
  elements: ExtractedElements;
  onUpdate: (elements: ExtractedElements) => void;
  onStartStory: (selectedTitle?: string) => void;
  onBackToChat: () => void;
  sessionId: number | null;
  isCreatingStory: boolean;
}

export default function RefinementWizard({ 
  elements, 
  onUpdate, 
  onStartStory,
  onBackToChat,
  sessionId,
  isCreatingStory 
}: RefinementWizardProps) {
  const [editingField, setEditingField] = useState<string | null>(null);
  const [selectedTitle, setSelectedTitle] = useState<string | null>(
    elements.suggested_titles?.[0] || null
  );
  const [isGeneratingCharacters, setIsGeneratingCharacters] = useState(false);
  const [useScenarioForChapter, setUseScenarioForChapter] = useState(true);
  const router = useRouter();

  const handleSave = (field: string, value: any) => {
    console.log('[RefinementWizard] Saving field:', field, 'with value:', value);
    onUpdate({
      ...elements,
      [field]: value
    });
    setEditingField(null);
  };

  const handleEdit = (field: string) => {
    console.log('[RefinementWizard] Opening editor for field:', field);
    setEditingField(field);
  };

  const getCharacterRoleIcon = (role: string) => {
    const roleMap: Record<string, string> = {
      protagonist: '⭐',
      antagonist: '⚔️',
      ally: '🤝',
      mentor: '🎓',
      love_interest: '💕',
      comic_relief: '😄',
      mysterious: '🎭',
      other: '👤'
    };
    return roleMap[role] || '👤';
  };

  const handleRemoveCharacter = (index: number) => {
    const updatedCharacters = elements.characters.filter((_, i) => i !== index);
    onUpdate({
      ...elements,
      characters: updatedCharacters
    });
  };

  const handleGenerateCharacters = async () => {
    if (!sessionId) return;
    
    setIsGeneratingCharacters(true);
    try {
      const data = await apiClient.generateCharactersForSession(sessionId);
      
      // Merge new characters with existing ones
      const existingCharacters = elements.characters || [];
      const newCharacters = data.characters || [];
      
      onUpdate({
        ...elements,
        characters: [...existingCharacters, ...newCharacters]
      });
    } catch (error) {
      console.error('Failed to generate characters:', error);
      alert('Failed to generate characters. Please try again or add them manually.');
    } finally {
      setIsGeneratingCharacters(false);
    }
  };

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="text-center mb-8">
        <h2 className="text-3xl font-bold text-white mb-4">✨ Refine Your Story Elements</h2>
        <p className="text-white/80 text-lg">
          Review and edit the extracted elements before creating your story
        </p>
      </div>

      {/* Genre & Tone */}
      <div className="grid md:grid-cols-2 gap-4">
        <IdeaCard 
          title="Genre" 
          icon="🎭"
          onEdit={() => setEditingField('genre')}
        >
          <p className="text-lg font-medium capitalize">{elements.genre || 'Not set'}</p>
        </IdeaCard>

        <IdeaCard 
          title="Tone" 
          icon="🎨"
          onEdit={() => setEditingField('tone')}
        >
          <p className="text-lg font-medium capitalize">{elements.tone || 'Not set'}</p>
        </IdeaCard>
      </div>

      {/* Title Suggestions - Clickable */}
      {elements.suggested_titles && elements.suggested_titles.length > 0 && (
        <IdeaCard 
          title="Title Suggestions (Click to Select)" 
          icon="📖"
          onEdit={() => setEditingField('suggested_titles')}
        >
          <div className="space-y-2">
            {elements.suggested_titles.map((title, index) => (
              <button
                key={index}
                onClick={() => setSelectedTitle(title)}
                className={`w-full p-3 rounded-lg transition-all text-left ${
                  selectedTitle === title
                    ? 'bg-purple-500/30 border-2 border-purple-400 shadow-lg'
                    : 'bg-white/5 hover:bg-white/10 border-2 border-transparent'
                }`}
              >
                <div className="flex items-start gap-2">
                  <span className="font-medium flex-1 break-words">{title}</span>
                  {selectedTitle === title && (
                    <Check className="w-5 h-5 text-purple-400 flex-shrink-0 mt-0.5" />
                  )}
                </div>
              </button>
            ))}
          </div>
          {selectedTitle && (
            <p className="text-xs text-purple-300 mt-3">
              ✓ Selected: <strong>{selectedTitle}</strong>
            </p>
          )}
        </IdeaCard>
      )}

      {/* Description */}
      {elements.description && (
        <IdeaCard 
          title="Story Description" 
          icon="📝"
          onEdit={() => setEditingField('description')}
        >
          <p>{elements.description}</p>
        </IdeaCard>
      )}

      {/* Characters - Always show, with generate button */}
      <IdeaCard 
        title="Characters" 
        icon="👥"
      >
        {elements.characters && elements.characters.length > 0 ? (
          <>
            <div className="space-y-3">
              {elements.characters.map((character, index) => (
                <div key={index} className="p-3 bg-white/5 rounded-lg">
                  <div className="flex items-start space-x-3">
                    <span className="text-2xl">
                      {getCharacterRoleIcon(character.role)}
                    </span>
                    <div className="flex-1">
                      <div className="flex justify-between items-start">
                        <h4 className="font-semibold text-white">{character.name}</h4>
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-purple-300 capitalize">{character.role}</span>
                          <button
                            onClick={() => handleRemoveCharacter(index)}
                            className="text-red-400 hover:text-red-300 transition-colors p-1 hover:bg-red-500/10 rounded"
                            title="Remove character"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                      {character.description && (
                        <p className="text-sm text-white/70 mt-1">{character.description}</p>
                      )}
                      {character.personality_traits && character.personality_traits.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {character.personality_traits.map((trait, i) => (
                            <span key={i} className="text-xs px-2 py-1 bg-purple-500/20 text-purple-200 rounded">
                              {trait}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {/* Generate More Characters Button */}
            <div className="mt-4 pt-4 border-t border-white/10">
              <button
                onClick={handleGenerateCharacters}
                disabled={isGeneratingCharacters}
                className="w-full px-4 py-2.5 bg-purple-600/20 hover:bg-purple-600/30 disabled:bg-gray-600/20 disabled:opacity-50 text-purple-300 hover:text-purple-200 border border-purple-500/30 rounded-lg font-medium transition-colors text-sm"
              >
                {isGeneratingCharacters ? (
                  <div className="flex items-center justify-center space-x-2">
                    <div className="w-4 h-4 border-2 border-purple-300/30 border-t-purple-300 rounded-full animate-spin"></div>
                    <span>Generating...</span>
                  </div>
                ) : (
                  '✨ Generate More Characters'
                )}
              </button>
              <p className="text-xs text-white/50 mt-2 text-center">
                AI will create additional characters for your story
              </p>
            </div>
          </>
        ) : (
          <div className="text-center py-8">
            <p className="text-white/60 mb-4">No characters generated yet</p>
            <button
              onClick={handleGenerateCharacters}
              disabled={isGeneratingCharacters}
              className="px-6 py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 disabled:opacity-50 text-white rounded-lg font-medium transition-colors"
            >
              {isGeneratingCharacters ? (
                <div className="flex items-center space-x-2">
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                  <span>Generating Characters...</span>
                </div>
              ) : (
                '✨ Generate Characters'
              )}
            </button>
            <p className="text-xs text-white/50 mt-3">
              AI will create characters based on your story elements
            </p>
          </div>
        )}
      </IdeaCard>

      {/* Scenario with Chapter 1 Pre-population Option */}
      {elements.scenario && (
        <IdeaCard 
          title="Opening Scenario" 
          icon="🎬"
          onEdit={() => setEditingField('scenario')}
        >
          <p className="mb-4">{elements.scenario}</p>
          <div className="mt-4 pt-4 border-t border-white/10">
            <label className="flex items-center space-x-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={useScenarioForChapter}
                onChange={(e) => setUseScenarioForChapter(e.target.checked)}
                className="w-4 h-4 rounded border-white/30 bg-white/10 text-purple-600 focus:ring-2 focus:ring-purple-500 focus:ring-offset-0 cursor-pointer"
              />
              <span className="text-sm text-white/80 group-hover:text-white transition-colors">
                Use this scenario for Chapter 1 setup
              </span>
            </label>
            <p className="text-xs text-white/50 mt-2 ml-7">
              {useScenarioForChapter 
                ? 'This scenario will pre-fill the Chapter 1 creation form'
                : 'You\'ll need to write your own scenario for Chapter 1'}
            </p>
          </div>
        </IdeaCard>
      )}

      {/* World Setting */}
      {elements.world_setting && (
        <IdeaCard 
          title="World & Setting" 
          icon="🌍"
          onEdit={() => setEditingField('world_setting')}
        >
          <p>{elements.world_setting}</p>
        </IdeaCard>
      )}

      {/* Themes */}
      {elements.themes && elements.themes.length > 0 && (
        <IdeaCard 
          title="Themes" 
          icon="💭"
          onEdit={() => handleEdit('themes')}
        >
          <div className="flex flex-wrap gap-2">
            {elements.themes.map((theme, index) => (
              <span key={index} className="px-3 py-1 bg-white/10 rounded-lg">
                {theme}
              </span>
            ))}
          </div>
        </IdeaCard>
      )}

      {/* Conflicts */}
      {elements.conflicts && elements.conflicts.length > 0 && (
        <IdeaCard 
          title="Conflicts" 
          icon="⚡"
          onEdit={() => handleEdit('conflicts')}
        >
          <ul className="space-y-2">
            {elements.conflicts.map((conflict, index) => (
              <li key={index} className="flex items-start space-x-2">
                <span>•</span>
                <span>{conflict}</span>
              </li>
            ))}
          </ul>
        </IdeaCard>
      )}

      {/* Plot Points */}
      {elements.plot_points && elements.plot_points.length > 0 && (
        <IdeaCard 
          title="Plot Points" 
          icon="📈"
          onEdit={() => handleEdit('plot_points')}
        >
          <ol className="space-y-2">
            {elements.plot_points.map((point, index) => (
              <li key={index} className="flex items-start space-x-2">
                <span className="font-semibold">{index + 1}.</span>
                <span>{point}</span>
              </li>
            ))}
          </ol>
        </IdeaCard>
      )}

      {/* Action Buttons */}
      <div className="flex justify-between pt-6">
        <button
          onClick={onBackToChat}
          disabled={isCreatingStory}
          className="px-8 py-3 rounded-xl font-semibold bg-white/20 text-white hover:bg-white/30 transition-colors disabled:opacity-50"
        >
          ← Back to Chat
        </button>
        <button
          onClick={() => {
            // Store the scenario preference in elements before proceeding
            if (useScenarioForChapter && elements.scenario) {
              onUpdate({
                ...elements,
                useScenarioForChapter: true
              });
            }
            onStartStory(selectedTitle || undefined);
          }}
          disabled={isCreatingStory}
          className={`px-8 py-3 rounded-xl font-semibold transition-all duration-200 ${
            isCreatingStory
              ? 'bg-white/20 text-white/50 cursor-not-allowed'
              : 'theme-btn-primary transform hover:scale-105'
          }`}
        >
          {isCreatingStory ? (
            <div className="flex items-center space-x-2">
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
              <span>Creating Story...</span>
            </div>
          ) : (
            '✨ Start Creating Story'
          )}
        </button>
      </div>

      {/* Element Editor Modal */}
      {editingField && (
        <>
          {console.log('[RefinementWizard] Rendering ElementEditor for:', editingField)}
          <ElementEditor
            title={editingField.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
            value={(elements as any)[editingField]}
            onSave={(value) => handleSave(editingField, value)}
            onCancel={() => {
              console.log('[RefinementWizard] Canceling edit');
              setEditingField(null);
            }}
            type={
              ['suggested_titles', 'themes', 'conflicts', 'plot_points'].includes(editingField) 
                ? 'list' 
                : ['scenario', 'world_setting', 'description'].includes(editingField)
                ? 'textarea'
                : 'text'
            }
          />
        </>
      )}
    </div>
  );
}

