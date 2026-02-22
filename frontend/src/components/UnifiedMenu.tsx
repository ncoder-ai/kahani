'use client';

import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/store';
import { useGlobalTTS } from '@/contexts/GlobalTTSContext';
import { audioContextManager } from '@/utils/audioContextManager';
import { useState, useEffect, useCallback } from 'react';
import {
  X, Settings, LogOut, User, Home, PlusCircle, BookOpen,
  ChevronRight, ChevronDown, Film, Trash2, Shield, Edit, Bug, GitBranch, Volume2, Users, UserCog, Package, Image, LayoutGrid, MessageSquare
} from 'lucide-react';
import BranchSelector from './BranchSelector';

interface StoryActions {
  onChapters?: () => void;
  onAddCharacter?: () => void;
  onEditCharacterVoices?: () => void;
  onViewAllCharacters?: () => void;
  onEditCharacterRoles?: () => void;
  onManageStoryCharacters?: () => void;
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
  // Branch-related props
  storyId?: number;
  currentBranchId?: number;
  currentSceneSequence?: number;
  onBranchChange?: (branchId: number) => void;
  onBranchCreated?: () => void;
}

interface UnifiedMenuProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenSettings: () => void;
  // Story-specific props (optional)
  isStoryPage?: boolean;
  storyActions?: StoryActions;
}

