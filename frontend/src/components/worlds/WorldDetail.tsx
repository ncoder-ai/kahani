'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronDown, ChevronRight, Check, X, Save, BookOpen, Users } from 'lucide-react';
import { WorldsApi } from '@/lib/api/worlds';

const worldsApi = new WorldsApi();
import type { World, WorldStory, WorldCharacter, WorldLocation, ChronicleEntry } from '@/lib/api/types';
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

  // Timeline ordering
  const [timelineEdits, setTimelineEdits] = useState<Record<number, string>>({});
  const [savingOrder, setSavingOrder] = useState(false);

  const loadStories = useCallback(async () => {
    try {
      const data = await worldsApi.getWorldStories(world.id);
      setStories(data);
      const edits: Record<number, string> = {};
      data.forEach((s) => {
        edits[s.id] = s.timeline_order != null ? String(s.timeline_order) : '';
      });
      setTimelineEdits(edits);
    } catch (err) {
      console.error('Failed to load stories:', err);
    }
  }, [world.id]);

  // Always load stories (needed by both Stories tab and snapshot dropdown in Characters tab)
  useEffect(() => { loadStories(); }, [loadStories]);

  const loadTabData = useCallback(async (tab: Tab) => {
    setLoadingTab(true);
    try {
      if (tab === 'stories') {
        await loadStories();
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
  }, [world.id, loadStories]);

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

  const hasTimelineChanges = stories.some((s) => {
    const current = s.timeline_order != null ? String(s.timeline_order) : '';
    return timelineEdits[s.id] !== current;
  });

  const saveTimelineOrder = async () => {
    setSavingOrder(true);
    try {
      const storyOrders = stories
        .filter((s) => timelineEdits[s.id] !== '')
        .map((s) => ({
          story_id: s.id,
          timeline_order: parseInt(timelineEdits[s.id], 10),
        }))
        .filter((o) => !isNaN(o.timeline_order));

      await worldsApi.reorderWorldStories(world.id, storyOrders);
      await loadTabData('stories');
    } catch (err) {
      console.error('Failed to save timeline order:', err);
      alert('Failed to save timeline order.');
    } finally {
      setSavingOrder(false);
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

      {/* Constellation View — visual world map */}
      {stories.length >= 2 && (
        <div className="mb-8">
          <ConstellationMap stories={stories} worldId={world.id} />
        </div>
      )}

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
                <>
                  {/* Timeline order header */}
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-white/40 text-xs">
                      Set timeline order to define chronological position (lower = earlier in timeline).
                    </p>
                    {hasTimelineChanges && (
                      <button
                        onClick={saveTimelineOrder}
                        disabled={savingOrder}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-600/50 text-white text-sm rounded-lg transition-colors"
                      >
                        <Save className="w-3.5 h-3.5" />
                        {savingOrder ? 'Saving...' : 'Save Order'}
                      </button>
                    )}
                  </div>
                  <div className="space-y-3">
                    {stories.map((story) => (
                      <div
                        key={story.id}
                        className="bg-white/5 border border-white/10 rounded-lg p-4 hover:bg-white/10 hover:border-white/20 transition-all flex items-center justify-between"
                      >
                        <div
                          className="flex-1 cursor-pointer"
                          onClick={() => router.push(`/story/${story.id}`)}
                        >
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
                        <div className="flex items-center gap-2 ml-4 flex-shrink-0">
                          <label className="text-white/30 text-xs">Order:</label>
                          <input
                            type="number"
                            value={timelineEdits[story.id] ?? ''}
                            onChange={(e) => setTimelineEdits((prev) => ({ ...prev, [story.id]: e.target.value }))}
                            onClick={(e) => e.stopPropagation()}
                            className="w-16 bg-white/10 border border-white/20 rounded px-2 py-1 text-sm text-white text-center focus:outline-none focus:border-indigo-400"
                            placeholder="-"
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </>
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
                              stories={stories}
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

// ========== Constellation Map ==========

const GENRE_COLORS: Record<string, string> = {
  fantasy: '#a78bfa',
  'sci-fi': '#22d3ee',
  'science fiction': '#22d3ee',
  romance: '#f472b6',
  erotica: '#fb7185',
  mystery: '#fbbf24',
  horror: '#ef4444',
  thriller: '#f97316',
  adventure: '#34d399',
  drama: '#c084fc',
};
const DEFAULT_STAR_COLOR = '#e2e8f0';

function getGenreColor(genre?: string): string {
  if (!genre) return DEFAULT_STAR_COLOR;
  return GENRE_COLORS[genre.toLowerCase()] ?? DEFAULT_STAR_COLOR;
}

function seededRandom(seed: number) {
  let s = seed;
  return () => {
    s = (s * 16807 + 0) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

function hashStringToHue(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  return Math.abs(hash) % 360;
}

function starSize(sceneCount: number): number {
  return Math.min(32, Math.max(12, 12 + Math.sqrt(sceneCount) * 2));
}

interface StarPosition {
  x: number;
  y: number;
  size: number;
  color: string;
  story: WorldStory;
}

function computeStarPositions(stories: WorldStory[]): StarPosition[] {
  if (stories.length === 0) return [];
  const cx = 50;
  const cy = 55;
  const rx = 36;
  const ry = 28;
  const startAngle = Math.PI;
  const endAngle = 0;
  const n = stories.length;

  return stories.map((story, i) => {
    const t = n === 1 ? 0.5 : i / (n - 1);
    const angle = startAngle + (endAngle - startAngle) * t;
    return {
      x: cx + rx * Math.cos(angle),
      y: cy - ry * Math.sin(angle),
      size: starSize(story.scene_count ?? 0),
      color: getGenreColor(story.genre),
      story,
    };
  });
}

interface CharacterLink {
  fromIdx: number;
  toIdx: number;
  characters: string[];
  color: string;
}

function findCharacterLinks(stories: WorldStory[]): CharacterLink[] {
  const links: CharacterLink[] = [];
  for (let i = 0; i < stories.length; i++) {
    for (let j = i + 1; j < stories.length; j++) {
      const a = stories[i].character_names ?? [];
      const b = stories[j].character_names ?? [];
      const shared = a.filter((name) => b.includes(name));
      if (shared.length > 0) {
        const hue = hashStringToHue(shared[0]);
        links.push({
          fromIdx: i,
          toIdx: j,
          characters: shared,
          color: `hsl(${hue}, 70%, 60%)`,
        });
      }
    }
  }
  return links;
}

function ConstellationMap({ stories, worldId }: { stories: WorldStory[]; worldId: number }) {
  const router = useRouter();
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [charIdMap, setCharIdMap] = useState<Record<string, number>>({});
  const [selectedCharName, setSelectedCharName] = useState<string | null>(null);
  const [charContent, setCharContent] = useState<string | null>(null);
  const [charEntries, setCharEntries] = useState<ChronicleEntry[]>([]);
  const [loadingChar, setLoadingChar] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [loadingDetails, setLoadingDetails] = useState(false);

  // Fetch character name → ID mapping once
  useEffect(() => {
    worldsApi.getWorldCharacters(worldId).then((chars) => {
      const map: Record<string, number> = {};
      chars.forEach((c) => { map[c.character_name] = c.character_id; });
      setCharIdMap(map);
    }).catch(() => {});
  }, [worldId]);

  const handleCharacterClick = async (name: string) => {
    if (selectedCharName === name) {
      setSelectedCharName(null);
      setCharContent(null);
      setCharEntries([]);
      setShowDetails(false);
      return;
    }
    setSelectedCharName(name);
    setCharContent(null);
    setCharEntries([]);
    setShowDetails(false);
    const charId = charIdMap[name];
    if (!charId) return;
    setLoadingChar(true);
    const branchId = selectedIdx !== null ? stories[selectedIdx]?.current_branch_id : undefined;
    try {
      const snap = await worldsApi.getCharacterSnapshot(worldId, charId, branchId);
      if (snap.snapshot_text) {
        setCharContent(snap.snapshot_text);
      } else {
        // No snapshot — load entries directly
        const entries = await worldsApi.getCharacterChronicle(worldId, charId, undefined, branchId);
        setCharEntries(entries);
      }
    } catch {
      setCharContent(null);
    } finally {
      setLoadingChar(false);
    }
  };

  const handleShowDetails = async () => {
    if (showDetails) { setShowDetails(false); return; }
    setShowDetails(true);
    if (charEntries.length > 0) return; // already loaded
    setLoadingDetails(true);
    const charId = selectedCharName ? charIdMap[selectedCharName] : null;
    if (!charId) { setLoadingDetails(false); return; }
    const branchId = selectedIdx !== null ? stories[selectedIdx]?.current_branch_id : undefined;
    try {
      const entries = await worldsApi.getCharacterChronicle(worldId, charId, undefined, branchId);
      setCharEntries(entries);
    } catch { /* ignore */ }
    finally { setLoadingDetails(false); }
  };

  const stars = useMemo(() => computeStarPositions(stories), [stories]);
  const links = useMemo(() => findCharacterLinks(stories), [stories]);
  const bgStars = useMemo(() => {
    const rand = seededRandom(worldId);
    return Array.from({ length: 100 }, () => ({
      x: rand() * 100,
      y: rand() * 100,
      size: rand() * 1.5 + 0.5,
      delay: rand() * 5,
      duration: rand() * 3 + 2,
    }));
  }, [worldId]);

  const selectedStory = selectedIdx !== null ? stories[selectedIdx] : null;

  return (
    <div className="space-y-3">
      {/* Canvas */}
      <div className="relative overflow-hidden rounded-2xl bg-[#0a0a1a] border border-white/10"
        style={{ height: 'clamp(320px, 40vw, 420px)' }}>
        {/* Background stars */}
        <div className="absolute inset-0 animate-drift">
          {bgStars.map((s, i) => (
            <div
              key={i}
              className="absolute rounded-full bg-white animate-twinkle"
              style={{
                left: `${s.x}%`,
                top: `${s.y}%`,
                width: `${s.size}px`,
                height: `${s.size}px`,
                animationDelay: `${s.delay}s`,
                animationDuration: `${s.duration}s`,
              }}
            />
          ))}
        </div>

        {/* SVG lines */}
        <svg className="absolute inset-0 w-full h-full z-10 pointer-events-none">
          {links.map((link, i) => {
            const from = stars[link.fromIdx];
            const to = stars[link.toIdx];
            if (!from || !to) return null;
            const connected = hoveredIdx !== null &&
              (link.fromIdx === hoveredIdx || link.toIdx === hoveredIdx);
            const dimmed = hoveredIdx !== null && !connected;

            return (
              <line
                key={i}
                x1={`${from.x}%`} y1={`${from.y}%`}
                x2={`${to.x}%`} y2={`${to.y}%`}
                stroke={link.color}
                strokeWidth={connected ? 1.5 : 1}
                strokeDasharray="4 4"
                opacity={dimmed ? 0.06 : connected ? 0.7 : 0.25}
                style={{
                  strokeDashoffset: 100,
                  animation: `lineDrawIn 1s ease-out ${0.6 + i * 0.12}s forwards`,
                  transition: 'opacity 0.3s ease',
                }}
              />
            );
          })}
        </svg>

        {/* Story stars */}
        {stars.map((star, i) => {
          const isHovered = hoveredIdx === i;
          const isSelected = selectedIdx === i;
          const isDimmed = hoveredIdx !== null && hoveredIdx !== i;
          const sz = star.size;
          const c = star.color;

          return (
            <div
              key={star.story.id}
              className="absolute z-20"
              style={{
                left: `${star.x}%`,
                top: `${star.y}%`,
                transform: 'translate(-50%, -50%)',
                opacity: 0,
                animation: `starAppear 0.5s ease-out ${i * 0.12}s forwards`,
              }}
            >
              <button
                onClick={() => { setSelectedIdx(selectedIdx === i ? null : i); setSelectedCharName(null); setCharContent(null); setCharEntries([]); }}
                onMouseEnter={() => setHoveredIdx(i)}
                onMouseLeave={() => setHoveredIdx(null)}
                className="relative flex items-center justify-center"
                style={{ minWidth: '44px', minHeight: '44px' }}
                title={star.story.title}
              >
                <div
                  className="rounded-full transition-all duration-300"
                  style={{
                    width: `${sz}px`,
                    height: `${sz}px`,
                    backgroundColor: c,
                    boxShadow: isHovered || isSelected
                      ? `0 0 ${sz}px ${c}, 0 0 ${sz * 2.5}px ${c}80, 0 0 ${sz * 4}px ${c}40`
                      : `0 0 ${sz * 0.6}px ${c}, 0 0 ${sz * 1.5}px ${c}50, 0 0 ${sz * 3}px ${c}20`,
                    transform: isHovered || isSelected ? 'scale(1.3)' : 'scale(1)',
                    opacity: isDimmed ? 0.4 : 1,
                  }}
                />
                {isSelected && (
                  <div
                    className="absolute rounded-full border-2 animate-pulse"
                    style={{
                      width: `${sz + 12}px`,
                      height: `${sz + 12}px`,
                      borderColor: `${c}60`,
                    }}
                  />
                )}
              </button>

              {/* Label */}
              <div
                className="absolute left-1/2 -translate-x-1/2 text-center pointer-events-none whitespace-nowrap transition-opacity duration-300"
                style={{ top: `${sz / 2 + 24}px`, opacity: isDimmed ? 0.3 : 1 }}
              >
                <p className="text-[11px] text-white/70 font-medium max-w-[100px] truncate">
                  {star.story.title}
                </p>
                <p className="text-[9px] text-white/40">
                  {star.story.scene_count ?? 0}s · {star.story.chapter_count ?? 0}ch
                </p>
              </div>

              {/* Hover tooltip */}
              {isHovered && (
                <div
                  className="absolute left-1/2 -translate-x-1/2 bg-black/80 backdrop-blur border border-white/20 rounded-lg px-3 py-2 pointer-events-none z-30 whitespace-nowrap"
                  style={{ bottom: `${sz / 2 + 20}px` }}
                >
                  <p className="text-xs font-semibold text-white">{star.story.title}</p>
                  {star.story.genre && (
                    <p className="text-[10px] mt-0.5" style={{ color: c }}>{star.story.genre}</p>
                  )}
                  {star.story.character_names && star.story.character_names.length > 0 && (
                    <p className="text-[10px] text-white/50 mt-0.5">
                      {star.story.character_names.slice(0, 4).join(', ')}
                      {star.story.character_names.length > 4 && ` +${star.story.character_names.length - 4}`}
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Selected story detail panel */}
      {selectedStory && (
        <div className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-5 relative animate-in slide-in-from-top-2 duration-200">
          <button
            onClick={() => setSelectedIdx(null)}
            className="absolute top-3 right-3 p-1.5 hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="w-4 h-4 text-white/50" />
          </button>

          <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-5">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <div
                  className="w-3 h-3 rounded-full flex-shrink-0"
                  style={{
                    backgroundColor: getGenreColor(selectedStory.genre),
                    boxShadow: `0 0 8px ${getGenreColor(selectedStory.genre)}`,
                  }}
                />
                <h4 className="text-lg font-bold text-white">{selectedStory.title}</h4>
              </div>
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                {selectedStory.genre && (
                  <span className="px-2 py-0.5 text-xs rounded-full"
                    style={{ backgroundColor: `${getGenreColor(selectedStory.genre)}20`, color: getGenreColor(selectedStory.genre) }}>
                    {selectedStory.genre}
                  </span>
                )}
                <span className={`px-2 py-0.5 text-xs rounded-full ${
                  selectedStory.status === 'active' ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'
                }`}>{selectedStory.status}</span>
                <span className="text-xs text-white/40 flex items-center gap-1">
                  <BookOpen className="w-3 h-3" />
                  {selectedStory.scene_count ?? 0} scenes · {selectedStory.chapter_count ?? 0} ch
                </span>
              </div>
              {selectedStory.description && (
                <p className="text-sm text-white/50 line-clamp-2 mb-3">{selectedStory.description}</p>
              )}
              <button
                onClick={() => router.push(`/story/${selectedStory.id}`)}
                className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
              >
                Open story &rarr;
              </button>
            </div>

            {selectedStory.character_names && selectedStory.character_names.length > 0 && (
              <div className="flex flex-wrap gap-2 items-start">
                {selectedStory.character_names.map((name, idx) => {
                  const hue = hashStringToHue(name);
                  const hasChronicle = !!charIdMap[name];
                  const isActive = selectedCharName === name;
                  return (
                    <button
                      key={idx}
                      onClick={() => hasChronicle && handleCharacterClick(name)}
                      className={`flex items-center gap-1.5 transition-all ${
                        hasChronicle ? 'cursor-pointer hover:opacity-80' : 'cursor-default'
                      } ${isActive ? 'ring-1 ring-indigo-400/50 rounded-full px-1.5 py-0.5 bg-white/5' : ''}`}
                      title={hasChronicle ? 'Click to view chronicle snapshot' : name}
                    >
                      <div
                        className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] text-white font-medium flex-shrink-0"
                        style={{ background: `linear-gradient(135deg, hsl(${hue}, 60%, 45%), hsl(${hue}, 70%, 35%))` }}
                      >
                        {name.charAt(0).toUpperCase()}
                      </div>
                      <span className="text-xs text-white/60">{name}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Character chronicle panel */}
          {selectedCharName && (
            <div className="col-span-full mt-2 pt-3 border-t border-white/10">
              <div className="flex items-center gap-2 mb-2">
                <h5 className="text-sm font-semibold text-white/80">{selectedCharName}</h5>
                <button
                  onClick={() => { setSelectedCharName(null); setCharContent(null); setCharEntries([]); }}
                  className="p-0.5 hover:bg-white/10 rounded transition-colors"
                >
                  <X className="w-3.5 h-3.5 text-white/40" />
                </button>
              </div>
              {loadingChar ? (
                <div className="flex items-center gap-2 py-3">
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span className="text-xs text-white/40">Loading...</span>
                </div>
              ) : charContent ? (
                <>
                  <p className="text-sm text-white/60 whitespace-pre-line leading-relaxed">{charContent}</p>
                  <button
                    onClick={handleShowDetails}
                    className="mt-2 text-xs text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1"
                  >
                    {showDetails ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                    {showDetails ? 'Hide details' : 'Show details'}
                  </button>
                  {showDetails && (
                    loadingDetails ? (
                      <div className="flex items-center gap-2 py-2 mt-1">
                        <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        <span className="text-xs text-white/40">Loading entries...</span>
                      </div>
                    ) : charEntries.length > 0 ? (
                      <div className="space-y-1.5 max-h-[300px] overflow-y-auto mt-2 pt-2 border-t border-white/5">
                        {charEntries.map((entry) => (
                          <div key={entry.id} className="flex items-start gap-2">
                            <span className="text-[10px] text-white/30 bg-white/5 px-1.5 py-0.5 rounded flex-shrink-0 mt-0.5">
                              {entry.entry_type}
                            </span>
                            <p className="text-sm text-white/60 leading-snug">{entry.description}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-white/40 italic mt-2">No individual entries found.</p>
                    )
                  )}
                </>
              ) : charEntries.length > 0 ? (
                <div className="space-y-1.5 max-h-[300px] overflow-y-auto">
                  {charEntries.map((entry) => (
                    <div key={entry.id} className="flex items-start gap-2">
                      <span className="text-[10px] text-white/30 bg-white/5 px-1.5 py-0.5 rounded flex-shrink-0 mt-0.5">
                        {entry.entry_type}
                      </span>
                      <p className="text-sm text-white/60 leading-snug">{entry.description}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-white/40 italic">No snapshot generated for this character.</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Legend */}
      {links.length > 0 && (
        <div className="flex items-center gap-4 text-[11px] text-white/35 px-1">
          <span className="flex items-center gap-1.5">
            <span className="w-4 h-px border-t border-dashed border-white/40" />
            Shared characters
          </span>
          <span>Click a star for details</span>
        </div>
      )}
    </div>
  );
}
