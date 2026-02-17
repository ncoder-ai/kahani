'use client';

import { useState, useEffect } from 'react';
import { getApiBaseUrl } from '@/lib/api';
import { useAuthStore } from '@/store';

interface StatsData {
  total_users: number;
  approved_users: number;
  pending_users: number;
  admin_users: number;
  total_stories: number;
  active_stories: number;
  draft_stories: number;
  archived_stories: number;
  nsfw_enabled_users: number;
  users_with_llm_access: number;
  users_with_tts_access: number;
}

export default function Statistics() {
  const { token } = useAuthStore();
  const [stats, setStats] = useState<StatsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${await getApiBaseUrl()}/api/admin/stats`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) throw new Error('Failed to fetch statistics');
      
      const data = await response.json();
      setStats(data);
    } catch (error) {
      console.error('Error fetching statistics:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="text-center py-12">
        <div className="w-12 h-12 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
        <p className="text-white/70">Loading statistics...</p>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="text-center py-12">
        <p className="text-red-400">Failed to load statistics</p>
      </div>
    );
  }

  const StatCard = ({ title, value, subtitle, icon, gradient }: {
    title: string;
    value: number;
    subtitle?: string;
    icon: string;
    gradient: string;
  }) => (
    <div className={`bg-gradient-to-br ${gradient} rounded-xl p-6 text-white`}>
      <div className="flex items-start justify-between mb-4">
        <div className="text-4xl">{icon}</div>
        <div className="text-right">
          <div className="text-3xl font-bold">{value.toLocaleString()}</div>
          {subtitle && <div className="text-sm opacity-80 mt-1">{subtitle}</div>}
        </div>
      </div>
      <div className="font-medium text-lg">{title}</div>
    </div>
  );

  const percentage = (part: number, total: number) => 
    total > 0 ? Math.round((part / total) * 100) : 0;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Platform Statistics</h2>
        <button
          onClick={fetchStats}
          className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors flex items-center gap-2"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
      </div>

      {/* User Statistics */}
      <div>
        <h3 className="text-xl font-bold text-white mb-4">User Statistics</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            title="Total Users"
            value={stats.total_users}
            icon="👥"
            gradient="from-blue-500 to-blue-600"
          />
          <StatCard
            title="Approved Users"
            value={stats.approved_users}
            subtitle={`${percentage(stats.approved_users, stats.total_users)}% of total`}
            icon="✅"
            gradient="from-green-500 to-green-600"
          />
          <StatCard
            title="Pending Approval"
            value={stats.pending_users}
            subtitle={`${percentage(stats.pending_users, stats.total_users)}% of total`}
            icon="⏳"
            gradient="from-yellow-500 to-yellow-600"
          />
          <StatCard
            title="Administrators"
            value={stats.admin_users}
            subtitle={`${percentage(stats.admin_users, stats.total_users)}% of total`}
            icon="👑"
            gradient="from-purple-500 to-purple-600"
          />
        </div>
      </div>

      {/* Story Statistics */}
      <div>
        <h3 className="text-xl font-bold text-white mb-4">Story Statistics</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            title="Total Stories"
            value={stats.total_stories}
            icon="📚"
            gradient="from-indigo-500 to-indigo-600"
          />
          <StatCard
            title="Active Stories"
            value={stats.active_stories}
            subtitle={`${percentage(stats.active_stories, stats.total_stories)}% of total`}
            icon="📖"
            gradient="from-cyan-500 to-cyan-600"
          />
          <StatCard
            title="Draft Stories"
            value={stats.draft_stories}
            subtitle={`${percentage(stats.draft_stories, stats.total_stories)}% of total`}
            icon="📝"
            gradient="from-orange-500 to-orange-600"
          />
          <StatCard
            title="Archived Stories"
            value={stats.archived_stories}
            subtitle={`${percentage(stats.archived_stories, stats.total_stories)}% of total`}
            icon="🗄️"
            gradient="from-gray-500 to-gray-600"
          />
        </div>
      </div>

      {/* Permission Statistics */}
      <div>
        <h3 className="text-xl font-bold text-white mb-4">Permission Distribution</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <StatCard
            title="NSFW Enabled"
            value={stats.nsfw_enabled_users}
            subtitle={`${percentage(stats.nsfw_enabled_users, stats.total_users)}% of users`}
            icon="🔥"
            gradient="from-red-500 to-red-600"
          />
          <StatCard
            title="LLM Access"
            value={stats.users_with_llm_access}
            subtitle={`${percentage(stats.users_with_llm_access, stats.total_users)}% of users`}
            icon="🤖"
            gradient="from-blue-500 to-purple-600"
          />
          <StatCard
            title="TTS Access"
            value={stats.users_with_tts_access}
            subtitle={`${percentage(stats.users_with_tts_access, stats.total_users)}% of users`}
            icon="🔊"
            gradient="from-green-500 to-teal-600"
          />
        </div>
      </div>

      {/* Overview Charts */}
      <div className="bg-white/5 rounded-xl p-6">
        <h3 className="text-xl font-bold text-white mb-6">Quick Overview</h3>
        
        {/* User Status Breakdown */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-2">
            <span className="text-white/80">User Approval Status</span>
            <span className="text-white/60 text-sm">{stats.total_users} total</span>
          </div>
          <div className="flex h-8 rounded-full overflow-hidden bg-white/10">
            {stats.approved_users > 0 && (
              <div
                className="bg-green-500 flex items-center justify-center text-white text-xs font-medium"
                style={{ width: `${percentage(stats.approved_users, stats.total_users)}%` }}
                title={`Approved: ${stats.approved_users}`}
              >
                {percentage(stats.approved_users, stats.total_users) > 10 && `${stats.approved_users}`}
              </div>
            )}
            {stats.pending_users > 0 && (
              <div
                className="bg-yellow-500 flex items-center justify-center text-white text-xs font-medium"
                style={{ width: `${percentage(stats.pending_users, stats.total_users)}%` }}
                title={`Pending: ${stats.pending_users}`}
              >
                {percentage(stats.pending_users, stats.total_users) > 10 && `${stats.pending_users}`}
              </div>
            )}
          </div>
          <div className="flex gap-4 mt-2 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-green-500"></div>
              <span className="text-white/60">Approved ({stats.approved_users})</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
              <span className="text-white/60">Pending ({stats.pending_users})</span>
            </div>
          </div>
        </div>

        {/* Story Status Breakdown */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-white/80">Story Status Distribution</span>
            <span className="text-white/60 text-sm">{stats.total_stories} total</span>
          </div>
          <div className="flex h-8 rounded-full overflow-hidden bg-white/10">
            {stats.active_stories > 0 && (
              <div
                className="bg-cyan-500 flex items-center justify-center text-white text-xs font-medium"
                style={{ width: `${percentage(stats.active_stories, stats.total_stories)}%` }}
                title={`Active: ${stats.active_stories}`}
              >
                {percentage(stats.active_stories, stats.total_stories) > 10 && `${stats.active_stories}`}
              </div>
            )}
            {stats.draft_stories > 0 && (
              <div
                className="bg-orange-500 flex items-center justify-center text-white text-xs font-medium"
                style={{ width: `${percentage(stats.draft_stories, stats.total_stories)}%` }}
                title={`Draft: ${stats.draft_stories}`}
              >
                {percentage(stats.draft_stories, stats.total_stories) > 10 && `${stats.draft_stories}`}
              </div>
            )}
            {stats.archived_stories > 0 && (
              <div
                className="bg-gray-500 flex items-center justify-center text-white text-xs font-medium"
                style={{ width: `${percentage(stats.archived_stories, stats.total_stories)}%` }}
                title={`Archived: ${stats.archived_stories}`}
              >
                {percentage(stats.archived_stories, stats.total_stories) > 10 && `${stats.archived_stories}`}
              </div>
            )}
          </div>
          <div className="flex gap-4 mt-2 text-sm flex-wrap">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-cyan-500"></div>
              <span className="text-white/60">Active ({stats.active_stories})</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-orange-500"></div>
              <span className="text-white/60">Draft ({stats.draft_stories})</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-gray-500"></div>
              <span className="text-white/60">Archived ({stats.archived_stories})</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

