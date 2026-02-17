'use client';

import { createContext, useContext, ReactNode, useState } from 'react';

export interface StoryActions {
  onChapters?: () => void;
  onAddCharacter?: () => void;
  onEditCharacterVoices?: () => void;
  onEditCharacterRoles?: () => void;
  onManageStoryCharacters?: () => void;
  onViewAllCharacters?: () => void;
  onDirectorMode?: () => void;
  onDeleteMode?: () => void;
  onEditStorySettings?: () => void;
  onShowInteractions?: () => void;
  onShowEntityStates?: () => void;
  onShowContradictions?: () => void;
  directorModeActive?: boolean;
  deleteModeActive?: boolean;
  showImagesActive?: boolean;
  onToggleImages?: () => void;
  onOpenGallery?: () => void;
  // Character suggestion banner
  showCharacterBanner?: boolean;
  onDiscoverCharacters?: () => void;
  // Generation/extraction status
  lastGenerationTime?: number | null;
  generationStartTime?: number | null;
  extractionStatus?: { status: 'extracting' | 'complete' | 'error'; message: string } | null;
  // Story title and content rating for banner display
  storyTitle?: string;
  contentRating?: 'sfw' | 'nsfw';
  // Branch-related props
  storyId?: number;
  currentBranchId?: number;
  currentSceneSequence?: number;
  onBranchChange?: (branchId: number) => void;
  onBranchCreated?: (branchId?: number) => void;
}

interface StoryContextType {
  storyActions?: StoryActions;
  setStoryActions: (actions: StoryActions | undefined) => void;
}

const StoryContext = createContext<StoryContextType | undefined>(undefined);

export function StoryProvider({ children }: { children: ReactNode }) {
  const [storyActions, setStoryActions] = useState<StoryActions | undefined>(undefined);

  return (
    <StoryContext.Provider value={{ storyActions, setStoryActions }}>
      {children}
    </StoryContext.Provider>
  );
}

export function useStoryActions() {
  const context = useContext(StoryContext);
  if (context === undefined) {
    throw new Error('useStoryActions must be used within a StoryProvider');
  }
  return context;
}
