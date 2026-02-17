'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuthStore } from '@/store';
import { useUISettings } from '@/hooks/useUISettings';
import apiClient from '@/lib/api';
import CharacterQuickAdd from '@/components/CharacterQuickAdd';

// Step Components
import StoryModeSelection from '@/components/story-creation/StoryModeSelection';
import GenreSelection from '@/components/story-creation/GenreSelection';
import ScenarioSetup from '@/components/story-creation/ScenarioSetup';
import TitleInput from '@/components/story-creation/TitleInput';
import CharacterSetup from '@/components/story-creation/CharacterSetup';
import PlotDevelopment from '@/components/story-creation/PlotDevelopment';
import WorldSelection from '@/components/story-creation/WorldSelection';
import FinalReview from '@/components/story-creation/FinalReview';

export interface StoryData {
  story_mode: 'dynamic' | 'structured';
  world_id?: number;
  timeline_order?: number;
  title: string;
  description: string;
  genre: string;
  tone: string;
  world_setting: string;
  initial_premise?: string;
  characters: Array<{
    id?: number;
    name: string;
    role: string;
    description: string;
    gender?: string;
  }>;
  plot_points: string[];
  scenario: string;
}

const STEPS = [
  { id: 'mode', title: 'Story Mode', component: StoryModeSelection },
  { id: 'world', title: 'World', component: WorldSelection },
  { id: 'genre', title: 'Choose Genre', component: GenreSelection },
  { id: 'characters', title: 'Characters', component: CharacterSetup },
  { id: 'scenario', title: 'Set Scenario', component: ScenarioSetup },
  { id: 'title', title: 'Story Title', component: TitleInput },
  { id: 'plot', title: 'Plot Points', component: PlotDevelopment },
  { id: 'review', title: 'Review', component: FinalReview },
];

function CreateStoryContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuthStore();
  const [currentStep, setCurrentStep] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isSavingDraft, setIsSavingDraft] = useState(false);
  const [showCharacterQuickAdd, setShowCharacterQuickAdd] = useState(false);
  const [draftStoryId, setDraftStoryId] = useState<number | null>(null);
  const [isLoadingDraft, setIsLoadingDraft] = useState(true);
  const [userSettings, setUserSettings] = useState<any>(null);
  const [isClient, setIsClient] = useState(false);
  const [storyData, setStoryData] = useState<StoryData>({
    story_mode: 'dynamic', // Default to dynamic mode
    title: '',
    description: '',
    genre: '',
    tone: '',
    world_setting: '',
    initial_premise: '',
    characters: [],
    plot_points: [],
    scenario: '',
  });

  // Ensure we're on the client side before applying UI settings
  useEffect(() => {
    setIsClient(true);
  }, []);

  // Apply UI settings (theme, font size, etc.) only on client side
  useUISettings(isClient ? userSettings?.ui_preferences || null : null);

  // Load user settings
  useEffect(() => {
    const loadUserSettings = async () => {
      try {
        const settings = await apiClient.getUserSettings();
        setUserSettings(settings.settings);
      } catch (err) {
        console.error('Failed to load user settings:', err);
      }
    };
    
    if (user) {
      loadUserSettings();
    }
  }, [user]);

  // Load existing draft or brainstorm data on component mount
  useEffect(() => {
    const loadDraft = async () => {
      try {
        // Check if we have brainstorm session to load
        const brainstormSessionId = searchParams.get('brainstorm_session_id');
        
        if (brainstormSessionId) {
          // Load brainstorm data and pre-populate
          const elements = await apiClient.getBrainstormExtractedElements(parseInt(brainstormSessionId));
          
          if (elements) {
            // Process character mappings to get actual character IDs
            const characters = [];
            if (elements.characterMappings && Array.isArray(elements.characterMappings)) {
              for (const mapping of elements.characterMappings) {
                if (mapping.action === 'create' && mapping.newCharacterId) {
                  characters.push({
                    id: mapping.newCharacterId,
                    name: mapping.brainstormChar.name,
                    role: mapping.brainstormChar.role,
                    description: mapping.brainstormChar.description
                  });
                } else if (mapping.action === 'use_existing' && mapping.existingCharacterId) {
                  // Fetch the existing character details
                  try {
                    const char = await apiClient.getCharacter(mapping.existingCharacterId);
                    characters.push({
                      id: char.id,
                      name: char.name,
                      role: mapping.brainstormChar.role, // Use the role from brainstorm
                      description: char.description
                    });
                  } catch (error) {
                    console.error('Failed to load character:', error);
                  }
                }
                // Skip characters with action === 'skip'
              }
            } else if (elements.characters && Array.isArray(elements.characters)) {
              // Fallback: use characters as-is if no mappings (shouldn't happen with new flow)
              characters.push(...elements.characters);
            }
            
            setStoryData({
              story_mode: 'dynamic',
              genre: elements.genre || '',
              tone: elements.tone || '',
              characters: characters,
              scenario: elements.scenario || '',
              title: elements.suggested_titles?.[0] || '',
              description: elements.description || '',
              world_setting: elements.world_setting || '',
              initial_premise: elements.description || '',
              plot_points: elements.plot_points || [],
            });
            
            // Calculate first incomplete step
            let startStep = 6; // Default to review
            if (!elements.genre) startStep = 1;
            else if (characters.length === 0) startStep = 2;
            else if (!elements.scenario) startStep = 3;
            else if (!elements.suggested_titles || elements.suggested_titles.length === 0) startStep = 4;
            
            setCurrentStep(startStep);
          }
          setIsLoadingDraft(false);
          return;
        }
        
        // Check if we have a specific story ID to load
        const storyIdParam = searchParams.get('story_id');
        
        if (storyIdParam) {
          // Load specific story
          const storyId = parseInt(storyIdParam);
          const response = await apiClient.getSpecificDraftStory(storyId);
          const draft = (response as any).draft ?? response;
          
          setDraftStoryId(draft.id);
          setCurrentStep(draft.creation_step || 0);
          
            // Restore story data from draft
            if (draft.draft_data) {
              setStoryData(draft.draft_data);
            } else {
              // Fallback to individual fields
              setStoryData({
                story_mode: draft.story_mode || 'dynamic',
                title: draft.title || '',
                description: draft.description || '',
                genre: draft.genre || '',
                tone: draft.tone || '',
                world_setting: draft.world_setting || '',
                initial_premise: draft.initial_premise || '',
                characters: [], // These would need to be loaded separately if needed
                plot_points: [],
                scenario: draft.scenario || '',
              });
            }
        } else {
          // Load user's general draft
          const response = await apiClient.getDraftStory();
          const draft = (response as any).draft ?? response;
          if (draft) {
            setDraftStoryId(draft.id);
            setCurrentStep(draft.creation_step);
            
            // Restore story data from draft
            if (draft.draft_data) {
              setStoryData(draft.draft_data);
            } else {
              // Fallback to individual fields
              setStoryData({
                story_mode: draft.story_mode || 'dynamic',
                title: draft.title || '',
                description: draft.description || '',
                genre: draft.genre || '',
                tone: draft.tone || '',
                world_setting: draft.world_setting || '',
                initial_premise: draft.initial_premise || '',
                characters: [],
                plot_points: [],
                scenario: draft.scenario || '',
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
      const response = await apiClient.createOrUpdateDraftStory({
        ...updatedData,
        step,
        story_id: draftStoryId || undefined,
      });
      setDraftStoryId(response.id);
    } catch (error) {
      console.error('Failed to save draft:', error);
    } finally {
      setIsSavingDraft(false);
    }
  };

  const handleNext = async () => {
    if (currentStep < STEPS.length - 1) {
      let nextStep = currentStep + 1;
      
      // Skip plot step if in dynamic mode
      if (storyData.story_mode === 'dynamic' && STEPS[nextStep].id === 'plot') {
        nextStep++; // Skip to review
      }
      
      // Save progress before moving to next step
      await saveDraft(nextStep);
      setCurrentStep(nextStep);
    }
  };

  const handleBack = () => {
    if (currentStep > 0) {
      let prevStep = currentStep - 1;
      
      // Skip plot step if in dynamic mode when going back
      if (storyData.story_mode === 'dynamic' && STEPS[prevStep].id === 'plot') {
        prevStep--; // Skip back to title
      }
      
      setCurrentStep(prevStep);
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
      let finalizedStoryId: number;
      
      console.log('[CreateStory] Finalizing story, draftStoryId:', draftStoryId);
      
      if (draftStoryId) {
        // Finalize the existing draft
        console.log('[CreateStory] Calling finalizeDraftStory...');
        const response = await apiClient.finalizeDraftStory(draftStoryId);
        console.log('[CreateStory] Finalize response:', response);
        finalizedStoryId = response.id;
      } else {
        // Fallback: create story directly if no draft
        console.log('[CreateStory] No draft ID, creating story directly...');
        const response = await apiClient.createStory({
          title: storyData.title,
          description: storyData.description,
          genre: storyData.genre,
          tone: storyData.tone,
          world_setting: storyData.world_setting,
          world_id: storyData.world_id,
          timeline_order: storyData.timeline_order,
        });
        console.log('[CreateStory] Create response:', response);
        finalizedStoryId = response.id;
      }
      
      // Redirect to the story page with chapter setup flag
      // The story page will check if the first chapter needs setup and show the wizard
      console.log('[CreateStory] Redirecting to story page:', finalizedStoryId);
      router.push(`/story/${finalizedStoryId}?setup_chapter=true`);
    } catch (error) {
      console.error('[CreateStory] Failed to create story:', error);
      alert('Failed to create story. Please try again.');
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
          story_mode: 'dynamic',
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

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!user) {
      router.push('/login');
    }
  }, [user, router]);

  if (!user) {
    return null;
  }

  // Show loading state until we're on the client side
  if (!isClient || isLoadingDraft) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-white/80">
            {!isClient ? 'Loading...' : 'Loading your story draft...'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen theme-bg-primary pt-16">
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
                {currentStep <= 2 && !storyData.genre && (
                  <a
                    href="/brainstorm"
                    className="text-sm text-white/60 hover:text-white/80 flex items-center gap-1 transition-colors"
                  >
                    <span>Need help getting started?</span>
                    <span className="theme-accent-primary">Try AI Brainstorming</span>
                  </a>
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
                className="px-4 py-2 theme-btn-primary rounded-lg transition-colors text-sm font-medium"
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
          {storyData.characters && storyData.characters.length > 0 && (
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
            className="theme-accent-primary h-2 rounded-full transition-all duration-500"
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
                    ? 'theme-accent-primary text-white'
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
          {STEPS[currentStep].id === 'mode' && (
            <StoryModeSelection
              selected={storyData.story_mode}
              onSelect={(mode) => {
                handleStoryDataUpdate({ story_mode: mode });
                // Auto-advance to next step after selection
                setTimeout(() => handleNext(), 500);
              }}
            />
          )}
          {STEPS[currentStep].id === 'world' && (
            <WorldSelection
              storyData={storyData}
              onUpdate={handleStoryDataUpdate}
              onNext={handleNext}
              onBack={handleBack}
            />
          )}
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

export default function CreateStoryPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-white/80">Loading...</p>
        </div>
      </div>
    }>
      <CreateStoryContent />
    </Suspense>
  );
}