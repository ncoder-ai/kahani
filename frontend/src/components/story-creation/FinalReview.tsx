'use client';

import { StoryData } from '@/app/create-story/page';

interface FinalReviewProps {
  storyData: StoryData;
  onUpdate: (data: Partial<StoryData>) => void;
  onFinish: () => void;
  onBack: () => void;
  isLoading: boolean;
}

export default function FinalReview({ storyData, onFinish, onBack, isLoading }: FinalReviewProps) {
  const handleCreateStory = () => {
    if (!isLoading) {
      onFinish();
    }
  };

  return (
    <div className="space-y-8">
      <div className="text-center">
        <h2 className="text-3xl font-bold text-white mb-4">Review Your Story</h2>
        <p className="text-white/80 text-lg">
          Take a final look at your story setup before creating it
        </p>
      </div>

      {/* Story Overview */}
      <div className="bg-white/10 border border-white/30 rounded-xl p-6">
        <h3 className="text-2xl font-bold text-white mb-4 text-center">{storyData.title}</h3>
        
        <div className="grid md:grid-cols-2 gap-6">
          {/* Basic Info */}
          <div className="space-y-4">
            <div>
              <h4 className="text-lg font-semibold text-white mb-2">Genre & Tone</h4>
              <div className="flex space-x-3">
                <span className="bg-gradient-to-r from-purple-500 to-pink-500 text-white px-3 py-1 rounded-lg text-sm font-medium">
                  {storyData.genre?.charAt(0).toUpperCase() + storyData.genre?.slice(1)}
                </span>
                <span className="bg-gradient-to-r from-blue-500 to-cyan-500 text-white px-3 py-1 rounded-lg text-sm font-medium">
                  {storyData.tone?.charAt(0).toUpperCase() + storyData.tone?.slice(1)}
                </span>
              </div>
            </div>

            {storyData.description && (
              <div>
                <h4 className="text-lg font-semibold text-white mb-2">Description</h4>
                <p className="text-white/80 bg-white/5 p-3 rounded-lg">{storyData.description}</p>
              </div>
            )}

            {storyData.world_setting && (
              <div>
                <h4 className="text-lg font-semibold text-white mb-2">World Setting</h4>
                <p className="text-white/80 bg-white/5 p-3 rounded-lg">{storyData.world_setting}</p>
              </div>
            )}
          </div>

          {/* Characters */}
          <div>
            <h4 className="text-lg font-semibold text-white mb-3">Characters ({storyData.characters?.length || 0})</h4>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {storyData.characters?.map((character, index) => (
                <div key={index} className="bg-white/5 p-3 rounded-lg">
                  <div className="flex justify-between items-start">
                    <span className="text-white font-medium">{character.name}</span>
                    <span className="text-purple-300 text-sm">{character.role}</span>
                  </div>
                  {character.description && (
                    <p className="text-white/70 text-sm mt-1">{character.description}</p>
                  )}
                </div>
              )) || (
                <p className="text-white/60 text-sm">No characters added</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Scenario */}
      {storyData.scenario && (
        <div className="bg-white/10 border border-white/30 rounded-xl p-6">
          <h4 className="text-lg font-semibold text-white mb-3">📖 Scenario</h4>
          <p className="text-white/80 bg-white/5 p-4 rounded-lg">{storyData.scenario}</p>
        </div>
      )}

      {/* Plot Points */}
      {storyData.plot_points && storyData.plot_points.some(point => point.trim()) && (
        <div className="bg-white/10 border border-white/30 rounded-xl p-6">
          <h4 className="text-lg font-semibold text-white mb-3">📈 Plot Points</h4>
          <div className="space-y-3">
            {storyData.plot_points.map((point, index) => {
              if (!point.trim()) return null;
              return (
                <div key={index} className="bg-white/5 p-3 rounded-lg">
                  <p className="text-white/80">{point}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Ready to Create */}
      <div className="bg-gradient-to-r from-purple-500/20 to-pink-500/20 border border-purple-300/30 rounded-xl p-6 text-center">
        <h4 className="text-xl font-semibold text-white mb-2">🎉 Ready to Create!</h4>
        <p className="text-white/80 mb-4">
          Your story framework is complete. Click below to create your story and start writing!
        </p>
        
        <div className="flex justify-center space-x-4">
          <button
            onClick={onBack}
            disabled={isLoading}
            className="px-6 py-2 bg-white/20 border border-white/30 text-white rounded-lg hover:bg-white/30 transition-colors disabled:opacity-50"
          >
            ← Edit More
          </button>
          <button
            onClick={handleCreateStory}
            disabled={isLoading}
            className={`px-8 py-3 rounded-xl font-semibold transition-all duration-200 ${
              isLoading
                ? 'bg-white/20 text-white/50 cursor-not-allowed'
                : 'bg-gradient-to-r from-purple-500 to-pink-500 text-white hover:from-purple-600 hover:to-pink-600 transform hover:scale-105'
            }`}
          >
            {isLoading ? (
              <div className="flex items-center space-x-2">
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                <span>Creating Story...</span>
              </div>
            ) : (
              '✨ Create My Story'
            )}
          </button>
        </div>
      </div>

      {/* Tips */}
      <div className="bg-white/5 rounded-xl p-4">
        <h5 className="text-white font-medium mb-2">💡 What happens next?</h5>
        <ul className="text-white/70 text-sm space-y-1">
          <li>• Your story will be saved to your dashboard</li>
          <li>• You can start writing chapters immediately</li>
          <li>• Use AI assistance to continue your story</li>
          <li>• Invite others to collaborate (coming soon)</li>
        </ul>
      </div>
    </div>
  );
}