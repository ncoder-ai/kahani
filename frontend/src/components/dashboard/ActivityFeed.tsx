'use client';

import { useState } from 'react';
import type { RoleplayListItem } from '@/lib/api/roleplay';
import StoryCard from './StoryCard';
import BrainstormCard from './BrainstormCard';
import BrainstormBulkActions from './BrainstormBulkActions';
import RoleplayCard from './RoleplayCard';

type Tab = 'all' | 'stories' | 'brainstorms' | 'roleplays';

interface ActivityFeedProps {
  stories: any[];
  brainstormSessions: any[];
  roleplays: RoleplayListItem[];
  isLoading: boolean;
  // Story handlers
  generatingStorySummaryId: number | null;
  onStoryClick: (storyId: number) => void;
  onViewSummary: (storyId: number) => void;
  onEditStory: (storyId: number) => void;
  onDeleteStory: (storyId: number, title: string) => void;
  onGenerateStorySummary: (storyId: number, e: React.MouseEvent) => void;
  onCreateStory: () => void;
  // Brainstorm handlers
  brainstormSelectMode: boolean;
  selectedBrainstormIds: Set<number>;
  isDeletingBrainstorms: boolean;
  onToggleBrainstormSelectMode: () => void;
  onToggleBrainstormSelection: (sessionId: number, e: React.MouseEvent) => void;
  onToggleSelectAllBrainstorms: () => void;
  onDeleteSelectedBrainstorms: () => void;
  onCancelBrainstormSelectMode: () => void;
  // Roleplay handlers
  onDeleteRoleplay: (id: number, title: string, e: React.MouseEvent) => void;
  formatRelativeDate: (dateStr: string) => string;
}

interface FeedItem {
  type: 'story' | 'brainstorm' | 'roleplay';
  updatedAt: string;
  data: any;
}

