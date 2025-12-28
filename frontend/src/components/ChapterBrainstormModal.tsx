'use client';

import React, { useState, useEffect, useRef } from 'react';
import apiClient, { StoryArc, ArcPhase, ChapterPlot } from '@/lib/api';
import StoryArcViewer from './StoryArcViewer';

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
  onPlotApplied: (plot?: ChapterPlot, sessionId?: number) => void;  // Now passes plot data back
  existingSessionId?: number;
}

export default function ChapterBrainstormModal({
  isOpen,
  storyId,
  chapterId,
  storyArc,
  onClose,
  onPlotApplied,
  existingSessionId
}: ChapterBrainstormModalProps) {
  const [sessionId, setSessionId] = useState<number | null>(existingSessionId || null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedPhase, setSelectedPhase] = useState<ArcPhase | null>(null);
  const [extractedPlot, setExtractedPlot] = useState<ChapterPlot | null>(null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [phase, setPhase] = useState<'select_phase' | 'chat' | 'review'>('select_phase');
  
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
        arcPhase?.id
      );
      setSessionId(response.session_id);
      
      // Add initial greeting
      const greeting = arcPhase 
        ? `I'll help you plan a chapter for the "${arcPhase.name}" phase of your story. This phase focuses on: ${arcPhase.description}\n\nWhat aspects of this chapter would you like to explore? Consider:\n• Key events that should happen\n• Which characters should appear\n• The emotional journey of this chapter`
        : "I'll help you plan your next chapter. What's on your mind? Tell me about:\n• What you want to happen in this chapter\n• Any characters you want to focus on\n• The mood or tone you're going for";
      
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
    console.log('[ChapterBrainstorm] Apply plot clicked', { extractedPlot: !!extractedPlot, sessionId, chapterId });
    
    if (!extractedPlot) {
      setApplyError('No plot to apply. Please extract the plot first.');
      return;
    }
    
    if (!sessionId) {
      setApplyError('Session not found. Please try again.');
      return;
    }
    
    setIsApplying(true);
    setApplyError(null);
    
    try {
      if (chapterId) {
        // Chapter exists - apply directly to the chapter
        await apiClient.applyChapterBrainstorm(storyId, sessionId, chapterId);
        console.log('[ChapterBrainstorm] Plot applied to existing chapter');
        onPlotApplied();
      } else {
        // No chapter yet - pass the plot back to the caller (ChapterWizard)
        // The caller will use this when creating the chapter
        console.log('[ChapterBrainstorm] Passing plot back to caller for new chapter');
        onPlotApplied(extractedPlot, sessionId || undefined);
      }
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

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-gradient-to-br from-slate-900 via-purple-900/50 to-slate-900 rounded-2xl w-full max-w-6xl h-[90vh] flex overflow-hidden border border-white/10">
        
        {/* Left Sidebar - Story Arc */}
        {storyArc && (
          <div className="w-64 border-r border-white/10 p-4 overflow-y-auto">
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
        <div className="flex-1 flex flex-col">
          {/* Header */}
          <div className="p-4 border-b border-white/10 flex items-center justify-between">
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
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Phase Selection */}
          {phase === 'select_phase' && (
            <div className="flex-1 p-6 overflow-y-auto">
              <div className="max-w-2xl mx-auto space-y-4">
                {storyArc?.phases.map((arcPhase) => (
                  <button
                    key={arcPhase.id}
                    onClick={() => handlePhaseSelect(arcPhase)}
                    disabled={isLoading}
                    className="w-full text-left p-4 bg-white/5 hover:bg-white/10 rounded-xl border border-white/10 hover:border-purple-500/50 transition-all"
                  >
                    <h3 className="text-white font-semibold">{arcPhase.name}</h3>
                    <p className="text-white/60 text-sm mt-1">{arcPhase.description}</p>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {arcPhase.key_events.slice(0, 3).map((event, i) => (
                        <span key={i} className="px-2 py-0.5 bg-purple-500/20 text-purple-300 text-xs rounded">
                          {event}
                        </span>
                      ))}
                    </div>
                  </button>
                ))}
                
                <button
                  onClick={() => handlePhaseSelect(null)}
                  disabled={isLoading}
                  className="w-full text-left p-4 bg-white/5 hover:bg-white/10 rounded-xl border border-dashed border-white/20 hover:border-white/40 transition-all"
                >
                  <h3 className="text-white/80 font-medium">Skip Phase Selection</h3>
                  <p className="text-white/50 text-sm mt-1">
                    Brainstorm freely without targeting a specific arc phase
                  </p>
                </button>
              </div>
            </div>
          )}

          {/* Chat Interface */}
          {phase === 'chat' && (
            <>
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.map((message, index) => (
                  <div
                    key={index}
                    className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[80%] p-3 rounded-xl ${
                        message.role === 'user'
                          ? 'bg-purple-600 text-white'
                          : 'bg-white/10 text-white/90'
                      }`}
                    >
                      <p className="whitespace-pre-wrap">{message.content}</p>
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
              <div className="p-4 border-t border-white/10">
                <div className="flex gap-2">
                  <textarea
                    ref={inputRef}
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Describe what you want in this chapter..."
                    className="flex-1 bg-white/10 border border-white/20 rounded-xl px-4 py-3 text-white placeholder-white/40 resize-none focus:outline-none focus:border-purple-500"
                    rows={2}
                    disabled={isLoading}
                  />
                  <div className="flex flex-col gap-2">
                    <button
                      onClick={handleSendMessage}
                      disabled={!inputValue.trim() || isLoading}
                      className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Send
                    </button>
                    <button
                      onClick={handleExtractPlot}
                      disabled={messages.length < 2 || isExtracting}
                      className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                    >
                      {isExtracting ? 'Extracting...' : 'Extract Plot'}
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}

          {/* Review Phase */}
          {phase === 'review' && extractedPlot && (
            <div className="flex-1 overflow-y-auto p-6">
              <div className="max-w-2xl mx-auto space-y-6">
                {/* Summary */}
                <div className="bg-white/5 rounded-xl p-4">
                  <h3 className="text-white font-semibold mb-2">Chapter Summary</h3>
                  <p className="text-white/80">{extractedPlot.summary}</p>
                </div>

                {/* Opening */}
                <div className="bg-white/5 rounded-xl p-4">
                  <h3 className="text-white font-semibold mb-2">Opening Situation</h3>
                  <p className="text-white/80">{extractedPlot.opening_situation}</p>
                </div>

                {/* Key Events */}
                <div className="bg-white/5 rounded-xl p-4">
                  <h3 className="text-white font-semibold mb-2">Key Events</h3>
                  <ul className="space-y-2">
                    {extractedPlot.key_events.map((event, i) => (
                      <li key={i} className="flex items-start gap-2 text-white/80">
                        <span className="text-purple-400 mt-1">•</span>
                        {event}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Climax & Resolution */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-white/5 rounded-xl p-4">
                    <h3 className="text-white font-semibold mb-2">Climax</h3>
                    <p className="text-white/80">{extractedPlot.climax}</p>
                  </div>
                  <div className="bg-white/5 rounded-xl p-4">
                    <h3 className="text-white font-semibold mb-2">Resolution</h3>
                    <p className="text-white/80">{extractedPlot.resolution}</p>
                  </div>
                </div>

                {/* Character Arcs */}
                {extractedPlot.character_arcs.length > 0 && (
                  <div className="bg-white/5 rounded-xl p-4">
                    <h3 className="text-white font-semibold mb-2">Character Development</h3>
                    <div className="space-y-2">
                      {extractedPlot.character_arcs.map((arc, i) => (
                        <div key={i} className="flex items-start gap-2">
                          <span className="text-purple-400 font-medium">{arc.character_name}:</span>
                          <span className="text-white/80">{arc.development}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* New Character Suggestions */}
                {extractedPlot.new_character_suggestions.length > 0 && (
                  <div className="bg-white/5 rounded-xl p-4">
                    <h3 className="text-white font-semibold mb-2">Suggested New Characters</h3>
                    <div className="space-y-3">
                      {extractedPlot.new_character_suggestions.map((char, i) => (
                        <div key={i} className="bg-white/5 rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-white font-medium">{char.name}</span>
                            <span className="px-2 py-0.5 bg-purple-500/30 text-purple-300 text-xs rounded">
                              {char.role}
                            </span>
                          </div>
                          <p className="text-white/60 text-sm">{char.description}</p>
                          <p className="text-white/40 text-xs mt-1">Why: {char.reason}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Error Message */}
                {applyError && (
                  <div className="bg-red-500/20 border border-red-500/50 rounded-xl p-4 text-red-300">
                    {applyError}
                  </div>
                )}

                {/* Info about what will happen */}
                {!chapterId && (
                  <div className="bg-blue-500/20 border border-blue-500/50 rounded-xl p-4 text-blue-300">
                    <p className="font-medium">Creating a new chapter</p>
                    <p className="text-sm mt-1">This plot will be used when you save the chapter. Click "Use This Plot" to continue.</p>
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-4 justify-center pt-4">
                  <button
                    onClick={() => setPhase('chat')}
                    className="px-6 py-3 bg-white/10 text-white rounded-xl hover:bg-white/20 transition-all"
                  >
                    ← Back to Chat
                  </button>
                  <button
                    onClick={handleApplyPlot}
                    disabled={isApplying}
                    className="px-6 py-3 bg-gradient-to-r from-green-600 to-emerald-600 text-white font-semibold rounded-xl hover:from-green-500 hover:to-emerald-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isApplying ? 'Applying...' : chapterId ? '✓ Apply to Chapter' : '✓ Use This Plot'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right Sidebar - Extracted Plot Preview (during chat) */}
        {phase === 'chat' && extractedPlot && (
          <div className="w-64 border-l border-white/10 p-4 overflow-y-auto">
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

