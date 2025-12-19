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

type BrainstormPhase = 'character_selection' | 'chat' | 'refining' | 'character_review';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

function BrainstormContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuthStore();
  
  const [phase, setPhase] = useState<BrainstormPhase>('character_selection');
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [extractedElements, setExtractedElements] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [isCreatingStory, setIsCreatingStory] = useState(false);
  const [userSettings, setUserSettings] = useState<any>(null);
  const [preSelectedCharacterIds, setPreSelectedCharacterIds] = useState<number[]>([]);

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
          // Load existing session - skip character selection
          const session = await apiClient.getBrainstormSession(parseInt(existingSessionId));
          setSessionId(session.session_id);
          // Cast messages to correct type
          setMessages((session.messages || []) as Message[]);
          if (session.extracted_elements) {
            setExtractedElements(session.extracted_elements);
            setPhase('refining');
          } else {
            setPhase('chat');
          }
        }
        // For new sessions, stay on character_selection phase (don't create session yet)
      } catch (error) {
        console.error('Failed to initialize session:', error);
        alert('Failed to start brainstorming session. Please try again.');
      }
    };

    if (user) {
      initializeSession();
    }
  }, [user, searchParams]);

  const handleSendMessage = async (message: string) => {
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
      const response = await apiClient.sendBrainstormMessage(sessionId, message);
      
      // Add AI response
      const aiMessage: Message = {
        role: 'assistant',
        content: response.ai_response,
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, aiMessage]);
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

  const handleProceedToCharacterReview = () => {
    // Move to character review phase if there are characters
    if (extractedElements?.characters && extractedElements.characters.length > 0) {
      setPhase('character_review');
    } else {
      // Skip character review if no characters
      handleStartStory();
    }
  };

  const handleCharacterReviewComplete = async (characterMappings: any[]) => {
    // Update extracted elements with character IDs
    const updatedElements = {
      ...extractedElements,
      characterMappings: characterMappings
    };
    setExtractedElements(updatedElements);
    
    // Save the character mappings to the session
    if (sessionId) {
      try {
        await apiClient.updateBrainstormElements(sessionId, updatedElements);
      } catch (error) {
        console.error('Failed to save character mappings:', error);
      }
    }
    
    // Proceed to story creation
    handleStartStory();
  };

  const handleStartStory = async () => {
    if (!sessionId || !extractedElements) return;

    setIsCreatingStory(true);
    
    try {
      console.log('[Brainstorm] Creating story from brainstorm data...');
      
      // Create the story (will be DRAFT initially)
      const storyResponse = await apiClient.createStory({
        title: extractedElements.suggested_titles?.[0] || 'Untitled Story',
        description: extractedElements.description || '',
        genre: extractedElements.genre || '',
        tone: extractedElements.tone || '',
        world_setting: extractedElements.world_setting || '',
        initial_premise: extractedElements.description || '',
      });
      
      console.log('[Brainstorm] Story created:', storyResponse);
      
      // Prepare character data for finalization
      // The finalize endpoint will handle linking characters to the story
      const characters = [];
      
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
        console.log('[Brainstorm] Added', preSelectedCharacterIds.length, 'pre-selected characters');
      }
      
      // Add AI-generated characters from character review
      if (extractedElements.characterMappings && Array.isArray(extractedElements.characterMappings)) {
        for (const mapping of extractedElements.characterMappings) {
          const characterId = mapping.action === 'create' 
            ? mapping.newCharacterId 
            : mapping.existingCharacterId;
          
          if (characterId) {
            characters.push({
              id: characterId,
              name: mapping.brainstormChar.name,
              role: mapping.brainstormChar.role,
              description: mapping.brainstormChar.description
            });
          }
        }
        console.log('[Brainstorm] Added', extractedElements.characterMappings.length, 'AI-generated characters');
      }
      
      // Update the draft with character data if any
      if (characters.length > 0) {
        await apiClient.createOrUpdateDraftStory({
          story_id: storyResponse.id,
          title: extractedElements.suggested_titles?.[0] || 'Untitled Story',
          characters: characters,
          step: 6
        });
        console.log('[Brainstorm] Updated draft with character data');
      }
      
      // Finalize the story to set it to ACTIVE and link characters
      await apiClient.finalizeDraftStory(storyResponse.id);
      console.log('[Brainstorm] Story finalized as ACTIVE');
      
      // Complete the brainstorm session
      await apiClient.completeBrainstormSession(sessionId, storyResponse.id);
      console.log('[Brainstorm] Session completed and linked to story');
      
      // Redirect to story page with chapter setup flag
      router.push(`/story/${storyResponse.id}?setup_chapter=true`);
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

  const handleCharacterSelectionComplete = async (selectedIds: number[]) => {
    try {
      setPreSelectedCharacterIds(selectedIds);
      
      // Create session with pre-selected characters (no LLM call yet)
      const newSession = await apiClient.createBrainstormSession(selectedIds);
      setSessionId(newSession.session_id);
      
      // Show a simple greeting without calling LLM
      // User will provide their story idea first
      const characterCount = selectedIds.length;
      const greetingMessage = characterCount > 0
        ? `Great! I see you've selected ${characterCount} character${characterCount !== 1 ? 's' : ''} to include in your story. Now, tell me about the story you want to create - what's the theme, genre, or concept you have in mind?`
        : "Hi! I'm excited to help you brainstorm your story. Tell me about the story you want to create - what's the theme, genre, or concept you have in mind?";
      
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
      {/* Header */}
      <div className="bg-white/10 backdrop-blur-md border-b border-white/20">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-2xl font-bold text-white">Story Brainstorming</h1>
              <p className="text-white/60 text-sm">
                Phase: <span className="text-white/80 capitalize">{phase}</span>
              </p>
            </div>
            <button
              onClick={() => router.push('/dashboard')}
              className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors"
            >
              ← Back to Dashboard
            </button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        {phase === 'character_selection' ? (
          <div className="bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 max-h-[calc(100vh-200px)] overflow-y-auto p-8">
            <CharacterSelection
              onContinue={handleCharacterSelectionComplete}
              onSkip={handleCharacterSelectionSkip}
            />
          </div>
        ) : phase === 'chat' ? (
          <div className="bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 h-[calc(100vh-200px)]">
            <BrainstormChat
              messages={messages}
              onSendMessage={handleSendMessage}
              onRefineIdeas={handleRefineIdeas}
              isLoading={isLoading || isExtracting}
            />
          </div>
        ) : phase === 'refining' ? (
          <div className="bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 max-h-[calc(100vh-200px)] overflow-y-auto">
            <RefinementWizard
              elements={extractedElements}
              onUpdate={handleUpdateElements}
              onStartStory={handleProceedToCharacterReview}
              onBackToChat={handleBackToChat}
              sessionId={sessionId}
              isCreatingStory={isCreatingStory}
            />
          </div>
        ) : (
          <div className="bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 max-h-[calc(100vh-200px)] overflow-y-auto p-8">
            <CharacterReview
              characters={extractedElements?.characters || []}
              preSelectedCharacterIds={preSelectedCharacterIds}
              onComplete={handleCharacterReviewComplete}
              onBack={handleBackToRefining}
            />
          </div>
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

