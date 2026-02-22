'use client';

import { memo } from 'react';
import { Sparkles } from 'lucide-react';
import type { RoleplayTurn, RoleplayCharacter } from '@/lib/api/roleplay';
import SceneContentDisplay from '@/components/SceneContentDisplay';

interface TurnDisplayProps {
  turn: RoleplayTurn;
  characters: RoleplayCharacter[];
  playerCharacterName?: string;
  isLastAiTurn: boolean;
  isStreaming?: boolean;
  streamingContent?: string;
  onRegenerate?: () => void;
  onEdit?: (turn: RoleplayTurn) => void;
  onDelete?: (turn: RoleplayTurn) => void;
  onPlayTTS?: (turn: RoleplayTurn) => void;
  isPlayingTTS?: boolean;
  onImage?: (turn: RoleplayTurn) => void;
  userSettings?: any;
  // Edit mode
  isEditing?: boolean;
  editContent?: string;
  onEditChange?: (content: string) => void;
  onEditSave?: () => void;
  onEditCancel?: () => void;
}

// Character color palette
const CHAR_STYLES = [
  { bg: 'bg-blue-500/30', border: 'border-blue-400/40', text: 'text-blue-300' },
  { bg: 'bg-emerald-500/30', border: 'border-emerald-400/40', text: 'text-emerald-300' },
  { bg: 'bg-amber-500/30', border: 'border-amber-400/40', text: 'text-amber-300' },
  { bg: 'bg-purple-500/30', border: 'border-purple-400/40', text: 'text-purple-300' },
  { bg: 'bg-rose-500/30', border: 'border-rose-400/40', text: 'text-rose-300' },
  { bg: 'bg-cyan-500/30', border: 'border-cyan-400/40', text: 'text-cyan-300' },
  { bg: 'bg-orange-500/30', border: 'border-orange-400/40', text: 'text-orange-300' },
  { bg: 'bg-lime-500/30', border: 'border-lime-400/40', text: 'text-lime-300' },
];

function getCharStyle(name: string, characters: RoleplayCharacter[]) {
  const idx = characters.findIndex(c => c.name === name);
  return CHAR_STYLES[idx >= 0 ? idx % CHAR_STYLES.length : 0];
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function CharAvatar({ name, characters }: { name: string; characters: RoleplayCharacter[] }) {
  const style = getCharStyle(name, characters);
  return (
    <div className={`w-7 h-7 rounded-full ${style.bg} border ${style.border} flex items-center justify-center font-semibold ${style.text} text-[10px] flex-shrink-0`} title={name}>
      {getInitials(name)}
    </div>
  );
}

/**
 * Strip character name from the start of section text.
 * Handles multiple LLM patterns:
 *   1. Full name on its own line: "Radhika Sharma\n..."
 *   2. First name on its own line: "Radhika\n..."
 *   3. Full name starting prose: "Radhika Sharma's eyes widen..." → "Her eyes widen..."
 *   4. First name starting prose: "Radhika's eyes widen..." → "Her eyes widen..."
 *   5. Markdown headings: "## Radhika Sharma\n..." or "# Opening Scene\n..."
 */
function stripLeadingName(text: string, charNames: string[]): string {
  let result = text;

  // Strip markdown headings (# or ##) at the start — these are formatting artifacts
  result = result.replace(/^\s*#{1,3}\s+[^\n]*\n+/g, '');

  for (const name of charNames) {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const parts = name.trim().split(/\s+/);
    const firstName = parts[0];
    const escapedFirst = firstName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    // Pattern 1: Full name on its own line
    const fullLinePattern = new RegExp(`^\\s*${escaped}\\s*\\n+`, 'i');
    const replaced1 = result.replace(fullLinePattern, '');
    if (replaced1 !== result) { result = replaced1; break; }

    // Pattern 2: First name on its own line (only if multi-word name)
    if (parts.length > 1) {
      const firstLinePattern = new RegExp(`^\\s*${escapedFirst}\\s*\\n+`, 'i');
      const replaced2 = result.replace(firstLinePattern, '');
      if (replaced2 !== result) { result = replaced2; break; }
    }

    // Pattern 3: Full name possessive — "Radhika Sharma's eyes widen..." → "Eyes widen..."
    const fullPossPattern = new RegExp(`^\\s*${escaped}'s\\s+`, 'i');
    if (fullPossPattern.test(result)) {
      result = result.replace(fullPossPattern, '').replace(/^./, c => c.toUpperCase());
      break;
    }

    // Pattern 4: First name possessive — "Radhika's eyes widen..." → "Eyes widen..."
    const firstPossPattern = new RegExp(`^\\s*${escapedFirst}'s\\s+`, 'i');
    if (firstPossPattern.test(result)) {
      result = result.replace(firstPossPattern, '').replace(/^./, c => c.toUpperCase());
      break;
    }

    // Pattern 5: Full name then verb — "Radhika Sharma turns..." → "Turns..."
    const fullVerbPattern = new RegExp(`^\\s*${escaped}\\s+(?=[a-z])`, 'i');
    if (fullVerbPattern.test(result)) {
      result = result.replace(fullVerbPattern, '').replace(/^./, c => c.toUpperCase());
      break;
    }

    // Pattern 6: First name then verb — "Radhika turns..." → "Turns..."
    const firstVerbPattern = new RegExp(`^\\s*${escapedFirst}\\s+(?=[a-z])`, 'i');
    if (firstVerbPattern.test(result)) {
      result = result.replace(firstVerbPattern, '').replace(/^./, c => c.toUpperCase());
      break;
    }
  }

  return result;
}

interface ContentSection {
  characterName: string | null;
  text: string;
}

function parseCharacterSections(content: string, characters: RoleplayCharacter[]): ContentSection[] {
  const charNames = characters.filter(c => !c.is_player).map(c => c.name);
  if (charNames.length === 0) return [{ characterName: null, text: content }];

  const escapedNames = charNames.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  // Match **Name**, ## Name, or **Name** embedded mid-line (e.g. "...text\n\n**Name** sits on...")
  const nameGroup = escapedNames.join('|');
  const pattern = new RegExp(`^\\s*(?:\\*\\*(${nameGroup})\\*\\*|#{1,3}\\s+(${nameGroup}))\\s*\\n?`, 'gm');
  const sections: ContentSection[] = [];
  let lastIdx = 0;
  let lastChar: string | null = null;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(content)) !== null) {
    if (match.index > lastIdx) {
      const text = content.slice(lastIdx, match.index);
      if (text.trim()) {
        sections.push({ characterName: lastChar, text: stripLeadingName(text, charNames) });
      }
    }
    lastChar = match[1] || match[2];
    lastIdx = match.index + match[0].length;
  }

  const remaining = content.slice(lastIdx);
  if (remaining.trim()) {
    sections.push({ characterName: lastChar, text: stripLeadingName(remaining, charNames) });
  }

  if (sections.length === 0) {
    return [{ characterName: null, text: stripLeadingName(content, charNames) }];
  }
  return sections;
}

