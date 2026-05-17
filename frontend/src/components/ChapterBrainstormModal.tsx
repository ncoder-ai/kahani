'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import apiClient, { StoryArc, ArcPhase, ChapterPlot, StructuredElements, CharacterArc, SuggestedElements } from '@/lib/api';
import StoryArcViewer from './StoryArcViewer';
import ThinkingBox from './ThinkingBox';
import CharacterReview from './brainstorm/CharacterReview';
import BrainstormMessage from './brainstorm/BrainstormMessage';

// Types for CharacterReview integration
interface BrainstormCharacter {
  name: string;
  role: string;
  description: string;
  gender?: string;
  personality_traits?: string[];
  background?: string;
  goals?: string;
  fears?: string;
  appearance?: string;
  suggested_voice_style?: string;
}

interface CharacterMapping {
  brainstormChar: BrainstormCharacter;
  action: 'create' | 'use_existing' | 'skip';
  existingCharacterId?: number;
  newCharacterId?: number;
}
import { GripVertical, X, Plus, ChevronLeft, ChevronDown, ChevronUp, Clock, MessageSquare, Trash2, RefreshCw, Check, Edit2, FileText, Users, Palette, List, Flag } from 'lucide-react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

interface PreviousSession {
  id: number;
  story_id: number;
  chapter_id: number | null;
  arc_phase_id: string | null;
  status: string;
  message_count: number;
  has_extracted_plot: boolean;
  created_at: string;
  updated_at: string | null;
}

interface ChapterBrainstormModalProps {
  isOpen: boolean;
  storyId: number;
  chapterId?: number;
  currentChapterIdForContext?: number;  // The current chapter whose content can be summarized for context
  storyArc?: StoryArc | null;
  onClose: () => void;
  onPlotApplied: (plot?: ChapterPlot, sessionId?: number, arcPhaseId?: string) => void;
  existingSessionId?: number;
  existingPlot?: ChapterPlot | null;
  existingArcPhaseId?: string;
  enableStreaming?: boolean;
  showThinkingContent?: boolean;
}

// Structured Element Slot Component
interface ElementSlotProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  suggestedValue?: string;
  isEditing: boolean;
  draft: string;
  onEdit: () => void;
  onSave: () => void;
  onCancel: () => void;
  onDraftChange: (value: string) => void;
  onConfirmSuggestion?: () => void;
  onDismissSuggestion?: () => void;
  onClear?: () => void;
  isSaving: boolean;
  multiline?: boolean;
  placeholder?: string;
}

function ElementSlot({
  icon,
  label,
  value,
  suggestedValue,
  isEditing,
  draft,
  onEdit,
  onSave,
  onCancel,
  onDraftChange,
  onConfirmSuggestion,
  onDismissSuggestion,
  onClear,
  isSaving,
  multiline = false,
  placeholder = ''
}: ElementSlotProps) {
  const hasValue = value && value.trim().length > 0;
  const hasSuggestion = suggestedValue && suggestedValue.trim().length > 0 && !hasValue;
  
  if (isEditing) {
    return (
      <div className="bg-white/5 rounded-lg p-2">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-purple-400">{icon}</span>
          <span className="text-white/80 text-xs font-medium">{label}</span>
        </div>
        {multiline ? (
          <textarea
            value={draft}
            onChange={(e) => onDraftChange(e.target.value)}
            placeholder={placeholder}
            className="w-full bg-white/10 border border-purple-500/50 rounded px-2 py-1.5 text-white text-xs resize-none focus:outline-none focus:border-purple-500"
            rows={3}
            autoFocus
          />
        ) : (
          <input
            type="text"
            value={draft}
            onChange={(e) => onDraftChange(e.target.value)}
            placeholder={placeholder}
            className="w-full bg-white/10 border border-purple-500/50 rounded px-2 py-1.5 text-white text-xs focus:outline-none focus:border-purple-500"
            autoFocus
          />
        )}
        <div className="flex justify-end gap-2 mt-2">
          <button
            onClick={onCancel}
            className="px-2 py-1 text-white/60 hover:text-white text-xs"
            disabled={isSaving}
          >
            Cancel
          </button>
          <button
            onClick={onSave}
            disabled={isSaving || !draft.trim()}
            className="px-2 py-1 bg-purple-600 text-white rounded text-xs hover:bg-purple-500 disabled:opacity-50"
          >
            {isSaving ? '...' : 'Save'}
          </button>
        </div>
      </div>
    );
  }
  
  // Show suggestion state (dashed border, sparkle icon, confirm button)
  if (hasSuggestion) {
    return (
      <div className="border border-dashed border-amber-500/50 rounded-lg p-2 bg-amber-500/5">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <span className="text-amber-400">{icon}</span>
            <span className="text-amber-300 text-xs font-medium">{label}</span>
            <span className="text-amber-400/70 text-[10px] bg-amber-500/20 px-1.5 py-0.5 rounded">✨ Suggested</span>
          </div>
        </div>
        <p className="text-white/70 text-xs mb-2 line-clamp-2">{suggestedValue}</p>
        <div className="flex gap-2">
          <button
            onClick={onConfirmSuggestion}
            className="flex-1 px-2 py-1 bg-amber-600 text-white rounded text-xs hover:bg-amber-500 flex items-center justify-center gap-1"
          >
            <Check className="w-3 h-3" />
            Confirm
          </button>
          <button
            onClick={onEdit}
            className="px-2 py-1 bg-white/10 text-white/70 rounded text-xs hover:bg-white/20"
          >
            Edit
          </button>
          <button
            onClick={onDismissSuggestion}
            className="px-2 py-1 text-white/40 hover:text-white/60 text-xs"
            title="Dismiss suggestion"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      </div>
    );
  }
  
  // Show confirmed state (solid border, checkmark)
  return (
    <div 
      className={`flex items-center justify-between p-2 rounded-lg transition-colors cursor-pointer ${
        hasValue 
          ? 'bg-green-500/10 hover:bg-green-500/20 border border-green-500/30' 
          : 'bg-white/5 hover:bg-white/10'
      }`}
      onClick={onEdit}
    >
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <span className={hasValue ? 'text-green-400' : 'text-white/40'}>{icon}</span>
        <span className={`text-xs font-medium ${hasValue ? 'text-green-300' : 'text-white/50'}`}>
          {label}
        </span>
        {hasValue && (
          <>
            <Check className="w-3 h-3 text-green-400 flex-shrink-0" />
            <span className="text-white/60 text-xs truncate">{value}</span>
          </>
        )}
        {!hasValue && (
          <span className="text-white/30 text-xs italic">Not set</span>
        )}
      </div>
      <div className="flex items-center gap-1 flex-shrink-0">
        {hasValue && onClear && (
          <button
            onClick={(e) => { e.stopPropagation(); onClear(); }}
            className="p-0.5 text-white/30 hover:text-red-400 transition-colors"
            title="Clear"
          >
            <X className="w-3 h-3" />
          </button>
        )}
        <Edit2 className="w-3 h-3 text-white/40" />
      </div>
    </div>
  );
}

