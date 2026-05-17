import { useState, useEffect } from 'react';

interface TokenInfoProps {
  className?: string;
}

export const TokenInfo: React.FC<TokenInfoProps> = ({ className = '' }) => {
  const [showTokenInfo, setShowTokenInfo] = useState(false);
  const [tokenUsage, setTokenUsage] = useState({
    used: 0,
    total: 0,
    percentage: 0
  });

  useEffect(() => {
    // Check if token info should be shown
    const checkSettings = () => {
      setShowTokenInfo(window.kahaniUISettings?.show_token_info || false);
    };

    checkSettings();

    // Listen for settings changes
    const handleSettingsChange = () => {
      checkSettings();
    };

    window.addEventListener('kahaniUISettingsChanged', handleSettingsChange);
    return () => window.removeEventListener('kahaniUISettingsChanged', handleSettingsChange);
  }, []);

  // Mock token usage - in real implementation, this would come from the API
  useEffect(() => {
    // Simulate token usage
    setTokenUsage({
      used: 1250,
      total: 4000,
      percentage: 31.25
    });
  }, []);

  if (!showTokenInfo) return null;

  return (
    <div className={`bg-gray-800/50 border border-gray-600 rounded-lg p-3 ${className}`}>
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-400">Context Usage:</span>
        <span className="text-white">
          {tokenUsage.used.toLocaleString()} / {tokenUsage.total.toLocaleString()} tokens
        </span>
      </div>
      <div className="mt-2">
        <div className="w-full bg-gray-700 rounded-full h-2">
          <div 
            className="bg-blue-500 h-2 rounded-full transition-all duration-300"
            style={{ width: `${tokenUsage.percentage}%` }}
          />
        </div>
        <div className="text-xs text-gray-400 mt-1 text-center">
          {tokenUsage.percentage.toFixed(1)}% used
        </div>
      </div>
    </div>
  );
};