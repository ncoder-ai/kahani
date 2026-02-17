'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store';
import { useUISettings } from '@/hooks/useUISettings';
import apiClient from '@/lib/api';
import { WorldsApi } from '@/lib/api/worlds';

const worldsApi = new WorldsApi();
import RouteProtection from '@/components/RouteProtection';
import WorldList from '@/components/worlds/WorldList';
import WorldDetail from '@/components/worlds/WorldDetail';
import type { World } from '@/lib/api/types';

function WorldsContent() {
  const router = useRouter();
  const { user } = useAuthStore();
  const [worlds, setWorlds] = useState<World[]>([]);
  const [selectedWorld, setSelectedWorld] = useState<World | null>(null);
  const [loading, setLoading] = useState(true);
  const [userSettings, setUserSettings] = useState<any>(null);

  useUISettings(userSettings?.ui_preferences || null);

  const loadWorlds = useCallback(async () => {
    try {
      setLoading(true);
      const data = await worldsApi.getWorlds();
      setWorlds(data);
    } catch (err) {
      console.error('Failed to load worlds:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user) {
      loadWorlds();
      apiClient.getUserSettings().then(s => setUserSettings(s.settings)).catch(() => {});
    }
  }, [user, loadWorlds]);

  const handleCreateWorld = async (name: string, description?: string) => {
    await worldsApi.createWorld(name, description);
    await loadWorlds();
  };

  const handleDeleteWorld = async (worldId: number) => {
    try {
      await worldsApi.deleteWorld(worldId);
      await loadWorlds();
    } catch (err: any) {
      const msg = err?.message || 'Failed to delete world';
      alert(msg);
    }
  };

  const handleSelectWorld = (world: World) => {
    setSelectedWorld(world);
  };

  const handleWorldUpdated = async () => {
    const data = await worldsApi.getWorlds();
    setWorlds(data);
    // Update the selected world reference
    if (selectedWorld) {
      const updated = data.find((w: World) => w.id === selectedWorld.id);
      if (updated) setSelectedWorld(updated);
    }
  };

  return (
    <div className="min-h-screen theme-bg-primary pt-16">
      {/* Header */}
      <div className="bg-white/10 backdrop-blur-md border-b border-white/20">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-white">Worlds</h1>
              <p className="text-white/70 text-sm mt-1">
                Manage shared universes, character chronicles, and location lorebooks
              </p>
            </div>
            <button
              onClick={() => router.push('/dashboard')}
              className="px-4 py-2 bg-white/10 hover:bg-white/20 border border-white/30 text-white rounded-lg transition-colors"
            >
              &larr; Back to Dashboard
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        {loading ? (
          <div className="py-16 text-center">
            <div className="w-12 h-12 border-3 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
            <p className="text-white/60">Loading worlds...</p>
          </div>
        ) : selectedWorld ? (
          <WorldDetail
            world={selectedWorld}
            onBack={() => setSelectedWorld(null)}
            onWorldUpdated={handleWorldUpdated}
          />
        ) : (
          <WorldList
            worlds={worlds}
            onSelectWorld={handleSelectWorld}
            onCreateWorld={handleCreateWorld}
            onDeleteWorld={handleDeleteWorld}
          />
        )}
      </div>
    </div>
  );
}

export default function WorldsPage() {
  return (
    <RouteProtection requireAuth={true} requireApproval={true}>
      <WorldsContent />
    </RouteProtection>
  );
}
