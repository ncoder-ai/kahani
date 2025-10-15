import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { useEffect, useState } from 'react';
import apiClient from '@/lib/api';

// User and auth store
interface User {
  id: number;
  username: string;
  email: string;
  display_name: string;
  is_admin: boolean;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (user: User, token: string) => void;
  logout: () => void;
  setUser: (user: User) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      login: (user, token) => {
        apiClient.setToken(token);
        set({ user, token, isAuthenticated: true });
      },
      logout: () => {
        apiClient.removeToken();
        set({ user: null, token: null, isAuthenticated: false });
      },
      setUser: (user) => set({ user }),
    }),
    {
      name: 'auth-storage',
      onRehydrateStorage: () => (state) => {
        if (state?.token) {
          apiClient.setToken(state.token);
        }
      },
    }
  )
);

// Story store
interface Story {
  id: number;
  title: string;
  description: string;
  genre: string;
  status: string;
  creation_step: number;
  created_at: string;
  updated_at: string;
  summary?: string;  // AI-generated story summary
  scenes?: Scene[];
}

interface Scene {
  id: number;
  sequence_number: number;
  title: string;
  content: string;
  location: string;
  characters_present: string[];
}

interface StoryState {
  stories: Story[];
  currentStory: Story | null;
  isLoading: boolean;
  error: string | null;
  setStories: (stories: Story[]) => void;
  setCurrentStory: (story: Story | null) => void;
  addStory: (story: Story) => void;
  updateStory: (id: number, updates: Partial<Story>) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useStoryStore = create<StoryState>((set) => ({
  stories: [],
  currentStory: null,
  isLoading: false,
  error: null,
  setStories: (stories) => set({ stories }),
  setCurrentStory: (story) => set({ currentStory: story }),
  addStory: (story) => set((state) => ({ stories: [...state.stories, story] })),
  updateStory: (id, updates) => set((state) => ({
    stories: state.stories.map((story) => 
      story.id === id ? { ...story, ...updates } : story
    ),
    currentStory: state.currentStory?.id === id 
      ? { ...state.currentStory, ...updates } 
      : state.currentStory
  })),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
}));

// Character store
interface Character {
  id: number;
  name: string;
  description: string;
  personality_traits: string[];
  is_template: boolean;
  created_at: string;
}

interface CharacterState {
  characters: Character[];
  isLoading: boolean;
  error: string | null;
  setCharacters: (characters: Character[]) => void;
  addCharacter: (character: Character) => void;
  updateCharacter: (id: number, updates: Partial<Character>) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useCharacterStore = create<CharacterState>((set) => ({
  characters: [],
  isLoading: false,
  error: null,
  setCharacters: (characters) => set({ characters }),
  addCharacter: (character) => set((state) => ({ 
    characters: [...state.characters, character] 
  })),
  updateCharacter: (id, updates) => set((state) => ({
    characters: state.characters.map((character) => 
      character.id === id ? { ...character, ...updates } : character
    )
  })),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
}));

// Hook to handle hydration
export const useHasHydrated = () => {
  const [hasHydrated, setHasHydrated] = useState(false);

  useEffect(() => {
    setHasHydrated(true);
  }, []);

  return hasHydrated;
};