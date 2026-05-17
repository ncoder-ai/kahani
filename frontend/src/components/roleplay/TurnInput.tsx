'use client';

import { useState, useRef, useCallback, useEffect, useImperativeHandle, forwardRef } from 'react';
import { Send, Users, Sparkles } from 'lucide-react';

export type InputMode = 'character' | 'narration' | 'direction';

export interface TurnInputHandle {
  setText: (text: string) => void;
}

interface TurnInputProps {
  playerCharacterName?: string;
  isGroupMode: boolean;
  isGenerating: boolean;
  autoContinueEnabled: boolean;
  maxAutoTurns: number;
  onSubmit: (content: string, mode: InputMode) => void;
  onAutoContinue: (numTurns: number) => void;
  onAutoPlayer?: () => void;
}

const MODE_LABELS: Record<InputMode, { label: string; placeholder: string; prefix?: string }> = {
  character: { label: 'In-Character', placeholder: 'What do you say or do...' },
  narration: { label: 'Narrate', placeholder: 'Describe what happens in the scene...' },
  direction: { label: 'Direct', placeholder: 'Give direction for how the scene should go...' },
};

const TurnInput = forwardRef<TurnInputHandle, TurnInputProps>(function TurnInput({
  playerCharacterName,
  isGroupMode,
  isGenerating,
  autoContinueEnabled,
  maxAutoTurns,
  onSubmit,
  onAutoContinue,
  onAutoPlayer,
}, ref) {
  const [mode, setMode] = useState<InputMode>('character');
  const [text, setText] = useState('');
  const [autoTurnCount, setAutoTurnCount] = useState(2);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Expose setText to parent via ref
  useImperativeHandle(ref, () => ({
    setText: (newText: string) => {
      setText(newText);
    },
  }), []);

  const info = MODE_LABELS[mode];
  const prefix = mode === 'character' && playerCharacterName ? `${playerCharacterName}: ` : '';

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
  }, [text]);

  const handleSubmit = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || isGenerating) return;
    onSubmit(trimmed, mode);
    setText('');
    // Reset height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [text, mode, isGenerating, onSubmit]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  return (
    <div className="border-t border-white/10 bg-black/40 backdrop-blur-md">
      {/* Mode tabs */}
      <div className="flex items-center gap-1 px-4 pt-3 pb-1">
        {(Object.keys(MODE_LABELS) as InputMode[]).map(m => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`px-3 py-1 text-xs rounded-full transition-colors ${
              mode === m
                ? 'bg-white/15 text-white font-medium'
                : 'text-white/40 hover:text-white/60 hover:bg-white/5'
            }`}
          >
            {MODE_LABELS[m].label}
          </button>
        ))}

        {/* Auto-continue (group only) */}
        {isGroupMode && autoContinueEnabled && (
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => !isGenerating && onAutoContinue(autoTurnCount)}
              disabled={isGenerating}
              className="flex items-center gap-1.5 px-3 py-1 text-xs rounded-full bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 transition-colors disabled:opacity-40"
            >
              <Users className="w-3.5 h-3.5" />
              Let them talk
            </button>
            <select
              value={autoTurnCount}
              onChange={e => setAutoTurnCount(Number(e.target.value))}
              className="bg-white/5 border border-white/10 rounded-md text-xs text-white/60 px-1.5 py-0.5"
            >
              {Array.from({ length: Math.min(maxAutoTurns, 5) }, (_, i) => i + 1).map(n => (
                <option key={n} value={n}>{n} turn{n > 1 ? 's' : ''}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="px-4 pb-3 pt-1">
        <div className="flex items-end gap-2">
          <div className="flex-1 relative">
            {prefix && (
              <span className="absolute left-3 top-2.5 text-sm text-blue-400/60 pointer-events-none">
                {prefix}
              </span>
            )}
            <textarea
              ref={textareaRef}
              value={text}
              onChange={e => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={info.placeholder}
              disabled={isGenerating}
              rows={1}
              className={`w-full bg-white/5 border border-white/15 rounded-xl text-sm text-white/90 placeholder:text-white/25 resize-none focus:outline-none focus:border-white/30 transition-colors disabled:opacity-40 py-2.5 pr-3 ${
                prefix ? 'pl-[calc(0.75rem+var(--prefix-w,0px))]' : 'pl-3'
              } ${mode === 'direction' ? 'italic' : ''}`}
              style={prefix ? { paddingLeft: `${prefix.length * 0.5 + 0.75}rem` } : undefined}
            />
          </div>
          {onAutoPlayer && (
            <button
              onClick={onAutoPlayer}
              disabled={isGenerating || !!text.trim()}
              title="Auto-generate your turn"
              className="p-2.5 rounded-xl bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 disabled:opacity-30 transition-all flex-shrink-0"
            >
              <Sparkles className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={handleSubmit}
            disabled={!text.trim() || isGenerating}
            className="p-2.5 rounded-xl theme-btn-primary disabled:opacity-30 transition-opacity flex-shrink-0"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        <div className="text-[10px] text-white/20 mt-1 px-1">
          Enter to send · Shift+Enter for new line
        </div>
      </div>
    </div>
  );
});

export default TurnInput;
