'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store';
import RouteProtection from '@/components/RouteProtection';
import UserManagement from '@/components/admin/UserManagement';
import SystemSettings from '@/components/admin/SystemSettings';
import Statistics from '@/components/admin/Statistics';

function AdminContent() {
  const router = useRouter();
  const { user } = useAuthStore();
  const [activeTab, setActiveTab] = useState<'users' | 'settings' | 'stats'>('users');

  const tabs = [
    { id: 'users' as const, name: 'User Management', icon: '👥' },
    { id: 'settings' as const, name: 'System Settings', icon: '⚙️' },
    { id: 'stats' as const, name: 'Statistics', icon: '📊' },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900">
      {/* Header */}
      <div className="bg-white/10 backdrop-blur-md border-b border-white/20">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-white flex items-center gap-2">
                🛡️ Admin Panel
              </h1>
              <p className="text-white/70 text-sm mt-1">
                Manage users, configure system settings, and view statistics
              </p>
            </div>
            <button
              onClick={() => router.push('/dashboard')}
              className="px-4 py-2 bg-white/10 hover:bg-white/20 border border-white/30 text-white rounded-lg transition-colors"
            >
              ← Back to Dashboard
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex space-x-2 mb-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-6 py-3 rounded-lg font-medium transition-all duration-200 ${
                activeTab === tab.id
                  ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white'
                  : 'bg-white/10 text-white/70 hover:bg-white/20 hover:text-white'
              }`}
            >
              <span className="mr-2">{tab.icon}</span>
              {tab.name}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 p-6">
          {activeTab === 'users' && <UserManagement />}
          {activeTab === 'settings' && <SystemSettings />}
          {activeTab === 'stats' && <Statistics />}
        </div>
      </div>
    </div>
  );
}

export default function AdminPage() {
  return (
    <RouteProtection requireAuth={true} requireApproval={true} requireAdmin={true}>
      <AdminContent />
    </RouteProtection>
  );
}

