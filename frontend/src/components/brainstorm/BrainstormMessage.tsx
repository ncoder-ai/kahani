'use client';

import { useState } from 'react';

interface BrainstormMessageProps {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  onSelectIdea?: (idea: string) => void;
}

function formatContent(content: string) {
  // Split content into lines
  const lines = content.split('\n');
  const formatted: JSX.Element[] = [];
  let currentList: string[] = [];
  let listType: 'numbered' | 'bullet' | null = null;

  const flushList = () => {
    if (currentList.length > 0) {
      if (listType === 'numbered') {
        formatted.push(
          <ol key={formatted.length} className="list-decimal list-inside space-y-2 my-3 ml-2">
            {currentList.map((item, i) => (
              <li key={i} className="text-white/90 leading-relaxed pl-2">
                <span className="ml-2">{item}</span>
              </li>
            ))}
          </ol>
        );
      } else if (listType === 'bullet') {
        formatted.push(
          <ul key={formatted.length} className="list-disc list-inside space-y-2 my-3 ml-2">
            {currentList.map((item, i) => (
              <li key={i} className="text-white/90 leading-relaxed pl-2">
                <span className="ml-2">{item}</span>
              </li>
            ))}
          </ul>
        );
      }
      currentList = [];
      listType = null;
    }
  };

  lines.forEach((line, index) => {
    const trimmedLine = line.trim();

    // Check for numbered list (1. 2. 3. or 1) 2) 3))
    const numberedMatch = trimmedLine.match(/^(\d+[\.)]\s+)(.+)$/);
    if (numberedMatch) {
      if (listType !== 'numbered') {
        flushList();
        listType = 'numbered';
      }
      currentList.push(numberedMatch[2]);
      return;
    }

    // Check for bullet list (-, *, •)
    const bulletMatch = trimmedLine.match(/^[-*•]\s+(.+)$/);
    if (bulletMatch) {
      if (listType !== 'bullet') {
        flushList();
        listType = 'bullet';
      }
      currentList.push(bulletMatch[1]);
      return;
    }

    // Not a list item, flush any pending list
    flushList();

    // Check for headings (##, ###, etc.)
    const headingMatch = trimmedLine.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const text = headingMatch[2];
      const className = level === 1 
        ? 'text-xl font-bold text-white mt-4 mb-2'
        : level === 2
        ? 'text-lg font-semibold text-white mt-3 mb-2'
        : 'text-base font-semibold text-white/90 mt-2 mb-1';
      
      formatted.push(
        <div key={index} className={className}>
          {text}
        </div>
      );
      return;
    }

    // Check for bold text (**text**)
    const boldMatch = trimmedLine.match(/\*\*(.+?)\*\*/g);
    if (boldMatch) {
      const parts = trimmedLine.split(/(\*\*.+?\*\*)/);
      formatted.push(
        <p key={index} className="text-white/90 leading-relaxed my-2">
          {parts.map((part, i) => {
            if (part.startsWith('**') && part.endsWith('**')) {
              return <strong key={i} className="font-semibold text-white">{part.slice(2, -2)}</strong>;
            }
            return part;
          })}
        </p>
      );
      return;
    }

    // Empty line - add spacing
    if (trimmedLine === '') {
      formatted.push(<div key={index} className="h-2" />);
      return;
    }

    // Regular paragraph
    formatted.push(
      <p key={index} className="text-white/90 leading-relaxed my-2">
        {line}
      </p>
    );
  });

  // Flush any remaining list
  flushList();

  return formatted;
}

