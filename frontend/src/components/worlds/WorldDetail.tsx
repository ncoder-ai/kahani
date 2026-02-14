'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronDown, ChevronRight, Check, X } from 'lucide-react';
import { WorldsApi } from '@/lib/api/worlds';

const worldsApi = new WorldsApi();
import type { World, WorldStory, WorldCharacter, WorldLocation } from '@/lib/api/types';
import CharacterChroniclePanel from './CharacterChroniclePanel';
import LocationLorebookPanel from './LocationLorebookPanel';

type Tab = 'stories' | 'characters' | 'locations';

const tabs: { id: Tab; name: string }[] = [
  { id: 'stories', name: 'Stories' },
  { id: 'characters', name: 'Characters' },
  { id: 'locations', name: 'Locations' },
];

interface WorldDetailProps {
  world: World;
  onBack: () => void;
  onWorldUpdated: () => void;
}

export default function WorldDetail({ world, onBack, onWorldUpdated }: WorldDetailProps) {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<Tab>('characters');
  const [stories, setStories] = useState<WorldStory[]>([]);
  const [characters, setCharacters] = useState<WorldCharacter[]>([]);
  const [locations, setLocations] = useState<WorldLocation[]>([]);
  const [loadingTab, setLoadingTab] = useState(false);
  const [expandedCharacter, setExpandedCharacter] = useState<number | null>(null);
  const [expandedLocation, setExpandedLocation] = useState<string | null>(null);

  // Inline name/description editing
  const [editingName, setEditingName] = useState(false);
  const [editName, setEditName] = useState(world.name);
  const [editingDesc, setEditingDesc] = useState(false);
  const [editDesc, setEditDesc] = useState(world.description || '');

  const loadTabData = useCallback(async (tab: Tab) => {
    setLoadingTab(true);
    try {
      if (tab === 'stories') {
        setStories(await worldsApi.getWorldStories(world.id));
      } else if (tab === 'characters') {
        setCharacters(await worldsApi.getWorldCharacters(world.id));
      } else {
        setLocations(await worldsApi.getWorldLocations(world.id));
      }
    } catch (err) {
      console.error(`Failed to load ${tab}:`, err);
    } finally {
      setLoadingTab(false);
    }
  }, [world.id]);

  useEffect(() => { loadTabData(activeTab); }, [activeTab, loadTabData]);

  const saveName = async () => {
    if (!editName.trim() || editName.trim() === world.name) {
      setEditingName(false);
      setEditName(world.name);
      return;
    }
    try {
      await worldsApi.updateWorld(world.id, { name: editName.trim() });
      onWorldUpdated();
      setEditingName(false);
    } catch (err) {
      console.error('Failed to update world name:', err);
    }
  };

  const saveDesc = async () => {
    const newDesc = editDesc.trim();
    if (newDesc === (world.description || '')) {
      setEditingDesc(false);
      return;
    }
    try {
      await worldsApi.updateWorld(world.id, { description: newDesc || undefined });
      onWorldUpdated();
      setEditingDesc(false);
    } catch (err) {
      console.error('Failed to update world description:', err);
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <button
          onClick={onBack}
          className="text-white/60 hover:text-white text-sm mb-4 inline-flex items-center gap-1 transition-colors"
        >
          &larr; Back to Worlds
        </button>

        {/* Editable name */}
        <div className="mb-2">
          {editingName ? (
            <div className="flex items-center gap-2">
              <input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="text-2xl font-bold bg-white/10 border border-white/20 rounded-lg px-3 py-1 text-white focus:outline-none focus:border-indigo-400"
                autoFocus
                onKeyDown={(e) => { if (e.key === 'Enter') saveName(); if (e.key === 'Escape') { setEditingName(false); setEditName(world.name); } }}
              />
              <button onClick={saveName} className="p-1 text-green-400 hover:bg-green-500/20 rounded"><Check className="w-5 h-5" /></button>
              <button onClick={() => { setEditingName(false); setEditName(world.name); }} className="p-1 text-white/40 hover:bg-white/10 rounded"><X className="w-5 h-5" /></button>
            </div>
          ) : (
            <h2
              className="text-2xl font-bold text-white cursor-pointer hover:text-white/80 transition-colors inline-block"
              onClick={() => setEditingName(true)}
              title="Click to edit"
            >
              {world.name}
            </h2>
          )}
        </div>

        {/* Editable description */}
        {editingDesc ? (
          <div className="flex items-start gap-2">
            <textarea
              value={editDesc}
              onChange={(e) => setEditDesc(e.target.value)}
              rows={2}
              className="flex-1 bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-white/80 text-sm focus:outline-none focus:border-indigo-400 resize-none"
              autoFocus
            />
            <button onClick={saveDesc} className="p-1 text-green-400 hover:bg-green-500/20 rounded"><Check className="w-4 h-4" /></button>
            <button onClick={() => { setEditingDesc(false); setEditDesc(world.description || ''); }} className="p-1 text-white/40 hover:bg-white/10 rounded"><X className="w-4 h-4" /></button>
          </div>
        ) : (
          <p
            className="text-white/60 text-sm cursor-pointer hover:text-white/80 transition-colors"
            onClick={() => setEditingDesc(true)}
            title="Click to edit"
          >
            {world.description || 'No description. Click to add one.'}
          </p>
        )}
      </div>

      {/* Tabs */}
      <div className="flex space-x-2 mb-6">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-6 py-3 rounded-lg font-medium transition-all duration-200 ${
              activeTab === tab.id
                ? 'bg-indigo-600 text-white'
                : 'bg-white/10 text-white/70 hover:bg-white/20 hover:text-white'
            }`}
          >
            {tab.name}
            {tab.id === 'stories' && stories.length > 0 && ` (${stories.length})`}
            {tab.id === 'characters' && characters.length > 0 && ` (${characters.length})`}
            {tab.id === 'locations' && locations.length > 0 && ` (${locations.length})`}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {loadingTab ? (
        <div className="py-12 text-center">
          <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-3"></div>
          <p className="text-white/60 text-sm">Loading...</p>
        </div>
      ) : (
        <>
          {/* Stories tab */}
          {activeTab === 'stories' && (
            <div>
              {stories.length === 0 ? (
                <div className="py-12 text-center text-white/50">No stories in this world yet.</div>
              ) : (
                <div className="space-y-3">
                  {stories.map((story) => (
                    <div
                      key={story.id}
                      onClick={() => router.push(`/story/${story.id}`)}
                      className="bg-white/5 border border-white/10 rounded-lg p-4 cursor-pointer hover:bg-white/10 hover:border-white/20 transition-all flex items-center justify-between"
                    >
                      <div>
                        <h4 className="text-white font-medium">{story.title}</h4>
                        <div className="flex items-center gap-3 mt-1">
                          {story.genre && <span className="text-white/50 text-xs">{story.genre}</span>}
                          <span className={`text-xs ${story.status === 'active' ? 'text-green-400' : 'text-gray-400'}`}>
                            {story.status}
                          </span>
                          <span className="text-white/30 text-xs">{story.content_rating}</span>
                        </div>
                        {story.description && (
                          <p className="text-white/50 text-sm mt-1 line-clamp-1">{story.description}</p>
                        )}
                      </div>
                      <span className="text-white/30 text-sm">&rarr;</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Characters tab */}
          {activeTab === 'characters' && (
            <div>
              {characters.length === 0 ? (
                <div className="py-12 text-center text-white/50">
                  No character chronicle entries in this world yet.
                  <br />
                  <span className="text-sm text-white/30">Chronicle entries are auto-extracted as stories progress.</span>
                </div>
              ) : (
                <div className="space-y-2">
                  {characters.map((char) => {
                    const isExpanded = expandedCharacter === char.character_id;
                    return (
                      <div key={char.character_id} className="bg-white/5 border border-white/10 rounded-lg overflow-hidden">
                        <button
                          onClick={() => setExpandedCharacter(isExpanded ? null : char.character_id)}
                          className="w-full px-4 py-3 flex items-center justify-between hover:bg-white/5 transition-colors"
                        >
                          <div className="flex items-center gap-3">
                            {isExpanded ? <ChevronDown className="w-4 h-4 text-white/40" /> : <ChevronRight className="w-4 h-4 text-white/40" />}
                            <span className="text-white font-medium">{char.character_name}</span>
                          </div>
                          <span className="text-white/40 text-sm">
                            {char.entry_count} {char.entry_count === 1 ? 'entry' : 'entries'}
                          </span>
                        </button>
                        {isExpanded && (
                          <div className="px-4 pb-4 border-t border-white/5">
                            <CharacterChroniclePanel
                              worldId={world.id}
                              characterId={char.character_id}
                              characterName={char.character_name}
                            />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Locations tab */}
          {activeTab === 'locations' && (
            <div>
              {locations.length === 0 ? (
                <div className="py-12 text-center text-white/50">
                  No location lorebook entries in this world yet.
                  <br />
                  <span className="text-sm text-white/30">Lorebook entries are auto-extracted as stories progress.</span>
                </div>
              ) : (
                <div className="space-y-2">
                  {locations.map((loc) => {
                    const isExpanded = expandedLocation === loc.location_name;
                    return (
                      <div key={loc.location_name} className="bg-white/5 border border-white/10 rounded-lg overflow-hidden">
                        <button
                          onClick={() => setExpandedLocation(isExpanded ? null : loc.location_name)}
                          className="w-full px-4 py-3 flex items-center justify-between hover:bg-white/5 transition-colors"
                        >
                          <div className="flex items-center gap-3">
                            {isExpanded ? <ChevronDown className="w-4 h-4 text-white/40" /> : <ChevronRight className="w-4 h-4 text-white/40" />}
                            <span className="text-white font-medium">{loc.location_name}</span>
                          </div>
                          <span className="text-white/40 text-sm">
                            {loc.entry_count} {loc.entry_count === 1 ? 'entry' : 'entries'}
                          </span>
                        </button>
                        {isExpanded && (
                          <div className="px-4 pb-4 border-t border-white/5">
                            <LocationLorebookPanel
                              worldId={world.id}
                              locationName={loc.location_name}
                            />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
