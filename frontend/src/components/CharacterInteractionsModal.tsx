'use client';

import { useState, useEffect } from 'react';
import { X, RefreshCw, Users, Trash2 } from 'lucide-react';
import apiClient from '@/lib/api';

interface Interaction {
  id: number;
  interaction_type: string;
  character_a: string;
  character_b: string;
  first_occurrence_scene: number;
  description: string | null;
}

interface CharacterInteractionsModalProps {
  isOpen: boolean;
  onClose: () => void;
  storyId: number;
  branchId?: number;
  storyTitle: string;
}

export default function CharacterInteractionsModal({
  isOpen,
  onClose,
  storyId,
  branchId,
  storyTitle
}: CharacterInteractionsModalProps) {
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [loading, setLoading] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionProgress, setExtractionProgress] = useState<{
    current: number;
    total: number;
    percentage: number;
  } | null>(null);
  const [extractionMessage, setExtractionMessage] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  
  useEffect(() => {
    if (isOpen) {
      loadInteractions();
    }
  }, [isOpen, storyId, branchId]);

  const loadInteractions = async () => {
    setLoading(true);
    try {
      const result = await apiClient.getStoryInteractions(storyId, branchId);
      setInteractions(result.interactions);
    } catch (err) {
      console.error('Failed to load interactions:', err);
    } finally {
      setLoading(false);
    }
  };
  
  const pollExtractionProgress = async () => {
    const pollInterval = setInterval(async () => {
      try {
        const result = await apiClient.getExtractionProgress(storyId);
        
        if (!result.in_progress) {
          clearInterval(pollInterval);
          setIsExtracting(false);
          setExtractionMessage(`Extraction complete! Found ${result.interactions_found} interactions.`);
          setExtractionProgress(null);
          
          // Reload interactions
          loadInteractions();
          return;
        }
        
        const percentage = result.total_batches > 0 
          ? Math.round((result.batches_processed / result.total_batches) * 100)
          : 0;
        
        setExtractionProgress({
          current: result.batches_processed,
          total: result.total_batches,
          percentage
        });
        
      } catch (err) {
        console.error('Failed to poll extraction progress:', err);
      }
    }, 2000);
    
    setTimeout(() => {
      clearInterval(pollInterval);
      setIsExtracting(false);
      setExtractionMessage('Extraction timeout. Check back later.');
      setExtractionProgress(null);
    }, 300000);
  };
  
  const handleReExtract = async () => {
    setIsExtracting(true);
    setExtractionMessage(null);
    setExtractionProgress(null);
    
    try {
      const result = await apiClient.extractInteractionsRetroactively(storyId);
      setExtractionMessage(`Scanning ${result.scene_count} scenes in ${result.num_batches} batches...`);
      pollExtractionProgress();
    } catch (err) {
      console.error('Failed to start extraction:', err);
      setExtractionMessage('Failed to start extraction');
      setIsExtracting(false);
    }
  };
  
  const handleDeleteInteraction = async (interactionId: number) => {
    if (deletingId) return; // Prevent double-clicks
    
    setDeletingId(interactionId);
    try {
      await apiClient.deleteInteraction(storyId, interactionId);
      // Remove from local state
      setInteractions(prev => prev.filter(i => i.id !== interactionId));
    } catch (err) {
      console.error('Failed to delete interaction:', err);
    } finally {
      setDeletingId(null);
    }
  };
  
  // Group interactions by character pairs
  const groupedInteractions = interactions.reduce((acc, interaction) => {
    const key = `${interaction.character_a}|${interaction.character_b}`;
    if (!acc[key]) {
      acc[key] = [];
    }
    acc[key].push(interaction);
    return acc;
  }, {} as Record<string, Interaction[]>);
  
  if (!isOpen) return null;
  
  return (
    <>
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4">
        <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-2xl w-full max-w-4xl max-h-[95vh] sm:max-h-[90vh] overflow-hidden flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between p-3 sm:p-6 border-b border-slate-700 bg-gradient-to-r from-purple-900/50 to-pink-900/50">
            <div className="flex items-center gap-2 sm:gap-3 min-w-0">
              <Users className="w-5 h-5 sm:w-6 sm:h-6 text-purple-400 flex-shrink-0" />
              <div className="min-w-0">
                <h2 className="text-lg sm:text-2xl font-bold text-white">Character Interactions</h2>
                <p className="text-xs sm:text-sm text-gray-300 truncate">{storyTitle}</p>
              </div>
            </div>
            <div className="flex items-center gap-1.5 sm:gap-2 flex-shrink-0">
              <button
                onClick={handleReExtract}
                disabled={isExtracting}
                className="flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-4 py-1.5 sm:py-2 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 disabled:bg-slate-700 disabled:text-gray-500 text-white rounded-lg text-xs sm:text-sm transition-colors"
              >
                <RefreshCw className={`w-3.5 h-3.5 sm:w-4 sm:h-4 ${isExtracting ? 'animate-spin' : ''}`} />
                <span className="hidden xs:inline">{isExtracting ? 'Extracting...' : 'Re-Extract'}</span>
              </button>
              <button
                onClick={onClose}
                className="p-2 hover:bg-slate-700 active:bg-slate-600 rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-gray-300" />
              </button>
            </div>
          </div>
          
          {/* Content */}
          <div className="flex-1 overflow-y-auto p-3 sm:p-6">
            {/* Extraction Progress */}
            {extractionMessage && (
              <div className="mb-3 sm:mb-4 p-2.5 sm:p-3 bg-blue-900/30 border border-blue-700/50 rounded-lg">
                <p className="text-xs sm:text-sm text-blue-300">{extractionMessage}</p>
              </div>
            )}

            {extractionProgress && (
              <div className="mb-3 sm:mb-4 p-3 sm:p-4 bg-slate-900/50 border border-slate-700 rounded-lg space-y-2">
                <div className="flex justify-between text-xs sm:text-sm text-gray-300">
                  <span>Processing batches...</span>
                  <span>{extractionProgress.current} of {extractionProgress.total} batches</span>
                </div>
                <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-purple-500 to-pink-500 h-full transition-all duration-500"
                    style={{ width: `${extractionProgress.percentage}%` }}
                  />
                </div>
                <p className="text-xs text-gray-400">{extractionProgress.percentage}% complete</p>
              </div>
            )}

            {/* Interactions List */}
            {loading ? (
              <div className="text-center py-12 text-gray-300">Loading interactions...</div>
            ) : interactions.length === 0 ? (
              <div className="text-center py-8 sm:py-12">
                <p className="text-gray-300 mb-3 sm:mb-4">No interactions tracked yet.</p>
                <p className="text-xs sm:text-sm text-gray-400">
                  Configure interaction types in Story Settings and click &quot;Re-Extract&quot;
                </p>
              </div>
            ) : (
              <div className="space-y-4 sm:space-y-6">
                {Object.entries(groupedInteractions).map(([key, interactions]) => {
                  const [charA, charB] = key.split('|');
                  return (
                    <div key={key} className="bg-slate-900/50 rounded-lg p-3 sm:p-5 border border-slate-700/50">
                      <h3 className="text-base sm:text-lg font-semibold text-white mb-3 sm:mb-4">
                        {charA} & {charB}
                      </h3>

                      <div className="space-y-2 sm:space-y-3">
                        {interactions.map((interaction) => (
                          <div key={interaction.id} className="bg-slate-800/50 rounded-lg p-3 sm:p-4 border border-slate-700/30">
                            <div className="flex items-start justify-between gap-2 mb-2">
                              <div className="flex-1 min-w-0">
                                <h4 className="text-sm sm:text-base font-medium text-purple-400 mb-1">
                                  {interaction.interaction_type}
                                </h4>
                                <p className="text-xs text-gray-400">
                                  Scene {interaction.first_occurrence_scene}
                                </p>
                              </div>
                              <button
                                onClick={() => handleDeleteInteraction(interaction.id)}
                                disabled={deletingId === interaction.id}
                                className="p-1.5 sm:p-2 hover:bg-red-900/50 active:bg-red-900/70 rounded transition-all text-gray-400 hover:text-red-400 disabled:opacity-50 flex-shrink-0"
                                title="Delete this interaction"
                              >
                                <Trash2 className={`w-4 h-4 ${deletingId === interaction.id ? 'animate-pulse' : ''}`} />
                              </button>
                            </div>

                            {interaction.description && (
                              <p className="text-gray-200 text-xs sm:text-sm">
                                {interaction.description}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

