'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuthStore } from '@/store';
import { useUISettings } from '@/hooks/useUISettings';
import apiClient from '@/lib/api';
import RouteProtection from '@/components/RouteProtection';
import BrainstormChat from '@/components/brainstorm/BrainstormChat';
import RefinementWizard from '@/components/brainstorm/RefinementWizard';
import CharacterReview from '@/components/brainstorm/CharacterReview';
import CharacterSelection from '@/components/brainstorm/CharacterSelection';
import ContentRatingSelection from '@/components/brainstorm/ContentRatingSelection';
import StoryArcEditor from '@/components/brainstorm/StoryArcEditor';
import { StoryArc } from '@/lib/api';

type BrainstormPhase = 'content_rating' | 'character_selection' | 'chat' | 'refining' | 'character_review' | 'arc_generation';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

function formatTimeAgo(date: Date): string {
  const seconds = Math.floor((new Date().getTime() - date.getTime()) / 1000);
  
  if (seconds < 60) return 'just now';
  if (seconds < 120) return '1 min ago';
  if (seconds < 3600) return `${Math.floor(seconds / 60)} mins ago`;
  if (seconds < 7200) return '1 hour ago';
  return `${Math.floor(seconds / 3600)} hours ago`;
}

function BrainstormContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuthStore();
  
  const [phase, setPhase] = useState<BrainstormPhase>('content_rating');
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [extractedElements, setExtractedElements] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [isCreatingStory, setIsCreatingStory] = useState(false);
  const [userSettings, setUserSettings] = useState<any>(null);
  const [preSelectedCharacterIds, setPreSelectedCharacterIds] = useState<number[]>([]);
  const [storyArc, setStoryArc] = useState<StoryArc | null>(null);
  const [isGeneratingArc, setIsGeneratingArc] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [contentRating, setContentRating] = useState<'sfw' | 'nsfw'>('sfw');

  // Apply UI settings
  useUISettings(userSettings?.ui_preferences || null);

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

  // Initialize or load session
  useEffect(() => {
    const initializeSession = async () => {
      try {
        // Check if we have a session ID in URL
        const existingSessionId = searchParams.get('session_id');
        
        if (existingSessionId) {
          // Load existing session - skip content rating and character selection
          const session = await apiClient.getBrainstormSession(parseInt(existingSessionId));
          setSessionId(session.session_id);
          // Cast messages to correct type
          setMessages((session.messages || []) as Message[]);
          // Load content rating from session if available
          if (session.extracted_elements?.content_rating) {
            setContentRating(session.extracted_elements.content_rating);
          }
          if (session.extracted_elements) {
            setExtractedElements(session.extracted_elements);
            setPhase('refining');
          } else {
            setPhase('chat');
          }
        }
        // For new sessions, stay on content_rating phase (don't create session yet)
      } catch (error) {
        console.error('Failed to initialize session:', error);
        alert('Failed to start brainstorming session. Please try again.');
      }
    };

    if (user) {
      initializeSession();
    }
  }, [user, searchParams]);

  const handleSendMessage = async (message: string, generateIdeas: boolean = false) => {
    if (!sessionId) return;

    // Add user message immediately
    const userMessage: Message = {
      role: 'user',
      content: message,
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMessage]);

    try {
      setIsLoading(true);
      const response = await apiClient.sendBrainstormMessage(sessionId, message, generateIdeas);
      
      // Add AI response
      const aiMessage: Message = {
        role: 'assistant',
        content: response.ai_response,
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, aiMessage]);
      
      // Update last saved timestamp (messages are saved on the backend)
      setLastSavedAt(new Date());
    } catch (error) {
      console.error('Failed to send message:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  const handleRefineIdeas = async () => {
    if (!sessionId) return;

    try {
      setIsExtracting(true);
      const result = await apiClient.extractBrainstormElements(sessionId);
      setExtractedElements(result.elements);
      setPhase('refining');
    } catch (error) {
      console.error('Failed to extract elements:', error);
      alert('Failed to extract story elements. Please try again or continue chatting to add more details.');
    } finally {
      setIsExtracting(false);
    }
  };

  const handleUpdateElements = async (updatedElements: any) => {
    if (!sessionId) return;

    try {
      await apiClient.updateBrainstormElements(sessionId, updatedElements);
      setExtractedElements(updatedElements);
    } catch (error) {
      console.error('Failed to update elements:', error);
      alert('Failed to save changes. Please try again.');
    }
  };

  const handleProceedToCharacterReview = (selectedTitle?: string) => {
    // Store selected title in extracted elements
    if (selectedTitle && extractedElements) {
      setExtractedElements({
        ...extractedElements,
        selectedTitle
      });
    }
    
    // Move to character review phase if there are characters
    if (extractedElements?.characters && extractedElements.characters.length > 0) {
      setPhase('character_review');
    } else {
      // Skip character review, go to arc generation
      handleProceedToArcGeneration(extractedElements);
    }
  };

  const handleProceedToArcGeneration = (elements?: any) => {
    const elementsToUse = elements || extractedElements;
    setExtractedElements(elementsToUse);
    setPhase('arc_generation');
  };

  const handleGenerateArc = async (structureType: string) => {
    if (!sessionId) {
      console.error('[Brainstorm] No session ID available for arc generation');
      return;
    }
    
    setIsGeneratingArc(true);
    
    try {
      console.log('[Brainstorm] Generating arc with structure type:', structureType);
      const result = await apiClient.generateArcFromSession(sessionId, structureType);
      
      console.log('[Brainstorm] Arc generated:', result.arc);
      setStoryArc(result.arc);
      
      // Also update extracted elements with the arc
      const updatedElements = {
        ...extractedElements,
        story_arc: result.arc
      };
      setExtractedElements(updatedElements);
      
    } catch (error) {
      console.error('[Brainstorm] Failed to generate arc:', error);
      alert('Failed to generate story arc. Please try again.');
    } finally {
      setIsGeneratingArc(false);
    }
  };

  const handleArcConfirm = () => {
    // Proceed to create the story with arc preferences
    handleStartStory(extractedElements, extractedElements?.selectedTitle);
  };

  const handleArcChange = (arc: StoryArc) => {
    setStoryArc(arc);
  };

  const handleCharacterReviewComplete = async (characterMappings: any[]) => {
    console.log('[Brainstorm] Character review completed with mappings:', characterMappings);
    
    // Update extracted elements with character IDs
    const updatedElements = {
      ...extractedElements,
      characterMappings: characterMappings
    };
    
    console.log('[Brainstorm] Updated elements with character mappings:', updatedElements);
    setExtractedElements(updatedElements);
    
    // Save the character mappings to the session
    if (sessionId) {
      try {
        await apiClient.updateBrainstormElements(sessionId, updatedElements);
        console.log('[Brainstorm] Saved character mappings to session');
      } catch (error) {
        console.error('Failed to save character mappings:', error);
      }
    }
    
    // CRITICAL: Pass updatedElements directly to avoid stale state issue
    // React state updates are asynchronous, so we can't rely on extractedElements being updated
    // Move to arc generation phase instead of directly creating story
    handleProceedToArcGeneration(updatedElements);
  };

  const handleStartStory = async (elementsToUse?: any, selectedTitle?: string) => {
    // Use passed elements or fall back to state (for direct calls)
    const elements = elementsToUse || extractedElements;
    
    if (!sessionId || !elements) return;

    setIsCreatingStory(true);
    
    try {
      console.log('[Brainstorm] Creating story from brainstorm data...');
      console.log('[Brainstorm] Using elements:', elements);
      console.log('[Brainstorm] Selected title:', selectedTitle);
      
      // Use selected title, or fall back to first suggested title, or 'Untitled Story'
      const finalTitle = selectedTitle || elements.selectedTitle || elements.suggested_titles?.[0] || 'Untitled Story';
      
      // Create the story (will be DRAFT initially)
      const storyResponse = await apiClient.createStory({
        title: finalTitle,
        description: elements.description || '',
        genre: elements.genre || '',
        tone: elements.tone || '',
        world_setting: elements.world_setting || '',
        initial_premise: elements.description || '',
        content_rating: contentRating, // Pass the content rating selected at the start
      });
      
      console.log('[Brainstorm] Story created:', storyResponse);
      
      // Prepare character data for finalization
      // The finalize endpoint will handle linking characters to the story
      const characters = [];
      
      console.log('[Brainstorm] Pre-selected character IDs:', preSelectedCharacterIds);
      console.log('[Brainstorm] Character mappings:', elements.characterMappings);
      
      // Add pre-selected characters first
      if (preSelectedCharacterIds && preSelectedCharacterIds.length > 0) {
        for (const charId of preSelectedCharacterIds) {
          characters.push({
            id: charId,
            name: '', // Will be populated by backend
            role: 'existing',
            description: ''
          });
        }
        console.log('[Brainstorm] Added', preSelectedCharacterIds.length, 'pre-selected characters:', characters);
      }
      
      // Add AI-generated characters from character review
      if (elements.characterMappings && Array.isArray(elements.characterMappings)) {
        for (const mapping of elements.characterMappings) {
          const characterId = mapping.action === 'create' 
            ? mapping.newCharacterId 
            : mapping.existingCharacterId;
          
          console.log('[Brainstorm] Processing mapping:', { 
            name: mapping.brainstormChar.name, 
            action: mapping.action, 
            characterId 
          });
          
          if (characterId) {
            characters.push({
              id: characterId,
              name: mapping.brainstormChar.name,
              role: mapping.brainstormChar.role,
              description: mapping.brainstormChar.description
            });
          } else {
            console.warn('[Brainstorm] Skipping character - no ID:', mapping.brainstormChar.name);
          }
        }
        console.log('[Brainstorm] After processing mappings, total characters:', characters.length);
      }
      
      console.log('[Brainstorm] Final character list to save:', characters);
      
      // Update the draft with character data if any
      if (characters.length > 0) {
        await apiClient.createOrUpdateDraftStory({
          story_id: storyResponse.id,
          title: finalTitle,
          characters: characters,
          step: 6
        });
        console.log('[Brainstorm] Updated draft with', characters.length, 'characters');
      }
      
      // Finalize the story to set it to ACTIVE and link characters
      await apiClient.finalizeDraftStory(storyResponse.id);
      console.log('[Brainstorm] Story finalized as ACTIVE');
      
      // Save the story arc if we have one from brainstorm
      if (storyArc && storyArc.phases && storyArc.phases.length > 0) {
        try {
          console.log('[Brainstorm] Saving story arc with', storyArc.phases.length, 'phases');
          await apiClient.updateStoryArc(storyResponse.id, storyArc);
          console.log('[Brainstorm] Story arc saved');
        } catch (arcError) {
          console.error('[Brainstorm] Failed to save arc (non-fatal):', arcError);
          // Continue anyway - arc is optional
        }
      }
      
      // Complete the brainstorm session
      await apiClient.completeBrainstormSession(sessionId, storyResponse.id);
      console.log('[Brainstorm] Session completed and linked to story');
      
      // Redirect to story page with chapter setup flag and optional scenario
      const queryParams = new URLSearchParams({ setup_chapter: 'true' });
      if (elements.useScenarioForChapter && elements.scenario) {
        queryParams.set('brainstorm_scenario', encodeURIComponent(elements.scenario));
      }
      router.push(`/story/${storyResponse.id}?${queryParams.toString()}`);
    } catch (error) {
      console.error('[Brainstorm] Failed to create story:', error);
      alert('Failed to create story. Please try again.');
      setIsCreatingStory(false);
    }
  };

  const handleBackToChat = () => {
    setPhase('chat');
  };

  const handleBackToRefining = () => {
    setPhase('refining');
  };

  const handleContentRatingComplete = (rating: 'sfw' | 'nsfw') => {
    setContentRating(rating);
    setPhase('character_selection');
  };

  const handleCharacterSelectionComplete = async (selectedIds: number[]) => {
    try {
      setPreSelectedCharacterIds(selectedIds);
      
      // Create session with pre-selected characters and content rating (no LLM call yet)
      const newSession = await apiClient.createBrainstormSession(selectedIds, contentRating);
      setSessionId(newSession.session_id);
      
      // Show a simple greeting without calling LLM
      // User will provide their story idea first
      const characterCount = selectedIds.length;
      const ratingNote = contentRating === 'sfw' 
        ? " I'll keep the content family-friendly."
        : " Since you've chosen mature content, I can explore darker themes freely.";
      const greetingMessage = characterCount > 0
        ? `Great! I see you've selected ${characterCount} character${characterCount !== 1 ? 's' : ''} to include in your story.${ratingNote} Now, tell me about the story you want to create - what's the theme, genre, or concept you have in mind?`
        : `Hi! I'm excited to help you brainstorm your story.${ratingNote} Tell me about the story you want to create - what's the theme, genre, or concept you have in mind?`;
      
      setMessages([
        {
          role: 'assistant',
          content: greetingMessage,
          timestamp: new Date().toISOString()
        }
      ]);
      
      setPhase('chat');
    } catch (error) {
      console.error('Failed to start session with characters:', error);
      alert('Failed to start brainstorming session. Please try again.');
    }
  };

  const handleCharacterSelectionSkip = async () => {
    try {
      // Create session without pre-selected characters (no LLM call yet)
      const newSession = await apiClient.createBrainstormSession();
      setSessionId(newSession.session_id);
      
      // Show a simple greeting without calling LLM
      // User will provide their story idea first
      setMessages([
        {
          role: 'assistant',
          content: "Hi! I'm excited to help you brainstorm your story. Tell me about the story you want to create - what's the theme, genre, or concept you have in mind?",
          timestamp: new Date().toISOString()
        }
      ]);
      
      setPhase('chat');
    } catch (error) {
      console.error('Failed to start session:', error);
      alert('Failed to start brainstorming session. Please try again.');
    }
  };

  if (!user) {
    return null;
  }

  return (
    <div className="min-h-screen theme-bg-primary pt-16">
      {/* Header - Hidden on mobile (persistent banner shows context), compact on desktop */}
      <div className="hidden md:block bg-white/10 backdrop-blur-md border-b border-white/20">
        <div className="max-w-7xl mx-auto px-6 py-2">
          <div className="flex justify-between items-center">
            <div className="min-w-0 flex-1">
              <h1 className="text-xl font-bold text-white truncate">Story Brainstorming</h1>
              <div className="flex items-center gap-3 text-xs">
                <span className="text-white/60">
                  Phase: <span className="text-white/80 capitalize">{phase.replace('_', ' ')}</span>
                </span>
                {/* Save indicator */}
                {sessionId && (
                  <span className="flex items-center gap-1">
                    {isSaving ? (
                      <>
                        <svg className="animate-spin h-3 w-3 text-purple-400" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        <span className="text-purple-400">Saving...</span>
                      </>
                    ) : lastSavedAt ? (
                      <>
                        <svg className="h-3 w-3 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                        <span className="text-green-400/80">
                          Saved {formatTimeAgo(lastSavedAt)}
                        </span>
                      </>
                    ) : (
                      <span className="text-white/40">Auto-save enabled</span>
                    )}
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={() => router.push('/dashboard')}
              className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors text-sm flex-shrink-0 ml-2"
            >
              ← Back to Dashboard
            </button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-2 md:px-6 py-2 md:py-4">
        {phase === 'character_selection' ? (
          <div className="bg-white/10 backdrop-blur-md rounded-lg md:rounded-2xl border border-white/20 max-h-[calc(100vh-80px)] md:max-h-[calc(100vh-180px)] overflow-y-auto p-4 md:p-8">
            <CharacterSelection
              onContinue={handleCharacterSelectionComplete}
              onSkip={handleCharacterSelectionSkip}
            />
          </div>
        ) : phase === 'content_rating' ? (
          <div className="bg-white/10 backdrop-blur-md rounded-lg md:rounded-2xl border border-white/20 p-6 md:p-8">
            <ContentRatingSelection
              onContinue={handleContentRatingComplete}
            />
          </div>
        ) : phase === 'chat' ? (
          <div className="bg-white/10 backdrop-blur-md rounded-lg md:rounded-2xl border border-white/20 h-[calc(100vh-80px)] md:h-[calc(100vh-180px)]">
            <BrainstormChat
              messages={messages}
              onSendMessage={handleSendMessage}
              onRefineIdeas={handleRefineIdeas}
              isLoading={isLoading || isExtracting}
            />
          </div>
        ) : phase === 'refining' ? (
          <div className="bg-white/10 backdrop-blur-md rounded-lg md:rounded-2xl border border-white/20 max-h-[calc(100vh-80px)] md:max-h-[calc(100vh-180px)] overflow-y-auto">
            <RefinementWizard
              elements={extractedElements}
              onUpdate={handleUpdateElements}
              onStartStory={handleProceedToCharacterReview}
              onBackToChat={handleBackToChat}
              sessionId={sessionId}
              isCreatingStory={isCreatingStory}
            />
          </div>
        ) : phase === 'character_review' ? (
          <div className="bg-white/10 backdrop-blur-md rounded-lg md:rounded-2xl border border-white/20 max-h-[calc(100vh-80px)] md:max-h-[calc(100vh-180px)] overflow-y-auto p-4 md:p-8">
            <CharacterReview
              characters={extractedElements?.characters || []}
              preSelectedCharacterIds={preSelectedCharacterIds}
              onComplete={handleCharacterReviewComplete}
              onBack={handleBackToRefining}
            />
          </div>
        ) : (
          <StoryArcEditor
            arc={storyArc}
            onArcChange={handleArcChange}
            onGenerate={handleGenerateArc}
            onConfirm={handleArcConfirm}
            isGenerating={isGeneratingArc || isCreatingStory}
            storyTitle={extractedElements?.selectedTitle || extractedElements?.suggested_titles?.[0]}
          />
        )}
      </div>
    </div>
  );
}

export default function BrainstormPage() {
  return (
    <RouteProtection requireAuth={true} requireApproval={true}>
      <BrainstormContent />
    </RouteProtection>
  );
}

