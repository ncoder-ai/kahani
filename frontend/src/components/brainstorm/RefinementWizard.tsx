'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import IdeaCard from './IdeaCard';
import ElementEditor from './ElementEditor';

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
}

interface RefinementWizardProps {
  elements: ExtractedElements;
  onUpdate: (elements: ExtractedElements) => void;
  onStartStory: () => void;
  onBackToChat: () => void;
  sessionId: number;
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
  const router = useRouter();

  const handleSave = (field: string, value: any) => {
    onUpdate({
      ...elements,
      [field]: value
    });
    setEditingField(null);
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

      {/* Title Suggestions */}
      {elements.suggested_titles && elements.suggested_titles.length > 0 && (
        <IdeaCard 
          title="Title Suggestions" 
          icon="📖"
          onEdit={() => setEditingField('suggested_titles')}
        >
          <div className="space-y-2">
            {elements.suggested_titles.map((title, index) => (
              <div key={index} className="p-2 bg-white/5 rounded-lg">
                {title}
              </div>
            ))}
          </div>
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

      {/* Characters */}
      {elements.characters && elements.characters.length > 0 && (
        <IdeaCard 
          title="Characters" 
          icon="👥"
        >
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
                      <span className="text-sm text-purple-300 capitalize">{character.role}</span>
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
        </IdeaCard>
      )}

      {/* Scenario */}
      {elements.scenario && (
        <IdeaCard 
          title="Opening Scenario" 
          icon="🎬"
          onEdit={() => setEditingField('scenario')}
        >
          <p>{elements.scenario}</p>
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
          onEdit={() => setEditingField('themes')}
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
          onEdit={() => setEditingField('conflicts')}
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
          onEdit={() => setEditingField('plot_points')}
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
          onClick={onStartStory}
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
        <ElementEditor
          title={editingField.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
          value={(elements as any)[editingField]}
          onSave={(value) => handleSave(editingField, value)}
          onCancel={() => setEditingField(null)}
          type={
            ['suggested_titles', 'themes', 'conflicts', 'plot_points'].includes(editingField) 
              ? 'list' 
              : ['scenario', 'world_setting', 'description'].includes(editingField)
              ? 'textarea'
              : 'text'
          }
        />
      )}
    </div>
  );
}

