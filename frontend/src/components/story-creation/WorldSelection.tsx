'use client';

import { useState, useEffect } from 'react';
import { Sparkles, Globe, BookOpen, Users, ChevronDown, ChevronUp, X } from 'lucide-react';
import { StoryData } from '@/app/create-story/page';
import { WorldsApi } from '@/lib/api/worlds';
import type { World, WorldStory, CharacterSnapshotData } from '@/lib/api/types';

const worldsApi = new WorldsApi();

interface WorldSelectionProps {
  storyData: StoryData;
  onUpdate: (data: Partial<StoryData>) => void;
  onNext: () => void;
  onBack: () => void;
}

export default function WorldSelection({ storyData, onUpdate, onNext, onBack }: WorldSelectionProps) {
  const [worlds, setWorlds] = useState<World[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedWorldId, setSelectedWorldId] = useState<number | undefined>(storyData.world_id);
  const [worldStories, setWorldStories] = useState<WorldStory[]>([]);
  const [loadingStories, setLoadingStories] = useState(false);
  const [insertionIndex, setInsertionIndex] = useState<number>(-1); // -1 = end
  const [expandedStoryId, setExpandedStoryId] = useState<number | null>(null);
  const [storySnapshots, setStorySnapshots] = useState<Record<string, CharacterSnapshotData>>({});

  useEffect(() => {
    loadWorlds();
  }, []);

  useEffect(() => {
    if (selectedWorldId) {
      loadWorldStories(selectedWorldId);
    } else {
      setWorldStories([]);
      setInsertionIndex(-1);
    }
  }, [selectedWorldId]);

  const loadWorlds = async () => {
    try {
      const data = await worldsApi.getWorlds();
      setWorlds(data);
    } catch (err) {
      console.error('Failed to load worlds:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadWorldStories = async (worldId: number) => {
    setLoadingStories(true);
    try {
      const stories = await worldsApi.getWorldStories(worldId);
      setWorldStories(stories);
      setInsertionIndex(-1); // default to end
    } catch (err) {
      console.error('Failed to load world stories:', err);
    } finally {
      setLoadingStories(false);
    }
  };

  const handleSelectWorld = (worldId: number | undefined) => {
    setSelectedWorldId(worldId);
    setExpandedStoryId(null);
    const timelineOrder = worldId ? computeTimelineOrder(-1) : undefined;
    onUpdate({ world_id: worldId, timeline_order: timelineOrder });
  };

  const handleInsertAt = (index: number) => {
    setInsertionIndex(index);
    onUpdate({ world_id: selectedWorldId, timeline_order: computeTimelineOrder(index) });
  };

  const computeTimelineOrder = (index: number): number | undefined => {
    if (!selectedWorldId) return undefined;
    if (worldStories.length === 0) return 1;
    if (index === -1 || index >= worldStories.length) {
      // After all stories
      const lastOrder = worldStories[worldStories.length - 1]?.timeline_order ?? worldStories.length;
      return lastOrder + 1;
    }
    if (index === 0) {
      // Before first story
      const firstOrder = worldStories[0]?.timeline_order ?? 1;
      return Math.max(1, firstOrder - 1);
    }
    // Between two stories
    const prev = worldStories[index - 1]?.timeline_order ?? index;
    const next = worldStories[index]?.timeline_order ?? index + 1;
    return Math.floor((prev + next) / 2) || index + 1;
  };

  const handleExpandStory = async (storyId: number) => {
    if (expandedStoryId === storyId) {
      setExpandedStoryId(null);
      return;
    }
    setExpandedStoryId(storyId);
  };

  const isNewUniverse = !selectedWorldId;
  const effectiveIndex = insertionIndex === -1 ? worldStories.length : insertionIndex;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center mb-4 sm:mb-8">
        <h2 className="text-xl sm:text-3xl font-bold mb-2 sm:mb-3 text-white">Choose a Universe</h2>
        <p className="text-white/70">
          Place your story in an existing world or create a fresh one
        </p>
      </div>

      {/* Loading */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="w-10 h-10 border-4 border-white/30 border-t-white rounded-full animate-spin" />
        </div>
      ) : (
        <>
          {/* World Cards Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-6">
            {/* New Universe Card */}
            <button
              onClick={() => handleSelectWorld(undefined)}
              className={`relative p-4 sm:p-6 rounded-2xl border-2 border-dashed transition-all text-left hover:scale-[1.02] ${
                isNewUniverse
                  ? 'border-indigo-500/60 bg-indigo-500/10 shadow-lg shadow-indigo-500/20'
                  : 'border-white/30 hover:border-white/50 bg-white/5'
              }`}
            >
              <div className="flex items-center gap-3 mb-3">
                <div className={`p-2.5 rounded-xl ${isNewUniverse ? 'bg-indigo-500/20' : 'bg-white/10'}`}>
                  <Sparkles className={`w-6 h-6 ${isNewUniverse ? 'text-indigo-400' : 'text-white/60'}`} />
                </div>
                <h3 className="text-lg font-bold text-white">New Universe</h3>
              </div>
              <p className="text-sm text-white/60">
                A brand new world created from your story
              </p>
              {isNewUniverse && (
                <div className="absolute top-3 right-3 w-3 h-3 rounded-full bg-indigo-500 shadow-lg shadow-indigo-500/50" />
              )}
            </button>

            {/* Existing World Cards */}
            {worlds.map((world) => (
              <button
                key={world.id}
                onClick={() => handleSelectWorld(world.id)}
                className={`relative p-4 sm:p-6 rounded-2xl border transition-all text-left hover:scale-[1.02] bg-white/10 backdrop-blur-md ${
                  selectedWorldId === world.id
                    ? 'border-indigo-500/40 bg-indigo-500/10 shadow-lg shadow-indigo-500/20'
                    : 'border-white/20 hover:border-white/40'
                }`}
              >
                <div className="flex items-center gap-3 mb-3">
                  <div className={`p-2.5 rounded-xl ${selectedWorldId === world.id ? 'bg-indigo-500/20' : 'bg-white/10'}`}>
                    <Globe className={`w-6 h-6 ${selectedWorldId === world.id ? 'text-indigo-400' : 'text-white/60'}`} />
                  </div>
                  <h3 className="text-lg font-bold text-white truncate">{world.name}</h3>
                </div>
                {world.description && (
                  <p className="text-sm text-white/60 line-clamp-2 mb-3">{world.description}</p>
                )}
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-500/20 text-indigo-400 rounded-full text-xs">
                    <BookOpen className="w-3 h-3" />
                    {world.story_count} {world.story_count === 1 ? 'story' : 'stories'}
                  </span>
                </div>
                {selectedWorldId === world.id && (
                  <div className="absolute top-3 right-3 w-3 h-3 rounded-full bg-indigo-500 shadow-lg shadow-indigo-500/50" />
                )}
              </button>
            ))}
          </div>

          {/* Visual Timeline — shown when an existing world is selected */}
          {selectedWorldId && (
            <div className="mt-8">
              <h3 className="text-lg font-semibold text-white mb-4">World Timeline</h3>

              {loadingStories ? (
                <div className="flex justify-center py-8">
                  <div className="w-8 h-8 border-3 border-white/30 border-t-white rounded-full animate-spin" />
                </div>
              ) : worldStories.length === 0 ? (
                <div className="text-center py-8 text-white/50">
                  <p>No stories in this world yet. Yours will be the first!</p>
                </div>
              ) : (
                <>
                  {/* Desktop: Horizontal Timeline */}
                  <div className="hidden md:block">
                    <DesktopTimeline
                      stories={worldStories}
                      insertionIndex={effectiveIndex}
                      expandedStoryId={expandedStoryId}
                      onInsertAt={handleInsertAt}
                      onExpandStory={handleExpandStory}
                    />
                  </div>

                  {/* Mobile: Vertical Timeline */}
                  <div className="md:hidden">
                    <MobileTimeline
                      stories={worldStories}
                      insertionIndex={effectiveIndex}
                      expandedStoryId={expandedStoryId}
                      onInsertAt={handleInsertAt}
                      onExpandStory={handleExpandStory}
                    />
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}

      {/* Navigation Buttons */}
      <div className="flex justify-between pt-6">
        <button
          onClick={onBack}
          className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-colors"
        >
          Back
        </button>
        <button
          onClick={onNext}
          className="px-8 py-3 theme-btn-primary rounded-xl transition-colors font-medium"
        >
          Next
        </button>
      </div>
    </div>
  );
}

/* ========== Desktop Horizontal Timeline ========== */

function DesktopTimeline({
  stories,
  insertionIndex,
  expandedStoryId,
  onInsertAt,
  onExpandStory,
}: {
  stories: WorldStory[];
  insertionIndex: number;
  expandedStoryId: number | null;
  onInsertAt: (index: number) => void;
  onExpandStory: (id: number) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="relative flex items-start overflow-x-auto pb-4 gap-0">
        {/* Connecting line */}
        <div className="absolute top-5 left-6 right-6 h-0.5 bg-gradient-to-r from-indigo-500/50 to-purple-500/50 z-0" />

        {stories.map((story, idx) => (
          <div key={story.id} className="flex items-start flex-shrink-0">
            {/* Insertion gap before this story */}
            <InsertionGap
              active={insertionIndex === idx}
              onClick={() => onInsertAt(idx)}
            />

            {/* Story node */}
            <div className="relative flex flex-col items-center z-10">
              <button
                onClick={() => onExpandStory(story.id)}
                className={`w-4 h-4 rounded-full transition-all flex-shrink-0 ${
                  expandedStoryId === story.id
                    ? 'bg-indigo-400 ring-4 ring-indigo-500/30 scale-125'
                    : 'bg-indigo-500 hover:bg-indigo-400 hover:scale-110'
                }`}
              />
              <div
                onClick={() => onExpandStory(story.id)}
                className="mt-3 bg-white/10 rounded-xl p-4 w-48 cursor-pointer hover:bg-white/15 transition-colors border border-white/10"
              >
                <p className="text-sm font-medium text-white truncate">{story.title}</p>
                {story.genre && (
                  <span className="inline-block mt-1 px-2 py-0.5 bg-purple-500/20 text-purple-400 text-xs rounded-full">
                    {story.genre}
                  </span>
                )}
                <p className="text-xs text-white/40 mt-1">
                  {story.scene_count ?? 0} scenes · {story.chapter_count ?? 0} ch.
                </p>
                {story.character_names && story.character_names.length > 0 && (
                  <p className="text-xs text-white/30 mt-1 truncate">
                    {story.character_names.slice(0, 3).join(', ')}
                    {story.character_names.length > 3 && ` +${story.character_names.length - 3}`}
                  </p>
                )}
              </div>
            </div>

            {/* Insertion gap after last story */}
            {idx === stories.length - 1 && (
              <InsertionGap
                active={insertionIndex >= stories.length}
                onClick={() => onInsertAt(-1)}
                isLast
              />
            )}
          </div>
        ))}

        {/* "Your Story" node at insertion point */}
        <YourStoryNode />
      </div>

      {/* Expanded story preview */}
      {expandedStoryId && (
        <StoryPreview
          story={stories.find(s => s.id === expandedStoryId)!}
          onClose={() => onExpandStory(expandedStoryId)}
        />
      )}
    </div>
  );
}

/* ========== Mobile Vertical Timeline ========== */

function MobileTimeline({
  stories,
  insertionIndex,
  expandedStoryId,
  onInsertAt,
  onExpandStory,
}: {
  stories: WorldStory[];
  insertionIndex: number;
  expandedStoryId: number | null;
  onInsertAt: (index: number) => void;
  onExpandStory: (id: number) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="relative pl-6">
        {/* Vertical connecting line */}
        <div className="absolute left-[11px] top-2 bottom-2 w-0.5 bg-gradient-to-b from-indigo-500/50 to-purple-500/50" />

        {stories.map((story, idx) => (
          <div key={story.id}>
            {/* Insertion zone before */}
            <MobileInsertionGap
              active={insertionIndex === idx}
              onClick={() => onInsertAt(idx)}
            />

            {/* Story node */}
            <div className="relative flex items-start gap-4 py-2">
              <button
                onClick={() => onExpandStory(story.id)}
                className={`absolute left-[-17px] top-3 w-3.5 h-3.5 rounded-full flex-shrink-0 z-10 transition-all ${
                  expandedStoryId === story.id
                    ? 'bg-indigo-400 ring-4 ring-indigo-500/30'
                    : 'bg-indigo-500'
                }`}
              />
              <div
                onClick={() => onExpandStory(story.id)}
                className="flex-1 bg-white/10 rounded-xl p-4 cursor-pointer hover:bg-white/15 transition-colors border border-white/10"
              >
                <p className="text-sm font-medium text-white">{story.title}</p>
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  {story.genre && (
                    <span className="px-2 py-0.5 bg-purple-500/20 text-purple-400 text-xs rounded-full">
                      {story.genre}
                    </span>
                  )}
                  <span className="text-xs text-white/40">
                    {story.scene_count ?? 0} scenes · {story.chapter_count ?? 0} ch.
                  </span>
                </div>
              </div>
            </div>

            {/* Expanded preview below this story */}
            {expandedStoryId === story.id && (
              <div className="ml-2 mb-2">
                <StoryPreview
                  story={story}
                  onClose={() => onExpandStory(story.id)}
                />
              </div>
            )}

            {/* Insertion zone after last */}
            {idx === stories.length - 1 && (
              <MobileInsertionGap
                active={insertionIndex >= stories.length}
                onClick={() => onInsertAt(-1)}
              />
            )}
          </div>
        ))}

        {/* Your story marker */}
        <div className="relative flex items-start gap-4 py-2">
          <div className="absolute left-[-17px] top-3 w-4 h-4 rounded-full bg-purple-500 animate-pulse z-10" />
          <div className="flex-1 bg-purple-500/10 border border-purple-500/30 rounded-xl p-4">
            <p className="text-sm font-medium text-purple-300">Your new story goes here</p>
            <p className="text-xs text-white/40 mt-1">Tap between stories to reposition</p>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ========== Shared Sub-components ========== */

function InsertionGap({
  active,
  onClick,
  isLast = false,
}: {
  active: boolean;
  onClick: () => void;
  isLast?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex-shrink-0 flex items-center justify-center w-12 h-10 z-10 transition-all group ${
        isLast ? '' : ''
      }`}
      title="Place your story here"
    >
      <div
        className={`w-6 h-6 rounded-full border-2 border-dashed flex items-center justify-center transition-all ${
          active
            ? 'border-purple-400 bg-purple-500/20 scale-110'
            : 'border-white/20 hover:border-purple-400/50 hover:bg-purple-500/10'
        }`}
      >
        <span className={`text-xs font-bold ${active ? 'text-purple-400' : 'text-white/30 group-hover:text-purple-400/60'}`}>+</span>
      </div>
    </button>
  );
}

function MobileInsertionGap({
  active,
  onClick,
}: {
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="relative w-full flex items-center justify-center min-h-[48px] group"
      title="Tap to place your story here"
    >
      <div
        className={`px-3 py-1 rounded-full border border-dashed text-xs transition-all ${
          active
            ? 'border-purple-400 bg-purple-500/20 text-purple-300'
            : 'border-white/15 text-white/20 group-hover:border-purple-400/50 group-hover:text-purple-300/60'
        }`}
      >
        + Place story here
      </div>
    </button>
  );
}

function YourStoryNode() {
  return null; // The insertion point is shown by the active InsertionGap instead
}

function StoryPreview({
  story,
  onClose,
}: {
  story: WorldStory;
  onClose: () => void;
}) {
  return (
    <div className="bg-white/5 backdrop-blur border border-white/15 rounded-2xl p-4 sm:p-6 relative animate-in slide-in-from-top-2 duration-200">
      <button
        onClick={onClose}
        className="absolute top-3 right-3 p-1.5 hover:bg-white/10 rounded-lg transition-colors"
      >
        <X className="w-4 h-4 text-white/50" />
      </button>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Left: Story overview */}
        <div>
          <h4 className="text-lg font-bold text-white mb-2">{story.title}</h4>
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            {story.genre && (
              <span className="px-2 py-0.5 bg-purple-500/20 text-purple-400 text-xs rounded-full">
                {story.genre}
              </span>
            )}
            <span className={`px-2 py-0.5 text-xs rounded-full ${
              story.status === 'active'
                ? 'bg-green-500/20 text-green-400'
                : story.status === 'archived'
                  ? 'bg-gray-500/20 text-gray-400'
                  : 'bg-blue-500/20 text-blue-400'
            }`}>
              {story.status}
            </span>
          </div>
          {story.description && (
            <p className="text-sm text-white/60 mb-3">{story.description}</p>
          )}
          <div className="flex items-center gap-3 text-xs text-white/40">
            <span>{story.scene_count ?? 0} scenes across {story.chapter_count ?? 0} chapters</span>
          </div>
        </div>

        {/* Right: Characters */}
        <div>
          <h5 className="text-sm font-semibold text-white/80 mb-3 flex items-center gap-2">
            <Users className="w-4 h-4" />
            Characters in this story
          </h5>
          {story.character_names && story.character_names.length > 0 ? (
            <div className="space-y-2">
              {story.character_names.map((name, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-xs text-white font-medium flex-shrink-0">
                    {name.charAt(0).toUpperCase()}
                  </div>
                  <span className="text-sm text-white/80">{name}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-white/40 italic">No characters yet</p>
          )}
        </div>
      </div>
    </div>
  );
}
