'use client';

import { createContext, useContext, ReactNode, useState } from 'react';

export interface StoryActions {
  onChapters?: () => void;
  onAddCharacter?: () => void;
  onViewAllCharacters?: () => void;
  onDirectorMode?: () => void;
  onLorebook?: () => void;
  onDeleteMode?: () => void;
  onExportStory?: () => void;
  onEditStorySettings?: () => void;
  directorModeActive?: boolean;
  lorebookActive?: boolean;
  deleteModeActive?: boolean;
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