export default function ActivityFeed({
  stories,
  brainstormSessions,
  roleplays,
  isLoading,
  generatingStorySummaryId,
  onStoryClick,
  onViewSummary,
  onEditStory,
  onDeleteStory,
  onGenerateStorySummary,
  onCreateStory,
  brainstormSelectMode,
  selectedBrainstormIds,
  isDeletingBrainstorms,
  onToggleBrainstormSelectMode,
  onToggleBrainstormSelection,
  onToggleSelectAllBrainstorms,
  onDeleteSelectedBrainstorms,
  onCancelBrainstormSelectMode,
  onDeleteRoleplay,
  formatRelativeDate,
}: ActivityFeedProps) {
  const [activeTab, setActiveTab] = useState<Tab>('all');

  const nonRoleplayStories = stories.filter(s => s.story_mode !== 'roleplay');

  const storyCount = nonRoleplayStories.length;
  const brainstormCount = brainstormSessions.length;
  const roleplayCount = roleplays.length;
  const totalCount = storyCount + brainstormCount + roleplayCount;

  // Build merged feed items for "All" tab
  const buildAllItems = (): FeedItem[] => {
    const items: FeedItem[] = [];
    nonRoleplayStories.forEach(s => items.push({
      type: 'story',
      updatedAt: s.updated_at,
      data: s,
    }));
    brainstormSessions.forEach(b => items.push({
      type: 'brainstorm',
      updatedAt: b.updated_at || b.created_at,
      data: b,
    }));
    roleplays.forEach(r => items.push({
      type: 'roleplay',
      updatedAt: r.updated_at || r.created_at,
      data: r,
    }));
    items.sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
    return items;
  };

  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: 'all', label: 'All', count: totalCount },
    { id: 'stories', label: 'Stories', count: storyCount },
    { id: 'brainstorms', label: 'Brainstorms', count: brainstormCount },
    { id: 'roleplays', label: 'Roleplays', count: roleplayCount },
  ];

  if (isLoading) {
    return (
      <div className="text-center py-16">
        <div className="w-16 h-16 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
        <p className="text-white/80">Loading your stories...</p>
      </div>
    );
  }

  if (totalCount === 0) {
    return (
      <div className="text-center py-8 sm:py-16">
        <div className="bg-white/10 backdrop-blur-md rounded-3xl border border-white/20 p-6 sm:p-12 max-w-md mx-auto">
          <div className="text-5xl sm:text-6xl mb-4 sm:mb-6">&#x1F4DA;</div>
          <h3 className="text-xl sm:text-2xl font-bold text-white mb-3 sm:mb-4">No stories yet</h3>
          <p className="text-white/70 mb-6 sm:mb-8 text-sm sm:text-base">
            Start your creative journey by creating your first interactive story
          </p>
          <button
            onClick={onCreateStory}
            className="theme-btn-primary px-6 py-3 rounded-xl font-semibold transform hover:scale-105 transition-all duration-200"
          >
            Create Your First Story
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Tab bar */}
      <div className="flex items-center gap-1 sm:gap-2 mb-4 sm:mb-6 border-b border-white/10 pb-3 overflow-x-auto -mx-2 px-2">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-3 sm:px-4 py-2 rounded-lg text-xs sm:text-sm font-medium transition-colors flex-shrink-0 ${
              activeTab === tab.id
                ? 'bg-white/20 text-white'
                : 'text-white/60 hover:text-white hover:bg-white/10'
            }`}
          >
            {tab.label} ({tab.count})
          </button>
        ))}

        {/* Brainstorm bulk actions in brainstorms tab */}
        {activeTab === 'brainstorms' && brainstormCount > 0 && (
          <div className="ml-auto flex-shrink-0">
            <BrainstormBulkActions
              selectMode={brainstormSelectMode}
              selectedCount={selectedBrainstormIds.size}
              totalCount={brainstormCount}
              isDeleting={isDeletingBrainstorms}
              onToggleSelectMode={onToggleBrainstormSelectMode}
              onToggleSelectAll={onToggleSelectAllBrainstorms}
              onDeleteSelected={onDeleteSelectedBrainstorms}
              onCancel={onCancelBrainstormSelectMode}
            />
          </div>
        )}
      </div>

      {/* Tab content */}
      {activeTab === 'all' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
          {buildAllItems().map((item, idx) => {
            if (item.type === 'story') {
              return (
                <StoryCard
                  key={`story-${item.data.id}`}
                  story={item.data}
                  generatingStorySummaryId={generatingStorySummaryId}
                  onStoryClick={onStoryClick}
                  onViewSummary={onViewSummary}
                  onEditStory={onEditStory}
                  onDeleteStory={onDeleteStory}
                  onGenerateStorySummary={onGenerateStorySummary}
                />
              );
            }
            if (item.type === 'brainstorm') {
              return (
                <BrainstormCard
                  key={`brainstorm-${item.data.id}`}
                  session={item.data}
                  selectMode={false}
                  isSelected={false}
                  onToggleSelection={() => {}}
                />
              );
            }
            return (
              <RoleplayCard
                key={`roleplay-${item.data.story_id}`}
                roleplay={item.data}
                formatRelativeDate={formatRelativeDate}
                onDelete={onDeleteRoleplay}
              />
            );
          })}

          {/* Add New Story Card */}
          <div
            onClick={onCreateStory}
            className="bg-white/5 border-2 border-dashed border-white/30 rounded-2xl p-4 sm:p-6 cursor-pointer hover:bg-white/10 hover:border-white/50 transition-all duration-200 flex flex-col items-center justify-center text-center min-h-[120px] sm:min-h-[200px] group"
          >
            <div className="text-4xl mb-4 group-hover:scale-110 transition-transform">+</div>
            <h4 className="text-lg font-semibold text-white mb-2">Create New Story</h4>
            <p className="text-white/60 text-sm">Start a new interactive adventure</p>
          </div>
        </div>
      )}

      {activeTab === 'stories' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
          {nonRoleplayStories.map(story => (
            <StoryCard
              key={story.id}
              story={story}
              generatingStorySummaryId={generatingStorySummaryId}
              onStoryClick={onStoryClick}
              onViewSummary={onViewSummary}
              onEditStory={onEditStory}
              onDeleteStory={onDeleteStory}
              onGenerateStorySummary={onGenerateStorySummary}
            />
          ))}

          <div
            onClick={onCreateStory}
            className="bg-white/5 border-2 border-dashed border-white/30 rounded-2xl p-4 sm:p-6 cursor-pointer hover:bg-white/10 hover:border-white/50 transition-all duration-200 flex flex-col items-center justify-center text-center min-h-[120px] sm:min-h-[200px] group"
          >
            <div className="text-4xl mb-4 group-hover:scale-110 transition-transform">+</div>
            <h4 className="text-lg font-semibold text-white mb-2">Create New Story</h4>
            <p className="text-white/60 text-sm">Start a new interactive adventure</p>
          </div>
        </div>
      )}

      {activeTab === 'brainstorms' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {brainstormSessions.length === 0 ? (
            <div className="col-span-full text-center py-12 text-white/60">
              No brainstorm sessions yet
            </div>
          ) : (
            brainstormSessions.map(session => (
              <BrainstormCard
                key={session.id}
                session={session}
                selectMode={brainstormSelectMode}
                isSelected={selectedBrainstormIds.has(session.id)}
                onToggleSelection={onToggleBrainstormSelection}
              />
            ))
          )}
        </div>
      )}

      {activeTab === 'roleplays' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {roleplays.length === 0 ? (
            <div className="col-span-full text-center py-12 text-white/60">
              No roleplay sessions yet
            </div>
          ) : (
            roleplays.map(rp => (
              <RoleplayCard
                key={rp.story_id}
                roleplay={rp}
                formatRelativeDate={formatRelativeDate}
                onDelete={onDeleteRoleplay}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
