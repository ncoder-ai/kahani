'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore, useStoryStore, useHasHydrated } from '@/store';
import apiClient, { getApiBaseUrl } from '@/lib/api';
import { RoleplayApi } from '@/lib/api/roleplay';
import type { RoleplayListItem } from '@/lib/api/roleplay';
import RouteProtection from '@/components/RouteProtection';
import { useUISettings } from '@/hooks/useUISettings';
import StorySettingsModal from '@/components/StorySettingsModal';
import HeroActions from '@/components/dashboard/HeroActions';
import ActivityFeed from '@/components/dashboard/ActivityFeed';
import DashboardStats from '@/components/dashboard/DashboardStats';
import StorySummaryModal from '@/components/dashboard/StorySummaryModal';

function DashboardContent() {
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const { stories, setStories, isLoading, setLoading } = useStoryStore();
  const hasHydrated = useHasHydrated();

  // Summary modal state
  const [selectedStory, setSelectedStory] = useState<any>(null);
  const [showSummaryModal, setShowSummaryModal] = useState(false);
  const [storySummary, setStorySummary] = useState<any>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [generatingStorySummaryId, setGeneratingStorySummaryId] = useState<number | null>(null);

  // Edit modal state
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingStoryId, setEditingStoryId] = useState<number | null>(null);

  // User settings
  const [userSettings, setUserSettings] = useState<any>(null);

  // Brainstorm state
  const [brainstormSessions, setBrainstormSessions] = useState<any[]>([]);
  const [selectedBrainstormIds, setSelectedBrainstormIds] = useState<Set<number>>(new Set());
  const [isDeletingBrainstorms, setIsDeletingBrainstorms] = useState(false);
  const [brainstormSelectMode, setBrainstormSelectMode] = useState(false);

  // Roleplay state
  const [roleplays, setRoleplays] = useState<RoleplayListItem[]>([]);
  const roleplayApiRef = useState(() => new RoleplayApi())[0];

  useUISettings(userSettings?.ui_preferences || null);

  // --- Data loading ---
  useEffect(() => {
    if (!hasHydrated) return;
    if (!user) { router.push('/login'); return; }
    loadStories();
    loadUserSettings();
    loadBrainstormSessions();
    loadRoleplays();
  }, [user, hasHydrated, router]);

  const loadStories = async () => {
    try {
      setLoading(true);
      const { token } = useAuthStore.getState();
      if (!token) { router.push('/login'); return; }
      const response = await fetch(`${await getApiBaseUrl()}/api/stories/?skip=0&limit=50&include_archived=true`, {
        method: 'GET',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      });
      if (!response.ok) {
        if (response.status === 401) { router.push('/login'); return; }
        throw new Error(`HTTP ${response.status}`);
      }
      setStories(await response.json());
    } catch (error) {
      console.error('Failed to load stories:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadUserSettings = async () => {
    try {
      const settings = await apiClient.getUserSettings();
      setUserSettings(settings.settings);
    } catch (err) {
      console.error('Failed to load user settings:', err);
    }
  };

  const loadBrainstormSessions = async () => {
    try {
      const response = await apiClient.getBrainstormSessions(false);
      setBrainstormSessions(response.sessions || []);
    } catch (error) {
      console.error('Failed to load brainstorm sessions:', error);
    }
  };

  const loadRoleplays = async () => {
    try {
      const data = await roleplayApiRef.listRoleplays();
      setRoleplays(data);
    } catch (error) {
      console.error('Failed to load roleplays:', error);
    }
  };

  // --- Helpers ---
  const formatRelativeDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = diffMs / (1000 * 60 * 60);
    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return `${Math.floor(diffHours)}h ago`;
    const diffDays = diffHours / 24;
    if (diffDays < 7) return `${Math.floor(diffDays)}d ago`;
    return date.toLocaleDateString();
  };

  // --- Story handlers ---
  const handleStoryClick = (storyId: number) => {
    const story = stories.find(s => s.id === storyId);
    if (story?.story_mode === 'roleplay') { router.push(`/roleplay/${storyId}`); return; }
    if (story && story.status === 'draft' && story.creation_step !== undefined && story.creation_step < 6) {
      router.push(`/create-story?story_id=${storyId}`);
    } else {
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
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      });
      if (response.ok) {
        setStorySummary(await response.json());
        setSelectedStory(stories.find(s => s.id === storyId));
      } else {
        setStorySummary({ error: 'Failed to load summary' });
      }
    } catch (error) {
      setStorySummary({ error: 'Error loading summary' });
    } finally {
      setLoadingSummary(false);
    }
  };

  const handleGenerateStorySummary = async (storyId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setGeneratingStorySummaryId(storyId);
    try {
      const { token } = useAuthStore.getState();
      const response = await fetch(`${await getApiBaseUrl()}/api/stories/${storyId}/generate-story-summary`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      });
      if (!response.ok) throw new Error('Failed to generate story summary');
      const data = await response.json();
      setStories(stories.map(s => s.id === storyId ? { ...s, summary: data.summary } : s));
      alert(`Story summary generated!\n\nChapters: ${data.chapters_summarized}\nScenes: ${data.total_scenes}`);
    } catch (error) {
      alert('Failed to generate story summary. Please try again.');
    } finally {
      setGeneratingStorySummaryId(null);
    }
  };

  const handleDeleteStory = async (storyId: number, _storyTitle: string) => {
    // Confirmation is handled by StoryCard's inline confirm UI (mobile-friendly)
    const { token } = useAuthStore.getState();
    const response = await fetch(`${await getApiBaseUrl()}/api/stories/${storyId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    if (!response.ok) {
      throw new Error('Failed to delete story');
    }
    // Refresh stories list
    const storiesData = await fetch(`${await getApiBaseUrl()}/api/stories`, {
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    if (storiesData.ok) setStories(await storiesData.json());
  };

  // --- Brainstorm handlers ---
  const toggleBrainstormSelection = (sessionId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedBrainstormIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(sessionId)) newSet.delete(sessionId);
      else newSet.add(sessionId);
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
    if (!confirm(`Are you sure you want to delete ${count} brainstorm session${count !== 1 ? 's' : ''}?\n\nThis action cannot be undone.`)) return;
    setIsDeletingBrainstorms(true);
    try {
      const result = await apiClient.deleteBrainstormSessions(Array.from(selectedBrainstormIds));
      await loadBrainstormSessions();
      setSelectedBrainstormIds(new Set());
      setBrainstormSelectMode(false);
      if (result.failed > 0) {
        alert(`Deleted ${result.succeeded} session${result.succeeded !== 1 ? 's' : ''}. ${result.failed} failed to delete.`);
      }
    } catch (error) {
      alert('Failed to delete some sessions. Please try again.');
    } finally {
      setIsDeletingBrainstorms(false);
    }
  };

  // --- Roleplay handlers ---
  const handleDeleteRoleplay = async (id: number, _title: string) => {
    const response = await roleplayApiRef.deleteRoleplay(id);
    setRoleplays(prev => prev.filter(rp => rp.story_id !== id));
  };

  // --- Brainstorm individual delete handler ---
  const handleDeleteBrainstorm = async (id: number, _summary: string) => {
    await apiClient.deleteBrainstormSessions([id]);
    await loadBrainstormSessions();
  };

  // --- Loading state ---
  if (!hasHydrated || !user) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-white/80">Loading...</p>
        </div>
      </div>
    );
  }

  const nonRoleplayStories = stories.filter(s => s.story_mode !== 'roleplay');

  return (
    <div className="min-h-screen theme-bg-primary pt-16">
      <main className="max-w-7xl mx-auto px-3 sm:px-6 py-6 sm:py-12">
        <HeroActions isAdmin={!!user?.is_admin} />

        <ActivityFeed
          stories={stories}
          brainstormSessions={brainstormSessions}
          roleplays={roleplays}
          isLoading={isLoading}
          generatingStorySummaryId={generatingStorySummaryId}
          onStoryClick={handleStoryClick}
          onViewSummary={handleViewSummary}
          onEditStory={(storyId) => { setEditingStoryId(storyId); setShowEditModal(true); }}
          onDeleteStory={handleDeleteStory}
          onGenerateStorySummary={handleGenerateStorySummary}
          onCreateStory={() => router.push('/create-story')}
          brainstormSelectMode={brainstormSelectMode}
          selectedBrainstormIds={selectedBrainstormIds}
          isDeletingBrainstorms={isDeletingBrainstorms}
          onToggleBrainstormSelectMode={() => setBrainstormSelectMode(true)}
          onToggleBrainstormSelection={toggleBrainstormSelection}
          onToggleSelectAllBrainstorms={toggleSelectAllBrainstorms}
          onDeleteSelectedBrainstorms={handleDeleteSelectedBrainstorms}
          onCancelBrainstormSelectMode={() => { setBrainstormSelectMode(false); setSelectedBrainstormIds(new Set()); }}
          onDeleteRoleplay={handleDeleteRoleplay}
          onDeleteBrainstorm={handleDeleteBrainstorm}
          formatRelativeDate={formatRelativeDate}
        />

        <DashboardStats
          storyCount={nonRoleplayStories.length}
          roleplayCount={roleplays.length}
        />
      </main>

      <StorySummaryModal
        isOpen={showSummaryModal}
        selectedStory={selectedStory}
        storySummary={storySummary}
        loadingSummary={loadingSummary}
        onClose={() => { setShowSummaryModal(false); setStorySummary(null); setSelectedStory(null); }}
        onSummaryUpdate={setStorySummary}
        onLoadingChange={setLoadingSummary}
      />

      <StorySettingsModal
        isOpen={showEditModal}
        onClose={() => { setShowEditModal(false); setEditingStoryId(null); }}
        storyId={editingStoryId || 0}
        onSaved={() => loadStories()}
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
