'use client';

import { useState } from 'react';
import { StoryData } from '@/app/create-story/page';
import apiClient from '@/lib/api';
import CharacterDisplay from '@/components/CharacterDisplay';

interface PlotDevelopmentProps {
  storyData: StoryData;
  onUpdate: (data: Partial<StoryData>) => void;
  onNext: () => void;
  onBack: () => void;
}

const PLOT_STRUCTURE = [
  {
    id: 'opening',
    title: 'Opening Hook',
    description: 'How does your story grab the reader\'s attention?',
    icon: '🎣',
    placeholder: 'The story begins when...'
  },
  {
    id: 'inciting_incident',
    title: 'Inciting Incident',
    description: 'What event sets the main plot in motion?',
    icon: '⚡',
    placeholder: 'Everything changes when...'
  },
  {
    id: 'rising_action',
    title: 'Rising Action',
    description: 'What obstacles and challenges will the protagonist face?',
    icon: '📈',
    placeholder: 'The protagonist must overcome...'
  },
  {
    id: 'climax',
    title: 'Climax',
    description: 'What is the story\'s most intense moment?',
    icon: '🔥',
    placeholder: 'At the peak of tension...'
  },
  {
    id: 'resolution',
    title: 'Resolution',
    description: 'How does everything wrap up?',
    icon: '🏁',
    placeholder: 'In the end...'
  }
];

