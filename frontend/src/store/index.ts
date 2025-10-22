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
  is_approved: boolean;
  // Content permissions
  allow_nsfw: boolean;
  // Feature permissions
  can_change_llm_provider: boolean;
  can_change_tts_settings: boolean;
  can_use_stt?: boolean;  // Future feature
  can_use_image_generation?: boolean;  // Future feature
  can_export_stories: boolean;
  can_import_stories: boolean;
  // Resource limits
  max_stories?: number | null;
  max_images_per_story?: number | null;  // Future feature
  max_stt_minutes_per_month?: number | null;  // Future feature
}

interface AuthState {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  login: (user: User, token: string, refreshToken?: string) => void;
  logout: () => void;
  setUser: (user: User) => void;
  refreshAccessToken: () => Promise<boolean>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      login: (user, token, refreshToken) => {
        apiClient.setToken(token);
        set({ user, token, refreshToken, isAuthenticated: true });
      },
      logout: () => {
        apiClient.removeToken();
        set({ user: null, token: null, refreshToken: null, isAuthenticated: false });
      },
      setUser: (user) => set({ user }),
      refreshAccessToken: async () => {
        const { refreshToken } = get();
        if (!refreshToken) {
          console.log('No refresh token available');
          return false;
        }

        try {
          console.log('Attempting to refresh access token...');
          const response = await apiClient.refreshToken(refreshToken);
          console.log('Token refresh successful');
          
          apiClient.setToken(response.access_token);
          set({ token: response.access_token });
          return true;
        } catch (error) {
          console.error('Token refresh failed:', error);
          // If refresh fails, logout the user
          get().logout();
          return false;
        }
      },
    }),
    {
      name: 'auth-storage',
      onRehydrateStorage: () => async (state) => {
        if (state?.token && state?.user) {
          apiClient.setToken(state.token);
          // Set isAuthenticated to true when rehydrating from storage
          state.isAuthenticated = true;
          
          // If we have a refresh token, try to refresh the access token in the background
          if (state.refreshToken) {
            try {
              console.log('[AuthStore] Rehydration: Attempting background token refresh...');
              const response = await apiClient.refreshToken(state.refreshToken);
              console.log('[AuthStore] Background token refresh successful');
              
              // Update the token in both the store and API client
              apiClient.setToken(response.access_token);
              state.token = response.access_token;
            } catch (error) {
              console.log('[AuthStore] Background token refresh failed, keeping existing token');
              // Don't logout here - let the user try to use the app
              // If the token is truly expired, the API client will handle it
            }
          }
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