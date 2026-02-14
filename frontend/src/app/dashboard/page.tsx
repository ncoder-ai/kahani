'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore, useStoryStore, useHasHydrated } from '@/store';
import { X, Trash2, CheckSquare, Square } from 'lucide-react';
import apiClient, { getApiBaseUrl } from '@/lib/api';
import RouteProtection from '@/components/RouteProtection';
import { useUISettings } from '@/hooks/useUISettings';
import StorySettingsModal from '@/components/StorySettingsModal';

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
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingStoryId, setEditingStoryId] = useState<number | null>(null);
  const [brainstormSessions, setBrainstormSessions] = useState<any[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [selectedBrainstormIds, setSelectedBrainstormIds] = useState<Set<number>>(new Set());
  const [isDeletingBrainstorms, setIsDeletingBrainstorms] = useState(false);
  const [brainstormSelectMode, setBrainstormSelectMode] = useState(false);

  // Apply UI settings (theme, font size, etc.)
  useUISettings(userSettings?.ui_preferences || null);

  useEffect(() => {
    if (!hasHydrated) return; 
    
    if (!user) {
      router.push('/login');
      return;
    }
    
    loadStories();
    loadUserSettings();
    loadBrainstormSessions();
  }, [user, hasHydrated, router]);

  const loadBrainstormSessions = async () => {
    try {
      setLoadingSessions(true);
      const response = await apiClient.getBrainstormSessions(false);
      setBrainstormSessions(response.sessions || []);
    } catch (error) {
      console.error('Failed to load brainstorm sessions:', error);
    } finally {
      setLoadingSessions(false);
    }
  };

  const toggleBrainstormSelection = (sessionId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedBrainstormIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(sessionId)) {
        newSet.delete(sessionId);
      } else {
        newSet.add(sessionId);
      }
      return newSet;
    });
  };

  const toggleSelectAllBrainstorms = () => {
    if (selectedBrainstormIds.size === brainstormSessions.length) {
      setSelectedBrainstormIds(new Set());
    } else {
      setSelectedBrainstormIds(new Set(brainstormSessions.map(s => s.id)));
    }
  };

  const handleDeleteSelectedBrainstorms = async () => {
    if (selectedBrainstormIds.size === 0) return;
    
    const count = selectedBrainstormIds.size;
    if (!confirm(`Are you sure you want to delete ${count} brainstorm session${count !== 1 ? 's' : ''}?\n\nThis action cannot be undone.`)) {
      return;
    }

    setIsDeletingBrainstorms(true);
    try {
      const result = await apiClient.deleteBrainstormSessions(Array.from(selectedBrainstormIds));
      
      // Reload sessions
      await loadBrainstormSessions();
      
      // Clear selection and exit select mode
      setSelectedBrainstormIds(new Set());
      setBrainstormSelectMode(false);
      
      if (result.failed > 0) {
        alert(`Deleted ${result.succeeded} session${result.succeeded !== 1 ? 's' : ''}. ${result.failed} failed to delete.`);
      }
    } catch (error) {
      console.error('Failed to delete brainstorm sessions:', error);
      alert('Failed to delete some sessions. Please try again.');
    } finally {
      setIsDeletingBrainstorms(false);
    }
  };

  const cancelBrainstormSelectMode = () => {
    setBrainstormSelectMode(false);
    setSelectedBrainstormIds(new Set());
  };

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
      
      if (!token) {
        console.error('No token available for stories request');
        router.push('/login');
        return;
      }
      
      // Make direct fetch request with explicit Authorization header - include all stories (active and archived)
      const response = await fetch(`${await getApiBaseUrl()}/api/stories/?skip=0&limit=50&include_archived=true`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });
      
      
      if (!response.ok) {
        if (response.status === 401) {
          console.error('Token invalid, redirecting to login');
          router.push('/login');
          return;
        }
        throw new Error(`HTTP ${response.status}`);
      }
      
      const storiesData = await response.json();
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
    
    console.log('[Dashboard] Story clicked:', {
      id: storyId,
      status: story?.status,
      creation_step: story?.creation_step
    });
    
    // Only redirect to creation flow if story is explicitly a draft AND incomplete
    // Stories with status='active' or creation_step=6 should always go to story view
    if (story && 
        story.status === 'draft' && 
        story.creation_step !== undefined && 
        story.creation_step < 6) {  // Changed from < 5 to < 6
      console.log('[Dashboard] Redirecting to create-story (incomplete draft)');
      router.push(`/create-story?story_id=${storyId}`);
    } else {
      // Story is fully created or from brainstorm, go to story view
      console.log('[Dashboard] Redirecting to story view');
      router.push(`/story/${storyId}`);
    }
  };

  const handleViewSummary = async (storyId: number) => {
    setLoadingSummary(true);
    setShowSummaryModal(true);
    
    try {
      const { token } = useAuthStore.getState();
      const url = `${await getApiBaseUrl()}/api/stories/${storyId}/summary`;
      
      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      
      if (response.ok) {
        const summaryData = await response.json();
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
        `${await getApiBaseUrl()}/api/stories/${storyId}/generate-story-summary`,
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

    
    try {
      const { token } = useAuthStore.getState();
      const response = await fetch(`${await getApiBaseUrl()}/api/stories/${storyId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        const data = await response.json();
        
        // Refresh the stories list
        const storiesData = await fetch(`${await getApiBaseUrl()}/api/stories`, {
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
          
          <div className="flex justify-center gap-4 flex-wrap">
            <button
              onClick={() => router.push('/brainstorm')}
              className="bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700 text-white px-8 py-4 rounded-2xl font-semibold text-lg transform hover:scale-105 transition-all duration-200 shadow-lg"
            >
              💡 Brainstorm New Story
            </button>
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
            <button
              onClick={() => router.push('/worlds')}
              className="bg-gradient-to-r from-indigo-500 to-blue-600 hover:from-indigo-600 hover:to-blue-700 text-white px-8 py-4 rounded-2xl font-semibold text-lg transform hover:scale-105 transition-all duration-200 shadow-lg"
            >
              Worlds
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

        {/* Continue Brainstorming Section */}
        {brainstormSessions.length > 0 && (
          <div className="mb-12">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold text-white flex items-center gap-2">
                💡 Continue Brainstorming
                <span className="text-sm font-normal text-white/60">
                  ({brainstormSessions.length} session{brainstormSessions.length !== 1 ? 's' : ''})
                </span>
              </h3>
              
              <div className="flex items-center gap-2">
                {brainstormSelectMode ? (
                  <>
                    <button
                      onClick={toggleSelectAllBrainstorms}
                      className="text-white/70 hover:text-white px-3 py-1.5 rounded-lg hover:bg-white/10 transition-colors text-sm flex items-center gap-1.5"
                    >
                      {selectedBrainstormIds.size === brainstormSessions.length ? (
                        <CheckSquare className="w-4 h-4" />
                      ) : (
                        <Square className="w-4 h-4" />
                      )}
                      {selectedBrainstormIds.size === brainstormSessions.length ? 'Deselect All' : 'Select All'}
                    </button>
                    <button
                      onClick={handleDeleteSelectedBrainstorms}
                      disabled={selectedBrainstormIds.size === 0 || isDeletingBrainstorms}
                      className="bg-red-600 hover:bg-red-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white px-3 py-1.5 rounded-lg text-sm flex items-center gap-1.5 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                      {isDeletingBrainstorms ? 'Deleting...' : `Delete (${selectedBrainstormIds.size})`}
                    </button>
                    <button
                      onClick={cancelBrainstormSelectMode}
                      className="text-white/70 hover:text-white px-3 py-1.5 rounded-lg hover:bg-white/10 transition-colors text-sm"
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    onClick={() => setBrainstormSelectMode(true)}
                    className="text-white/70 hover:text-white px-3 py-1.5 rounded-lg hover:bg-white/10 transition-colors text-sm flex items-center gap-1.5"
                  >
                    <Trash2 className="w-4 h-4" />
                    Manage
                  </button>
                )}
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {brainstormSessions.map((session) => (
                <div
                  key={session.id}
                  onClick={(e) => {
                    if (brainstormSelectMode) {
                      toggleBrainstormSelection(session.id, e);
                    } else {
                      router.push(`/brainstorm?session_id=${session.id}`);
                    }
                  }}
                  className={`relative bg-gradient-to-r from-green-500/10 to-emerald-500/10 backdrop-blur-md border rounded-xl p-4 text-left transition-all group cursor-pointer ${
                    selectedBrainstormIds.has(session.id)
                      ? 'border-red-500 ring-2 ring-red-500/30'
                      : 'border-green-500/30 hover:from-green-500/20 hover:to-emerald-500/20'
                  }`}
                >
                  {/* Selection checkbox */}
                  {brainstormSelectMode && (
                    <div 
                      className="absolute top-2 right-2 z-10"
                      onClick={(e) => toggleBrainstormSelection(session.id, e)}
                    >
                      {selectedBrainstormIds.has(session.id) ? (
                        <CheckSquare className="w-5 h-5 text-red-400" />
                      ) : (
                        <Square className="w-5 h-5 text-white/40 hover:text-white/70" />
                      )}
                    </div>
                  )}
                  
                  <div className="flex items-start justify-between mb-2">
                    <span className="text-green-400 text-sm font-medium capitalize">
                      {session.status}
                    </span>
                    <span className={`text-white/40 text-xs ${brainstormSelectMode ? 'mr-6' : ''}`}>
                      {session.message_count} messages
                    </span>
                  </div>
                  <p className="text-white/80 text-sm line-clamp-2 mb-2">
                    {session.summary || 'Brainstorming session...'}
                  </p>
                  <div className="flex items-center justify-between text-xs text-white/50">
                    <span>
                      {session.updated_at ? new Date(session.updated_at).toLocaleDateString() : 'Recently'}
                    </span>
                    {!brainstormSelectMode && (
                      <span className="text-green-400 opacity-0 group-hover:opacity-100 transition-opacity">
                        Continue →
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

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
                      <span className="text-xs text-gray-400">No story summary available</span>
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
                          setEditingStoryId(story.id);
                          setShowEditModal(true);
                        }}
                        className="bg-yellow-600/20 hover:bg-yellow-600/40 text-yellow-200 hover:text-white px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200"
                        title="Edit story settings"
                      >
                        ✏️
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
                    setLoadingSummary(true);
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
      
      {/* Story Settings Edit Modal */}
      <StorySettingsModal
        isOpen={showEditModal}
        onClose={() => {
          setShowEditModal(false);
          setEditingStoryId(null);
        }}
        storyId={editingStoryId || 0}
        onSaved={() => {
          loadStories(); // Reload stories after save
        }}
      />
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