export default function PlotDevelopment({ storyData, onUpdate, onNext, onBack }: PlotDevelopmentProps) {
  const [plotPoints, setPlotPoints] = useState<string[]>(storyData.plot_points || ['', '', '', '', '']);
  const [worldSetting, setWorldSetting] = useState(storyData.world_setting || '');
  const [isGeneratingComplete, setIsGeneratingComplete] = useState(false);
  const [generatingPointIndex, setGeneratingPointIndex] = useState<number | null>(null);

  const handlePlotPointChange = (index: number, value: string) => {
    const newPlotPoints = [...plotPoints];
    newPlotPoints[index] = value;
    setPlotPoints(newPlotPoints);
    onUpdate({ plot_points: newPlotPoints });
  };

  const handleWorldSettingChange = (value: string) => {
    setWorldSetting(value);
    onUpdate({ world_setting: value });
  };

  const generateCompletePlot = async () => {
    setIsGeneratingComplete(true);
    try {
      const response = await apiClient.generatePlot({
        genre: storyData.genre,
        tone: storyData.tone,
        scenario: storyData.scenario,
        characters: storyData.characters || [],
        world_setting: worldSetting,
        plot_type: 'complete'
      });


      if (response && response.plot_points) {
        setPlotPoints(response.plot_points);
        onUpdate({ plot_points: response.plot_points });
      } else {
        console.warn('No plot_points in response or response is invalid');
        console.warn('Response structure:', JSON.stringify(response, null, 2));
      }
    } catch (error) {
      console.error('=== PLOT GENERATION ERROR ===');
      console.error('Failed to generate complete plot:', error);
      if (error instanceof Error) {
        console.error('Error message:', error.message);
        console.error('Error stack:', error.stack);
      }
      if (typeof error === 'object' && error !== null) {
        console.error('Error details:', JSON.stringify(error, null, 2));
      }
      // Keep existing plot points on error
    } finally {
      setIsGeneratingComplete(false);
    }
  };

  const generateSinglePlotPoint = async (index: number) => {
    setGeneratingPointIndex(index);
    try {
      const response = await apiClient.generatePlot({
        genre: storyData.genre,
        tone: storyData.tone,
        scenario: storyData.scenario,
        characters: storyData.characters || [],
        world_setting: worldSetting,
        plot_type: 'single_point',
        plot_point_index: index
      });


      if (response && response.plot_point) {
        handlePlotPointChange(index, response.plot_point);
      } else {
        console.warn(`No plot_point in response for index ${index}`);
      }
    } catch (error) {
      console.error(`=== PLOT POINT GENERATION ERROR (index ${index}) ===`);
      console.error('Failed to generate plot point:', error);
      if (error instanceof Error) {
        console.error('Error message:', error.message);
      }
      // Fallback to old suggestion system
      generatePlotSuggestion(index);
    } finally {
      setGeneratingPointIndex(null);
    }
  };

  const generatePlotSuggestion = (index: number) => {
    const suggestions: Record<number, string[]> = {
      0: [
        'A mysterious message arrives at dawn',
        'An ordinary day takes an extraordinary turn',
        'A long-lost friend returns unexpectedly',
        'A strange discovery changes everything'
      ],
      1: [
        'A shocking revelation is made',
        'An unexpected betrayal occurs',
        'A dangerous enemy emerges',
        'A critical choice must be made'
      ],
      2: [
        'Obstacles mount as allies are tested',
        'The stakes rise with each challenge',
        'Hidden truths begin to surface',
        'Powers grow stronger through struggle'
      ],
      3: [
        'All forces converge in a final confrontation',
        'The ultimate truth is revealed',
        'Everything the protagonist believes is challenged',
        'The fate of all hangs in the balance'
      ],
      4: [
        'A new equilibrium is established',
        'Lessons learned shape a better future',
        'Relationships are forever changed',
        'The journey comes full circle'
      ]
    };

    const options = suggestions[index] || [];
    const suggestion = options[Math.floor(Math.random() * options.length)];
    handlePlotPointChange(index, suggestion);
  };

  const filledPlotPoints = plotPoints.filter(point => point.trim().length > 0).length;
  const canProceed = filledPlotPoints >= 3; // At least 3 plot points required

  return (
    <div className="space-y-4 sm:space-y-8">
      <div className="text-center">
        <h2 className="text-xl sm:text-3xl font-bold text-white mb-2 sm:mb-4">Develop Your Plot</h2>
        <p className="text-white/80 text-sm sm:text-lg mb-3 sm:mb-6">
          Create a compelling story arc tailored to your characters and scenario
        </p>
      </div>

      {/* Character Display */}
      <CharacterDisplay characters={storyData.characters} />
        
      {/* AI Plot Generation */}
      <div className="bg-white/10 rounded-xl p-4 sm:p-6">
        <h3 className="text-base sm:text-xl font-semibold text-white mb-2 sm:mb-3">AI-Powered Plot Generation</h3>
        <p className="text-white/70 text-sm sm:text-base mb-3 sm:mb-4">
          Let AI create a complete plot structure based on your characters and scenario
        </p>
        <button
          onClick={generateCompletePlot}
          disabled={isGeneratingComplete || !storyData.scenario}
          className="px-5 sm:px-8 py-2.5 sm:py-3 theme-btn-primary rounded-xl transition-colors font-semibold text-sm sm:text-base disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isGeneratingComplete ? (
            <>
              <span className="animate-spin inline-block mr-2">⚡</span>
              Generating Character-Driven Plot...
            </>
          ) : (
            '🎭 Generate Complete Plot'
          )}
        </button>
        {!storyData.scenario && (
          <p className="text-yellow-300 text-sm mt-2">
            Complete the scenario step first for better plot generation
          </p>
        )}
      </div>

      {/* Plot Structure */}
      <div className="space-y-4 sm:space-y-6">
        {PLOT_STRUCTURE.map((element, index) => (
          <div key={element.id} className="bg-white/10 border border-white/30 rounded-xl p-4 sm:p-6">
            <div className="flex items-center mb-3 sm:mb-4">
              <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-full flex items-center justify-center text-white text-base sm:text-xl mr-3 sm:mr-4"
                   style={{ background: 'linear-gradient(to right, var(--color-accentPrimary), var(--color-accentSecondary))' } as React.CSSProperties}>
                {element.icon}
              </div>
              <div>
                <h3 className="text-base sm:text-xl font-semibold text-white">{element.title}</h3>
                <p className="text-white/70 text-sm">{element.description}</p>
              </div>
            </div>
            
            <div className="space-y-3">
              <textarea
                value={plotPoints[index] ?? ''}
                onChange={(e) => handlePlotPointChange(index, e.target.value)}
                placeholder={element.placeholder}
                rows={3}
                className="w-full p-4 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none theme-focus-ring"
              />
              <div className="flex gap-2">
                <button
                  onClick={() => generateSinglePlotPoint(index)}
                  disabled={generatingPointIndex === index}
                  className="px-4 py-2 bg-gradient-to-r from-blue-500 to-cyan-500 text-white rounded-lg hover:from-blue-600 hover:to-cyan-600 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {generatingPointIndex === index ? (
                    <>
                      <span className="animate-spin inline-block mr-1">⚡</span>
                      Generating...
                    </>
                  ) : (
                    '✨ AI Generate'
                  )}
                </button>
                <button
                  onClick={() => generatePlotSuggestion(index)}
                  className="px-3 py-2 bg-white/20 border border-white/30 text-white rounded-lg text-sm hover:bg-white/30 transition-colors"
                >
                  🎲 Random
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* World Setting */}
      <div className="bg-white/10 border border-white/30 rounded-xl p-4 sm:p-6">
        <h3 className="text-base sm:text-xl font-semibold text-white mb-3 sm:mb-4">World Setting</h3>
        <p className="text-white/70 text-sm sm:text-base mb-3 sm:mb-4">
          Describe the world where your story takes place
        </p>
        <textarea
          value={worldSetting}
          onChange={(e) => handleWorldSettingChange(e.target.value)}
          placeholder="Describe the world, time period, culture, rules, and atmosphere..."
          rows={4}
          className="w-full p-4 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
        />
      </div>

      {/* Progress Indicator */}
      <div className="bg-white/5 rounded-xl p-4 text-center">
        <p className="text-white/80 mb-2">Plot Development Progress</p>
        <div className="flex justify-center space-x-2">
          {PLOT_STRUCTURE.map((_, index) => (
            <div
              key={index}
              className={`w-3 h-3 rounded-full ${
                plotPoints[index]?.trim() ? 'theme-btn-primary' : 'bg-white/30'
              }`}
            />
          ))}
        </div>
        <p className="text-white/60 text-sm mt-2">
          {filledPlotPoints} of {PLOT_STRUCTURE.length} plot points completed
        </p>
      </div>

      {/* Navigation */}
      <div className="flex justify-between pt-4 sm:pt-6">
        <button
          onClick={onBack}
          className="px-5 sm:px-8 py-2.5 sm:py-3 rounded-xl font-semibold bg-white/20 text-white hover:bg-white/30 transition-colors"
        >
          ← Back
        </button>
        <button
          onClick={onNext}
          disabled={!canProceed}
          className={`px-5 sm:px-8 py-2.5 sm:py-3 rounded-xl font-semibold transition-all duration-200 ${
            canProceed
              ? 'theme-btn-primary'
              : 'bg-white/20 text-white/50 cursor-not-allowed'
          }`}
        >
          Continue →
        </button>
      </div>
    </div>
  );
}