import { useState, useEffect } from 'react';
import { useAuthStore } from '@/store';
import { API_BASE_URL } from '@/lib/api';

interface ContextInfoProps {
  className?: string;
  storyId?: number;
}

export const ContextInfo: React.FC<ContextInfoProps> = ({ className = '', storyId }) => {
  const [showContextInfo, setShowContextInfo] = useState(false);
  const [contextStats, setContextStats] = useState({
    totalScenes: 0,
    recentScenes: 0,
    summarizedScenes: 0,
    contextBudget: 4000,
    estimatedTokens: 0,
    usagePercentage: 0
  });
  const [loading, setLoading] = useState(false);
  const { token } = useAuthStore();

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

  // Fetch real context stats from the API
  useEffect(() => {
    if (!storyId || !token || !showContextInfo) return;

    const fetchContextStats = async () => {
      try {
        setLoading(true);
        const response = await fetch(`${API_BASE_URL}/api/stories/${storyId}/summary`, {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });

        if (response.ok) {
          const data = await response.json();
          setContextStats({
            totalScenes: data.context_info.total_scenes,
            recentScenes: data.context_info.recent_scenes,
            summarizedScenes: data.context_info.summarized_scenes,
            contextBudget: data.context_info.context_budget,
            estimatedTokens: data.context_info.estimated_tokens || 0,
            usagePercentage: data.context_info.usage_percentage || 0
          });
        }
      } catch (error) {
        console.error('Failed to fetch context stats:', error);
        // Keep default values on error
      } finally {
        setLoading(false);
      }
    };

    fetchContextStats();
  }, [storyId, token, showContextInfo]);

  if (!showContextInfo) return null;

  return (
    <div className={`bg-gray-800/50 border border-gray-600 rounded-lg p-3 ${className}`}>
      {/* Context Usage Bar */}
      <div className="mb-3">
        <div className="flex justify-between items-center text-sm font-medium text-gray-300 mb-1">
          <span>Context Usage:</span>
          <span>{contextStats.estimatedTokens.toLocaleString()} / {contextStats.contextBudget.toLocaleString()} tokens</span>
        </div>
        <div className="w-full bg-gray-700 rounded-full h-2">
          <div 
            className={`h-2 rounded-full transition-all duration-300 ${
              contextStats.usagePercentage > 90 ? 'bg-red-500' : 
              contextStats.usagePercentage > 75 ? 'bg-yellow-500' : 'bg-blue-500'
            }`}
            style={{ width: `${Math.min(100, contextStats.usagePercentage)}%` }}
          ></div>
        </div>
        <div className="text-xs text-gray-400 mt-1 text-center">
          {contextStats.usagePercentage.toFixed(1)}% used
        </div>
      </div>

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
      
      {loading && (
        <div className="text-xs text-gray-400 mt-2 text-center">
          Loading context info...
        </div>
      )}
    </div>
  );
};