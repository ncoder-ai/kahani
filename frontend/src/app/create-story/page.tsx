'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store';
import apiClient from '@/lib/api';
import CharacterQuickAdd from '@/components/CharacterQuickAdd';

// Step Components
import GenreSelection from '@/components/story-creation/GenreSelection';
import ScenarioSetup from '@/components/story-creation/ScenarioSetup';
import TitleInput from '@/components/story-creation/TitleInput';
import CharacterSetup from '@/components/story-creation/CharacterSetup';
import PlotDevelopment from '@/components/story-creation/PlotDevelopment';
import FinalReview from '@/components/story-creation/FinalReview';

export interface StoryData {
  title: string;
  description: string;
  genre: string;
  tone: string;
  world_setting: string;
  characters: Array<{
    name: string;
    role: string;
    description: string;
  }>;
  plot_points: string[];
  scenario: string;
}

const STEPS = [
  { id: 'genre', title: 'Choose Genre', component: GenreSelection },
  { id: 'characters', title: 'Characters', component: CharacterSetup },
  { id: 'scenario', title: 'Set Scenario', component: ScenarioSetup },
  { id: 'title', title: 'Story Title', component: TitleInput },
  { id: 'plot', title: 'Plot Points', component: PlotDevelopment },
  { id: 'review', title: 'Review', component: FinalReview },
];

export default function CreateStoryPage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const [currentStep, setCurrentStep] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [showCharacterQuickAdd, setShowCharacterQuickAdd] = useState(false);
  const [storyData, setStoryData] = useState<StoryData>({
    title: '',
    description: '',
    genre: '',
    tone: '',
    world_setting: '',
    characters: [],
    plot_points: [],
    scenario: '',
  });

  const handleNext = () => {
    if (currentStep < STEPS.length - 1) {
      setCurrentStep(currentStep + 1);
    }
  };

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleCharacterAdd = (character: any) => {
    const updatedCharacters = [...storyData.characters, character];
    setStoryData(prev => ({ ...prev, characters: updatedCharacters }));
    setShowCharacterQuickAdd(false);
  };

  const handleStoryDataUpdate = (data: Partial<StoryData>) => {
    setStoryData(prev => ({ ...prev, ...data }));
  };

  const handleCreateStory = async () => {
    setIsLoading(true);
    try {
      await apiClient.createStory({
        title: storyData.title,
        description: storyData.description,
        genre: storyData.genre,
        tone: storyData.tone,
        world_setting: storyData.world_setting,
      });
      router.push('/dashboard');
    } catch (error) {
      console.error('Failed to create story:', error);
    } finally {
      setIsLoading(false);
    }
  };

  if (!user) {
    router.push('/login');
    return null;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900 pt-16">
      {/* Header */}
      <div className="bg-white/10 backdrop-blur-md border-b border-white/20">
        <div className="max-w-4xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold text-white">Create Your Story</h1>
            <div className="flex items-center space-x-4">
              <button
                onClick={() => setShowCharacterQuickAdd(true)}
                className="px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white rounded-lg transition-colors text-sm font-medium"
              >
                + Add Character
              </button>
              <button
                onClick={() => router.push('/characters')}
                className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-colors text-sm font-medium border border-white/30"
              >
                📚 Manage Characters
              </button>
              <div className="text-white/80">
                Step {currentStep + 1} of {STEPS.length}
              </div>
            </div>
          </div>
          
          {/* Character Count Display */}
          {storyData.characters.length > 0 && (
            <div className="mt-3 flex items-center justify-center">
              <div className="bg-white/10 rounded-full px-4 py-2 text-white/80 text-sm">
                {storyData.characters.length} character{storyData.characters.length !== 1 ? 's' : ''} added: {' '}
                {storyData.characters.map(char => char.name).join(', ')}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Progress Bar */}
      <div className="max-w-4xl mx-auto px-6 py-6">
        <div className="bg-white/10 rounded-full h-2 mb-8">
          <div
            className="bg-gradient-to-r from-purple-400 to-pink-400 h-2 rounded-full transition-all duration-500"
            style={{ width: `${((currentStep + 1) / STEPS.length) * 100}%` }}
          />
        </div>

        {/* Step Indicators */}
        <div className="flex justify-between mb-12">
          {STEPS.map((step, index) => (
            <div
              key={step.id}
              className={`flex flex-col items-center ${
                index <= currentStep ? 'text-white' : 'text-white/40'
              }`}
            >
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium mb-2 ${
                  index <= currentStep
                    ? 'bg-gradient-to-r from-purple-400 to-pink-400 text-white'
                    : 'bg-white/20 text-white/60'
                }`}
              >
                {index + 1}
              </div>
              <span className="text-xs font-medium">{step.title}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-4xl mx-auto px-6 pb-12">
        <div className="bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 p-8">
          {STEPS[currentStep].id === 'genre' && (
            <GenreSelection
              storyData={storyData}
              onUpdate={handleStoryDataUpdate}
              onNext={handleNext}
              isFirstStep={currentStep === 0}
            />
          )}
          {STEPS[currentStep].id === 'characters' && (
            <CharacterSetup
              storyData={storyData}
              onUpdate={handleStoryDataUpdate}
              onNext={handleNext}
              onBack={handleBack}
            />
          )}
          {STEPS[currentStep].id === 'scenario' && (
            <ScenarioSetup
              storyData={storyData}
              onUpdate={handleStoryDataUpdate}
              onNext={handleNext}
              onBack={handleBack}
            />
          )}
          {STEPS[currentStep].id === 'title' && (
            <TitleInput
              storyData={storyData}
              onUpdate={handleStoryDataUpdate}
              onNext={handleNext}
              onBack={handleBack}
            />
          )}
          {STEPS[currentStep].id === 'plot' && (
            <PlotDevelopment
              storyData={storyData}
              onUpdate={handleStoryDataUpdate}
              onNext={handleNext}
              onBack={handleBack}
            />
          )}
          {STEPS[currentStep].id === 'review' && (
            <FinalReview
              storyData={storyData}
              onUpdate={handleStoryDataUpdate}
              onFinish={handleCreateStory}
              onBack={handleBack}
              isLoading={isLoading}
            />
          )}
        </div>
      </div>

      {/* Character Quick Add Modal */}
      {showCharacterQuickAdd && (
        <CharacterQuickAdd
          onCharacterAdd={handleCharacterAdd}
          onClose={() => setShowCharacterQuickAdd(false)}
          existingCharacters={storyData.characters}
        />
      )}
    </div>
  );
}