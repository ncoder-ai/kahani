'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Sparkles, X, RotateCcw, Play, Square, Volume2,
  Trash2, Users, Settings, StopCircle,
} from 'lucide-react';

interface RoleplayActionMenuProps {
  isGenerating: boolean;
  hasTurns: boolean;
  hasLastAiTurn: boolean;
  isPlayingTTS: boolean;
  onRegenerate: () => void;
  onAutoContinue: (numTurns: number) => void;
  onStop: () => void;
  onPlayTTS: () => void;
  onDelete: () => void;
  onToggleRoster: () => void;
  onOpenSettings: () => void;
  onSubmitDirection: (direction: string) => void;
  showRoster: boolean;
}

const TAB_HIDE_MS = 3000; // Hide tab after 3s (matches story page)

export default function RoleplayActionMenu({
  isGenerating,
  hasTurns,
  hasLastAiTurn,
  isPlayingTTS,
  onRegenerate,
  onAutoContinue,
  onStop,
  onPlayTTS,
  onDelete,
  onToggleRoster,
  onOpenSettings,
  onSubmitDirection,
  showRoster,
}: RoleplayActionMenuProps) {
  const [showMenu, setShowMenu] = useState(false);
  const [showGuided, setShowGuided] = useState(false);
  const [customGuide, setCustomGuide] = useState('');
  const [isTabVisible, setIsTabVisible] = useState(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Reset the auto-hide timer for the tab
  const resetTabTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    setIsTabVisible(true);
    timerRef.current = setTimeout(() => {
      setIsTabVisible(false);
    }, TAB_HIDE_MS);
  }, []);

  const hideTab = useCallback(() => {
    setIsTabVisible(false);
  }, []);

  // Start timer on mount
  useEffect(() => {
    if (hasTurns) {
      resetTabTimer();
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [hasTurns, resetTabTimer]);

  // Keep tab visible when menu or guided panel is open; restart timer when they close
  useEffect(() => {
    if (showMenu || showGuided) {
      // Cancel hide timer while menu is open
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
      setIsTabVisible(true);
    } else {
      // Menu closed — restart hide timer
      resetTabTimer();
    }
  }, [showMenu, showGuided, resetTabTimer]);

  if (!hasTurns) return null;

  const guidedOptions = [
    { label: 'More Dialogue', prompt: 'Focus on dialogue and character conversation in the next response.' },
    { label: 'Internal Thoughts', prompt: 'Include more internal thoughts and character emotions.' },
    { label: 'Describe Setting', prompt: 'Add more environmental description and atmosphere.' },
    { label: 'Action/Movement', prompt: 'Focus on physical action and character movement.' },
    { label: 'Build Tension', prompt: 'Build dramatic tension and suspense.' },
    { label: 'Slow Down', prompt: 'Slow the pace, add more detail and sensory description to this moment.' },
  ];

  return (
    <div
      className="fixed right-0 bottom-24 z-50"
      onMouseEnter={resetTabTimer}
      onMouseLeave={() => {
        if (!showMenu && !showGuided) {
          hideTab();
        }
      }}
      onTouchStart={resetTabTimer}
    >
      {/* Menu items */}
      {showMenu && (
        <div className="absolute right-16 md:right-20 bottom-0 space-y-2 animate-fade-in">
          {/* Stop — only when generating */}
          {isGenerating && (
            <button
              onClick={() => { setShowMenu(false); onStop(); }}
              className="flex items-center gap-2 w-full px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg shadow-lg transition-all backdrop-blur-sm"
            >
              <StopCircle className="w-5 h-5" />
              <span className="text-sm font-medium">Stop</span>
            </button>
          )}

          {/* Regenerate */}
          {hasLastAiTurn && (
            <button
              onClick={() => { setShowMenu(false); onRegenerate(); }}
              disabled={isGenerating}
              className="flex items-center gap-2 w-full px-4 py-2 bg-pink-600 hover:bg-pink-700 disabled:bg-pink-800 disabled:opacity-50 text-white rounded-lg shadow-lg transition-all backdrop-blur-sm"
            >
              <RotateCcw className="w-5 h-5" />
              <span className="text-sm font-medium">Regenerate</span>
            </button>
          )}

          {/* Continue (auto-continue) */}
          <button
            onClick={() => { setShowMenu(false); onAutoContinue(1); }}
            disabled={isGenerating}
            className="flex items-center gap-2 w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:opacity-50 text-white rounded-lg shadow-lg transition-all backdrop-blur-sm"
          >
            <Play className="w-5 h-5" />
            <span className="text-sm font-medium">Continue</span>
          </button>

          {/* Guided */}
          <button
            onClick={() => {
              setShowGuided(!showGuided);
              if (!showGuided) setShowMenu(false);
            }}
            disabled={isGenerating}
            className={`flex items-center gap-2 w-full px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-800 disabled:opacity-50 text-white rounded-lg shadow-lg transition-all backdrop-blur-sm ${showGuided ? 'ring-2 ring-purple-400' : ''}`}
          >
            <Sparkles className="w-5 h-5" />
            <span className="text-sm font-medium">Guided</span>
          </button>

          {/* TTS */}
          {hasLastAiTurn && (
            <button
              onClick={() => { setShowMenu(false); onPlayTTS(); }}
              className={`flex items-center gap-2 w-full px-4 py-2 rounded-lg shadow-lg transition-all backdrop-blur-sm text-white ${
                isPlayingTTS ? 'bg-red-600 hover:bg-red-700' : 'bg-green-600 hover:bg-green-700'
              }`}
            >
              {isPlayingTTS ? <Square className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
              <span className="text-sm font-medium">{isPlayingTTS ? 'Stop TTS' : 'Play TTS'}</span>
            </button>
          )}

          {/* Delete last turn */}
          {hasLastAiTurn && (
            <button
              onClick={() => { setShowMenu(false); onDelete(); }}
              disabled={isGenerating}
              className="flex items-center gap-2 w-full px-4 py-2 bg-gray-700 hover:bg-red-600 text-gray-200 disabled:opacity-50 rounded-lg shadow-lg transition-all backdrop-blur-sm"
            >
              <Trash2 className="w-5 h-5" />
              <span className="text-sm font-medium">Delete</span>
            </button>
          )}

          {/* Divider */}
          <div className="border-t border-white/20 my-1" />

          {/* Characters */}
          <button
            onClick={() => { setShowMenu(false); onToggleRoster(); }}
            className={`flex items-center gap-2 w-full px-4 py-2 rounded-lg shadow-lg transition-all backdrop-blur-sm text-white ${
              showRoster ? 'bg-white/20' : 'bg-gray-700 hover:bg-gray-600'
            }`}
          >
            <Users className="w-5 h-5" />
            <span className="text-sm font-medium">Characters</span>
          </button>

          {/* Settings */}
          <button
            onClick={() => { setShowMenu(false); onOpenSettings(); }}
            className="flex items-center gap-2 w-full px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg shadow-lg transition-all backdrop-blur-sm"
          >
            <Settings className="w-5 h-5" />
            <span className="text-sm font-medium">Settings</span>
          </button>
        </div>
      )}

      {/* Guided options panel */}
      {showGuided && (
        <div className="fixed right-16 md:right-20 top-16 bottom-4 w-52 md:w-64 animate-fade-in z-50">
          <div className="bg-gray-900/95 backdrop-blur-md rounded-xl border border-purple-500/30 shadow-2xl overflow-hidden h-auto max-h-full flex flex-col">
            <div className="flex items-center justify-between px-3 py-2 bg-gradient-to-r from-purple-600/30 to-pink-600/30 border-b border-purple-500/20 flex-shrink-0">
              <span className="text-xs font-semibold text-purple-200">Guided Options</span>
              <button onClick={() => setShowGuided(false)} className="p-1 hover:bg-white/10 rounded transition-colors">
                <X className="w-4 h-4 text-purple-200" />
              </button>
            </div>
            <div className="p-2 space-y-1 overflow-y-auto flex-1">
              {guidedOptions.map((opt, i) => (
                <button
                  key={i}
                  onClick={() => {
                    setShowGuided(false);
                    onSubmitDirection(opt.prompt);
                  }}
                  disabled={isGenerating}
                  className="w-full text-left px-3 py-2.5 text-sm text-gray-200 hover:text-white hover:bg-purple-600/30 rounded-lg transition-all duration-150 disabled:opacity-50"
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <div className="p-2 border-t border-purple-500/20">
              <div className="text-xs text-purple-300 mb-1.5 px-1">Custom Direction</div>
              <textarea
                value={customGuide}
                onChange={(e) => setCustomGuide(e.target.value)}
                placeholder="Describe what should happen next..."
                disabled={isGenerating}
                className="w-full px-3 py-2 text-sm bg-gray-800/80 border border-purple-500/30 rounded-lg text-gray-200 placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500/50 resize-none disabled:opacity-50"
                rows={2}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey && customGuide.trim()) {
                    e.preventDefault();
                    setShowGuided(false);
                    onSubmitDirection(customGuide.trim());
                    setCustomGuide('');
                  }
                }}
              />
              <button
                onClick={() => {
                  if (customGuide.trim()) {
                    setShowGuided(false);
                    onSubmitDirection(customGuide.trim());
                    setCustomGuide('');
                  }
                }}
                disabled={isGenerating || !customGuide.trim()}
                className="w-full mt-2 px-3 py-2 text-sm font-medium text-white bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 rounded-lg transition-all duration-150 disabled:opacity-50"
              >
                Send Direction
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edge tab button */}
      <button
        onClick={() => {
          setShowMenu(!showMenu);
          if (showGuided) setShowGuided(false);
          resetTabTimer();
        }}
        onMouseEnter={resetTabTimer}
        className={
          'w-8 md:w-10 h-20 md:h-24 rounded-l-xl bg-gradient-to-r from-pink-600 to-purple-600 ' +
          'hover:from-pink-700 hover:to-purple-700 shadow-lg ' +
          'flex items-center justify-center transition-all backdrop-blur-sm ' +
          'border-l border-t border-b border-white/20 ' +
          (showMenu || showGuided || isTabVisible ? 'translate-x-0 opacity-100' : 'translate-x-6 md:translate-x-8 opacity-30 hover:translate-x-0 hover:opacity-100')
        }
        title="Actions"
      >
        {showMenu || showGuided ? (
          <X className="w-5 h-5 md:w-6 md:h-6 text-white" />
        ) : (
          <Sparkles className="w-5 h-5 md:w-6 md:h-6 text-white" />
        )}
      </button>
    </div>
  );
}
