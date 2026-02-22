'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore, useHasHydrated } from '@/store';
import { PlusCircle, Trash2, MessageSquare, Users, Clock } from 'lucide-react';
import { RoleplayApi } from '@/lib/api/roleplay';
import type { RoleplayListItem } from '@/lib/api/roleplay';
import RouteProtection from '@/components/RouteProtection';
import { useUISettings } from '@/hooks/useUISettings';
import apiClient from '@/lib/api';

const roleplayApi = new RoleplayApi();

function RoleplayContent() {
  const router = useRouter();
  const { user } = useAuthStore();
  const hasHydrated = useHasHydrated();
  const [roleplays, setRoleplays] = useState<RoleplayListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [userSettings, setUserSettings] = useState<any>(null);

  useUISettings(userSettings?.ui_preferences || null);

  useEffect(() => {
    if (!hasHydrated || !user) return;
    loadRoleplays();
    loadSettings();
  }, [user, hasHydrated]);

  const loadRoleplays = async () => {
    try {
      setIsLoading(true);
      const data = await roleplayApi.listRoleplays();
      setRoleplays(data);
    } catch (error) {
      console.error('Failed to load roleplays:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const loadSettings = async () => {
    try {
      const settings = await apiClient.getUserSettings();
      setUserSettings(settings);
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  };

  const handleDelete = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this roleplay? This cannot be undone.')) return;
    try {
      setDeletingId(id);
      await roleplayApi.deleteRoleplay(id);
      setRoleplays(prev => prev.filter(rp => rp.story_id !== id));
    } catch (error) {
      console.error('Failed to delete roleplay:', error);
    } finally {
      setDeletingId(null);
    }
  };

  const formatDate = (dateStr: string) => {
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

  if (!hasHydrated || !user) {
    return (
      <div className="min-h-screen theme-bg-primary flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen theme-bg-primary pt-16">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <MessageSquare className="w-8 h-8 theme-accent-primary" />
              Roleplay Sessions
            </h1>
            <p className="text-white/60 mt-1">Interactive character roleplay conversations</p>
          </div>
          <button
            onClick={() => router.push('/roleplay/create')}
            className="theme-btn-primary flex items-center gap-2 px-5 py-2.5 rounded-xl font-medium"
          >
            <PlusCircle className="w-5 h-5" />
            New Roleplay
          </button>
        </div>

        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          </div>
        )}

        {/* Empty state */}
        {!isLoading && roleplays.length === 0 && (
          <div className="text-center py-20">
            <MessageSquare className="w-16 h-16 text-white/20 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-white/70 mb-2">No roleplays yet</h2>
            <p className="text-white/40 mb-6">Create your first roleplay session to get started</p>
            <button
              onClick={() => router.push('/roleplay/create')}
              className="theme-btn-primary px-6 py-3 rounded-xl font-medium"
            >
              Create Roleplay
            </button>
          </div>
        )}

        {/* Roleplay grid */}
        {!isLoading && roleplays.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {roleplays.map((rp) => (
              <div
                key={rp.story_id}
                onClick={() => router.push(`/roleplay/${rp.story_id}`)}
                className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl p-6 cursor-pointer hover:bg-white/15 hover:scale-[1.02] transition-all duration-200 group"
              >
                {/* Title + rating badge */}
                <div className="flex items-start justify-between mb-3">
                  <h3 className="text-lg font-semibold text-white group-hover:theme-accent-primary transition-colors line-clamp-1">
                    {rp.title}
                  </h3>
                  {rp.content_rating === 'nsfw' && (
                    <span className="text-xs px-2 py-0.5 bg-red-500/30 text-red-300 rounded-full flex-shrink-0 ml-2">
                      NSFW
                    </span>
                  )}
                </div>

                {/* Scenario */}
                {rp.scenario && (
                  <p className="text-white/50 text-sm line-clamp-2 mb-4">{rp.scenario}</p>
                )}

                {/* Characters */}
                <div className="flex items-center gap-2 mb-4">
                  <Users className="w-4 h-4 text-white/40 flex-shrink-0" />
                  <div className="text-sm text-white/60 line-clamp-1">
                    {rp.characters.join(', ')}
                  </div>
                </div>

                {/* Footer: turn count + date + actions */}
                <div className="flex items-center justify-between pt-3 border-t border-white/10">
                  <div className="flex items-center gap-4 text-xs text-white/40">
                    <span className="flex items-center gap-1">
                      <MessageSquare className="w-3.5 h-3.5" />
                      {rp.turn_count} turns
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5" />
                      {formatDate(rp.updated_at || rp.created_at)}
                    </span>
                  </div>
                  <button
                    onClick={(e) => handleDelete(rp.story_id, e)}
                    disabled={deletingId === rp.story_id}
                    className="p-1.5 hover:bg-red-500/20 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                  >
                    <Trash2 className={`w-4 h-4 ${deletingId === rp.story_id ? 'text-white/30 animate-pulse' : 'text-red-400'}`} />
                  </button>
                </div>
              </div>
            ))}

            {/* Create new card */}
            <div
              onClick={() => router.push('/roleplay/create')}
              className="bg-white/5 border-2 border-dashed border-white/20 rounded-2xl p-6 cursor-pointer hover:bg-white/10 hover:border-white/40 transition-all duration-200 flex flex-col items-center justify-center min-h-[200px]"
            >
              <PlusCircle className="w-10 h-10 text-white/30 mb-3" />
              <span className="text-white/50 font-medium">New Roleplay</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function RoleplayPage() {
  return (
    <RouteProtection requireAuth={true} requireApproval={true}>
      <RoleplayContent />
    </RouteProtection>
  );
}