export default function BrainstormMessage({ role, content, timestamp, onSelectIdea }: BrainstormMessageProps) {
  const isUser = role === 'user';
  const [selectedIdea, setSelectedIdea] = useState<string | null>(null);

  // Detect if this message contains story ideas (multiple formats)
  const hasStoryIdeas = !isUser && (
    // Format A: Option N:
    (content.match(/Option \d+:/g)?.length || 0) >= 2 ||
    // Format B/C: Numbered bold titles "1. Title:" or "**1. Title:**"
    (content.match(/^\*?\*?\d+\.\s+.+?:\*?\*?/gm)?.length || 0) >= 2 ||
    // Format D: **Idea N: Title**
    (content.match(/\*\*Idea \d+:/g)?.length || 0) >= 2
  );

  // Extract story ideas with title and synopsis - handles multiple formats
  const extractIdeas = () => {
    if (!hasStoryIdeas) return [];
    
    const ideas: Array<{title: string, synopsis: string}> = [];
    
    // FORMAT B/C: "1. Title:" or "**1. Title:**" (numbered with title and colon)
    // This is the most common recent format
    const numberedPattern = /(\*\*)?(\d+)\.\s+(.+?):(\*\*)?\s*([\s\S]*?)(?=\n\n(?:\*\*)?\d+\.|Which of these|$)/g;
    const numberedMatches = Array.from(content.matchAll(numberedPattern));
    
    if (numberedMatches.length >= 2) {
      numberedMatches.forEach(match => {
        const title = match[3].replace(/\*\*/g, '').trim();
        const synopsisRaw = match[5].trim();
        // Get text until double newline or end
        const synopsis = synopsisRaw.split(/\n\n(?=\d+\.|\*\*\d+\.)/)[0].trim();
        
        if (title && synopsis && synopsis.length > 20) {
          ideas.push({ title, synopsis });
        }
      });
      
      if (ideas.length >= 2) return ideas;
    }
    
    // FORMAT A: "Option N:" followed by prose
    // Use first sentence or ~60 chars as title, rest as synopsis
    const optionPattern = /Option (\d+):\s*([\s\S]*?)(?=Option \d+:|Which|$)/g;
    const optionMatches = Array.from(content.matchAll(optionPattern));
    
    if (optionMatches.length >= 2) {
      optionMatches.forEach(match => {
        const fullText = match[2].trim();
        // Try to extract title from "In "Title"" pattern
        const quotedTitleMatch = fullText.match(/In\s+"([^"]+)"/);
        
        if (quotedTitleMatch) {
          const title = quotedTitleMatch[1];
          const synopsis = fullText.replace(/In\s+"[^"]+",?\s*/, '').trim();
          if (title && synopsis.length > 20) {
            ideas.push({ title, synopsis });
          }
        } else {
          // No quoted title - use first sentence as title
          const sentences = fullText.split(/[.!?]\s+/);
          if (sentences.length >= 2) {
            const title = sentences[0].substring(0, 60).trim();
            const synopsis = sentences.slice(1).join('. ').trim();
            if (title && synopsis.length > 20) {
              ideas.push({ title, synopsis });
            }
          }
        }
      });
      
      if (ideas.length >= 2) return ideas;
    }
    
    // FORMAT D: **Idea N: Title** followed by synopsis
    const ideaPattern = /\*\*Idea (\d+):\s*(.+?)\*\*\s*([\s\S]*?)(?=\*\*Idea \d+:|$)/g;
    const ideaMatches = Array.from(content.matchAll(ideaPattern));
    
    if (ideaMatches.length >= 2) {
      ideaMatches.forEach(match => {
        const title = match[2].trim();
        const synopsis = match[3].trim().split(/\n\n/)[0].trim();
        
        if (title && synopsis && synopsis.length > 10) {
          ideas.push({ title, synopsis });
        }
      });
      
      if (ideas.length >= 2) return ideas;
    }
    
    return ideas;
  };

  const ideas = extractIdeas();

  // If we found ideas, strip them from the content to avoid duplication
  const getDisplayContent = () => {
    if (ideas.length === 0) return content;
    
    // Remove the ideas section from content
    // Look for the pattern that starts the ideas and remove everything after
    let cleanContent = content;
    
    // Try to find where the ideas start
    const patterns = [
      /\*?\*?\d+\.\s+.+?:/,  // Numbered titles
      /Option \d+:/,          // Option format
      /\*\*Idea \d+:/         // Idea format
    ];
    
    for (const pattern of patterns) {
      const match = cleanContent.match(pattern);
      if (match && match.index !== undefined) {
        // Keep everything before the first idea
        cleanContent = cleanContent.substring(0, match.index).trim();
        break;
      }
    }
    
    return cleanContent;
  };

  const displayContent = getDisplayContent();

  const handleIdeaClick = (idea: {title: string, synopsis: string}) => {
    setSelectedIdea(idea.title);
    if (onSelectIdea) {
      onSelectIdea(`I'd like to explore: ${idea.title}\n\n${idea.synopsis}`);
    }
  };

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3 md:mb-4`}>
      <div className={`max-w-[85%] md:max-w-[80%] rounded-xl md:rounded-2xl p-3 md:p-4 ${
        isUser 
          ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white' 
          : 'bg-white/10 text-white border border-white/20'
      }`}>
        <div className="flex items-start space-x-2 md:space-x-3">
          <div className="text-xl md:text-2xl flex-shrink-0">
            {isUser ? '👤' : '🤖'}
          </div>
          <div className="flex-1 min-w-0">
            {isUser ? (
              <p className="whitespace-pre-wrap text-white leading-relaxed text-sm md:text-base">{content}</p>
            ) : (
              <>
                {displayContent && (
                  <div className="space-y-1 text-sm md:text-base">
                    {formatContent(displayContent)}
                  </div>
                )}
                
                {/* Render clickable idea cards with title and synopsis */}
                {ideas.length > 0 && (
                  <div className="mt-4 space-y-3">
                    <p className="text-xs text-purple-300 font-medium">👆 Click an idea to explore it further:</p>
                    {ideas.map((idea, index) => (
                      <button
                        key={index}
                        onClick={() => handleIdeaClick(idea)}
                        className={`w-full text-left p-4 rounded-lg transition-all border-2 ${
                          selectedIdea === idea.title
                            ? 'bg-purple-500/30 border-purple-400 shadow-lg'
                            : 'bg-white/5 border-white/20 hover:bg-purple-500/20 hover:border-purple-400 cursor-pointer'
                        }`}
                      >
                        <div className="font-semibold text-base mb-2 text-white">{idea.title}</div>
                        <div className="text-sm text-white/80 leading-relaxed">{idea.synopsis}</div>
                        {selectedIdea === idea.title && (
                          <div className="text-xs text-purple-300 mt-3 font-medium">✓ Selected</div>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}
            {timestamp && (
              <p className={`text-xs mt-2 md:mt-3 ${isUser ? 'text-white/70' : 'text-white/50'}`}>
                {new Date(timestamp).toLocaleTimeString()}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

