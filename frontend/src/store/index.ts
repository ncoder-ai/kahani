import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { useEffect, useState } from 'react';
import apiClient from '@/lib/api';
import { getTokenExpirationMs, isTokenExpired } from '@/utils/jwt';

// Constants for token refresh
const REFRESH_BUFFER_MS = 5 * 60 * 1000; // Refresh 5 minutes before expiry
const MIN_REFRESH_INTERVAL_MS = 30 * 1000; // Don't refresh more often than every 30 seconds

// Global refresh timer reference (outside store to persist across re-renders)
let refreshTimerId: ReturnType<typeof setTimeout> | null = null;

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
  // Token expiration tracking
  accessTokenExpiresAt: number | null;  // ms since epoch
  refreshTokenExpiresAt: number | null; // ms since epoch (null = no refresh token)
  // Actions
  login: (user: User, token: string, refreshToken?: string) => void;
  logout: () => void;
  setUser: (user: User) => void;
  refreshAccessToken: () => Promise<boolean>;
  scheduleTokenRefresh: () => void;
  clearRefreshTimer: () => void;
}

/**
 * Clear the global refresh timer
 */
function clearRefreshTimer() {
  if (refreshTimerId) {
    clearTimeout(refreshTimerId);
    refreshTimerId = null;
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      accessTokenExpiresAt: null,
      refreshTokenExpiresAt: null,

      login: (user, token, refreshToken) => {
        // Parse expiration times from tokens
        const accessTokenExpiresAt = getTokenExpirationMs(token);
        const refreshTokenExpiresAt = refreshToken 
          ? getTokenExpirationMs(refreshToken) 
          : null;

        apiClient.setToken(token);
        set({ 
          user, 
          token, 
          refreshToken, 
          isAuthenticated: true,
          accessTokenExpiresAt,
          refreshTokenExpiresAt,
        });

        // Schedule proactive token refresh
        get().scheduleTokenRefresh();
      },

      logout: () => {
        clearRefreshTimer();
        apiClient.removeToken();
        set({ 
          user: null, 
          token: null, 
          refreshToken: null, 
          isAuthenticated: false,
          accessTokenExpiresAt: null,
          refreshTokenExpiresAt: null,
        });
      },

      setUser: (user) => set({ user }),

      refreshAccessToken: async () => {
        const { refreshToken } = get();
        if (!refreshToken) {
          console.log('[Auth] No refresh token available');
          return false;
        }

        // Check if refresh token itself is expired
        if (isTokenExpired(refreshToken)) {
          console.log('[Auth] Refresh token expired, logging out');
          get().logout();
          return false;
        }

        try {
          console.log('[Auth] Refreshing access token...');
          const response = await apiClient.refreshToken(refreshToken);
          
          const newAccessTokenExpiresAt = getTokenExpirationMs(response.access_token);
          
          apiClient.setToken(response.access_token);
          set({ 
            token: response.access_token,
            accessTokenExpiresAt: newAccessTokenExpiresAt,
          });

          console.log('[Auth] Token refreshed successfully');
          
          // Schedule next refresh
          get().scheduleTokenRefresh();
          
          return true;
        } catch (error) {
          console.error('[Auth] Token refresh failed:', error);
          // If refresh fails, logout the user
          get().logout();
          return false;
        }
      },

      scheduleTokenRefresh: () => {
        const { token, refreshToken, accessTokenExpiresAt } = get();
        
        // Clear any existing timer
        clearRefreshTimer();

        // Can't refresh without a refresh token
        if (!refreshToken) {
          console.log('[Auth] No refresh token, skipping proactive refresh scheduling');
          return;
        }

        // Can't schedule without knowing expiration
        if (!token || !accessTokenExpiresAt) {
          console.log('[Auth] No token or expiration time, skipping refresh scheduling');
          return;
        }

        // Calculate when to refresh (5 minutes before expiry)
        const now = Date.now();
        const timeUntilExpiry = accessTokenExpiresAt - now;
        const timeUntilRefresh = timeUntilExpiry - REFRESH_BUFFER_MS;

        // If already expired or about to expire, refresh immediately
        if (timeUntilRefresh <= 0) {
          console.log('[Auth] Token expired or expiring soon, refreshing immediately');
          get().refreshAccessToken();
          return;
        }

        // Don't schedule if it's too soon (prevent rapid refreshes)
        const refreshDelay = Math.max(timeUntilRefresh, MIN_REFRESH_INTERVAL_MS);

        console.log(`[Auth] Scheduling token refresh in ${Math.round(refreshDelay / 1000 / 60)} minutes`);
        
        refreshTimerId = setTimeout(() => {
          console.log('[Auth] Proactive token refresh triggered');
          get().refreshAccessToken();
        }, refreshDelay);
      },

      clearRefreshTimer: () => {
        clearRefreshTimer();
      },
    }),
    {
      name: 'auth-storage',
      // Only persist these fields (exclude functions and timers)
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
        accessTokenExpiresAt: state.accessTokenExpiresAt,
        refreshTokenExpiresAt: state.refreshTokenExpiresAt,
      }),
      onRehydrateStorage: () => (state) => {
        // Fast, synchronous hydration - no blocking API calls
        if (state?.token && state?.user) {
          apiClient.setToken(state.token);
          // Set isAuthenticated to true when rehydrating from storage
          state.isAuthenticated = true;
          
          // Check if access token is expired
          if (state.token && isTokenExpired(state.token)) {
            console.log('[Auth] Access token expired on rehydration');
            
            // If we have a valid refresh token, try to refresh
            if (state.refreshToken && !isTokenExpired(state.refreshToken)) {
              console.log('[Auth] Will attempt refresh after hydration');
              // Schedule refresh for after hydration completes
              setTimeout(() => {
                useAuthStore.getState().refreshAccessToken();
              }, 100);
            } else {
              console.log('[Auth] No valid refresh token, will require re-login');
              // Clear auth state - user needs to log in again
              setTimeout(() => {
                useAuthStore.getState().logout();
              }, 100);
            }
          } else {
            // Token is valid, schedule proactive refresh
            setTimeout(() => {
              useAuthStore.getState().scheduleTokenRefresh();
            }, 100);
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
  content_rating?: string;  // "sfw" or "nsfw"
  plot_check_mode?: '1' | '3' | 'all';  // How many events to check
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
