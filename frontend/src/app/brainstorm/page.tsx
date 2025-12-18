'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuthStore } from '@/store';
import { useUISettings } from '@/hooks/useUISettings';
import apiClient from '@/lib/api';
import RouteProtection from '@/components/RouteProtection';
import BrainstormChat from '@/components/brainstorm/BrainstormChat';
import RefinementWizard from '@/components/brainstorm/RefinementWizard';

type BrainstormPhase = 'chat' | 'refining';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

function BrainstormContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuthStore();
  
  const [phase, setPhase] = useState<BrainstormPhase>('chat');
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [extractedElements, setExtractedElements] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [isCreatingStory, setIsCreatingStory] = useState(false);
  const [userSettings, setUserSettings] = useState<any>(null);

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
          // Load existing session
          const session = await apiClient.getBrainstormSession(parseInt(existingSessionId));
          setSessionId(session.session_id);
          setMessages(session.messages || []);
          if (session.extracted_elements) {
            setExtractedElements(session.extracted_elements);
            setPhase('refining');
          }
        } else {
          // Create new session
          const newSession = await apiClient.createBrainstormSession();
          setSessionId(newSession.session_id);
          
          // Generate initial AI greeting to start the conversation
          if (newSession.session_id) {
            try {
              // Send a starter message that encourages idea generation
              const greeting = await apiClient.sendBrainstormMessage(
                newSession.session_id,
                "I want to create a new story. Can you help me brainstorm some ideas?"
              );
              setMessages([
                {
                  role: 'user',
                  content: "I want to create a new story. Can you help me brainstorm some ideas?",
                  timestamp: new Date().toISOString()
                },
                {
                  role: 'assistant',
                  content: greeting.ai_response,
                  timestamp: new Date().toISOString()
                }
              ]);
            } catch (error) {
              console.error('Failed to generate initial greeting:', error);
              // Fallback greeting if API fails
              setMessages([
                {
                  role: 'assistant',
                  content: "Hi! I'm excited to help you brainstorm your story. Let's start by exploring what excites you - are you thinking about a specific genre? A character? A world? Or maybe a theme or conflict? Share what's on your mind and I'll generate some creative ideas to build on!",
                  timestamp: new Date().toISOString()
                }
              ]);
            }
          }
        }
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

  const handleStartStory = async () => {
    if (!sessionId || !extractedElements) return;

    setIsCreatingStory(true);
    
    // Navigate to create-story with brainstorm session ID
    router.push(`/create-story?brainstorm_session_id=${sessionId}`);
  };

  const handleBackToChat = () => {
    setPhase('chat');
  };

  if (!user) {
    return null;
  }

  if (!sessionId) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-white/80">Starting brainstorm session...</p>
        </div>
      </div>
    );
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
        {phase === 'chat' ? (
          <div className="bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 h-[calc(100vh-200px)]">
            <BrainstormChat
              messages={messages}
              onSendMessage={handleSendMessage}
              onRefineIdeas={handleRefineIdeas}
              isLoading={isLoading || isExtracting}
            />
          </div>
        ) : (
          <div className="bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 max-h-[calc(100vh-200px)] overflow-y-auto">
            <RefinementWizard
              elements={extractedElements}
              onUpdate={handleUpdateElements}
              onStartStory={handleStartStory}
              onBackToChat={handleBackToChat}
              sessionId={sessionId}
              isCreatingStory={isCreatingStory}
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

