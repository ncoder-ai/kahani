import { useState, useEffect } from 'react';

interface ContextInfoProps {
  className?: string;
}

export const ContextInfo: React.FC<ContextInfoProps> = ({ className = '' }) => {
  const [showContextInfo, setShowContextInfo] = useState(false);
  const [contextStats, setContextStats] = useState({
    totalScenes: 0,
    recentScenes: 0,
    summarizedScenes: 0,
    contextBudget: 4000
  });

  useEffect(() => {
    // Check if context info should be shown
    const checkSettings = () => {
      setShowContextInfo(window.kahaniUISettings?.showContextInfo || false);
    };

    checkSettings();

    // Listen for settings changes
    const handleSettingsChange = () => {
      checkSettings();
    };

    window.addEventListener('kahaniUISettingsChanged', handleSettingsChange);
    return () => window.removeEventListener('kahaniUISettingsChanged', handleSettingsChange);
  }, []);

  // Mock context stats - in real implementation, this would come from the API
  useEffect(() => {
    setContextStats({
      totalScenes: 12,
      recentScenes: 3,
      summarizedScenes: 9,
      contextBudget: 4000
    });
  }, []);

  if (!showContextInfo) return null;

  return (
    <div className={`bg-gray-800/50 border border-gray-600 rounded-lg p-3 ${className}`}>
      <div className="text-sm font-medium text-gray-300 mb-2">Context Management</div>
      <div className="space-y-1 text-xs">
        <div className="flex justify-between">
          <span className="text-gray-400">Total Scenes:</span>
          <span className="text-white">{contextStats.totalScenes}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">Recent (Full):</span>
          <span className="text-green-400">{contextStats.recentScenes}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">Summarized:</span>
          <span className="text-blue-400">{contextStats.summarizedScenes}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">Budget:</span>
          <span className="text-white">{contextStats.contextBudget.toLocaleString()} tokens</span>
        </div>
      </div>
    </div>
  );
};