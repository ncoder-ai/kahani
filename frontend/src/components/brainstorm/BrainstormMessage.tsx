'use client';

interface BrainstormMessageProps {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
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

export default function BrainstormMessage({ role, content, timestamp }: BrainstormMessageProps) {
  const isUser = role === 'user';

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
              <div className="space-y-1 text-sm md:text-base">
                {formatContent(content)}
              </div>
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

