'use client';

interface BrainstormMessageProps {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

export default function BrainstormMessage({ role, content, timestamp }: BrainstormMessageProps) {
  const isUser = role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className={`max-w-[80%] rounded-2xl p-4 ${
        isUser 
          ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white' 
          : 'bg-white/10 text-white border border-white/20'
      }`}>
        <div className="flex items-start space-x-2">
          <div className="text-2xl mb-1">
            {isUser ? '👤' : '🤖'}
          </div>
          <div className="flex-1">
            <p className="whitespace-pre-wrap">{content}</p>
            {timestamp && (
              <p className={`text-xs mt-2 ${isUser ? 'text-white/70' : 'text-white/50'}`}>
                {new Date(timestamp).toLocaleTimeString()}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

