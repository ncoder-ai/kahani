'use client';

import { useState, useRef, useEffect } from 'react';
import BrainstormMessage from './BrainstormMessage';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

interface BrainstormChatProps {
  messages: Message[];
  onSendMessage: (message: string, generateIdeas?: boolean) => Promise<void>;
  onRefineIdeas: () => void;
  isLoading: boolean;
}

export default function BrainstormChat({ 
  messages, 
  onSendMessage, 
  onRefineIdeas,
  isLoading 
}: BrainstormChatProps) {
  const [inputMessage, setInputMessage] = useState('');
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!inputMessage.trim() || isSending) return;

    setIsSending(true);
    try {
      // First user message should trigger structured idea generation
      const shouldGenerateIdeas = messages.length === 0; // No messages yet - this is the first one
      
      console.log('[BrainstormChat] Sending message, shouldGenerateIdeas:', shouldGenerateIdeas, 'messages.length:', messages.length);
      
      await onSendMessage(inputMessage, shouldGenerateIdeas);
      setInputMessage('');
    } catch (error) {
      console.error('Failed to send message:', error);
      alert('Failed to send message. Please try again.');
    } finally {
      setIsSending(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const canRefine = messages.length >= 4; // At least 2 exchanges

  return (
    <div className="flex flex-col h-full">
      {/* Messages Area - Full height, no header */}
      <div className="flex-1 overflow-y-auto p-3 md:p-6 space-y-3 md:space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-8 md:py-12 px-4">
            <div className="text-4xl md:text-6xl mb-3 md:mb-4">💡</div>
            <h3 className="text-lg md:text-xl font-semibold text-white mb-2">
              Let's Brainstorm Your Story!
            </h3>
            <p className="text-white/70 text-sm md:text-base max-w-md mx-auto">
              Tell me about your story idea. What excites you? What kind of story do you want to create?
            </p>
          </div>
        )}
        
        {messages.map((message, index) => (
          <BrainstormMessage
            key={index}
            role={message.role}
            content={message.content}
            timestamp={message.timestamp}
            onSelectIdea={(idea) => {
              // Auto-fill the input with the selected idea
              setInputMessage(idea);
            }}
          />
        ))}
        
        {isSending && (
          <div className="flex justify-start mb-4">
            <div className="bg-white/10 rounded-2xl p-4 border border-white/20">
              <div className="flex items-center space-x-2">
                <div className="text-2xl">🤖</div>
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-white/60 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-2 h-2 bg-white/60 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-2 h-2 bg-white/60 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area - Compact on mobile */}
      <div className="bg-white/10 backdrop-blur-md border-t border-white/20 p-2 md:p-4">
        <div className="flex items-end space-x-2 md:space-x-3">
          <textarea
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Share your story ideas..."
            rows={2}
            disabled={isSending}
            className="flex-1 p-2 md:p-3 bg-white/10 border border-white/30 rounded-lg md:rounded-xl text-sm md:text-base text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!inputMessage.trim() || isSending}
            className="px-4 md:px-6 py-2 md:py-3 theme-btn-primary rounded-lg md:rounded-xl font-semibold text-sm md:text-base transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </div>
        
        {canRefine && (
          <div className="mt-3 md:mt-4">
            <button
              onClick={onRefineIdeas}
              disabled={isLoading}
              className="w-full px-4 md:px-8 py-2.5 md:py-3 bg-gradient-to-r from-green-500 to-emerald-600 text-white rounded-lg md:rounded-xl hover:from-green-600 hover:to-emerald-700 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed font-semibold text-sm md:text-base"
            >
              ✨ Refine Ideas & Extract Elements
            </button>
            <p className="text-white/60 text-xs md:text-sm mt-1.5 md:mt-2 text-center hidden md:block">
              Ready to structure your ideas? AI will extract story elements from this conversation.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

