'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import apiClient, { StoryArc, ArcPhase, ChapterPlot } from '@/lib/api';
import StoryArcViewer from './StoryArcViewer';
import { GripVertical, X, Plus, ChevronLeft, ChevronDown, ChevronUp } from 'lucide-react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

interface ChapterBrainstormModalProps {
  isOpen: boolean;
  storyId: number;
  chapterId?: number;
  storyArc?: StoryArc | null;
  onClose: () => void;
  onPlotApplied: (plot?: ChapterPlot, sessionId?: number, arcPhaseId?: string) => void;
  existingSessionId?: number;
  existingPlot?: ChapterPlot | null;
  existingArcPhaseId?: string;
}

export default function ChapterBrainstormModal({
  isOpen,
  storyId,
  chapterId,
  storyArc,
  onClose,
  onPlotApplied,
  existingSessionId,
  existingPlot,
  existingArcPhaseId
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
  const [phase, setPhase] = useState<'select_phase' | 'chat' | 'review'>(existingPlot ? 'review' : 'select_phase');
  const [isEditingPlot, setIsEditingPlot] = useState(false);
  const [showArcSidebar, setShowArcSidebar] = useState(false);
  
  // Drag state for reordering
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

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
    } catch (error) {
      console.error('Failed to load session:', error);
    }
  };

  const handlePhaseSelect = async (arcPhase: ArcPhase | null) => {
    setSelectedPhase(arcPhase);
    setIsLoading(true);
    
    try {
      const response = await apiClient.createChapterBrainstormSession(
        storyId, 
        arcPhase?.id,
        chapterId
      );
      setSessionId(response.session_id);
      
      const chapterContext = chapterId ? 'this chapter' : 'your next chapter';
      const greeting = arcPhase 
        ? `I'll help you plan ${chapterContext} for the "${arcPhase.name}" phase of your story. This phase focuses on: ${arcPhase.description}\n\nWhat aspects of this chapter would you like to explore? Consider:\n• Key events that should happen\n• Which characters should appear\n• The emotional journey of this chapter`
        : `I'll help you plan ${chapterContext}. What's on your mind? Tell me about:\n• What you want to happen in this chapter\n• Any characters you want to focus on\n• The mood or tone you're going for`;
      
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
    
    try {
      const response = await apiClient.sendChapterBrainstormMessage(
        storyId,
        sessionId,
        userMessage
      );
      setMessages(prev => [...prev, { role: 'assistant', content: response.ai_response }]);
    } catch (error) {
      console.error('Failed to send message:', error);
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: 'Sorry, I encountered an error. Please try again.' 
      }]);
    } finally {
      setIsLoading(false);
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
            {phase === 'select_phase' && 'Select Arc Phase'}
            {phase === 'chat' && 'Brainstorm'}
            {phase === 'review' && 'Review Plot'}
          </h2>
          {storyArc && (
            <button
              onClick={() => setShowArcSidebar(!showArcSidebar)}
              className="p-2 text-purple-400 hover:text-purple-300 touch-manipulation"
            >
              {showArcSidebar ? 'Hide Arc' : 'Arc'}
            </button>
          )}
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

        {/* Desktop Left Sidebar - Story Arc */}
        {storyArc && (
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
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Desktop Header */}
          <div className="hidden md:flex p-4 border-b border-white/10 items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-white">
                {phase === 'select_phase' && 'Select Arc Phase'}
                {phase === 'chat' && 'Chapter Brainstorm'}
                {phase === 'review' && 'Review Chapter Plot'}
              </h2>
              <p className="text-white/60 text-sm">
                {phase === 'select_phase' && 'Choose which part of your story this chapter belongs to'}
                {phase === 'chat' && 'Discuss your chapter ideas with AI'}
                {phase === 'review' && 'Review and edit the extracted chapter plot'}
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-white/60 hover:text-white p-2"
            >
              <X className="w-6 h-6" />
            </button>
          </div>

          {/* Phase Selection */}
          {phase === 'select_phase' && (
            <div className="flex-1 p-4 md:p-6 overflow-y-auto">
              <div className="max-w-2xl mx-auto space-y-3 md:space-y-4">
                {storyArc?.phases.map((arcPhase) => (
                  <button
                    key={arcPhase.id}
                    onClick={() => handlePhaseSelect(arcPhase)}
                    disabled={isLoading}
                    className="w-full text-left p-3 md:p-4 bg-white/5 hover:bg-white/10 active:bg-white/15 rounded-xl border border-white/10 hover:border-purple-500/50 transition-all touch-manipulation"
                  >
                    <h3 className="text-white font-semibold text-sm md:text-base">{arcPhase.name}</h3>
                    <p className="text-white/60 text-xs md:text-sm mt-1 line-clamp-2">{arcPhase.description}</p>
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
                  </button>
                ))}
                
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

          {/* Chat Interface */}
          {phase === 'chat' && (
            <>
              <div className="flex-1 overflow-y-auto p-3 md:p-4 space-y-3 md:space-y-4">
                {messages.map((message, index) => (
                  <div
                    key={index}
                    className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[85%] md:max-w-[80%] p-3 rounded-xl text-sm md:text-base ${
                        message.role === 'user'
                          ? 'bg-purple-600 text-white'
                          : 'bg-white/10 text-white/90'
                      }`}
                    >
                      <p className="whitespace-pre-wrap break-words">{message.content}</p>
                    </div>
                  </div>
                ))}
                
                {isLoading && (
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
                      disabled={messages.length < 2 || isExtracting}
                      className="px-3 md:px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-500 active:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-xs touch-manipulation min-h-[44px]"
                    >
                      {isExtracting ? '...' : 'Extract'}
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
                    {isEditingPlot ? 'Editing mode - changes will be saved when you apply' : 'Tap Edit to make changes'}
                  </span>
                  <button
                    type="button"
                    onClick={() => setIsEditingPlot(!isEditingPlot)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all touch-manipulation min-h-[44px] ${
                      isEditingPlot 
                        ? 'bg-purple-600 text-white' 
                        : 'bg-white/10 text-white/70 hover:bg-white/20 active:bg-white/30'
                    }`}
                  >
                    {isEditingPlot ? '✓ Done' : '✏️ Edit'}
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
                          <span className="text-purple-400 font-medium text-sm">{arc.character_name}:</span>
                          <span className="text-white/80 text-sm">{arc.development}</span>
                        </div>
                      ))}
                    </div>
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
                  {sessionId ? (
                    <button
                      type="button"
                      onClick={() => setPhase('chat')}
                      className="px-6 py-3 bg-white/10 text-white rounded-xl hover:bg-white/20 active:bg-white/30 transition-all touch-manipulation min-h-[48px] flex items-center justify-center gap-2"
                    >
                      <ChevronLeft className="w-4 h-4" />
                      Back to Chat
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setPhase('select_phase')}
                      className="px-6 py-3 bg-white/10 text-white rounded-xl hover:bg-white/20 active:bg-white/30 transition-all touch-manipulation min-h-[48px] flex items-center justify-center gap-2"
                    >
                      <ChevronLeft className="w-4 h-4" />
                      New Brainstorm
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={handleApplyPlot}
                    disabled={isApplying}
                    className="px-6 py-3 bg-gradient-to-r from-green-600 to-emerald-600 text-white font-semibold rounded-xl hover:from-green-500 hover:to-emerald-500 active:from-green-700 active:to-emerald-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed touch-manipulation min-h-[48px]"
                  >
                    {isApplying ? 'Applying...' : chapterId ? '✓ Apply to Chapter' : '✓ Use This Plot'}
                  </button>
                </div>
              </div>
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
