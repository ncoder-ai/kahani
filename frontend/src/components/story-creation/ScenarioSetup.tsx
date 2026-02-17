'use client';

import { useState } from 'react';
import { StoryData } from '@/app/create-story/page';
import apiClient from '@/lib/api';
import CharacterDisplay from '@/components/CharacterDisplay';

interface ScenarioSetupProps {
  storyData: StoryData;
  onUpdate: (data: Partial<StoryData>) => void;
  onNext: () => void;
  onBack: () => void;
}

const SCENARIO_PROMPTS = [
  {
    id: 'opening',
    title: 'How does your story begin?',
    options: [
      'A mysterious letter arrives',
      'A stranger comes to town',
      'Something goes terribly wrong',
      'A discovery changes everything',
      'An old friend returns',
      'A new adventure beckons'
    ]
  },
  {
    id: 'setting',
    title: 'Where does it take place?',
    options: [
      'A bustling modern city',
      'A quiet small town',
      'A magical realm',
      'A distant planet',
      'An ancient castle',
      'A post-apocalyptic world'
    ]
  },
  {
    id: 'conflict',
    title: 'What drives the story forward?',
    options: [
      'A quest for redemption',
      'A race against time',
      'A forbidden love',
      'A hidden conspiracy',
      'A battle for survival',
      'A search for truth'
    ]
  }
];

export default function ScenarioSetup({ storyData, onUpdate, onNext, onBack }: ScenarioSetupProps) {
  const [selectedOptions, setSelectedOptions] = useState<Record<string, string>>({});
  const [customInputs, setCustomInputs] = useState<Record<string, string>>({});
  const [customScenario, setCustomScenario] = useState(storyData.scenario || '');
  const [isGenerating, setIsGenerating] = useState(false);

  const handleOptionSelect = (promptId: string, option: string) => {
    setSelectedOptions(prev => ({ ...prev, [promptId]: option }));
    // Clear custom input when selecting predefined option
    setCustomInputs(prev => ({ ...prev, [promptId]: '' }));
  };

  const handleCustomInput = (promptId: string, value: string) => {
    setCustomInputs(prev => ({ ...prev, [promptId]: value }));
    // Clear selected option when typing custom input
    if (value.trim()) {
      setSelectedOptions(prev => ({ ...prev, [promptId]: value }));
    }
  };

  const generateScenario = async () => {
    const parts = SCENARIO_PROMPTS.map(prompt => {
      const customValue = customInputs[prompt.id];
      const selectedValue = selectedOptions[prompt.id];
      return customValue || selectedValue;
    }).filter(Boolean);
    
    if (parts.length === 0) return;

    setIsGenerating(true);
    try {
      // Use LLM to generate creative scenario based on selected elements and characters
      const response = await apiClient.generateScenario({
        genre: storyData.genre,
        tone: storyData.tone,
        elements: {
          opening: parts[0] || '',
          setting: parts[1] || '',
          conflict: parts[2] || ''
        },
        characters: storyData.characters || []
      });

      if (response && response.scenario) {
        setCustomScenario(response.scenario);
        onUpdate({ scenario: response.scenario });
      } else {
        // Fallback to simple combination if API fails
        const generated = parts.join('. ') + '.';
        setCustomScenario(generated);
        onUpdate({ scenario: generated });
      }
    } catch (error) {
      console.error('Failed to generate scenario:', error);
      console.error('Error details:', error instanceof Error ? error.message : error);
      // Show user there was an error with the LLM
      alert(`LLM Generation failed: ${error instanceof Error ? error.message : 'Unknown error'}. Using fallback.`);
      // Fallback to simple combination
      const generated = parts.join('. ') + '.';
      setCustomScenario(generated);
      onUpdate({ scenario: generated });
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCustomScenarioChange = (value: string) => {
    setCustomScenario(value);
    onUpdate({ scenario: value });
  };

  const canProceed = customScenario.trim().length > 10;

  return (
    <div className="space-y-8">
      <div className="text-center">
        <h2 className="text-3xl font-bold text-white mb-4">Set Your Story Scenario</h2>
        <p className="text-white/80 text-lg">
          Choose elements to build your story's foundation, or write your own
        </p>
      </div>

      {/* Character Display */}
      <CharacterDisplay characters={storyData.characters} />

      {/* Scenario Builder */}
      <div className="space-y-6">
        {SCENARIO_PROMPTS.map((prompt) => (
          <div key={prompt.id} className="space-y-3">
            <h3 className="text-xl font-semibold text-white">{prompt.title}</h3>
            
            {/* Predefined Options */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {prompt.options.map((option) => (
                <button
                  key={option}
                  onClick={() => handleOptionSelect(prompt.id, option)}
                  className={`p-3 rounded-lg text-left transition-all duration-200 ${
                    selectedOptions[prompt.id] === option && !customInputs[prompt.id]
                      ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white'
                      : 'bg-white/10 border border-white/30 text-white hover:bg-white/20'
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
            
            {/* Custom Input */}
            <div className="mt-3">
              <input
                type="text"
                value={customInputs[prompt.id] ?? ''}
                onChange={(e) => handleCustomInput(prompt.id, e.target.value)}
                placeholder={`Or write your own ${prompt.title.toLowerCase().replace('?', '')}...`}
                className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              />
            </div>
          </div>
        ))}
      </div>

      {/* Generate Button */}
      {(Object.keys(selectedOptions).length > 0 || Object.values(customInputs).some(v => v.trim())) && (
        <div className="text-center">
          <button
            onClick={generateScenario}
            disabled={isGenerating}
            className="px-8 py-3 bg-gradient-to-r from-green-500 to-emerald-600 text-white rounded-xl hover:from-green-600 hover:to-emerald-700 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
          >
            {isGenerating ? '🤖 Creating Scenario...' : '✨ Generate Creative Scenario'}
          </button>
          <p className="text-white/60 text-sm mt-2">
            AI will create a unique scenario based on your choices
          </p>
        </div>
      )}

      {/* Custom Scenario Input */}
      <div className="space-y-3">
        <h3 className="text-xl font-semibold text-white">Your Scenario</h3>
        <textarea
          value={customScenario}
          onChange={(e) => handleCustomScenarioChange(e.target.value)}
          placeholder="Describe the starting situation of your story..."
          rows={4}
          className="w-full p-4 bg-white/10 border border-white/30 rounded-xl text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
        />
        <p className="text-white/60 text-sm">
          {customScenario.length} characters (minimum 10 required)
        </p>
      </div>

      {/* Navigation */}
      <div className="flex justify-between pt-6">
        <button
          onClick={onBack}
          className="px-8 py-3 rounded-xl font-semibold bg-white/20 text-white hover:bg-white/30 transition-colors"
        >
          ← Back
        </button>
        <button
          onClick={onNext}
          disabled={!canProceed}
          className={`px-8 py-3 rounded-xl font-semibold transition-all duration-200 ${
            canProceed
              ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white hover:from-purple-600 hover:to-pink-600'
              : 'bg-white/20 text-white/50 cursor-not-allowed'
          }`}
        >
          Continue →
        </button>
      </div>
    </div>
  );
}