export default function ChapterBrainstormModal({
  isOpen,
  storyId,
  chapterId,
  currentChapterIdForContext,
  storyArc,
  onClose,
  onPlotApplied,
  existingSessionId,
  existingPlot,
  existingArcPhaseId,
  enableStreaming = true,
  showThinkingContent = true
}: ChapterBrainstormModalProps) {
  const [sessionId, setSessionId] = useState<number | null>(existingSessionId || null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedPhase, setSelectedPhase] = useState<ArcPhase | null>(() => {
    if (existingArcPhaseId && storyArc?.phases) {
      return storyArc.phases.find(p => p.id === existingArcPhaseId) || null;
    }
    return null;
  });
  const [extractedPlot, setExtractedPlot] = useState<ChapterPlot | null>(existingPlot || null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionStep, setExtractionStep] = useState(0);
  const [extractionElapsed, setExtractionElapsed] = useState(0);
  const [phase, setPhase] = useState<'session_select' | 'select_phase' | 'prior_context' | 'chat' | 'review' | 'character_review'>(
    existingPlot ? 'review' : 'session_select'
  );
  
  // Prior chapter context state
  const [priorChapterSummary, setPriorChapterSummary] = useState('');
  const [isLoadingPriorContext, setIsLoadingPriorContext] = useState(false);
  const [priorChapterContext, setPriorChapterContext] = useState<{
    chapter_number: number;
    title: string | null;
    has_summary: boolean;
    summary: string | null;
    scene_count: number;
    total_words: number;
  } | null>(null);
  const [currentChapterId, setCurrentChapterId] = useState<number | null>(null);
  
  // Character review state
  const [characterMappings, setCharacterMappings] = useState<CharacterMapping[]>([]);
  const [isEditingPlot, setIsEditingPlot] = useState(false);
  const [isSavingPlotEdits, setIsSavingPlotEdits] = useState(false);
  const [showArcSidebar, setShowArcSidebar] = useState(false);
  
  const [expandedArcPhaseId, setExpandedArcPhaseId] = useState<string | null>(null);

  // Previous sessions state
  const [previousSessions, setPreviousSessions] = useState<PreviousSession[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [deletingSessionId, setDeletingSessionId] = useState<number | null>(null);
  
  // Streaming state
  const [streamingContent, setStreamingContent] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingContent, setThinkingContent] = useState('');
  const abortControllerRef = useRef<AbortController | null>(null);
  
  // Structured elements state
  const [structuredElements, setStructuredElements] = useState<StructuredElements>({
    overview: '',
    characters: [],
    tone: '',
    key_events: [],
    ending: ''
  });
  // Suggested elements from AI (not yet confirmed)
  const [suggestedElements, setSuggestedElements] = useState<SuggestedElements>({});
  const [showElementsPanel, setShowElementsPanel] = useState(true);
  const [editingElement, setEditingElement] = useState<string | null>(null);
  const [elementDraft, setElementDraft] = useState('');
  const [savingElement, setSavingElement] = useState(false);
  
  // Drag state for reordering
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Cycle through extraction status messages while extracting
  const extractionMessages = [
    'Reading your brainstorm conversation...',
    'Identifying key plot elements...',
    'Structuring chapter events...',
    'Building character arcs...',
    'Refining chapter outline...',
    'Almost there...',
  ];

  useEffect(() => {
    if (!isExtracting) {
      setExtractionStep(0);
      setExtractionElapsed(0);
      return;
    }
    const stepInterval = setInterval(() => {
      setExtractionStep(prev => (prev + 1) % extractionMessages.length);
    }, 3000);
    const timerInterval = setInterval(() => {
      setExtractionElapsed(prev => prev + 1);
    }, 1000);
    return () => { clearInterval(stepInterval); clearInterval(timerInterval); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isExtracting]);

  // Load previous sessions when modal opens
  useEffect(() => {
    if (isOpen && phase === 'session_select' && !existingSessionId && !existingPlot) {
      loadPreviousSessions();
    }
  }, [isOpen, phase, existingSessionId, existingPlot, storyId]);

  const loadPreviousSessions = async () => {
    setIsLoadingSessions(true);
    try {
      const response = await apiClient.getChapterBrainstormSessions(storyId);
      // Filter to only show incomplete sessions (not 'applied' status)
      const incompleteSessions = response.sessions.filter(
        s => s.status !== 'applied' && s.message_count > 0
      );
      setPreviousSessions(incompleteSessions);
      
      // If no previous sessions, skip directly to phase selection
      if (incompleteSessions.length === 0) {
        setPhase('select_phase');
      }
    } catch (error) {
      console.error('Failed to load previous sessions:', error);
      // On error, proceed to phase selection
      setPhase('select_phase');
    } finally {
      setIsLoadingSessions(false);
    }
  };

  const handleResumeSession = async (session: PreviousSession) => {
    setIsLoading(true);
    try {
      await loadExistingSession(session.id);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteSession = async (sessionIdToDelete: number) => {
    setDeletingSessionId(sessionIdToDelete);
    try {
      await apiClient.deleteChapterBrainstormSession(storyId, sessionIdToDelete);
      setPreviousSessions(prev => prev.filter(s => s.id !== sessionIdToDelete));
      
      // If no more sessions, go to phase selection
      if (previousSessions.length <= 1) {
        setPhase('select_phase');
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
    } finally {
      setDeletingSessionId(null);
    }
  };

  const handleStartNewSession = async () => {
    // Reset state
    setSessionId(null);
    setMessages([]);
    setExtractedPlot(null);
    setSelectedPhase(null);
    setPriorChapterSummary('');
    setPriorChapterContext(null);
    
    // If we have a current chapter to get context from, go to prior_context phase
    if (currentChapterIdForContext) {
      setCurrentChapterId(currentChapterIdForContext);
      setIsLoadingPriorContext(true);
      try {
        const context = await apiClient.getChapterBrainstormContext(storyId, currentChapterIdForContext);
        setPriorChapterContext(context);
        setPhase('prior_context');
      } catch (error) {
        console.error('Failed to load prior chapter context:', error);
        // Skip to phase selection on error
        setPhase('select_phase');
      } finally {
        setIsLoadingPriorContext(false);
      }
    } else {
      // No current chapter, go directly to phase selection
      setPhase('select_phase');
    }
  };

  const formatSessionDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (existingSessionId) {
      loadExistingSession(existingSessionId);
    }
  }, [existingSessionId]);

  // Update extractedPlot when existingPlot changes (e.g., modal reopened)
  useEffect(() => {
    if (existingPlot) {
      setExtractedPlot(existingPlot);
      setPhase('review');
    }
  }, [existingPlot]);

  const loadExistingSession = async (id: number) => {
    try {
      const session = await apiClient.getChapterBrainstormSession(storyId, id);
      setSessionId(session.session_id);
      setMessages(session.messages.map(m => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
        timestamp: m.timestamp
      })));
      if (session.extracted_plot) {
        setExtractedPlot(session.extracted_plot);
      }
      if (session.arc_phase_id && storyArc) {
        const phase = storyArc.phases.find(p => p.id === session.arc_phase_id);
        if (phase) setSelectedPhase(phase);
      }
      setPhase(session.extracted_plot ? 'review' : 'chat');
      
      // Load structured elements
      await loadStructuredElements(id);
    } catch (error) {
      console.error('Failed to load session:', error);
    }
  };

  const loadStructuredElements = async (sessId: number) => {
    try {
      const response = await apiClient.getChapterBrainstormElements(storyId, sessId);
      setStructuredElements(response.structured_elements);
      // Also load any suggested elements parsed from the last message
      if (response.suggested_elements) {
        setSuggestedElements(response.suggested_elements);
      }
    } catch (error) {
      console.error('Failed to load structured elements:', error);
    }
  };

  const saveStructuredElement = async (
    elementType: 'overview' | 'characters' | 'tone' | 'key_events' | 'ending',
    value: string | CharacterArc[] | string[]
  ) => {
    if (!sessionId) return;
    
    setSavingElement(true);
    try {
      const response = await apiClient.updateChapterBrainstormElement(
        storyId,
        sessionId,
        elementType,
        value
      );
      setStructuredElements(response.structured_elements);
      setEditingElement(null);
      setElementDraft('');
    } catch (error) {
      console.error('Failed to save element:', error);
    } finally {
      setSavingElement(false);
    }
  };

  // Confirm a suggested element (saves it to backend and clears suggestion)
  const confirmSuggestion = async (elementType: 'overview' | 'characters' | 'tone' | 'key_events' | 'ending') => {
    const suggestion = suggestedElements[elementType];
    if (!suggestion || !sessionId) return;
    
    setSavingElement(true);
    try {
      // For key_events, use the array directly; for characters, convert string to array
      let value: string | CharacterArc[] | string[] = suggestion;
      if (elementType === 'characters' && typeof suggestion === 'string') {
        // Parse characters string: each line is "Name: development text"
        // Split by newline, then split each line by first colon to separate name from development
        // This preserves the full development text including any commas or extra colons
        value = suggestion.split('\n').filter(l => l.trim()).map(line => {
          const colonIndex = line.indexOf(':');
          if (colonIndex > 0) {
            const name = line.substring(0, colonIndex).trim();
            const development = line.substring(colonIndex + 1).trim();
            return { character_name: name, name: name, development: development };
          }
          // Fallback: no colon found, treat whole line as name
          return { character_name: line.trim(), name: line.trim(), development: '' };
        });
      }
      
      const response = await apiClient.updateChapterBrainstormElement(
        storyId,
        sessionId,
        elementType,
        value
      );
      setStructuredElements(response.structured_elements);
      
      // Clear this suggestion
      setSuggestedElements(prev => {
        const updated = { ...prev };
        delete updated[elementType];
        return updated;
      });
    } catch (error) {
      console.error('Failed to confirm suggestion:', error);
    } finally {
      setSavingElement(false);
    }
  };

  // Dismiss a suggestion without saving
  const dismissSuggestion = (elementType: 'overview' | 'characters' | 'tone' | 'key_events' | 'ending') => {
    setSuggestedElements(prev => {
      const updated = { ...prev };
      delete updated[elementType];
      return updated;
    });
  };

  // Clear a confirmed element (reset to empty)
  const clearElement = async (elementType: 'overview' | 'characters' | 'tone' | 'key_events' | 'ending') => {
    const emptyValue = (elementType === 'characters' || elementType === 'key_events') ? [] : '';
    await saveStructuredElement(elementType, emptyValue);
  };

  const getElementCount = () => {
    let count = 0;
    if (structuredElements.overview) count++;
    if (structuredElements.characters.length > 0) count++;
    if (structuredElements.tone) count++;
    if (structuredElements.key_events.length > 0) count++;
    if (structuredElements.ending) count++;
    return count;
  };

  // Transform new_character_suggestions to BrainstormCharacter[] for CharacterReview
  const getNewCharactersForReview = (): BrainstormCharacter[] => {
    if (!extractedPlot?.new_character_suggestions) return [];
    return extractedPlot.new_character_suggestions.map(suggestion => ({
      name: suggestion.name,
      role: suggestion.role,
      description: `${suggestion.description}${suggestion.reason ? ` (${suggestion.reason})` : ''}`,
      personality_traits: [],
      suggested_voice_style: suggestion.suggested_voice_style
    }));
  };

  // Check if we have new characters to review
  const hasNewCharacterSuggestions = () => {
    return extractedPlot?.new_character_suggestions && extractedPlot.new_character_suggestions.length > 0;
  };

  const getSuggestionCount = () => {
    let count = 0;
    // Only count suggestions for elements that aren't already confirmed
    if (suggestedElements.overview && !structuredElements.overview) count++;
    if (suggestedElements.characters && structuredElements.characters.length === 0) count++;
    if (suggestedElements.tone && !structuredElements.tone) count++;
    if (suggestedElements.key_events && structuredElements.key_events.length === 0) count++;
    if (suggestedElements.ending && !structuredElements.ending) count++;
    return count;
  };

  const handlePhaseSelect = async (arcPhase: ArcPhase | null) => {
    setSelectedPhase(arcPhase);
    setIsLoading(true);
    
    try {
      const response = await apiClient.createChapterBrainstormSession(
        storyId, 
        arcPhase?.id,
        chapterId,
        priorChapterSummary || undefined  // Pass prior chapter summary if provided
      );
      setSessionId(response.session_id);
      
      const chapterContext = chapterId ? 'this chapter' : 'your next chapter';
      const priorContext = priorChapterSummary 
        ? `\n\nI've noted your summary of what happened in the current chapter. I'll use that context to help plan what comes next.`
        : '';
      const greeting = arcPhase 
        ? `I'll help you plan ${chapterContext} for the "${arcPhase.name}" phase of your story. This phase focuses on: ${arcPhase.description}${priorContext}\n\nWhat aspects of this chapter would you like to explore? Consider:\n• Key events that should happen\n• Which characters should appear\n• The emotional journey of this chapter`
        : `I'll help you plan ${chapterContext}.${priorContext}\n\nWhat's on your mind? Tell me about:\n• What you want to happen in this chapter\n• Any characters you want to focus on\n• The mood or tone you're going for`;
      
      setMessages([{ role: 'assistant', content: greeting }]);
      setPhase('chat');
    } catch (error) {
      console.error('Failed to create session:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim() || !sessionId || isLoading) return;
    
    const userMessage = inputValue.trim();
    setInputValue('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsLoading(true);
    setStreamingContent('');
    setThinkingContent('');
    setIsThinking(false);
    
    // Cancel any previous request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    
    if (enableStreaming) {
      // Use streaming API
      abortControllerRef.current = new AbortController();
      
      await apiClient.sendChapterBrainstormMessageStreaming(
        storyId,
        sessionId,
        userMessage,
        // onChunk
        (chunk) => {
          setStreamingContent(prev => prev + chunk);
        },
        // onComplete
        (aiResponse, messageCount) => {
          setMessages(prev => [...prev, { role: 'assistant', content: aiResponse }]);
          setStreamingContent('');
          setIsLoading(false);
          setIsThinking(false);
          setThinkingContent('');
        },
        // onError
        (error) => {
          console.error('Streaming error:', error);
          // Provide more helpful error messages
          let errorMessage = 'Sorry, I encountered an error. Please try again.';
          if (error.includes('AuthenticationError') || error.includes('401') || error.includes('User not found')) {
            errorMessage = 'Authentication error: Please check your LLM API key in Settings.';
          } else if (error.includes('timeout') || error.includes('Timeout')) {
            errorMessage = 'The request timed out. Please try again.';
          } else if (error.includes('rate limit') || error.includes('429')) {
            errorMessage = 'Rate limit exceeded. Please wait a moment and try again.';
          }
          setMessages(prev => [...prev, { 
            role: 'assistant', 
            content: errorMessage
          }]);
          setStreamingContent('');
          setIsLoading(false);
          setIsThinking(false);
          setThinkingContent('');
        },
        // onThinkingStart
        () => {
          setIsThinking(true);
          setThinkingContent('');
        },
        // onThinkingChunk
        (chunk) => {
          setThinkingContent(prev => prev + chunk);
        },
        // onThinkingEnd
        (totalChars) => {
          setIsThinking(false);
        },
        // onSuggestions
        (elements) => {
          setSuggestedElements(prev => ({ ...prev, ...elements }));
        },
        abortControllerRef.current.signal
      );
    } else {
      // Use non-streaming API
      try {
        const response = await apiClient.sendChapterBrainstormMessage(
          storyId,
          sessionId,
          userMessage
        );
        setMessages(prev => [...prev, { role: 'assistant', content: response.ai_response }]);
        
        // Handle suggested elements if present
        if (response.suggested_elements) {
          setSuggestedElements(prev => ({ ...prev, ...response.suggested_elements }));
        }
      } catch (error) {
        console.error('Failed to send message:', error);
        setMessages(prev => [...prev, { 
          role: 'assistant', 
          content: 'Sorry, I encountered an error. Please try again.' 
        }]);
      } finally {
        setIsLoading(false);
      }
    }
  };

  const handleExtractPlot = async () => {
    if (!sessionId) return;
    
    setIsExtracting(true);
    try {
      const response = await apiClient.extractChapterPlot(storyId, sessionId);
      setExtractedPlot(response.extracted_plot);
      setPhase('review');
    } catch (error) {
      console.error('Failed to extract plot:', error);
    } finally {
      setIsExtracting(false);
    }
  };

  const [isApplying, setIsApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);

  const handleApplyPlot = async () => {
    console.log('[ChapterBrainstorm] Apply plot clicked', { extractedPlot: !!extractedPlot, sessionId, chapterId, arcPhaseId: selectedPhase?.id });
    
    if (!extractedPlot) {
      setApplyError('No plot to apply. Please extract the plot first.');
      return;
    }
    
    setIsApplying(true);
    setApplyError(null);
    
    try {
      // Always pass the edited plot back to the caller
      // The caller (ChapterSidebar/ChapterWizard) will save it when the chapter is saved
      console.log('[ChapterBrainstorm] Passing edited plot back to caller:', extractedPlot);
      onPlotApplied(extractedPlot, sessionId || undefined, selectedPhase?.id);
    } catch (error) {
      console.error('Failed to apply plot:', error);
      setApplyError('Failed to apply plot. Please try again.');
    } finally {
      setIsApplying(false);
    }
  };

  // Save plot edits to the backend when exiting edit mode
  const handleSavePlotEdits = async () => {
    console.log('[ChapterBrainstorm] handleSavePlotEdits called', { extractedPlot: !!extractedPlot, sessionId });

    if (!extractedPlot || !sessionId) {
      // No session to save to, just exit edit mode
      console.log('[ChapterBrainstorm] No session to save, just exiting edit mode');
      setIsEditingPlot(false);
      return;
    }

    setIsSavingPlotEdits(true);
    try {
      console.log('[ChapterBrainstorm] Saving plot edits to backend:', {
        storyId,
        sessionId,
        climax: extractedPlot.climax,
        summary: extractedPlot.summary?.substring(0, 50)
      });
      const result = await apiClient.updateChapterBrainstormPlot(storyId, sessionId, extractedPlot);
      console.log('[ChapterBrainstorm] Plot edits saved successfully:', result);
      setIsEditingPlot(false);
    } catch (error) {
      console.error('[ChapterBrainstorm] Failed to save plot edits:', error);
      alert('Failed to save edits: ' + (error instanceof Error ? error.message : 'Unknown error'));
      // Still exit edit mode even if save fails - user can try again
      setIsEditingPlot(false);
    } finally {
      setIsSavingPlotEdits(false);
    }
  };

  // Apply plot with character mappings from CharacterReview
  const handleApplyPlotWithCharacters = async (mappings: CharacterMapping[]) => {
    console.log('[ChapterBrainstorm] Apply plot with characters', { 
      extractedPlot: !!extractedPlot, 
      sessionId, 
      chapterId, 
      arcPhaseId: selectedPhase?.id,
      characterMappings: mappings.length 
    });
    
    if (!extractedPlot) {
      setApplyError('No plot to apply. Please extract the plot first.');
      return;
    }
    
    setIsApplying(true);
    setApplyError(null);
    
    try {
      // Collect character IDs from mappings
      const characterIds: number[] = [];
      for (const mapping of mappings) {
        if (mapping.action === 'create' && mapping.newCharacterId) {
          characterIds.push(mapping.newCharacterId);
        } else if (mapping.action === 'use_existing' && mapping.existingCharacterId) {
          characterIds.push(mapping.existingCharacterId);
        }
        // 'skip' action means we don't include this character
      }
      
      console.log('[ChapterBrainstorm] Character IDs to include:', characterIds);
      
      // Update the plot with character info if needed
      const plotWithCharacters = {
        ...extractedPlot,
        // Add character IDs to the plot so they can be associated with the chapter
        _characterIds: characterIds
      };
      
      // Pass the edited plot back to the caller
      console.log('[ChapterBrainstorm] Passing plot with characters back to caller:', plotWithCharacters);
      onPlotApplied(plotWithCharacters as ChapterPlot, sessionId || undefined, selectedPhase?.id);
    } catch (error) {
      console.error('Failed to apply plot with characters:', error);
      setApplyError('Failed to apply plot. Please try again.');
      setPhase('review'); // Go back to review on error
    } finally {
      setIsApplying(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Drag and drop handlers for key events reordering
  const handleDragStart = (index: number) => {
    setDraggedIndex(index);
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    setDragOverIndex(index);
  };

  const handleDrop = (e: React.DragEvent, dropIndex: number) => {
    e.preventDefault();
    if (draggedIndex === null || !extractedPlot) return;
    
    const newEvents = [...extractedPlot.key_events];
    const [draggedItem] = newEvents.splice(draggedIndex, 1);
    newEvents.splice(dropIndex, 0, draggedItem);
    
    setExtractedPlot({ ...extractedPlot, key_events: newEvents });
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  const handleDragEnd = () => {
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  // Touch-based reordering (move up/down buttons for mobile)
  const moveEvent = (index: number, direction: 'up' | 'down') => {
    if (!extractedPlot) return;
    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= extractedPlot.key_events.length) return;
    
    const newEvents = [...extractedPlot.key_events];
    [newEvents[index], newEvents[newIndex]] = [newEvents[newIndex], newEvents[index]];
    setExtractedPlot({ ...extractedPlot, key_events: newEvents });
  };

  const updateEvent = (index: number, value: string) => {
    if (!extractedPlot) return;
    const newEvents = [...extractedPlot.key_events];
    newEvents[index] = value;
    setExtractedPlot({ ...extractedPlot, key_events: newEvents });
  };

  const removeEvent = (index: number) => {
    if (!extractedPlot) return;
    const newEvents = extractedPlot.key_events.filter((_, i) => i !== index);
    setExtractedPlot({ ...extractedPlot, key_events: newEvents });
  };

  const addEvent = () => {
    if (!extractedPlot) return;
    setExtractedPlot({ ...extractedPlot, key_events: [...extractedPlot.key_events, ''] });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-end md:items-center justify-center">
      <div className="bg-gradient-to-br from-slate-900 via-purple-900/50 to-slate-900 w-full md:rounded-2xl md:w-[95vw] md:max-w-6xl h-[95vh] md:h-[90vh] flex flex-col md:flex-row overflow-hidden border-t md:border border-white/10">
        
        {/* Mobile Header with Arc Toggle */}
        <div className="md:hidden flex items-center justify-between p-3 border-b border-white/10 bg-slate-900/80">
          <button
            onClick={onClose}
            className="p-2 text-white/60 hover:text-white touch-manipulation"
          >
            <X className="w-5 h-5" />
          </button>
          <h2 className="text-white font-semibold text-sm">
            {phase === 'session_select' && 'Resume or Start New'}
            {phase === 'select_phase' && 'Select Arc Phase'}
            {phase === 'prior_context' && 'Summarize Current Chapter'}
            {phase === 'chat' && 'Brainstorm'}
            {phase === 'review' && 'Review Plot'}
            {phase === 'character_review' && 'Review Characters'}
          </h2>
          {storyArc && phase !== 'session_select' && (
            <button
              onClick={() => setShowArcSidebar(!showArcSidebar)}
              className="p-2 text-purple-400 hover:text-purple-300 touch-manipulation"
            >
              {showArcSidebar ? 'Hide Arc' : 'Arc'}
            </button>
          )}
          {phase === 'session_select' && <div className="w-10" />}
        </div>

        {/* Mobile Arc Sidebar (collapsible) */}
        {storyArc && showArcSidebar && (
          <div className="md:hidden border-b border-white/10 p-3 bg-slate-900/50 max-h-48 overflow-y-auto">
            <StoryArcViewer 
              arc={storyArc} 
              currentPhaseId={selectedPhase?.id}
              onPhaseClick={(arcPhase) => {
                if (phase === 'select_phase') {
                  handlePhaseSelect(arcPhase);
                  setShowArcSidebar(false);
                }
              }}
            />
          </div>
        )}

        {/* Desktop Left Sidebar - Story Arc (hidden during session selection and prior context) */}
        {storyArc && phase !== 'session_select' && phase !== 'prior_context' && (
          <div className="hidden md:block w-64 border-r border-white/10 p-4 overflow-y-auto flex-shrink-0">
            <h3 className="text-white font-semibold mb-4">Story Arc</h3>
            <StoryArcViewer 
              arc={storyArc} 
              currentPhaseId={selectedPhase?.id}
              onPhaseClick={(arcPhase) => {
                if (phase === 'select_phase') {
                  handlePhaseSelect(arcPhase);
                }
              }}
            />
            
            {selectedPhase && (
              <div className="mt-4 p-3 bg-purple-500/20 rounded-lg">
                <span className="text-purple-300 text-xs font-medium">Selected Phase</span>
                <p className="text-white text-sm mt-1">{selectedPhase.name}</p>
              </div>
            )}
          </div>
        )}

        {/* Main Content */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
          {/* Desktop Header */}
          <div className="hidden md:flex p-4 border-b border-white/10 items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-white">
                {phase === 'session_select' && 'Resume or Start New'}
                {phase === 'select_phase' && 'Select Arc Phase'}
                {phase === 'prior_context' && 'Summarize Current Chapter'}
                {phase === 'chat' && 'Chapter Brainstorm'}
                {phase === 'review' && 'Review Chapter Plot'}
                {phase === 'character_review' && 'Review New Characters'}
              </h2>
              <p className="text-white/60 text-sm">
                {phase === 'session_select' && 'You have previous brainstorming sessions for this story'}
                {phase === 'select_phase' && 'Choose which part of your story this chapter belongs to'}
                {phase === 'prior_context' && 'Tell the AI what happened in the current chapter so it can help plan what comes next'}
                {phase === 'chat' && 'Discuss your chapter ideas with AI'}
                {phase === 'review' && 'Review and edit the extracted chapter plot'}
                {phase === 'character_review' && 'Choose to create, use existing, or skip each suggested character'}
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-white/60 hover:text-white p-2"
            >
              <X className="w-6 h-6" />
            </button>
          </div>

          {/* Session Selection - Resume or Start New */}
          {phase === 'session_select' && (
            <div className="flex-1 p-4 md:p-6 overflow-y-auto">
              <div className="max-w-2xl mx-auto space-y-4">
                {isLoadingSessions ? (
                  <div className="flex items-center justify-center py-12">
                    <RefreshCw className="w-6 h-6 text-purple-400 animate-spin" />
                    <span className="ml-2 text-white/60">Loading sessions...</span>
                  </div>
                ) : (
                  <>
                    {/* Previous Sessions */}
                    {previousSessions.length > 0 && (
                      <div className="space-y-3">
                        <h3 className="text-white/80 font-medium text-sm flex items-center gap-2">
                          <Clock className="w-4 h-4" />
                          Previous Sessions
                        </h3>
                        {previousSessions.map((session) => {
                          const arcPhase = session.arc_phase_id && storyArc?.phases
                            ? storyArc.phases.find(p => p.id === session.arc_phase_id)
                            : null;
                          
                          return (
                            <div
                              key={session.id}
                              className="bg-white/5 rounded-xl border border-white/10 p-4 hover:border-purple-500/50 transition-all"
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <span className="text-white font-medium text-sm">
                                      {arcPhase?.name || 'Free Brainstorm'}
                                    </span>
                                    {session.has_extracted_plot && (
                                      <span className="px-2 py-0.5 bg-green-500/20 text-green-300 text-xs rounded">
                                        Plot Ready
                                      </span>
                                    )}
                                    <span className="text-white/40 text-xs">
                                      {formatSessionDate(session.updated_at || session.created_at)}
                                    </span>
                                  </div>
                                  <div className="flex items-center gap-3 mt-1 text-white/50 text-xs">
                                    <span className="flex items-center gap-1">
                                      <MessageSquare className="w-3 h-3" />
                                      {session.message_count} messages
                                    </span>
                                  </div>
                                </div>
                                <div className="flex items-center gap-2">
                                  <button
                                    onClick={() => handleResumeSession(session)}
                                    disabled={isLoading}
                                    className="px-3 py-1.5 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-500 disabled:opacity-50 transition-all"
                                  >
                                    Resume
                                  </button>
                                  <button
                                    onClick={() => handleDeleteSession(session.id)}
                                    disabled={deletingSessionId === session.id}
                                    className="p-1.5 text-white/40 hover:text-red-400 disabled:opacity-50 transition-all"
                                    title="Delete session"
                                  >
                                    {deletingSessionId === session.id ? (
                                      <RefreshCw className="w-4 h-4 animate-spin" />
                                    ) : (
                                      <Trash2 className="w-4 h-4" />
                                    )}
                                  </button>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* Start New Session */}
                    <div className="pt-4 border-t border-white/10">
                      <button
                        onClick={handleStartNewSession}
                        className="w-full text-left p-4 bg-gradient-to-r from-purple-600/20 to-indigo-600/20 hover:from-purple-600/30 hover:to-indigo-600/30 rounded-xl border border-purple-500/30 hover:border-purple-500/50 transition-all"
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-full bg-purple-600/30 flex items-center justify-center">
                            <Plus className="w-5 h-5 text-purple-300" />
                          </div>
                          <div>
                            <h3 className="text-white font-semibold text-sm md:text-base">Start New Brainstorm</h3>
                            <p className="text-white/50 text-xs md:text-sm mt-0.5">
                              Begin a fresh chapter planning session
                            </p>
                          </div>
                        </div>
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Phase Selection */}
          {phase === 'select_phase' && (
            <div className="flex-1 p-4 md:p-6 overflow-y-auto">
              <div className="max-w-2xl mx-auto space-y-2 md:space-y-3">
                {storyArc?.phases.map((arcPhase) => {
                  const isExpanded = expandedArcPhaseId === arcPhase.id;
                  return (
                    <div
                      key={arcPhase.id}
                      className="w-full text-left p-2.5 md:p-4 bg-white/5 hover:bg-white/10 rounded-xl border border-white/10 hover:border-purple-500/50 transition-all"
                    >
                      <button
                        onClick={() => setExpandedArcPhaseId(isExpanded ? null : arcPhase.id)}
                        className="w-full text-left touch-manipulation"
                      >
                        <div className="flex items-center justify-between">
                          <h3 className="text-white font-semibold text-sm md:text-base">{arcPhase.name}</h3>
                          <svg className={`w-4 h-4 text-white/40 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                        </div>
                        <p className={`text-white/60 text-xs md:text-sm mt-1 ${isExpanded ? '' : 'line-clamp-2'}`}>{arcPhase.description}</p>
                      </button>
                      {isExpanded ? (
                        <div className="mt-2">
                          <div className="flex flex-wrap gap-1">
                            {arcPhase.key_events.map((event, i) => (
                              <span key={i} className="px-2 py-0.5 bg-purple-500/20 text-purple-300 text-xs rounded">
                                {event}
                              </span>
                            ))}
                          </div>
                          <button
                            onClick={() => handlePhaseSelect(arcPhase)}
                            disabled={isLoading}
                            className="mt-3 w-full py-1.5 bg-purple-600 hover:bg-purple-500 text-white text-sm rounded-lg transition-colors disabled:opacity-50"
                          >
                            Select this phase
                          </button>
                        </div>
                      ) : (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {arcPhase.key_events.slice(0, 2).map((event, i) => (
                            <span key={i} className="px-2 py-0.5 bg-purple-500/20 text-purple-300 text-xs rounded truncate max-w-[150px]">
                              {event}
                            </span>
                          ))}
                          {arcPhase.key_events.length > 2 && (
                            <span className="px-2 py-0.5 bg-white/10 text-white/50 text-xs rounded">
                              +{arcPhase.key_events.length - 2}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
                
                <button
                  onClick={() => handlePhaseSelect(null)}
                  disabled={isLoading}
                  className="w-full text-left p-3 md:p-4 bg-white/5 hover:bg-white/10 active:bg-white/15 rounded-xl border border-dashed border-white/20 hover:border-white/40 transition-all touch-manipulation"
                >
                  <h3 className="text-white/80 font-medium text-sm md:text-base">Skip Phase Selection</h3>
                  <p className="text-white/50 text-xs md:text-sm mt-1">
                    Brainstorm freely without targeting a specific arc phase
                  </p>
                </button>
              </div>
            </div>
          )}

          {/* Prior Context - Summarize Current Chapter */}
          {phase === 'prior_context' && (
            <div className="flex-1 p-4 md:p-6 overflow-y-auto">
              <div className="max-w-2xl mx-auto space-y-4">
                {isLoadingPriorContext ? (
                  <div className="flex items-center justify-center py-12">
                    <RefreshCw className="w-6 h-6 text-purple-400 animate-spin" />
                    <span className="ml-2 text-white/60">Loading chapter context...</span>
                  </div>
                ) : (
                  <>
                    {/* Chapter Info */}
                    {priorChapterContext && (
                      <div className="bg-white/5 rounded-xl p-4 border border-white/10">
                        <h3 className="text-white font-semibold text-sm mb-2">
                          Chapter {priorChapterContext.chapter_number}: {priorChapterContext.title || 'Untitled'}
                        </h3>
                        <div className="flex gap-4 text-white/50 text-xs">
                          <span>{priorChapterContext.scene_count} scenes</span>
                          <span>{priorChapterContext.total_words.toLocaleString()} words</span>
                        </div>
                        {priorChapterContext.has_summary && priorChapterContext.summary && (
                          <div className="mt-3 p-3 bg-green-500/10 border border-green-500/30 rounded-lg">
                            <span className="text-green-300 text-xs font-medium">Existing Summary</span>
                            <p className="text-white/70 text-sm mt-1">{priorChapterContext.summary.slice(0, 300)}...</p>
                            <button
                              onClick={() => setPriorChapterSummary(priorChapterContext.summary || '')}
                              className="mt-2 text-green-400 text-xs hover:text-green-300"
                            >
                              Use this summary →
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Summary Input */}
                    <div className="space-y-2">
                      <label className="text-white/80 text-sm font-medium">
                        What happened in this chapter? (Optional)
                      </label>
                      <p className="text-white/50 text-xs">
                        Summarize the key events so the AI can help plan what comes next naturally.
                      </p>
                      <textarea
                        value={priorChapterSummary}
                        onChange={(e) => setPriorChapterSummary(e.target.value)}
                        placeholder="E.g., 'The main character discovered the secret letter and confronted their father about it. The chapter ended with them deciding to leave home...'"
                        className="w-full bg-white/10 border border-white/20 rounded-xl px-4 py-3 text-white placeholder-white/40 resize-none focus:outline-none focus:border-purple-500 text-sm"
                        rows={5}
                      />
                      {priorChapterSummary && (
                        <p className="text-white/40 text-xs text-right">
                          {priorChapterSummary.length} characters
                        </p>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex flex-col md:flex-row gap-3 pt-4">
                      <button
                        onClick={() => setPhase('select_phase')}
                        className="flex-1 px-4 py-3 bg-purple-600 text-white font-medium rounded-xl hover:bg-purple-500 transition-all"
                      >
                        {priorChapterSummary ? 'Continue with Summary →' : 'Continue without Summary →'}
                      </button>
                      <button
                        onClick={() => {
                          setPriorChapterSummary('');
                          setPhase('select_phase');
                        }}
                        className="px-4 py-3 bg-white/10 text-white/70 rounded-xl hover:bg-white/20 transition-all"
                      >
                        Skip
                      </button>
                    </div>

                    <p className="text-white/40 text-xs text-center">
                      Providing context helps the AI understand where your story is and suggest relevant next steps.
                    </p>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Chat Interface */}
          {phase === 'chat' && (
            <>
              {/* Extraction overlay */}
              {isExtracting && (
                <div className="absolute inset-0 z-10 bg-black/60 backdrop-blur-sm flex items-center justify-center rounded-xl">
                  <div className="text-center p-6 max-w-sm">
                    <div className="inline-block mb-4">
                      <div className="w-10 h-10 border-3 border-purple-400 border-t-transparent rounded-full animate-spin" />
                    </div>
                    <div className="text-white font-medium text-base mb-2">Extracting Chapter Plot</div>
                    <div className="text-white/70 text-sm transition-opacity duration-500">
                      {extractionMessages[extractionStep]}
                    </div>
                    <div className="text-white/40 text-xs mt-3">
                      {extractionElapsed}s elapsed
                    </div>
                    <div className="mt-2 w-48 mx-auto h-1 bg-white/10 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-purple-500 rounded-full transition-all duration-[3000ms] ease-linear"
                        style={{ width: `${((extractionStep + 1) / extractionMessages.length) * 100}%` }}
                      />
                    </div>
                  </div>
                </div>
              )}
              <div className="flex-1 overflow-y-auto p-3 md:p-4 space-y-3 md:space-y-4">
                {messages.map((message, index) => (
                  <BrainstormMessage
                    key={index}
                    role={message.role}
                    content={message.content}
                    onSelectIdea={(idea) => {
                      setInputValue(idea);
                    }}
                  />
                ))}
                
                {/* Thinking Display */}
                {isLoading && (isThinking || thinkingContent) && (
                  <div className="flex justify-start">
                    <div className="max-w-[85%] md:max-w-[80%]">
                      <ThinkingBox 
                        thinking={thinkingContent}
                        isThinking={isThinking}
                        showContent={showThinkingContent}
                      />
                    </div>
                  </div>
                )}
                
                {/* Streaming Content Display */}
                {isLoading && streamingContent && (
                  <div className="flex justify-start">
                    <div className="max-w-[85%] md:max-w-[80%] p-3 rounded-xl text-sm md:text-base bg-white/10 text-white/90">
                      <p className="whitespace-pre-wrap break-words">{streamingContent}</p>
                      <span className="inline-block w-2 h-4 bg-purple-400 animate-pulse ml-1" />
                    </div>
                  </div>
                )}
                
                {/* Loading indicator (only when not streaming) */}
                {isLoading && !streamingContent && !isThinking && !thinkingContent && (
                  <div className="flex justify-start">
                    <div className="bg-white/10 p-3 rounded-xl">
                      <div className="flex gap-1">
                        <span className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <span className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <span className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Structured Elements Panel - Collapsible */}
              {sessionId && (
                <div className="border-t border-white/10 bg-slate-900/70">
                  <button
                    onClick={() => setShowElementsPanel(!showElementsPanel)}
                    className="w-full flex items-center justify-between p-3 text-left hover:bg-white/5 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-purple-400" />
                      <span className="text-white/80 text-sm font-medium">Chapter Elements</span>
                      <div className="flex items-center gap-2">
                        {getSuggestionCount() > 0 && (
                          <span className="px-2 py-0.5 bg-amber-500/20 text-amber-300 text-xs rounded animate-pulse">
                            ✨ {getSuggestionCount()} new
                          </span>
                        )}
                        <span className="px-2 py-0.5 bg-purple-500/20 text-purple-300 text-xs rounded">
                          {getElementCount()}/5 confirmed
                        </span>
                      </div>
                    </div>
                    {showElementsPanel ? (
                      <ChevronUp className="w-4 h-4 text-white/40" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-white/40" />
                    )}
                  </button>
                  
                    {showElementsPanel && (
                    <div className="px-3 pb-3 space-y-2 max-h-48 overflow-y-auto">
                      {/* Overview */}
                      <ElementSlot
                        icon={<FileText className="w-3.5 h-3.5" />}
                        label="Overview"
                        value={structuredElements.overview}
                        suggestedValue={suggestedElements.overview}
                        isEditing={editingElement === 'overview'}
                        draft={elementDraft}
                        onEdit={() => {
                          setEditingElement('overview');
                          setElementDraft(suggestedElements.overview || structuredElements.overview);
                        }}
                        onSave={() => saveStructuredElement('overview', elementDraft)}
                        onCancel={() => { setEditingElement(null); setElementDraft(''); }}
                        onDraftChange={setElementDraft}
                        onConfirmSuggestion={() => confirmSuggestion('overview')}
                        onDismissSuggestion={() => dismissSuggestion('overview')}
                        onClear={() => clearElement('overview')}
                        isSaving={savingElement}
                      />

                      {/* Tone */}
                      <ElementSlot
                        icon={<Palette className="w-3.5 h-3.5" />}
                        label="Tone"
                        value={structuredElements.tone}
                        suggestedValue={suggestedElements.tone}
                        isEditing={editingElement === 'tone'}
                        draft={elementDraft}
                        onEdit={() => {
                          setEditingElement('tone');
                          setElementDraft(suggestedElements.tone || structuredElements.tone);
                        }}
                        onSave={() => saveStructuredElement('tone', elementDraft)}
                        onCancel={() => { setEditingElement(null); setElementDraft(''); }}
                        onDraftChange={setElementDraft}
                        onConfirmSuggestion={() => confirmSuggestion('tone')}
                        onDismissSuggestion={() => dismissSuggestion('tone')}
                        onClear={() => clearElement('tone')}
                        isSaving={savingElement}
                      />

                      {/* Key Events */}
                      <ElementSlot
                        icon={<List className="w-3.5 h-3.5" />}
                        label="Key Events"
                        value={structuredElements.key_events.length > 0 
                          ? `${structuredElements.key_events.length} events: ${structuredElements.key_events.slice(0, 2).join(', ')}${structuredElements.key_events.length > 2 ? '...' : ''}`
                          : ''}
                        suggestedValue={suggestedElements.key_events 
                          ? `${suggestedElements.key_events.length} events: ${suggestedElements.key_events.slice(0, 2).join(', ')}${suggestedElements.key_events.length > 2 ? '...' : ''}`
                          : undefined}
                        isEditing={editingElement === 'key_events'}
                        draft={elementDraft}
                        onEdit={() => {
                          setEditingElement('key_events');
                          const events = suggestedElements.key_events || structuredElements.key_events;
                          setElementDraft(events.join('\n'));
                        }}
                        onSave={() => saveStructuredElement('key_events', elementDraft.split('\n').filter(e => e.trim()))}
                        onCancel={() => { setEditingElement(null); setElementDraft(''); }}
                        onDraftChange={setElementDraft}
                        onConfirmSuggestion={() => confirmSuggestion('key_events')}
                        onDismissSuggestion={() => dismissSuggestion('key_events')}
                        onClear={() => clearElement('key_events')}
                        isSaving={savingElement}
                        multiline
                        placeholder="Enter each event on a new line"
                      />

                      {/* Ending */}
                      <ElementSlot
                        icon={<Flag className="w-3.5 h-3.5" />}
                        label="Ending"
                        value={structuredElements.ending}
                        suggestedValue={suggestedElements.ending}
                        isEditing={editingElement === 'ending'}
                        draft={elementDraft}
                        onEdit={() => {
                          setEditingElement('ending');
                          setElementDraft(suggestedElements.ending || structuredElements.ending);
                        }}
                        onSave={() => saveStructuredElement('ending', elementDraft)}
                        onCancel={() => { setEditingElement(null); setElementDraft(''); }}
                        onDraftChange={setElementDraft}
                        onConfirmSuggestion={() => confirmSuggestion('ending')}
                        onDismissSuggestion={() => dismissSuggestion('ending')}
                        onClear={() => clearElement('ending')}
                        isSaving={savingElement}
                      />

                      {/* Characters */}
                      <ElementSlot
                        icon={<Users className="w-3.5 h-3.5" />}
                        label="Characters"
                        value={structuredElements.characters.length > 0 
                          ? structuredElements.characters.map(c => c.character_name || c.name).join(', ')
                          : ''}
                        suggestedValue={suggestedElements.characters}
                        isEditing={editingElement === 'characters'}
                        draft={elementDraft}
                        onEdit={() => {
                          setEditingElement('characters');
                          if (suggestedElements.characters) {
                            setElementDraft(suggestedElements.characters);
                          } else {
                            setElementDraft(structuredElements.characters.map(c => 
                              `${c.character_name || c.name}: ${c.development || ''}`
                            ).join('\n'));
                          }
                        }}
                        onSave={() => {
                          const chars = elementDraft.split('\n').filter(l => l.trim()).map(line => {
                            const [name, ...rest] = line.split(':');
                            return { character_name: name.trim(), development: rest.join(':').trim() };
                          });
                          saveStructuredElement('characters', chars);
                        }}
                        onConfirmSuggestion={() => confirmSuggestion('characters')}
                        onDismissSuggestion={() => dismissSuggestion('characters')}
                        onClear={() => clearElement('characters')}
                        onCancel={() => { setEditingElement(null); setElementDraft(''); }}
                        onDraftChange={setElementDraft}
                        isSaving={savingElement}
                        multiline
                        placeholder="Format: Character Name: Their role/development"
                      />
                    </div>
                  )}
                </div>
              )}

              {/* Input Area */}
              <div className="p-3 md:p-4 border-t border-white/10 bg-slate-900/50">
                <div className="flex gap-2">
                  <textarea
                    ref={inputRef}
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Describe what you want in this chapter..."
                    className="flex-1 bg-white/10 border border-white/20 rounded-xl px-3 py-2 md:px-4 md:py-3 text-white placeholder-white/40 resize-none focus:outline-none focus:border-purple-500 text-sm md:text-base touch-manipulation"
                    rows={2}
                    disabled={isLoading}
                  />
                  <div className="flex flex-col gap-2">
                    <button
                      type="button"
                      onClick={handleSendMessage}
                      disabled={!inputValue.trim() || isLoading}
                      className="px-3 md:px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-500 active:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm touch-manipulation min-h-[44px]"
                    >
                      Send
                    </button>
                    <button
                      type="button"
                      onClick={handleExtractPlot}
                      disabled={messages.length < 2 || isExtracting || getElementCount() < 5}
                      className="px-3 md:px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-500 active:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-xs touch-manipulation min-h-[44px]"
                      title={getElementCount() < 5 ? `Confirm all 5 elements first (${getElementCount()}/5 confirmed)` : 'Extract chapter plot'}
                    >
                      {isExtracting ? 'Extracting...' : `Extract (${getElementCount()}/5)`}
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}

          {/* Review Phase */}
          {phase === 'review' && extractedPlot && (
            <div className="flex-1 overflow-y-auto p-3 md:p-6">
              <div className="max-w-2xl mx-auto space-y-4 md:space-y-6">
                {/* Edit Toggle */}
                <div className="flex justify-between items-center">
                  <span className="text-white/60 text-sm">
                    {isEditingPlot ? 'Editing mode - click Done to save changes' : 'Tap Edit to make changes'}
                  </span>
                  <button
                    type="button"
                    onClick={() => isEditingPlot ? handleSavePlotEdits() : setIsEditingPlot(true)}
                    disabled={isSavingPlotEdits}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all touch-manipulation min-h-[44px] ${
                      isEditingPlot
                        ? 'bg-purple-600 text-white'
                        : 'bg-white/10 text-white/70 hover:bg-white/20 active:bg-white/30'
                    } ${isSavingPlotEdits ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    {isSavingPlotEdits ? '💾 Saving...' : (isEditingPlot ? '✓ Done' : '✏️ Edit')}
                  </button>
                </div>

                {/* Summary */}
                <div className="bg-white/5 rounded-xl p-3 md:p-4">
                  <h3 className="text-white font-semibold mb-2 text-sm md:text-base">Chapter Summary</h3>
                  {isEditingPlot ? (
                    <textarea
                      value={extractedPlot.summary}
                      onChange={(e) => setExtractedPlot({ ...extractedPlot, summary: e.target.value })}
                      className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white text-sm md:text-base resize-none focus:outline-none focus:border-purple-500 touch-manipulation"
                      rows={4}
                    />
                  ) : (
                    <p className="text-white/80 text-sm md:text-base">{extractedPlot.summary}</p>
                  )}
                </div>

                {/* Opening */}
                <div className="bg-white/5 rounded-xl p-3 md:p-4">
                  <h3 className="text-white font-semibold mb-2 text-sm md:text-base">Opening Situation</h3>
                  {isEditingPlot ? (
                    <textarea
                      value={extractedPlot.opening_situation}
                      onChange={(e) => setExtractedPlot({ ...extractedPlot, opening_situation: e.target.value })}
                      className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white text-sm md:text-base resize-none focus:outline-none focus:border-purple-500 touch-manipulation"
                      rows={3}
                    />
                  ) : (
                    <p className="text-white/80 text-sm md:text-base">{extractedPlot.opening_situation}</p>
                  )}
                </div>

                {/* Key Events with Reordering */}
                <div className="bg-white/5 rounded-xl p-3 md:p-4">
                  <h3 className="text-white font-semibold mb-2 text-sm md:text-base">Key Events</h3>
                  {isEditingPlot ? (
                    <div className="space-y-2">
                      {extractedPlot.key_events.map((event, i) => (
                        <div 
                          key={i} 
                          className={`flex items-start gap-2 p-2 rounded-lg transition-colors ${
                            dragOverIndex === i ? 'bg-purple-500/20' : ''
                          }`}
                          draggable
                          onDragStart={() => handleDragStart(i)}
                          onDragOver={(e) => handleDragOver(e, i)}
                          onDrop={(e) => handleDrop(e, i)}
                          onDragEnd={handleDragEnd}
                        >
                          {/* Drag handle (desktop) */}
                          <div className="hidden md:flex items-center cursor-grab active:cursor-grabbing text-white/40 hover:text-white/60 mt-2">
                            <GripVertical className="w-4 h-4" />
                          </div>
                          
                          {/* Mobile reorder buttons */}
                          <div className="flex md:hidden flex-col gap-1">
                            <button
                              type="button"
                              onClick={() => moveEvent(i, 'up')}
                              disabled={i === 0}
                              className="p-1 text-white/40 hover:text-white/60 disabled:opacity-30 touch-manipulation"
                            >
                              <ChevronUp className="w-4 h-4" />
                            </button>
                            <button
                              type="button"
                              onClick={() => moveEvent(i, 'down')}
                              disabled={i === extractedPlot.key_events.length - 1}
                              className="p-1 text-white/40 hover:text-white/60 disabled:opacity-30 touch-manipulation"
                            >
                              <ChevronDown className="w-4 h-4" />
                            </button>
                          </div>
                          
                          <span className="text-purple-400 mt-2 text-sm">{i + 1}.</span>
                          <textarea
                            value={event}
                            onChange={(e) => updateEvent(i, e.target.value)}
                            className="flex-1 bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white text-sm resize-none focus:outline-none focus:border-purple-500 touch-manipulation min-h-[60px]"
                            rows={2}
                          />
                          <button
                            type="button"
                            onClick={() => removeEvent(i)}
                            className="p-2 text-red-400 hover:text-red-300 active:text-red-500 touch-manipulation min-w-[44px] min-h-[44px] flex items-center justify-center"
                          >
                            <X className="w-5 h-5" />
                          </button>
                        </div>
                      ))}
                      <button
                        type="button"
                        onClick={addEvent}
                        className="flex items-center gap-2 text-purple-400 text-sm hover:text-purple-300 active:text-purple-500 p-2 touch-manipulation"
                      >
                        <Plus className="w-4 h-4" />
                        Add Event
                      </button>
                    </div>
                  ) : (
                    <ul className="space-y-2">
                      {extractedPlot.key_events.map((event, i) => (
                        <li key={i} className="flex items-start gap-2 text-white/80 text-sm md:text-base">
                          <span className="text-purple-400 mt-0.5">{i + 1}.</span>
                          <span className="break-words">{event}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Climax & Resolution - Stack on mobile */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4">
                  <div className="bg-white/5 rounded-xl p-3 md:p-4">
                    <h3 className="text-white font-semibold mb-2 text-sm md:text-base">Climax</h3>
                    {isEditingPlot ? (
                      <textarea
                        value={extractedPlot.climax}
                        onChange={(e) => setExtractedPlot({ ...extractedPlot, climax: e.target.value })}
                        className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white text-sm resize-none focus:outline-none focus:border-purple-500 touch-manipulation"
                        rows={3}
                      />
                    ) : (
                      <p className="text-white/80 text-sm md:text-base">{extractedPlot.climax}</p>
                    )}
                  </div>
                  <div className="bg-white/5 rounded-xl p-3 md:p-4">
                    <h3 className="text-white font-semibold mb-2 text-sm md:text-base">Resolution</h3>
                    {isEditingPlot ? (
                      <textarea
                        value={extractedPlot.resolution}
                        onChange={(e) => setExtractedPlot({ ...extractedPlot, resolution: e.target.value })}
                        className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white text-sm resize-none focus:outline-none focus:border-purple-500 touch-manipulation"
                        rows={3}
                      />
                    ) : (
                      <p className="text-white/80 text-sm md:text-base">{extractedPlot.resolution}</p>
                    )}
                  </div>
                </div>

                {/* Location & Mood */}
                {(extractedPlot.location || extractedPlot.mood) && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4">
                    {extractedPlot.location && (
                      <div className="bg-white/5 rounded-xl p-3 md:p-4">
                        <h3 className="text-white font-semibold mb-2 text-sm md:text-base">Location</h3>
                        {isEditingPlot ? (
                          <input
                            type="text"
                            value={extractedPlot.location}
                            onChange={(e) => setExtractedPlot({ ...extractedPlot, location: e.target.value })}
                            className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-purple-500 touch-manipulation"
                          />
                        ) : (
                          <p className="text-white/80 text-sm md:text-base">{extractedPlot.location}</p>
                        )}
                      </div>
                    )}
                    {extractedPlot.mood && (
                      <div className="bg-white/5 rounded-xl p-3 md:p-4">
                        <h3 className="text-white font-semibold mb-2 text-sm md:text-base">Mood</h3>
                        {isEditingPlot ? (
                          <input
                            type="text"
                            value={extractedPlot.mood}
                            onChange={(e) => setExtractedPlot({ ...extractedPlot, mood: e.target.value })}
                            className="w-full bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-purple-500 touch-manipulation"
                          />
                        ) : (
                          <p className="text-white/80 text-sm md:text-base">{extractedPlot.mood}</p>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Character Arcs */}
                {extractedPlot.character_arcs && extractedPlot.character_arcs.length > 0 && (
                  <div className="bg-white/5 rounded-xl p-3 md:p-4">
                    <h3 className="text-white font-semibold mb-2 text-sm md:text-base">Character Development</h3>
                    <div className="space-y-2">
                      {extractedPlot.character_arcs.map((arc, i) => (
                        <div key={i} className="flex flex-col md:flex-row md:items-start gap-1 md:gap-2">
                          <span className="text-purple-400 font-medium text-sm whitespace-nowrap">{arc.character_name || arc.name}:</span>
                          {isEditingPlot ? (
                            <input
                              type="text"
                              value={arc.development}
                              onChange={(e) => {
                                const updatedArcs = [...extractedPlot.character_arcs];
                                updatedArcs[i] = { ...updatedArcs[i], development: e.target.value };
                                setExtractedPlot({ ...extractedPlot, character_arcs: updatedArcs });
                              }}
                              className="flex-1 bg-white/10 border border-white/20 rounded-lg px-3 py-1 text-white text-sm focus:outline-none focus:border-purple-500 touch-manipulation"
                            />
                          ) : (
                            <span className="text-white/80 text-sm">{arc.development}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* New Character Suggestions */}
                {extractedPlot.new_character_suggestions && extractedPlot.new_character_suggestions.length > 0 && (
                  <div className="bg-purple-500/10 border border-purple-500/30 rounded-xl p-3 md:p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Users className="w-4 h-4 text-purple-400" />
                      <h3 className="text-white font-semibold text-sm md:text-base">New Characters Suggested</h3>
                      <span className="px-2 py-0.5 bg-purple-500/20 text-purple-300 text-xs rounded">
                        {extractedPlot.new_character_suggestions.length} new
                      </span>
                    </div>
                    <div className="space-y-3">
                      {extractedPlot.new_character_suggestions.map((char, i) => (
                        <div key={i} className="bg-white/5 rounded-lg p-2">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-purple-300 font-medium text-sm">{char.name}</span>
                            <span className="text-xs px-2 py-0.5 bg-white/10 text-white/60 rounded">{char.role}</span>
                          </div>
                          <p className="text-white/70 text-xs">{char.description}</p>
                          {char.reason && (
                            <p className="text-white/50 text-xs mt-1 italic">Why: {char.reason}</p>
                          )}
                        </div>
                      ))}
                    </div>
                    <p className="text-purple-300/70 text-xs mt-3">
                      You'll review these characters in the next step.
                    </p>
                  </div>
                )}

                {/* Error Message */}
                {applyError && (
                  <div className="bg-red-500/20 border border-red-500/50 rounded-xl p-3 md:p-4 text-red-300 text-sm">
                    {applyError}
                  </div>
                )}

                {/* Info about what will happen */}
                {!chapterId && !existingPlot && (
                  <div className="bg-blue-500/20 border border-blue-500/50 rounded-xl p-3 md:p-4 text-blue-300 text-sm">
                    <p className="font-medium">Creating a new chapter</p>
                    <p className="text-xs md:text-sm mt-1">This plot will be used when you save the chapter.</p>
                  </div>
                )}

                {/* Actions */}
                <div className="flex flex-col md:flex-row gap-3 md:gap-4 justify-center pt-4 pb-6">
                  {/* Show Back to Chat if we have a session with messages */}
                  {(sessionId || messages.length > 0) && (
                    <button
                      type="button"
                      onClick={() => setPhase('chat')}
                      className="px-6 py-3 bg-white/10 text-white rounded-xl hover:bg-white/20 active:bg-white/30 transition-all touch-manipulation min-h-[48px] flex items-center justify-center gap-2"
                    >
                      <ChevronLeft className="w-4 h-4" />
                      Back to Chat
                    </button>
                  )}
                  {/* Show New Brainstorm only if we don't have a session */}
                  {!sessionId && messages.length === 0 && (
                    <button
                      type="button"
                      onClick={() => setPhase('select_phase')}
                      className="px-6 py-3 bg-white/10 text-white rounded-xl hover:bg-white/20 active:bg-white/30 transition-all touch-manipulation min-h-[48px] flex items-center justify-center gap-2"
                    >
                      <ChevronLeft className="w-4 h-4" />
                      New Brainstorm
                    </button>
                  )}
                  {hasNewCharacterSuggestions() ? (
                    <button
                      type="button"
                      onClick={() => setPhase('character_review')}
                      className="px-6 py-3 bg-gradient-to-r from-purple-600 to-indigo-600 text-white font-semibold rounded-xl hover:from-purple-500 hover:to-indigo-500 active:from-purple-700 active:to-indigo-700 transition-all touch-manipulation min-h-[48px] flex items-center justify-center gap-2"
                    >
                      <Users className="w-4 h-4" />
                      Next: Review Characters ({extractedPlot?.new_character_suggestions?.length})
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={handleApplyPlot}
                      disabled={isApplying}
                      className="px-6 py-3 bg-gradient-to-r from-green-600 to-emerald-600 text-white font-semibold rounded-xl hover:from-green-500 hover:to-emerald-500 active:from-green-700 active:to-emerald-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed touch-manipulation min-h-[48px]"
                    >
                      {isApplying ? 'Applying...' : chapterId ? '✓ Apply to Chapter' : '✓ Use This Plot'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Character Review Phase */}
          {phase === 'character_review' && extractedPlot && (
            <div className="flex-1 overflow-y-auto">
              <CharacterReview
                characters={getNewCharactersForReview()}
                preSelectedCharacterIds={[]}
                onComplete={(mappings) => {
                  setCharacterMappings(mappings);
                  // After character review, apply the plot with character info
                  handleApplyPlotWithCharacters(mappings);
                }}
                onBack={() => setPhase('review')}
                continueButtonText="Apply Plot with Characters →"
              />
            </div>
          )}
        </div>

        {/* Desktop Right Sidebar - Extracted Plot Preview (during chat) */}
        {phase === 'chat' && extractedPlot && (
          <div className="hidden md:block w-64 border-l border-white/10 p-4 overflow-y-auto flex-shrink-0">
            <h3 className="text-white font-semibold mb-4">Plot Preview</h3>
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-white/60">Summary:</span>
                <p className="text-white/80 line-clamp-3">{extractedPlot.summary}</p>
              </div>
              {extractedPlot.key_events.length > 0 && (
                <div>
                  <span className="text-white/60">Key Events:</span>
                  <ul className="mt-1">
                    {extractedPlot.key_events.slice(0, 3).map((event, i) => (
                      <li key={i} className="text-white/70 text-xs line-clamp-1">• {event}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
