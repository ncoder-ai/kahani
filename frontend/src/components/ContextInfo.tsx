import { useState, useEffect } from 'react';
import { useAuthStore } from '@/store';
import { getApiBaseUrl } from '@/lib/api';

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
      console.log('ContextInfo checking settings:', window.kahaniUISettings);
      const shouldShow = window.kahaniUISettings?.showContextInfo || false;
      console.log('ContextInfo should show:', shouldShow);
      setShowContextInfo(shouldShow);
    };

    checkSettings();

    // Listen for settings changes
    const handleSettingsChange = () => {
      console.log('ContextInfo settings changed event received');
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
        console.log('Fetching context stats for story:', storyId);
        const response = await fetch(`${getApiBaseUrl()}/api/stories/${storyId}/summary`, {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });

        console.log('Context API response status:', response.status);
        if (response.ok) {
          const data = await response.json();
          console.log('Context API data:', data);
          setContextStats({
            totalScenes: data.context_info.total_scenes,
            recentScenes: data.context_info.recent_scenes,
            summarizedScenes: data.context_info.summarized_scenes,
            contextBudget: data.context_info.context_budget,
            estimatedTokens: data.context_info.estimated_tokens || 0,
            usagePercentage: data.context_info.usage_percentage || 0
          });
        } else {
          console.error('Context API error:', response.status, response.statusText);
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

  // Debug logging
  console.log('ContextInfo rendering with stats:', contextStats);

  return (
    <div className={`bg-gray-800/50 border border-gray-600 rounded-lg p-3 relative z-50 mb-20 ${className}`}>
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
      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-300">Total Scenes:</span>
          <span className="text-white font-medium">{contextStats.totalScenes}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-300">Recent (Full):</span>
          <span className="text-green-400 font-medium">{contextStats.recentScenes}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-300">Summarized:</span>
          <span className="text-blue-400 font-medium">{contextStats.summarizedScenes}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-300">Budget:</span>
          <span className="text-white font-medium">{contextStats.contextBudget.toLocaleString()} tokens</span>
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