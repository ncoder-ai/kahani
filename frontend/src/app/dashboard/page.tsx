'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore, useStoryStore, useHasHydrated } from '@/store';
import { X } from 'lucide-react';
import apiClient, { getApiBaseUrl } from '@/lib/api';
import RouteProtection from '@/components/RouteProtection';
import { useUISettings } from '@/hooks/useUISettings';

function DashboardContent() {
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const { stories, setStories, isLoading, setLoading } = useStoryStore();
  const hasHydrated = useHasHydrated();
  const [selectedStory, setSelectedStory] = useState<any>(null);
  const [showSummaryModal, setShowSummaryModal] = useState(false);
  const [storySummary, setStorySummary] = useState<any>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [generatingStorySummaryId, setGeneratingStorySummaryId] = useState<number | null>(null);
  const [userSettings, setUserSettings] = useState<any>(null);

  // Apply UI settings (theme, font size, etc.)
  useUISettings(userSettings?.ui_preferences || null);

  useEffect(() => {
    if (!hasHydrated) return; 
    
    if (!user) {
      console.log('No user found, redirecting to login');
      router.push('/login');
      return;
    }
    
    console.log('User found, loading stories:', user);
    loadStories();
    loadUserSettings();
  }, [user, hasHydrated, router]);

  const loadUserSettings = async () => {
    try {
      const settings = await apiClient.getUserSettings();
      setUserSettings(settings.settings);
    } catch (err) {
      console.error('Failed to load user settings:', err);
    }
  };

  const loadStories = async () => {
    try {
      setLoading(true);
      
      // Get fresh token from auth store
      const { token } = useAuthStore.getState();
      console.log('Dashboard loadStories - checking token:', token ? 'exists' : 'missing');
      
      if (!token) {
        console.error('No token available for stories request');
        router.push('/login');
        return;
      }
      
      // Make direct fetch request with explicit Authorization header - include all stories (active and archived)
      const response = await fetch(`${getApiBaseUrl()}/api/stories/?skip=0&limit=10&include_archived=true`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });
      
      console.log('Stories response status:', response.status);
      
      if (!response.ok) {
        if (response.status === 401) {
          console.error('Token invalid, redirecting to login');
          router.push('/login');
          return;
        }
        throw new Error(`HTTP ${response.status}`);
      }
      
      const storiesData = await response.json();
      console.log('Stories loaded successfully:', storiesData);
      setStories(storiesData);
    } catch (error) {
      console.error('Failed to load stories:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    logout();
    router.push('/login');
  };

  const handleStoryClick = (storyId: number) => {
    // Find the story in our local state to check its creation status
    const story = stories.find(s => s.id === storyId);
    
    // If story is still a draft and hasn't completed all creation steps, 
    // redirect to the creation flow
    if (story && story.status === 'draft' && (story.creation_step < 5)) {
      router.push(`/create-story?story_id=${storyId}`);
    } else {
      // Story is fully created, go to story view
      router.push(`/story/${storyId}`);
    }
  };

  const handleViewSummary = async (storyId: number) => {
    console.log('[SUMMARY] Loading summary for story:', storyId);
    setLoadingSummary(true);
    setShowSummaryModal(true);
    
    try {
      const { token } = useAuthStore.getState();
      const url = `${getApiBaseUrl()}/api/stories/${storyId}/summary`;
      console.log('[SUMMARY] Fetching from:', url);
      
      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      console.log('[SUMMARY] Initial load response status:', response.status);
      
      if (response.ok) {
        const summaryData = await response.json();
        console.log('[SUMMARY] Initial summary data:', summaryData);
        console.log('[SUMMARY] Summary content:', summaryData.summary);
        setStorySummary(summaryData);
        setSelectedStory(stories.find(s => s.id === storyId));
      } else {
        const errorText = await response.text();
        console.error('[SUMMARY] Failed to load summary:', response.status, errorText);
        setStorySummary({ error: 'Failed to load summary' });
      }
    } catch (error) {
      console.error('[SUMMARY] Error loading summary:', error);
      setStorySummary({ error: 'Error loading summary' });
    } finally {
      setLoadingSummary(false);
    }
  };

  const handleCreateStory = () => {
    router.push('/create-story');
  };

  const handleGenerateStorySummary = async (storyId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    
    setGeneratingStorySummaryId(storyId);
    
    try {
      const { token } = useAuthStore.getState();
      const response = await fetch(
        `${getApiBaseUrl()}/api/stories/${storyId}/generate-story-summary`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );
      
      if (!response.ok) {
        throw new Error('Failed to generate story summary');
      }
      
      const data = await response.json();
      
      // Update the story in the local state
      const updatedStories = stories.map(s => 
        s.id === storyId ? { ...s, summary: data.summary } : s
      );
      setStories(updatedStories);
      
      alert(`✓ Story summary generated!\n\nChapters: ${data.chapters_summarized}\nScenes: ${data.total_scenes}`);
    } catch (error) {
      console.error('Failed to generate story summary:', error);
      alert('✗ Failed to generate story summary. Please try again.');
    } finally {
      setGeneratingStorySummaryId(null);
    }
  };

  const handleDeleteStory = async (storyId: number, storyTitle: string) => {
    if (!confirm(`Are you sure you want to delete "${storyTitle}"?\n\nThis will permanently delete:\n- The story\n- All scenes and variants\n- All choices\n- Story summary\n\nCharacters will NOT be deleted.\n\nThis action cannot be undone.`)) {
      return;
    }

    console.log('[DELETE] Deleting story:', storyId);
    
    try {
      const { token } = useAuthStore.getState();
      const response = await fetch(`${getApiBaseUrl()}/api/stories/${storyId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        const data = await response.json();
        console.log('[DELETE] Story deleted:', data);
        
        // Refresh the stories list
        const storiesData = await fetch(`${getApiBaseUrl()}/api/stories`, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        });
        
        if (storiesData.ok) {
          const stories = await storiesData.json();
          setStories(stories);
        }
      } else {
        const errorText = await response.text();
        console.error('[DELETE] Failed to delete story:', response.status, errorText);
        alert('Failed to delete story. Please try again.');
      }
    } catch (error) {
      console.error('[DELETE] Error deleting story:', error);
      alert('Error deleting story. Please try again.');
    }
  };

  // Show loading while hydration is happening or user is not available
  if (!hasHydrated || !user) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-white/80">Loading...</p>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen theme-bg-primary pt-16">
      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-12">
        {/* Hero Section */}
        <div className="text-center mb-12">
          <h2 className="text-4xl font-bold text-white mb-4">Your Story Universe</h2>
          <p className="text-white/80 text-lg mb-8">
            Create immersive stories with AI assistance and bring your imagination to life
          </p>
          
          <div className="flex justify-center gap-4">
            <button
              onClick={handleCreateStory}
              className="theme-btn-primary px-8 py-4 rounded-2xl font-semibold text-lg transform hover:scale-105 transition-all duration-200 shadow-lg"
            >
              ✨ Create New Story
            </button>
            <button
              onClick={() => router.push('/characters')}
              className="theme-btn-secondary px-8 py-4 rounded-2xl font-semibold text-lg transform hover:scale-105 transition-all duration-200 shadow-lg"
            >
              👥 Manage Characters
            </button>
            {user?.is_admin && (
              <button
                onClick={() => router.push('/admin')}
                className="bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-white px-8 py-4 rounded-2xl font-semibold text-lg transform hover:scale-105 transition-all duration-200 shadow-lg"
              >
                🛡️ Admin Panel
              </button>
            )}
          </div>
        </div>

        {/* Stories Grid */}
        {isLoading ? (
          <div className="text-center py-16">
            <div className="w-16 h-16 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
            <p className="text-white/80">Loading your stories...</p>
          </div>
        ) : stories.length === 0 ? (
          <div className="text-center py-16">
            <div className="bg-white/10 backdrop-blur-md rounded-3xl border border-white/20 p-12 max-w-md mx-auto">
              <div className="text-6xl mb-6">📚</div>
              <h3 className="text-2xl font-bold text-white mb-4">No stories yet</h3>
              <p className="text-white/70 mb-8">
                Start your creative journey by creating your first interactive story
              </p>
              <button
                onClick={handleCreateStory}
                className="theme-btn-primary px-6 py-3 rounded-xl font-semibold transform hover:scale-105 transition-all duration-200"
              >
                Create Your First Story
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Stories Header */}
            <div className="flex justify-between items-center mb-8">
              <h3 className="text-2xl font-bold text-white">Your Stories ({stories.length})</h3>
              <div className="flex space-x-4">
                <button className="text-white/80 hover:text-white px-4 py-2 rounded-lg hover:bg-white/10 transition-colors">
                  🔍 Search
                </button>
                <button className="text-white/80 hover:text-white px-4 py-2 rounded-lg hover:bg-white/10 transition-colors">
                  📊 Sort
                </button>
              </div>
            </div>

            {/* Stories Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {stories.map((story) => (
                <div
                  key={story.id}
                  onClick={() => handleStoryClick(story.id)}
                  className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl p-6 cursor-pointer hover:bg-white/15 hover:scale-105 transition-all duration-200 group"
                >
                  {/* Story Header */}
                  <div className="flex justify-between items-start mb-4">
                    <div className="flex-1">
                      <h4 className="text-xl font-bold text-white mb-2 group-hover:text-gray-200 transition-colors">
                        {story.title}
                        {story.status === 'archived' && (
                          <span className="ml-2 text-xs bg-gray-600/50 text-gray-300 px-2 py-1 rounded">
                            Archived
                          </span>
                        )}
                      </h4>
                      {story.genre && (
                        <span className="theme-accent-primary bg-opacity-20 text-white px-3 py-1 rounded-lg text-sm font-medium">
                          {story.genre.charAt(0).toUpperCase() + story.genre.slice(1)}
                        </span>
                      )}
                    </div>
                    <div className="text-white/60 group-hover:text-white/80 transition-colors">
                      →
                    </div>
                  </div>

                  {/* Story Description */}
                  {story.description && (
                    <p className="text-white/70 text-sm mb-4 line-clamp-3">
                      {story.description}
                    </p>
                  )}

                  {/* Story Summary - NEW */}
                  {story.summary ? (
                    <div className="mb-4 p-3 theme-bg-secondary border theme-border-accent rounded-lg">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-xs font-semibold theme-accent-primary">📖 STORY SUMMARY</span>
                      </div>
                      <p className="text-white/80 text-xs line-clamp-3 whitespace-pre-wrap">
                        {story.summary}
                      </p>
                    </div>
                  ) : (
                    <div className="mb-4 p-3 bg-gray-500/10 border border-gray-500/20 rounded-lg">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-400">No story summary yet</span>
                        <button
                          onClick={(e) => handleGenerateStorySummary(story.id, e)}
                          disabled={generatingStorySummaryId === story.id}
                          className="px-2 py-1 text-xs bg-green-600/20 hover:bg-green-600/40 text-green-200 rounded disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                          {generatingStorySummaryId === story.id ? '⚙️ Generating...' : '✨ Generate'}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Story Footer */}
                  <div className="pt-4 border-t border-white/20">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        <div className={`w-2 h-2 rounded-full ${
                          story.status === 'active' ? 'bg-green-400' : 'bg-gray-400'
                        }`}></div>
                        <span className="text-white/60 text-sm capitalize">{story.status}</span>
                      </div>
                      <span className="text-white/50 text-xs">
                        {new Date(story.updated_at).toLocaleDateString()}
                      </span>
                    </div>
                    <div className="flex space-x-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleViewSummary(story.id);
                        }}
                        className="flex-1 bg-blue-600/20 hover:bg-blue-600/40 text-blue-200 hover:text-white px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200"
                      >
                        📄 Summary
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleStoryClick(story.id);
                        }}
                        className="flex-1 bg-purple-600/20 hover:bg-purple-600/40 text-purple-200 hover:text-white px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200"
                      >
                        ▶️ Continue
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteStory(story.id, story.title);
                        }}
                        className="bg-red-600/20 hover:bg-red-600/40 text-red-200 hover:text-white px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200"
                        title="Delete story"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                </div>
              ))}

              {/* Add New Story Card */}
              <div
                onClick={handleCreateStory}
                className="bg-white/5 border-2 border-dashed border-white/30 rounded-2xl p-6 cursor-pointer hover:bg-white/10 hover:border-white/50 transition-all duration-200 flex flex-col items-center justify-center text-center min-h-[200px] group"
              >
                <div className="text-4xl mb-4 group-hover:scale-110 transition-transform">✨</div>
                <h4 className="text-lg font-semibold text-white mb-2">Create New Story</h4>
                <p className="text-white/60 text-sm">
                  Start a new interactive adventure
                </p>
              </div>
            </div>
          </>
        )}

        {/* Footer Stats */}
        {stories.length > 0 && (
          <div className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-xl p-6 text-center">
              <div className="text-3xl font-bold text-white mb-2">{stories.length}</div>
              <div className="text-white/70">Stories Created</div>
            </div>
            <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-xl p-6 text-center">
              <div className="text-3xl font-bold text-white mb-2">
                {stories.filter(s => s.status === 'active').length}
              </div>
              <div className="text-white/70">Active Stories</div>
            </div>
            <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-xl p-6 text-center">
              <div className="text-3xl font-bold text-white mb-2">∞</div>
              <div className="text-white/70">Possibilities</div>
            </div>
          </div>
        )}
      </main>

      {/* Summary Modal */}
      {showSummaryModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-[60] flex items-center justify-center p-4">
          <div className="bg-white rounded-lg max-w-4xl w-full max-h-[80vh] overflow-hidden">
            <div className="p-6 border-b">
              <div className="flex justify-between items-center">
                <h2 className="text-xl font-semibold">
                  Story Summary: {selectedStory?.title || 'Loading...'}
                </h2>
                <button
                  onClick={() => {
                    setShowSummaryModal(false);
                    setStorySummary(null);
                    setSelectedStory(null);
                  }}
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
                      {(() => {
                        const summaryText = storySummary.summary || 'No summary available';
                        console.log('[SUMMARY] Displaying summary:', summaryText);
                        console.log('[SUMMARY] Summary object:', storySummary);
                        return summaryText;
                      })()}
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
                  onClick={async () => {
                    console.log('[SUMMARY] Regenerate button clicked');
                    console.log('[SUMMARY] Selected story:', selectedStory);
                    setLoadingSummary(true);
                    try {
                      const { token } = useAuthStore.getState();
                      const url = `${getApiBaseUrl()}/api/stories/${selectedStory.id}/regenerate-summary`;
                      console.log('[SUMMARY] Calling API:', url);
                      
                      const response = await fetch(url, {
                        method: 'POST',
                        headers: {
                          'Authorization': `Bearer ${token}`,
                          'Content-Type': 'application/json',
                        },
                      });

                      console.log('[SUMMARY] Response status:', response.status);
                      
                      if (response.ok) {
                        const updatedSummary = await response.json();
                        console.log('[SUMMARY] Received response:', updatedSummary);
                        console.log('[SUMMARY] Summary content:', updatedSummary.summary);
                        console.log('[SUMMARY] Summary length:', updatedSummary.summary?.length);
                        setStorySummary(updatedSummary);
                      } else {
                        const errorText = await response.text();
                        console.error('[SUMMARY] Failed to regenerate summary:', response.status, errorText);
                      }
                    } catch (error) {
                      console.error('[SUMMARY] Error regenerating summary:', error);
                    } finally {
                      setLoadingSummary(false);
                    }
                  }}
                  disabled={loadingSummary}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  {loadingSummary ? 'Regenerating...' : 'Regenerate Summary'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <RouteProtection requireAuth={true} requireApproval={true}>
      <DashboardContent />
    </RouteProtection>
  );
}