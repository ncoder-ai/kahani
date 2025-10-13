// API configuration and utilities

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class ApiClient {
  private baseURL: string;
  private token: string | null = null;

  constructor(baseURL: string) {
    this.baseURL = baseURL;
    this.loadToken();
  }

  private loadToken() {
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('auth_token');
    }
  }

  setToken(token: string) {
    this.token = token;
    if (typeof window !== 'undefined') {
      localStorage.setItem('auth_token', token);
    }
  }

  removeToken() {
    this.token = null;
    if (typeof window !== 'undefined') {
      localStorage.removeItem('auth_token');
    }
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseURL}${endpoint}`;
    const isFormData = (typeof FormData !== 'undefined') && (options.body instanceof FormData);

    const headers: Record<string, string> = {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers as Record<string, string>,
    };

    if (this.token) {
      headers.Authorization = `Bearer ${this.token}`;
    }

    console.log(`[API] ${options.method || 'GET'} ${url}`);
    console.log('[API] Base URL:', this.baseURL);
    console.log('[API] Endpoint:', endpoint);
    console.log('[API] Headers:', Object.keys(headers));

    try {
      const response = await fetch(url, { ...options, headers });
      console.log(`[API] Response status: ${response.status} ${response.statusText}`);

      if (!response.ok) {
        if (response.status === 401) {
          console.log('[API] 401 Unauthorized - removing token');
          this.removeToken();
          if (typeof window !== 'undefined') {
            window.location.href = '/login';
          }
          throw new Error('Authentication required');
        }

        let errorData: any;
        try {
          errorData = await response.json();
          console.log('[API] Error response data:', errorData);
        } catch (e) {
          console.error('[API] Failed to parse error response:', e);
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        if (errorData.detail && Array.isArray(errorData.detail)) {
          const errorMessages = errorData.detail.map((err: any) => {
            const location = err.loc ? err.loc.slice(1).join(' -> ') : 'Field';
            return `${location}: ${err.msg}`;
          }).join(', ');
          throw new Error(errorMessages);
        }

        const errorMessage = errorData.detail || errorData.message || `HTTP ${response.status}: ${response.statusText}`;
        throw new Error(typeof errorMessage === 'string' ? errorMessage : JSON.stringify(errorMessage));
      }

      const data = await response.json();
      console.log('[API] Response data received successfully');
      return data;
    } catch (error) {
      if (error instanceof Error) {
        console.error('[API] Request failed:', error.message);
      } else {
        console.error('[API] Request failed with unknown error:', error);
      }
      throw error;
    }
  }

  // Authentication
  async login(email: string, password: string) {
    return this.request<{
      access_token: string;
      token_type: string;
      user: any;
    }>(`/api/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  }

  async register(data: { email: string; username: string; password: string; display_name?: string; }) {
    return this.request<{ access_token: string; token_type: string; user: any; }>(`/api/auth/register`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getCurrentUser() {
    return this.request<any>(`/api/auth/me`);
  }

  // User settings
  async getUserSettings() {
    return this.request<{ settings: any }>(`/api/settings/`);
  }

  // Settings
  async getLastAccessedStory() {
    // New path under settings API
    return this.request<{ auto_open_last_story: boolean; last_accessed_story_id?: number; }>(`/api/settings/last-story`);
  }

  // Stories
  async getStories(skip = 0, limit = 10) {
    return this.request<any[]>(`/api/stories/?skip=${skip}&limit=${limit}`);
  }

  async getStory(id: number) {
    return this.request<any>(`/api/stories/${id}`);
  }

  async createStory(data: { title: string; description?: string; genre?: string; tone?: string; world_setting?: string; initial_premise?: string; }) {
    return this.request<any>(`/api/stories/`, { method: 'POST', body: JSON.stringify(data) });
  }

  async generateScene(storyId: number, customPrompt = '') {
    const formData = new FormData();
    formData.append('custom_prompt', customPrompt);
    return this.request<any>(`/api/stories/${storyId}/scenes`, { method: 'POST', headers: {}, body: formData });
  }

  async generateSceneStreaming(
    storyId: number,
    customPrompt = '',
    onChunk?: (chunk: string) => void,
    onComplete?: (sceneId: number, choices: any[]) => void,
    onError?: (error: string) => void
  ) {
    const formData = new FormData();
    formData.append('custom_prompt', customPrompt);
    const headers: Record<string, string> = {};
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    try {
      const response = await fetch(`${this.baseURL}/api/stories/${storyId}/scenes/stream`, { method: 'POST', headers, body: formData });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      if (!response.body) throw new Error('No response body');
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              if (data === '[DONE]') return;
              try {
                const parsed = JSON.parse(data);
                if (parsed.type === 'content' && onChunk) onChunk(parsed.chunk);
                else if (parsed.type === 'complete' && onComplete) onComplete(parsed.scene_id, parsed.choices);
                else if (parsed.type === 'error' && onError) onError(parsed.message);
              } catch {}
            }
          }
        }
      } finally {
        reader.releaseLock();
      }
    } catch (error) {
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error');
      throw error;
    }
  }

  async generateScenario(data: { genre?: string; tone?: string; elements: { opening?: string; setting?: string; conflict?: string; }; characters?: Array<{ name: string; role: string; description: string; }>; }) {
    return this.request<{ scenario: string; message: string; }>(`/api/stories/generate-scenario`, { method: 'POST', body: JSON.stringify(data) });
  }

  async generateTitles(data: { genre?: string; tone?: string; scenario?: string; characters?: Array<{ name: string; role: string; description: string; }>; story_elements?: Record<string, any>; }) {
    return this.request<{ titles: string[]; message: string; }>(`/api/stories/generate-title`, { method: 'POST', body: JSON.stringify(data) });
  }

  async generatePlot(data: { genre?: string; tone?: string; scenario?: string; characters?: Array<{ name: string; role: string; description: string; }>; world_setting?: string; plot_type?: 'complete' | 'single_point'; plot_point_index?: number; }) {
    return this.request<{ plot_points?: string[]; plot_point?: string; message: string; }>(`/api/stories/generate-plot`, { method: 'POST', body: JSON.stringify(data) });
  }

  async getStoryChoices(storyId: number) {
    return this.request<{ choices: Array<{ text: string; order: number; }>; }>(`/api/stories/${storyId}/choices`);
  }

  async generateMoreChoices(storyId: number) {
    return this.request<{ choices: Array<{ text: string; order: number; }>; }>(`/api/stories/${storyId}/generate-more-choices`, { method: 'POST' });
  }

  async regenerateLastScene(storyId: number) {
    return this.request<{ message: string; scene: { id: number; sequence_number: number; title: string; content: string; location: string; characters_present: string[]; }; variant: { id: number; variant_number: number; is_original: boolean; generation_method: string; choices: Array<{ id: number; text: string; description: string; order: number; }>; }; }>(`/api/stories/${storyId}/regenerate-last-scene`, { method: 'POST' });
  }

  async regenerateLastSceneStreaming(
    storyId: number,
    customPrompt = '',
    onChunk?: (chunk: string) => void,
    onComplete?: (variant: any) => void,
    onError?: (error: string) => void
  ) {
    const headers: Record<string, string> = {};
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    try {
      const formData = new FormData();
      formData.append('custom_prompt', customPrompt);
      const response = await fetch(`${this.baseURL}/api/stories/${storyId}/regenerate-last-scene/stream`, { method: 'POST', headers, body: formData });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const reader = response.body?.getReader();
      if (!reader) throw new Error('Failed to get response reader');
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') return;
            try {
              const parsed = JSON.parse(data);
              if (parsed.type === 'content' && onChunk) onChunk(parsed.chunk);
              else if (parsed.type === 'complete' && onComplete) onComplete(parsed.variant);
              else if (parsed.type === 'error' && onError) onError(parsed.message);
            } catch (e) {
              console.error('Failed to parse streaming data:', e);
            }
          }
        }
      }
    } catch (error) {
      console.error('Streaming regeneration failed:', error);
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error');
    }
  }

  // Scene Variants
  async createSceneVariant(storyId: number, sceneId: number, customPrompt?: string) {
    return this.request<{ message: string; variant: any }>(`/api/stories/${storyId}/scenes/${sceneId}/variants`, {
      method: 'POST',
      body: JSON.stringify({ custom_prompt: customPrompt }),
    });
  }

  async createSceneVariantStreaming(
    storyId: number,
    sceneId: number,
    customPrompt = '',
    onChunk?: (chunk: string) => void,
    onComplete?: (variant: any) => void,
    onError?: (error: string) => void
  ) {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    
    try {
      const response = await fetch(`${this.baseURL}/api/stories/${storyId}/scenes/${sceneId}/variants/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ custom_prompt: customPrompt })
      });
      
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      
      const reader = response.body?.getReader();
      if (!reader) throw new Error('Failed to get response reader');
      
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          const chunk = new TextDecoder().decode(value);
          const lines = chunk.split('\n');
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              if (data === '[DONE]') continue;
              
              try {
                const parsed = JSON.parse(data);
                if (parsed.type === 'content' && onChunk) onChunk(parsed.chunk);
                else if (parsed.type === 'complete' && onComplete) onComplete(parsed.variant);
                else if (parsed.type === 'error' && onError) onError(parsed.message);
              } catch (e) {
                console.error('Failed to parse streaming data:', e);
              }
            }
          }
        }
      } finally {
        reader.releaseLock();
      }
    } catch (error) {
      console.error('Streaming variant creation failed:', error);
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error');
    }
  }

  async getSceneVariants(storyId: number, sceneId: number) {
    return this.request<{ scene_id: number; variants: any[] }>(`/api/stories/${storyId}/scenes/${sceneId}/variants`);
  }

  async activateSceneVariant(storyId: number, sceneId: number, variantId: number) {
    return this.request<{ message: string }>(`/api/stories/${storyId}/scenes/${sceneId}/variants/${variantId}/activate`, {
      method: 'POST',
    });
  }

  // Scene Continuation
  async continueScene(storyId: number, sceneId: number, customPrompt?: string) {
    return this.request<{ message: string; scene: any }>(`/api/stories/${storyId}/scenes/${sceneId}/continue`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ custom_prompt: customPrompt }),
    });
  }

  async continueSceneStreaming(
    storyId: number,
    sceneId: number,
    customPrompt = '',
    onChunk?: (chunk: string) => void,
    onComplete?: (sceneId: number, newContent: string) => void,
    onError?: (error: string) => void
  ) {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    try {
      const response = await fetch(`${this.baseURL}/api/stories/${storyId}/scenes/${sceneId}/continue/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ custom_prompt: customPrompt }),
      });

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const reader = response.body?.getReader();
      if (!reader) throw new Error('Failed to get response reader');
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') return;
            try {
              const parsed = JSON.parse(data);
              if (parsed.type === 'content' && onChunk) onChunk(parsed.chunk);
              else if (parsed.type === 'complete' && onComplete) onComplete(parsed.scene_id, parsed.new_content);
              else if (parsed.type === 'error' && onError) onError(parsed.message);
            } catch (e) {
              // ignore non-JSON lines
            }
          }
        }
      }
    } catch (error) {
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error');
    }
  }

  // Delete scenes from sequence
  async deleteScenesFromSequence(storyId: number, sequenceNumber: number) {
    return this.request<{ message: string }>(`/api/stories/${storyId}/scenes/from/${sequenceNumber}`, {
      method: 'DELETE',
    });
  }

  // Character API
  async getCharacter(characterId: number) {
    return this.request<{ id: number; name: string; description: string; personality_traits: string[]; background: string; goals: string; fears: string; appearance: string; is_template: boolean; is_public: boolean; creator_id: number; created_at: string; updated_at: string | null; }>(`/api/characters/${characterId}`);
  }

  async getCharacters(skip = 0, limit = 50, includePublic = true, templatesOnly = false) {
    const params = new URLSearchParams({ skip: String(skip), limit: String(limit), include_public: String(includePublic), templates_only: String(templatesOnly) });
    return this.request<Array<{ id: number; name: string; description: string; personality_traits: string[]; background: string; goals: string; fears: string; appearance: string; is_template: boolean; is_public: boolean; creator_id: number; created_at: string; updated_at: string | null; }>>(`/api/characters/?${params}`);
  }

  async deleteCharacter(characterId: number) {
    return this.request<{ message: string; }>(`/api/characters/${characterId}`, { method: 'DELETE' });
  }

  async updateCharacter(characterId: number, data: { name?: string; description?: string; personality_traits?: string[]; background?: string; goals?: string; fears?: string; appearance?: string; is_template?: boolean; is_public?: boolean; }) {
    return this.request<{ id: number; name: string; description: string; personality_traits: string[]; background: string; goals: string; fears: string; appearance: string; is_template: boolean; is_public: boolean; creator_id: number; created_at: string; updated_at: string | null; }>(`/api/characters/${characterId}`, { method: 'PUT', body: JSON.stringify(data) });
  }

  async createCharacter(data: { name: string; description?: string; personality_traits?: string[]; background?: string; goals?: string; fears?: string; appearance?: string; is_template?: boolean; is_public?: boolean; }) {
    return this.request<{ id: number; name: string; description: string; personality_traits: string[]; background: string; goals: string; fears: string; appearance: string; is_template: boolean; is_public: boolean; creator_id: number; created_at: string; updated_at: string | null; }>(`/api/characters/`, { method: 'POST', body: JSON.stringify(data) });
  }

  // Draft Stories
  async getDraftStory() {
    return this.request<{ id: number; title: string; scenario: string; characters: Array<{ id: number; name: string; description: string; }>; plot_points: string[]; created_at: string; updated_at: string; }>(`/api/stories/draft`);
  }

  async getSpecificDraftStory(storyId: number) {
    return this.request<{ id: number; title: string; scenario: string; characters: Array<{ id: number; name: string; description: string; }>; plot_points: string[]; created_at: string; updated_at: string; }>(`/api/stories/draft/${storyId}`);
  }

  async createOrUpdateDraftStory(data: { title?: string; scenario?: string; characters?: any[]; plot_points?: string[]; step?: number; story_id?: number; }) {
    return this.request<any>(`/api/stories/draft`, { method: 'POST', body: JSON.stringify(data) });
  }

  async finalizeDraftStory(draftStoryId: number) {
    return this.request<{ id: number; title: string; scenario: string; characters: Array<{ id: number; name: string; description: string; }>; plot_points: string[]; created_at: string; updated_at: string; }>(`/api/stories/draft/${draftStoryId}/finalize`, { method: 'POST' });
  }

  async deleteDraftStory(draftStoryId: number) {
    return this.request<{ message: string; }>(`/api/stories/draft/${draftStoryId}`, { method: 'DELETE' });
  }

  // Writing Style Presets
  async listWritingPresets() {
    return this.request<Array<{
      id: number;
      user_id: number;
      name: string;
      description: string | null;
      system_prompt: string;
      summary_system_prompt: string | null;
      is_active: boolean;
      created_at: string;
      updated_at: string | null;
    }>>(`/api/writing-presets/`);
  }

  async getWritingPreset(presetId: number) {
    return this.request<{
      id: number;
      user_id: number;
      name: string;
      description: string | null;
      system_prompt: string;
      summary_system_prompt: string | null;
      is_active: boolean;
      created_at: string;
      updated_at: string | null;
    }>(`/api/writing-presets/${presetId}`);
  }

  async createWritingPreset(data: {
    name: string;
    description?: string;
    system_prompt: string;
    summary_system_prompt?: string;
  }) {
    return this.request<{
      id: number;
      user_id: number;
      name: string;
      description: string | null;
      system_prompt: string;
      summary_system_prompt: string | null;
      is_active: boolean;
      created_at: string;
      updated_at: string | null;
    }>(`/api/writing-presets/`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateWritingPreset(presetId: number, data: {
    name?: string;
    description?: string;
    system_prompt?: string;
    summary_system_prompt?: string;
  }) {
    return this.request<{
      id: number;
      user_id: number;
      name: string;
      description: string | null;
      system_prompt: string;
      summary_system_prompt: string | null;
      is_active: boolean;
      created_at: string;
      updated_at: string | null;
    }>(`/api/writing-presets/${presetId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteWritingPreset(presetId: number) {
    return this.request<void>(`/api/writing-presets/${presetId}`, {
      method: 'DELETE',
    });
  }

  async activateWritingPreset(presetId: number) {
    return this.request<{
      id: number;
      user_id: number;
      name: string;
      description: string | null;
      system_prompt: string;
      summary_system_prompt: string | null;
      is_active: boolean;
      created_at: string;
      updated_at: string | null;
    }>(`/api/writing-presets/${presetId}/activate`, {
      method: 'POST',
    });
  }

  async duplicateWritingPreset(presetId: number) {
    return this.request<{
      id: number;
      user_id: number;
      name: string;
      description: string | null;
      system_prompt: string;
      summary_system_prompt: string | null;
      is_active: boolean;
      created_at: string;
      updated_at: string | null;
    }>(`/api/writing-presets/${presetId}/duplicate`, {
      method: 'POST',
    });
  }

  async getDefaultWritingPresetTemplate() {
    return this.request<{
      name: string;
      description: string;
      system_prompt: string;
      summary_system_prompt: string | null;
    }>(`/api/writing-presets/default/template`);
  }

  // Chapters
  async getChapters(storyId: number) {
    return this.request<Array<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
    }>>(`/api/stories/${storyId}/chapters`);
  }

  async getChapter(storyId: number, chapterId: number) {
    return this.request<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
    }>(`/api/stories/${storyId}/chapters/${chapterId}`);
  }

  async getActiveChapter(storyId: number) {
    return this.request<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
    }>(`/api/stories/${storyId}/active-chapter`);
  }

  async createChapter(storyId: number, data: {
    title?: string;
    description?: string;
    plot_point?: string;
    plot_point_index?: number;
    story_so_far?: string;
  }) {
    return this.request<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
    }>(`/api/stories/${storyId}/chapters`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateChapter(storyId: number, chapterId: number, data: {
    title?: string;
    description?: string;
    story_so_far?: string;
    plot_point?: string;
  }) {
    return this.request<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
    }>(`/api/stories/${storyId}/chapters/${chapterId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async completeChapter(storyId: number, chapterId: number) {
    return this.request<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
    }>(`/api/stories/${storyId}/chapters/${chapterId}/complete`, {
      method: 'POST',
    });
  }

  async getChapterContextStatus(storyId: number, chapterId: number) {
    return this.request<{
      chapter_id: number;
      current_tokens: number;
      max_tokens: number;
      percentage_used: number;
      should_create_new_chapter: boolean;
      reason: string | null;
      scenes_count: number;
      avg_generation_time?: number | null;
    }>(`/api/stories/${storyId}/chapters/${chapterId}/context-status`);
  }

  async generateChapterSummary(storyId: number, chapterId: number) {
    return this.request<{
      id: number;
      story_id: number;
      chapter_number: number;
      title: string | null;
      description: string | null;
      plot_point: string | null;
      plot_point_index: number | null;
      story_so_far: string | null;
      auto_summary: string | null;
      status: 'draft' | 'active' | 'completed';
      context_tokens_used: number;
      scenes_count: number;
      last_summary_scene_count: number;
      created_at: string;
      updated_at: string | null;
    }>(`/api/stories/${storyId}/chapters/${chapterId}/generate-summary`, {
      method: 'POST',
    });
  }

  async deleteChapterScenes(storyId: number, chapterId: number) {
    return this.request<{ message: string }>(`/api/stories/${storyId}/chapters/${chapterId}/scenes`, {
      method: 'DELETE',
    });
  }
}

export default new ApiClient(API_BASE_URL);
