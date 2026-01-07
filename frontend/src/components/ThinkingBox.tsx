'use client';

import { useState, useEffect, useRef } from 'react';
import { ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline';

interface ThinkingBoxProps {
  thinking: string;           // Accumulated thinking content
  isThinking: boolean;        // True while still streaming
  showContent: boolean;       // From user setting: show_thinking_content
}

/**
 * ThinkingBox - Displays LLM reasoning/thinking content
 * 
 * Two modes based on showContent setting:
 * 1. showContent=true: Collapsible box with live streaming thinking content
 * 2. showContent=false: Simple "Thinking..." indicator
 */
export default function ThinkingBox({ thinking, isThinking, showContent }: ThinkingBoxProps) {
  const [isExpanded, setIsExpanded] = useState(true); // Auto-expand when thinking starts
  const [userManuallyToggled, setUserManuallyToggled] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  
  // Auto-expand when thinking starts (if user hasn't manually toggled)
  useEffect(() => {
    if (isThinking && !userManuallyToggled) {
      setIsExpanded(true);
    }
  }, [isThinking, userManuallyToggled]);
  
  // Auto-collapse when thinking ends (if user hasn't manually expanded)
  useEffect(() => {
    if (!isThinking && thinking && !userManuallyToggled) {
      // Small delay before collapsing so user can see the final state
      const timer = setTimeout(() => {
        setIsExpanded(false);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isThinking, thinking, userManuallyToggled]);
  
  // Auto-scroll to bottom as content streams in
  useEffect(() => {
    if (isExpanded && contentRef.current && isThinking) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [thinking, isExpanded, isThinking]);
  
  // Handle manual toggle
  const handleToggle = () => {
    setUserManuallyToggled(true);
    setIsExpanded(!isExpanded);
  };
  
  // Reset manual toggle when thinking starts fresh
  useEffect(() => {
    if (isThinking && thinking === '') {
      setUserManuallyToggled(false);
    }
  }, [isThinking, thinking]);
  
  // Don't render if no thinking content and not currently thinking
  if (!thinking && !isThinking) {
    return null;
  }
  
  // Mode 2: Simple "Thinking..." indicator (showContent=false)
  if (!showContent) {
    if (!isThinking) return null; // Hide when done thinking
    
    return (
      <div className="thinking-indicator">
        <div className="thinking-indicator-content">
          <div className="thinking-spinner" />
          <span>Thinking...</span>
        </div>
        
        <style jsx>{`
          .thinking-indicator {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 12px 16px;
            margin-bottom: 16px;
            background: rgba(139, 92, 246, 0.1);
            border: 1px solid rgba(139, 92, 246, 0.2);
            border-radius: 8px;
          }
          
          .thinking-indicator-content {
            display: flex;
            align-items: center;
            gap: 10px;
            color: rgba(139, 92, 246, 0.9);
            font-size: 14px;
            font-weight: 500;
          }
          
          .thinking-spinner {
            width: 16px;
            height: 16px;
            border: 2px solid rgba(139, 92, 246, 0.3);
            border-top-color: rgba(139, 92, 246, 0.9);
            border-radius: 50%;
            animation: spin 1s linear infinite;
          }
          
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }
  
  // Mode 1: Full collapsible box with streaming content
  const charCount = thinking.length;
  
  return (
    <div className={`thinking-box ${isThinking ? 'is-thinking' : 'done-thinking'}`}>
      {/* Header - always visible */}
      <button 
        className="thinking-header"
        onClick={handleToggle}
        aria-expanded={isExpanded}
      >
        <div className="thinking-title">
          {isThinking && <div className="thinking-spinner" />}
          <span>{isThinking ? 'Thinking...' : `View Thinking (${charCount.toLocaleString()} chars)`}</span>
        </div>
        {isExpanded ? (
          <ChevronUpIcon className="toggle-icon" />
        ) : (
          <ChevronDownIcon className="toggle-icon" />
        )}
      </button>
      
      {/* Content - collapsible */}
      {isExpanded && (
        <div 
          ref={contentRef}
          className="thinking-content"
        >
          <pre>{thinking || (isThinking ? 'Processing...' : '')}</pre>
        </div>
      )}
      
      <style jsx>{`
        .thinking-box {
          margin-bottom: 16px;
          border-radius: 8px;
          overflow: hidden;
          background: rgba(30, 30, 40, 0.6);
          border: 1px solid rgba(139, 92, 246, 0.2);
          transition: border-color 0.3s ease;
        }
        
        .thinking-box.is-thinking {
          border-color: rgba(139, 92, 246, 0.4);
          box-shadow: 0 0 12px rgba(139, 92, 246, 0.1);
        }
        
        .thinking-box.done-thinking {
          background: rgba(30, 30, 40, 0.4);
        }
        
        .thinking-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          width: 100%;
          padding: 10px 14px;
          background: transparent;
          border: none;
          cursor: pointer;
          color: rgba(139, 92, 246, 0.9);
          font-size: 13px;
          font-weight: 500;
          transition: background 0.2s ease;
        }
        
        .thinking-header:hover {
          background: rgba(139, 92, 246, 0.1);
        }
        
        .thinking-title {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        
        .thinking-spinner {
          width: 14px;
          height: 14px;
          border: 2px solid rgba(139, 92, 246, 0.3);
          border-top-color: rgba(139, 92, 246, 0.9);
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }
        
        .toggle-icon {
          width: 16px;
          height: 16px;
          opacity: 0.7;
        }
        
        .thinking-content {
          max-height: 300px;
          overflow-y: auto;
          padding: 12px 14px;
          border-top: 1px solid rgba(139, 92, 246, 0.15);
          background: rgba(0, 0, 0, 0.2);
        }
        
        .thinking-content pre {
          margin: 0;
          font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', monospace;
          font-size: 12px;
          line-height: 1.6;
          color: rgba(200, 200, 220, 0.8);
          white-space: pre-wrap;
          word-break: break-word;
        }
        
        /* Scrollbar styling */
        .thinking-content::-webkit-scrollbar {
          width: 6px;
        }
        
        .thinking-content::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 0.2);
        }
        
        .thinking-content::-webkit-scrollbar-thumb {
          background: rgba(139, 92, 246, 0.3);
          border-radius: 3px;
        }
        
        .thinking-content::-webkit-scrollbar-thumb:hover {
          background: rgba(139, 92, 246, 0.5);
        }
        
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