/**
 * Detect which character is speaking when there are no **Name** headers.
 */
function detectSpeaker(content: string, characters: RoleplayCharacter[]): RoleplayCharacter | null {
  const aiChars = characters.filter(c => !c.is_player && c.is_active);
  if (aiChars.length === 1) return aiChars[0];
  if (aiChars.length > 1) {
    const earlyContent = content.toLowerCase().slice(0, 200);
    for (const c of aiChars) {
      if (earlyContent.includes(c.name.toLowerCase())) return c;
    }
  }
  return null;
}

/**
 * Process AI turn content: parse character sections, strip names,
 * and return cleaned content ready for SceneDisplay.
 * Also returns the detected character name for the avatar.
 */
function processAiContent(content: string, characters: RoleplayCharacter[]): { cleanedContent: string; speakerName: string | null } {
  const sections = parseCharacterSections(content, characters);

  if (sections.length <= 1) {
    const parsedName = sections.length === 1 ? sections[0].characterName : null;
    const parsedText = sections.length === 1 ? sections[0].text.trim() : content;

    if (parsedName) {
      return { cleanedContent: parsedText, speakerName: parsedName };
    }

    const speaker = detectSpeaker(parsedText, characters);
    return { cleanedContent: parsedText, speakerName: speaker?.name || null };
  }

  // Multiple sections — rebuild content without **Name** headers (already stripped)
  // but keep section breaks
  const rebuilt = sections.map(s => s.text.trim()).join('\n\n');
  return { cleanedContent: rebuilt, speakerName: sections[0].characterName };
}

// ---- Main component ----

function TurnDisplayInner({
  turn,
  characters,
  playerCharacterName,
  isLastAiTurn,
  isStreaming,
  streamingContent,
  onRegenerate,
  onEdit,
  onDelete,
  onPlayTTS,
  isPlayingTTS,
  onImage,
  userSettings,
  isEditing,
  editContent,
  onEditChange,
  onEditSave,
  onEditCancel,
}: TurnDisplayProps) {
  const method = turn.generation_method;
  const rawContent = isStreaming && streamingContent !== undefined ? streamingContent : turn.content;

  // --- Direction turns — italic system message ---
  if (method === 'direction') {
    return (
      <div className="py-3">
        <div className="text-sm text-white/40 italic border-l-2 border-purple-500/30 pl-3">
          {rawContent}
        </div>
      </div>
    );
  }

  // Process content for AI turns (strip names, detect speaker)
  const isUserTurn = method === 'user_written' || method === 'auto_player';
  const { cleanedContent, speakerName } = isUserTurn
    ? { cleanedContent: rawContent, speakerName: playerCharacterName || null }
    : processAiContent(rawContent, characters);

  // Build a scene object for SceneContentDisplay
  const sceneForDisplay = {
    id: turn.scene_id,
    sequence_number: turn.sequence,
    title: '',
    content: cleanedContent,
    location: '',
    characters_present: [] as string[],
  };

  // Only show action buttons when not streaming and scene is persisted
  const showActions = !isStreaming && turn.scene_id > 0;

  return (
    <SceneContentDisplay
      scene={sceneForDisplay}
      userSettings={userSettings}
      showTitle={false}
      isEditing={isEditing || false}
      editContent={editContent || ''}
      onSaveEdit={() => onEditSave?.()}
      onCancelEdit={() => onEditCancel?.()}
      onContentChange={(content) => onEditChange?.(content)}
      isStreamingVariant={isStreaming}
      onEdit={showActions && onEdit ? () => onEdit(turn) : undefined}
      onCopy={showActions ? () => navigator.clipboard.writeText(cleanedContent).catch(() => {}) : undefined}
      onDelete={showActions && onDelete ? () => onDelete(turn) : undefined}
      onRegenerate={showActions && isLastAiTurn && onRegenerate ? onRegenerate : undefined}
      onPlayTTS={showActions && onPlayTTS ? () => onPlayTTS(turn) : undefined}
      isPlayingTTS={isPlayingTTS}
      onImage={showActions && onImage ? () => onImage(turn) : undefined}
      headerContent={speakerName ? (
        <div className="flex items-center gap-2 mb-1">
          <CharAvatar name={speakerName} characters={characters} />
          {method === 'auto_player' && (
            <span title="Auto-generated"><Sparkles className="w-3 h-3 text-purple-400/60" /></span>
          )}
        </div>
      ) : undefined}
    />
  );
}

const TurnDisplay = memo(TurnDisplayInner);
export default TurnDisplay;
