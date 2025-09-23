'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
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
  const searchParams = useSearchParams();
  const { user } = useAuthStore();
  const [currentStep, setCurrentStep] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isSavingDraft, setIsSavingDraft] = useState(false);
  const [showCharacterQuickAdd, setShowCharacterQuickAdd] = useState(false);
  const [draftStoryId, setDraftStoryId] = useState<number | null>(null);
  const [isLoadingDraft, setIsLoadingDraft] = useState(true);
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

  // Load existing draft on component mount
  useEffect(() => {
    const loadDraft = async () => {
      try {
        // Check if we have a specific story ID to load
        const storyIdParam = searchParams.get('story_id');
        
        if (storyIdParam) {
          // Load specific story
          const storyId = parseInt(storyIdParam);
          const response = await apiClient.getStory(storyId);
          setDraftStoryId(response.id);
          setCurrentStep(response.creation_step || 0);
          
          // Restore story data from draft
          if (response.draft_data) {
            setStoryData(response.draft_data);
          } else {
            // Fallback to individual fields
            setStoryData({
              title: response.title || '',
              description: response.description || '',
              genre: response.genre || '',
              tone: response.tone || '',
              world_setting: response.world_setting || '',
              characters: [], // These would need to be loaded separately if needed
              plot_points: [],
              scenario: '',
            });
          }
        } else {
          // Load user's general draft
          const response = await apiClient.getDraftStory();
          if (response.draft) {
            const draft = response.draft;
            setDraftStoryId(draft.id);
            setCurrentStep(draft.creation_step);
            
            // Restore story data from draft
            if (draft.draft_data) {
              setStoryData(draft.draft_data);
            } else {
              // Fallback to individual fields
              setStoryData({
                title: draft.title || '',
                description: draft.description || '',
                genre: draft.genre || '',
                tone: draft.tone || '',
                world_setting: draft.world_setting || '',
                characters: [],
                plot_points: [],
                scenario: '',
              });
            }
          }
        }
      } catch (error) {
        console.error('Failed to load draft:', error);
      } finally {
        setIsLoadingDraft(false);
      }
    };

    if (user) {
      loadDraft();
    } else {
      setIsLoadingDraft(false);
    }
  }, [user, searchParams]);

  const saveDraft = async (step: number, data?: Partial<StoryData>) => {
    const updatedData = data ? { ...storyData, ...data } : storyData;
    
    try {
      setIsSavingDraft(true);
      const response = await apiClient.createOrUpdateDraftStory(updatedData, step);
      setDraftStoryId(response.id);
      console.log('Draft saved:', response.message);
    } catch (error) {
      console.error('Failed to save draft:', error);
    } finally {
      setIsSavingDraft(false);
    }
  };

  const handleNext = async () => {
    if (currentStep < STEPS.length - 1) {
      // Save progress before moving to next step
      await saveDraft(currentStep + 1);
      setCurrentStep(currentStep + 1);
    }
  };

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleCharacterAdd = async (character: any) => {
    const updatedCharacters = [...storyData.characters, character];
    const updatedData = { ...storyData, characters: updatedCharacters };
    setStoryData(updatedData);
    setShowCharacterQuickAdd(false);
    
    // Save draft with updated characters
    await saveDraft(currentStep, updatedData);
  };

  const handleStoryDataUpdate = async (data: Partial<StoryData>) => {
    const updatedData = { ...storyData, ...data };
    setStoryData(updatedData);
    
    // Auto-save after data updates (debounced to avoid too many requests)
    setTimeout(async () => {
      await saveDraft(currentStep, updatedData);
    }, 1000);
  };

  const handleCreateStory = async () => {
    setIsLoading(true);
    try {
      if (draftStoryId) {
        // Finalize the existing draft
        await apiClient.finalizeDraftStory(draftStoryId);
      } else {
        // Fallback: create story directly if no draft
        await apiClient.createStory({
          title: storyData.title,
          description: storyData.description,
          genre: storyData.genre,
          tone: storyData.tone,
          world_setting: storyData.world_setting,
        });
      }
      router.push('/dashboard');
    } catch (error) {
      console.error('Failed to create story:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteDraft = async () => {
    if (draftStoryId && confirm('Are you sure you want to delete this draft and start over?')) {
      try {
        await apiClient.deleteDraftStory(draftStoryId);
        setDraftStoryId(null);
        setCurrentStep(0);
        setStoryData({
          title: '',
          description: '',
          genre: '',
          tone: '',
          world_setting: '',
          characters: [],
          plot_points: [],
          scenario: '',
        });
      } catch (error) {
        console.error('Failed to delete draft:', error);
      }
    }
  };

  if (!user) {
    router.push('/login');
    return null;
  }

  if (isLoadingDraft) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900 flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-white/80">Loading your story draft...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900 pt-16">
      {/* Header */}
      <div className="bg-white/10 backdrop-blur-md border-b border-white/20">
        <div className="max-w-4xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-white">
                {draftStoryId ? 'Continue Your Story' : 'Create Your Story'}
              </h1>
              <div className="flex items-center space-x-4 mt-1">
                <span className="text-sm text-white/60">
                  Step {currentStep + 1} of {STEPS.length}
                </span>
                {isSavingDraft && (
                  <div className="flex items-center space-x-1 text-green-400 text-xs">
                    <div className="w-2 h-2 border border-green-400 border-t-transparent rounded-full animate-spin"></div>
                    <span>Saving...</span>
                  </div>
                )}
                {draftStoryId && !isSavingDraft && (
                  <span className="text-green-400 text-xs">✓ Draft Saved</span>
                )}
              </div>
            </div>
            <div className="flex items-center space-x-4">
              {draftStoryId && (
                <button
                  onClick={handleDeleteDraft}
                  className="px-3 py-1 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded text-xs border border-red-400/30"
                >
                  Start Over
                </button>
              )}
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