'use client';

interface FormattedTextProps {
  content: string;
  className?: string;
}

export default function FormattedText({ content, className = "" }: FormattedTextProps) {
  const formatText = (text: string) => {
    // Split by lines first to preserve paragraph structure
    const paragraphs = text.split('\n\n');
    
    return paragraphs.map((paragraph, pIndex) => {
      if (!paragraph.trim()) return null;
      
      // Parse the paragraph for different text types
      const segments = parseTextSegments(paragraph);
      
      return (
        <p key={pIndex} className="mb-4 leading-relaxed">
          {segments.map((segment, sIndex) => {
            switch (segment.type) {
              case 'dialogue':
                return (
                  <span key={sIndex} className="text-blue-300 font-medium">
                    {segment.content}
                  </span>
                );
              case 'thought':
                return (
                  <span key={sIndex} className="text-purple-300 italic">
                    {segment.content}
                  </span>
                );
              case 'narrative':
              default:
                return (
                  <span key={sIndex} className="text-gray-200">
                    {segment.content}
                  </span>
                );
            }
          })}
        </p>
      );
    }).filter(Boolean);
  };

  const parseTextSegments = (text: string) => {
    const segments: Array<{ type: 'dialogue' | 'thought' | 'narrative'; content: string }> = [];
    let currentPos = 0;
    
    // Regular expressions for different text types
    const dialogueRegex = /"([^"]*?)"/g;
    const thoughtRegex = /\*([^*]*?)\*/g;
    
    // Find all matches and their positions
    const matches: Array<{ type: 'dialogue' | 'thought'; start: number; end: number; content: string }> = [];
    
    // Find dialogue matches
    let match;
    while ((match = dialogueRegex.exec(text)) !== null) {
      matches.push({
        type: 'dialogue',
        start: match.index,
        end: match.index + match[0].length,
        content: match[0] // Include the quotes
      });
    }
    
    // Reset regex lastIndex
    thoughtRegex.lastIndex = 0;
    
    // Find thought matches
    while ((match = thoughtRegex.exec(text)) !== null) {
      matches.push({
        type: 'thought',
        start: match.index,
        end: match.index + match[0].length,
        content: match[1] // Content without asterisks
      });
    }
    
    // Sort matches by position
    matches.sort((a, b) => a.start - b.start);
    
    // Build segments
    for (const textMatch of matches) {
      // Add narrative text before this match
      if (currentPos < textMatch.start) {
        const narrativeText = text.slice(currentPos, textMatch.start);
        if (narrativeText.trim()) {
          segments.push({
            type: 'narrative',
            content: narrativeText
          });
        }
      }
      
      // Add the matched segment
      segments.push({
        type: textMatch.type,
        content: textMatch.content
      });
      
      currentPos = textMatch.end;
    }
    
    // Add remaining narrative text
    if (currentPos < text.length) {
      const remainingText = text.slice(currentPos);
      if (remainingText.trim()) {
        segments.push({
          type: 'narrative',
          content: remainingText
        });
      }
    }
    
    // If no special formatting found, treat entire text as narrative
    if (segments.length === 0) {
      segments.push({
        type: 'narrative',
        content: text
      });
    }
    
    return segments;
  };

  return (
    <div className={`prose prose-invert prose-lg max-w-none ${className}`}>
      {formatText(content)}
    </div>
  );
}