export default function UnifiedMenu({ 
  isOpen, 
  onClose, 
  onOpenSettings,
  isStoryPage = false,
  storyActions
}: UnifiedMenuProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, logout } = useAuthStore();
  const { currentSceneId, isPlaying, isGenerating, error, progress, chunksReceived, totalChunks } = useGlobalTTS();
  const [showDebug, setShowDebug] = useState(false);
  const [audioState, setAudioState] = useState<string>('unknown');
  const [isUnlocking, setIsUnlocking] = useState(false);
  const [showCharactersSubmenu, setShowCharactersSubmenu] = useState(false);
  
  // Only show debug option on mobile
  const isMobile = typeof window !== 'undefined' && /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
  
  // Update AudioContext state periodically when debug panel is open
  useEffect(() => {
    if (!showDebug) return;
    
    const updateState = () => {
      setAudioState(audioContextManager.getState());
    };
    
    updateState();
    const interval = setInterval(updateState, 500);
    
    return () => clearInterval(interval);
  }, [showDebug]);
  
  // Handle unlock button click
  const handleUnlockAudio = useCallback(async () => {
    setIsUnlocking(true);
    console.log('[TTS Debug Menu] Attempting to unlock AudioContext...');
    
    const success = await audioContextManager.unlock();
    
    if (success) {
      console.log('[TTS Debug Menu] ✓ AudioContext unlocked');
      setAudioState(audioContextManager.getState());
    } else {
      console.error('[TTS Debug Menu] ✗ Failed to unlock AudioContext');
    }
    
    setIsUnlocking(false);
  }, []);
  
  // Handle test audio button click
  const handleTestAudio = useCallback(async () => {
    console.log('[TTS Debug Menu] Testing audio playback...');
    await audioContextManager.testAudio();
  }, []);
  
  const isAudioReady = audioState === 'running';

  if (!isOpen) return null;

  const handleLogout = () => {
    onClose();
    logout();
    router.push('/login');
  };

  const handleDashboard = () => {
    onClose();
    router.push('/dashboard');
  };

  const handleCharacters = () => {
    onClose();
    router.push('/characters');
  };

  const handleCreateStory = () => {
    onClose();
    router.push('/create-story');
  };

  const handleRoleplay = () => {
    onClose();
    router.push('/roleplay');
  };

  const handleSettings = () => {
    onClose();
    onOpenSettings();
  };

  const handleAdminPanel = () => {
    onClose();
    router.push('/admin');
  };

  return (
    <>
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
        onClick={onClose}
      />
      
      {/* Menu Modal - Top Right */}
      <div className="fixed right-4 top-16 z-50 w-80 max-w-[calc(100vw-2rem)] theme-card border border-gray-700 rounded-lg shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700 theme-banner">
          <div>
            <h2 className="text-lg font-semibold text-white">📖 Menu</h2>
            {user && <p className="text-xs text-white/60">{user.display_name}</p>}
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-white/10 rounded transition-colors"
          >
            <X className="w-5 h-5 text-white" />
          </button>
        </div>
        
        {/* Menu Items */}
        <div className="p-2 max-h-[calc(100vh-12rem)] overflow-y-auto">
          
          {/* Story-Specific Actions - Show first when on story page */}
          {isStoryPage && storyActions && (
            <div className="space-y-1">
              <div className="px-3 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Story Actions
              </div>

              {/* Branch Selector with Director/Delete Mode Icons */}
              {storyActions.storyId && (
                <div className="px-3 py-2 border-b border-gray-700/50 mb-2">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2 text-xs text-gray-400">
                      <GitBranch className="w-3.5 h-3.5" />
                      <span>Story Branch</span>
                    </div>
                    {/* Director Mode & Delete Mode Icons */}
                    <div className="flex items-center gap-1">
                      {storyActions.onDirectorMode && (
                        <button
                          onClick={() => {
                            storyActions.onDirectorMode?.();
                          }}
                          className={`p-1.5 rounded-md transition-colors ${
                            storyActions.directorModeActive 
                              ? 'bg-pink-600/30 text-pink-400' 
                              : 'hover:bg-white/10 text-gray-400 hover:text-white'
                          }`}
                          title={storyActions.directorModeActive ? 'Director Mode ON' : 'Director Mode OFF'}
                        >
                          <Film className="w-4 h-4" />
                        </button>
                      )}
                      {storyActions.onDeleteMode && (
                        <button
                          onClick={() => {
                            storyActions.onDeleteMode?.();
                          }}
                          className={`p-1.5 rounded-md transition-colors ${
                            storyActions.deleteModeActive
                              ? 'bg-red-600/30 text-red-400'
                              : 'hover:bg-white/10 text-gray-400 hover:text-white'
                          }`}
                          title={storyActions.deleteModeActive ? 'Delete Mode ON' : 'Delete Mode OFF'}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                      {storyActions.onToggleImages && (
                        <button
                          onClick={() => {
                            storyActions.onToggleImages?.();
                          }}
                          className={`p-1.5 rounded-md transition-colors ${
                            storyActions.showImagesActive
                              ? 'bg-purple-600/30 text-purple-400'
                              : 'hover:bg-white/10 text-gray-400 hover:text-white'
                          }`}
                          title={storyActions.showImagesActive ? 'Images ON' : 'Images OFF'}
                        >
                          <Image className="w-4 h-4" />
                        </button>
                      )}
                      {storyActions.onOpenGallery && (
                        <button
                          onClick={() => {
                            onClose();
                            storyActions.onOpenGallery?.();
                          }}
                          className="p-1.5 rounded-md transition-colors hover:bg-white/10 text-gray-400 hover:text-white"
                          title="Image Gallery"
                        >
                          <LayoutGrid className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>
                  <BranchSelector
                    storyId={storyActions.storyId}
                    currentBranchId={storyActions.currentBranchId}
                    currentSceneSequence={storyActions.currentSceneSequence || 1}
                    onBranchChange={(branchId) => {
                      onClose();
                      storyActions.onBranchChange?.(branchId);
                    }}
                    onBranchCreated={() => {
                      onClose();
                      storyActions.onBranchCreated?.();
                    }}
                  />
                </div>
              )}

              {/* Chapters */}
              {storyActions.onChapters && (
                <button
                  onClick={() => {
                    onClose();
                    storyActions.onChapters?.();
                  }}
                  className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
                >
                  <div className="p-2 bg-white/10 rounded-lg group-hover:bg-white/20 transition-colors">
                    <BookOpen className="w-5 h-5 theme-accent-primary" />
                  </div>
                  <div className="flex-1">
                    <div className="font-medium text-white">Chapters</div>
                    <div className="text-xs text-gray-400">View chapter info</div>
                  </div>
                  <ChevronRight className="w-5 h-5 text-gray-500" />
                </button>
              )}

              {/* Edit Story Settings */}
              {storyActions.onEditStorySettings && (
                <button
                  onClick={() => {
                    onClose();
                    storyActions.onEditStorySettings?.();
                  }}
                  className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
                >
                  <div className="p-2 bg-white/10 rounded-lg group-hover:bg-white/20 transition-colors">
                    <Edit className="w-5 h-5 theme-accent-primary" />
                  </div>
                  <div className="flex-1">
                    <div className="font-medium text-white">Edit Story Settings</div>
                    <div className="text-xs text-gray-400">Title, genre, scenario, etc.</div>
                  </div>
                  <ChevronRight className="w-5 h-5 text-gray-500" />
                </button>
              )}

              {/* Characters Submenu */}
              <div>
                <button
                  onClick={() => setShowCharactersSubmenu(!showCharactersSubmenu)}
                  className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
                >
                  <div className="p-2 bg-purple-600/20 rounded-lg group-hover:bg-purple-600/30 transition-colors">
                    <Users className="w-5 h-5 text-purple-400" />
                  </div>
                  <div className="flex-1">
                    <div className="font-medium text-white">Characters</div>
                    <div className="text-xs text-gray-400">Manage story characters</div>
                  </div>
                  <ChevronDown className={`w-5 h-5 text-gray-500 transition-transform ${showCharactersSubmenu ? 'rotate-180' : ''}`} />
                </button>
                
                {/* Characters Submenu Items */}
                {showCharactersSubmenu && (
                  <div className="ml-4 mt-1 space-y-1 border-l-2 border-purple-600/30 pl-2">
                    {/* Add Character */}
                    {storyActions.onAddCharacter && (
                      <button
                        onClick={() => {
                          onClose();
                          storyActions.onAddCharacter?.();
                        }}
                        className="w-full flex items-center gap-3 p-2.5 hover:bg-white/10 rounded-lg transition-colors text-left group"
                      >
                        <div className="p-1.5 bg-white/10 rounded-lg group-hover:bg-white/20 transition-colors">
                          <PlusCircle className="w-4 h-4 theme-accent-primary" />
                        </div>
                        <div className="flex-1">
                          <div className="text-sm font-medium text-white">Add Character</div>
                          <div className="text-xs text-gray-400">Quick add to story</div>
                        </div>
                      </button>
                    )}

                    {/* Manage Story Characters */}
                    {storyActions.onManageStoryCharacters && (
                      <button
                        onClick={() => {
                          onClose();
                          storyActions.onManageStoryCharacters?.();
                        }}
                        className="w-full flex items-center gap-3 p-2.5 hover:bg-white/10 rounded-lg transition-colors text-left group"
                      >
                        <div className="p-1.5 bg-blue-600/20 rounded-lg group-hover:bg-blue-600/30 transition-colors">
                          <Edit className="w-4 h-4 text-blue-400" />
                        </div>
                        <div className="flex-1">
                          <div className="text-sm font-medium text-white">Manage Story Characters</div>
                          <div className="text-xs text-gray-400">Edit details, portraits & more</div>
                        </div>
                      </button>
                    )}

                    {/* Character Voices */}
                    {storyActions.onEditCharacterVoices && (
                      <button
                        onClick={() => {
                          onClose();
                          storyActions.onEditCharacterVoices?.();
                        }}
                        className="w-full flex items-center gap-3 p-2.5 hover:bg-white/10 rounded-lg transition-colors text-left group"
                      >
                        <div className="p-1.5 bg-pink-600/20 rounded-lg group-hover:bg-pink-600/30 transition-colors">
                          <Volume2 className="w-4 h-4 text-pink-400" />
                        </div>
                        <div className="flex-1">
                          <div className="text-sm font-medium text-white">Character Voices</div>
                          <div className="text-xs text-gray-400">Edit how characters speak</div>
                        </div>
                      </button>
                    )}

                    {/* Character Interactions */}
                    {storyActions.onShowInteractions && (
                      <button
                        onClick={() => {
                          onClose();
                          storyActions.onShowInteractions?.();
                        }}
                        className="w-full flex items-center gap-3 p-2.5 hover:bg-white/10 rounded-lg transition-colors text-left group"
                      >
                        <div className="p-1.5 bg-white/10 rounded-lg group-hover:bg-white/20 transition-colors">
                          <Users className="w-4 h-4 theme-accent-primary" />
                        </div>
                        <div className="flex-1">
                          <div className="text-sm font-medium text-white">Character Interactions</div>
                          <div className="text-xs text-gray-400">View interaction history</div>
                        </div>
                      </button>
                    )}

                    {/* Entity States */}
                    {storyActions.onShowEntityStates && (
                      <button
                        onClick={() => {
                          onClose();
                          storyActions.onShowEntityStates?.();
                        }}
                        className="w-full flex items-center gap-3 p-2.5 hover:bg-white/10 rounded-lg transition-colors text-left group"
                      >
                        <div className="p-1.5 bg-emerald-600/20 rounded-lg group-hover:bg-emerald-600/30 transition-colors">
                          <Package className="w-4 h-4 text-emerald-400" />
                        </div>
                        <div className="flex-1">
                          <div className="text-sm font-medium text-white">Entity States</div>
                          <div className="text-xs text-gray-400">View character, location & object states</div>
                        </div>
                      </button>
                    )}

                    {/* Contradictions */}
                    {storyActions.onShowContradictions && (
                      <button
                        onClick={() => {
                          onClose();
                          storyActions.onShowContradictions?.();
                        }}
                        className="w-full flex items-center gap-3 p-2.5 hover:bg-white/10 rounded-lg transition-colors text-left group"
                      >
                        <div className="p-1.5 bg-red-600/20 rounded-lg group-hover:bg-red-600/30 transition-colors">
                          <Bug className="w-4 h-4 text-red-400" />
                        </div>
                        <div className="flex-1">
                          <div className="text-sm font-medium text-white">Contradictions</div>
                          <div className="text-xs text-gray-400">View continuity errors & resolve them</div>
                        </div>
                      </button>
                    )}

                    {/* Edit Character Roles */}
                    {storyActions.onEditCharacterRoles && (
                      <button
                        onClick={() => {
                          onClose();
                          storyActions.onEditCharacterRoles?.();
                        }}
                        className="w-full flex items-center gap-3 p-2.5 hover:bg-white/10 rounded-lg transition-colors text-left group"
                      >
                        <div className="p-1.5 bg-amber-600/20 rounded-lg group-hover:bg-amber-600/30 transition-colors">
                          <UserCog className="w-4 h-4 text-amber-400" />
                        </div>
                        <div className="flex-1">
                          <div className="text-sm font-medium text-white">Edit Character Roles</div>
                          <div className="text-xs text-gray-400">Change roles in story</div>
                        </div>
                      </button>
                    )}

                    {/* View All Characters */}
                    {storyActions.onViewAllCharacters && (
                      <button
                        onClick={() => {
                          onClose();
                          storyActions.onViewAllCharacters?.();
                        }}
                        className="w-full flex items-center gap-3 p-2.5 hover:bg-white/10 rounded-lg transition-colors text-left group"
                      >
                        <div className="p-1.5 bg-white/10 rounded-lg group-hover:bg-white/20 transition-colors">
                          <User className="w-4 h-4 theme-accent-primary" />
                        </div>
                        <div className="flex-1">
                          <div className="text-sm font-medium text-white">View All Characters</div>
                          <div className="text-xs text-gray-400">Character library</div>
                        </div>
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Separator between story and global actions */}
          {isStoryPage && storyActions && (
            <div className="my-3 border-t border-gray-700"></div>
          )}

          {/* Global Actions */}
          <div className="space-y-1">
            {/* Dashboard */}
            {pathname !== '/dashboard' && (
              <button
                onClick={handleDashboard}
                className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
              >
                <div className="p-2 bg-white/10 rounded-lg group-hover:bg-white/20 transition-colors">
                  <Home className="w-5 h-5 theme-accent-primary" />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">Dashboard</div>
                  <div className="text-xs text-gray-400">View all stories</div>
                </div>
              </button>
            )}

            {/* Characters */}
            <button
              onClick={handleCharacters}
              className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
            >
              <div className="p-2 bg-white/10 rounded-lg group-hover:bg-white/20 transition-colors">
                <User className="w-5 h-5 theme-accent-primary" />
              </div>
              <div className="flex-1">
                <div className="font-medium text-white">Characters</div>
                <div className="text-xs text-gray-400">Manage character library</div>
              </div>
            </button>

            {/* Worlds */}
            <button
              onClick={() => {
                onClose();
                router.push('/worlds');
              }}
              className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
            >
              <div className="p-2 bg-white/10 rounded-lg group-hover:bg-white/20 transition-colors">
                <LayoutGrid className="w-5 h-5 theme-accent-primary" />
              </div>
              <div className="flex-1">
                <div className="font-medium text-white">Worlds</div>
                <div className="text-xs text-gray-400">Manage shared universes</div>
              </div>
            </button>

            {/* Create New Story */}
            <button
              onClick={handleCreateStory}
              className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
            >
              <div className="p-2 bg-white/10 rounded-lg group-hover:bg-white/20 transition-colors">
                <PlusCircle className="w-5 h-5 theme-accent-primary" />
              </div>
              <div className="flex-1">
                <div className="font-medium text-white">Create New Story</div>
                <div className="text-xs text-gray-400">Start a new adventure</div>
              </div>
            </button>

            {/* Roleplay */}
            <button
              onClick={handleRoleplay}
              className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
            >
              <div className="p-2 bg-white/10 rounded-lg group-hover:bg-white/20 transition-colors">
                <MessageSquare className="w-5 h-5 theme-accent-primary" />
              </div>
              <div className="flex-1">
                <div className="font-medium text-white">Roleplay</div>
                <div className="text-xs text-gray-400">Interactive character sessions</div>
              </div>
            </button>

            {/* Settings */}
            <button
              onClick={handleSettings}
              className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
            >
              <div className="p-2 bg-white/10 rounded-lg group-hover:bg-white/20 transition-colors">
                <Settings className="w-5 h-5 theme-accent-primary" />
              </div>
              <div className="flex-1">
                <div className="font-medium text-white">Settings</div>
                <div className="text-xs text-gray-400">Configure your preferences</div>
              </div>
            </button>
          </div>


          {/* Bottom Actions */}
          <div className="my-3 border-t border-gray-700"></div>
          <div className="space-y-1">
            {/* TTS Debug - Mobile Only */}
            {isMobile && (
              <>
                <button
                  onClick={() => setShowDebug(!showDebug)}
                  className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
                >
                  <div className="p-2 bg-blue-600/20 rounded-lg group-hover:bg-blue-600/30 transition-colors">
                    <Bug className="w-5 h-5 text-blue-400" />
                  </div>
                  <div className="flex-1">
                    <div className="font-medium text-white">Debug TTS</div>
                    <div className="text-xs text-gray-400">Troubleshooting info</div>
                  </div>
                  <ChevronRight className={`w-5 h-5 text-gray-500 transition-transform ${showDebug ? 'rotate-90' : ''}`} />
                </button>
                
                {/* Debug Panel - Collapsible */}
                {showDebug && (
                  <div className="ml-4 mr-2 mb-2 p-3 bg-black/50 border border-gray-700 rounded-lg text-xs">
                    {/* Status Header */}
                    <div className="flex items-center justify-between mb-3">
                      <div className="font-bold text-sm text-white">🔍 TTS Debug Info</div>
                      <div className={`px-2 py-0.5 rounded text-[10px] ${
                        error ? 'bg-red-500' : isGenerating ? 'bg-blue-500' : isPlaying ? 'bg-green-500' : 'bg-gray-600'
                      }`}>
                        {error ? 'ERROR' : isGenerating ? 'GENERATING' : isPlaying ? 'PLAYING' : 'IDLE'}
                      </div>
                    </div>
                    
                    {/* AudioContext Status - Prominent */}
                    <div className={`mb-3 p-2 rounded border ${
                      isAudioReady 
                        ? 'bg-green-500/20 border-green-500/50' 
                        : 'bg-orange-500/20 border-orange-500/50'
                    }`}>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${isAudioReady ? 'bg-green-400' : 'bg-orange-400 animate-pulse'}`}></span>
                          <span className="text-[11px] font-semibold text-white">
                            Audio: <span className="font-mono">{audioState}</span>
                          </span>
                        </div>
                        {!isAudioReady && (
                          <button
                            onClick={handleUnlockAudio}
                            disabled={isUnlocking}
                            className="px-2 py-1 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-600 text-white text-[10px] rounded transition-colors"
                          >
                            {isUnlocking ? '...' : 'Unlock'}
                          </button>
                        )}
                      </div>
                      {!isAudioReady && (
                        <p className="text-[10px] text-orange-300 mt-1">
                          Tap Unlock to enable TTS playback
                        </p>
                      )}
                    </div>
                    
                    {/* Status Info */}
                    <div className="mb-3 space-y-1 text-[11px]">
                      <div className="flex justify-between">
                        <span className="text-gray-400">Scene:</span>
                        <span className="font-mono text-white">{currentSceneId || 'None'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Progress:</span>
                        <span className="font-mono text-white">{progress}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Chunks:</span>
                        <span className="font-mono text-white">{chunksReceived} / {totalChunks || '?'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Online:</span>
                        <span className={typeof navigator !== 'undefined' && navigator.onLine ? 'text-green-400' : 'text-red-400'}>
                          {typeof navigator !== 'undefined' && navigator.onLine ? '✓ Yes' : '✗ No'}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Auth:</span>
                        <span className={typeof window !== 'undefined' && localStorage.getItem('auth_token') ? 'text-green-400' : 'text-red-400'}>
                          {typeof window !== 'undefined' && localStorage.getItem('auth_token') ? '✓ Present' : '✗ Missing'}
                        </span>
                      </div>
                    </div>
                    
                    {/* Error Display */}
                    {error && (
                      <div className="mb-3 p-2 bg-red-500/20 border border-red-500/50 rounded text-[11px]">
                        <div className="font-semibold text-red-400 mb-1">Error:</div>
                        <div className="text-red-300">{error}</div>
                      </div>
                    )}
                    
                    {/* Device Info */}
                    {typeof window !== 'undefined' && (
                      <div className="pt-3 border-t border-gray-700 text-[10px] text-gray-500">
                        <div>Device: {/iPhone|iPad|iPod/i.test(navigator.userAgent) ? 'iOS' : 
                                      /Android/i.test(navigator.userAgent) ? 'Android' : 'Desktop'}</div>
                        <div>Screen: {window.innerWidth}×{window.innerHeight}</div>
                      </div>
                    )}
                    
                    {/* Test Audio Button */}
                    <div className="mt-3 pt-3 border-t border-gray-700">
                      <button
                        onClick={handleTestAudio}
                        disabled={!isAudioReady}
                        className={`w-full text-white text-xs py-2 px-3 rounded transition-colors ${
                          isAudioReady 
                            ? 'bg-yellow-600 hover:bg-yellow-700' 
                            : 'bg-gray-600 cursor-not-allowed'
                        }`}
                      >
                        🔊 Test Audio (Beep)
                      </button>
                      {!isAudioReady && (
                        <p className="text-[10px] text-gray-500 mt-1 text-center">
                          Unlock audio first
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </>
            )}

            {/* Admin Panel */}
            {user?.is_admin && (
              <button
                onClick={handleAdminPanel}
                className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
              >
                <div className="p-2 bg-amber-600/20 rounded-lg group-hover:bg-amber-600/30 transition-colors">
                  <Shield className="w-5 h-5 text-amber-400" />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-white">Admin Panel</div>
                  <div className="text-xs text-gray-400">System administration</div>
                </div>
              </button>
            )}

            {/* Logout */}
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 p-3 hover:bg-red-500/10 rounded-lg transition-colors text-left group"
            >
              <div className="p-2 bg-red-500/20 rounded-lg group-hover:bg-red-500/30 transition-colors">
                <LogOut className="w-5 h-5 text-red-400" />
              </div>
              <div className="flex-1">
                <div className="font-medium text-white">Logout</div>
                <div className="text-xs text-gray-400">Sign out of your account</div>
              </div>
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
