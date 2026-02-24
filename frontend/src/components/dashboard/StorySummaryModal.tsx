'use client';

import { useAuthStore } from '@/store';
import { getApiBaseUrl } from '@/lib/api';

interface StorySummaryModalProps {
  isOpen: boolean;
  selectedStory: any;
  storySummary: any;
  loadingSummary: boolean;
  onClose: () => void;
  onSummaryUpdate: (summary: any) => void;
  onLoadingChange: (loading: boolean) => void;
}

export default function StorySummaryModal({
  isOpen,
  selectedStory,
  storySummary,
  loadingSummary,
  onClose,
  onSummaryUpdate,
  onLoadingChange,
}: StorySummaryModalProps) {
  if (!isOpen) return null;

  const handleRegenerate = async () => {
    if (!selectedStory) return;
    onLoadingChange(true);
    try {
      const { token } = useAuthStore.getState();
      const url = `${await getApiBaseUrl()}/api/stories/${selectedStory.id}/regenerate-summary`;

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        const updatedSummary = await response.json();
        onSummaryUpdate(updatedSummary);
      } else {
        console.error('[SUMMARY] Failed to regenerate summary:', response.status);
      }
    } catch (error) {
      console.error('[SUMMARY] Error regenerating summary:', error);
    } finally {
      onLoadingChange(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-[60] flex items-center justify-center p-4">
      <div className="bg-white rounded-lg max-w-4xl w-full max-h-[80vh] overflow-hidden">
        <div className="p-6 border-b">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-semibold">
              Story Summary: {selectedStory?.title || 'Loading...'}
            </h2>
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-gray-700"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div className="p-6 overflow-y-auto max-h-96">
          {loadingSummary ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <span className="ml-2">Loading summary...</span>
            </div>
          ) : storySummary?.error ? (
            <div className="text-red-600 text-center py-8">
              {storySummary.error}
            </div>
          ) : storySummary ? (
            <div className="space-y-4">
              <div className="bg-gray-50 p-4 rounded-lg">
                <h3 className="font-medium text-gray-700 mb-2">Summary:</h3>
                <p className="text-gray-800 whitespace-pre-wrap">
                  {storySummary.summary || 'No summary available'}
                </p>
              </div>

              {storySummary.token_count && (
                <div className="text-sm text-gray-600">
                  Token count: {storySummary.token_count.toLocaleString()}
                </div>
              )}

              {storySummary.last_updated && (
                <div className="text-sm text-gray-600">
                  Last updated: {new Date(storySummary.last_updated).toLocaleString()}
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500">
              No summary data available
            </div>
          )}
        </div>

        {storySummary && !storySummary.error && selectedStory && (
          <div className="p-6 border-t bg-gray-50">
            <button
              onClick={handleRegenerate}
              disabled={loadingSummary}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {loadingSummary ? 'Regenerating...' : 'Regenerate Summary'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
