'use client';

import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/store';
import { useGlobalTTS } from '@/contexts/GlobalTTSContext';
import { audioContextManager } from '@/utils/audioContextManager';
import { useState } from 'react';
import { 
  X, Settings, LogOut, User, Home, PlusCircle, BookOpen, 
  ChevronRight, Film, Trash2, Shield, FileText, Edit, Bug
} from 'lucide-react';

interface StoryActions {
  onChapters?: () => void;
  onAddCharacter?: () => void;
  onViewAllCharacters?: () => void;
  onDirectorMode?: () => void;
  onDeleteMode?: () => void;
  onExportStory?: () => void;
  onEditStorySettings?: () => void;
  directorModeActive?: boolean;
  deleteModeActive?: boolean;
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
  const { currentSceneId, isPlaying, isGenerating, error, debugLogs } = useGlobalTTS();
  const [showDebug, setShowDebug] = useState(false);
  
  // Only show debug option on mobile
  const isMobile = typeof window !== 'undefined' && /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);

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

              {/* Add Character */}
              {storyActions.onAddCharacter && (
                <button
                  onClick={() => {
                    onClose();
                    storyActions.onAddCharacter?.();
                  }}
                  className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
                >
                  <div className="p-2 bg-white/10 rounded-lg group-hover:bg-white/20 transition-colors">
                    <PlusCircle className="w-5 h-5 theme-accent-primary" />
                  </div>
                  <div className="flex-1">
                    <div className="font-medium text-white">Add Character</div>
                    <div className="text-xs text-gray-400">Quick add</div>
                  </div>
                </button>
              )}

              {/* Director Mode */}
              {storyActions.onDirectorMode && (
                <button
                  onClick={() => {
                    onClose();
                    storyActions.onDirectorMode?.();
                  }}
                  className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
                >
                  <div className={`p-2 rounded-lg transition-colors ${
                    storyActions.directorModeActive 
                      ? 'bg-pink-600/20 group-hover:bg-pink-600/30' 
                      : 'bg-white/10 group-hover:bg-white/20'
                  }`}>
                    <Film className={`w-5 h-5 ${storyActions.directorModeActive ? 'text-pink-400' : 'theme-accent-primary'}`} />
                  </div>
                  <div className="flex-1">
                    <div className="font-medium text-white">Director Mode</div>
                    <div className={`text-xs ${storyActions.directorModeActive ? 'text-pink-400' : 'text-gray-400'}`}>
                      {storyActions.directorModeActive ? 'Control scene details' : 'Direct what happens'}
                    </div>
                  </div>
                  <div className={`px-2 py-1 rounded text-xs font-medium ${
                    storyActions.directorModeActive 
                      ? 'bg-pink-600/20 text-pink-400' 
                      : 'bg-gray-600/20 text-gray-400'
                  }`}>
                    {storyActions.directorModeActive ? 'ON' : 'OFF'}
                  </div>
                </button>
              )}

              {/* Delete Mode */}
              {storyActions.onDeleteMode && (
                <button
                  onClick={() => {
                    onClose();
                    storyActions.onDeleteMode?.();
                  }}
                  className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
                >
                  <div className={`p-2 rounded-lg transition-colors ${
                    storyActions.deleteModeActive 
                      ? 'bg-red-600/20 group-hover:bg-red-600/30' 
                      : 'bg-white/10 group-hover:bg-white/20'
                  }`}>
                    <Trash2 className={`w-5 h-5 ${storyActions.deleteModeActive ? 'text-red-400' : 'theme-accent-primary'}`} />
                  </div>
                  <div className="flex-1">
                    <div className="font-medium text-white">Delete Mode</div>
                    <div className={`text-xs ${storyActions.deleteModeActive ? 'text-red-400' : 'text-gray-400'}`}>
                      {storyActions.deleteModeActive ? 'Select scenes to delete' : 'Remove scenes'}
                    </div>
                  </div>
                  <div className={`px-2 py-1 rounded text-xs font-medium ${
                    storyActions.deleteModeActive 
                      ? 'bg-red-600/20 text-red-400' 
                      : 'bg-gray-600/20 text-gray-400'
                  }`}>
                    {storyActions.deleteModeActive ? 'ON' : 'OFF'}
                  </div>
                </button>
              )}

              {/* Export Story */}
              {storyActions.onExportStory && (
                <button
                  onClick={() => {
                    onClose();
                    storyActions.onExportStory?.();
                  }}
                  className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
                >
                  <div className="p-2 bg-white/10 rounded-lg group-hover:bg-white/20 transition-colors">
                    <FileText className="w-5 h-5 theme-accent-primary" />
                  </div>
                  <div className="flex-1">
                    <div className="font-medium text-white">Export Story</div>
                    <div className="text-xs text-gray-400">Download as text</div>
                  </div>
                </button>
              )}
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
                    
                    {/* Status Info */}
                    <div className="mb-3 space-y-1 text-[11px]">
                      <div className="flex justify-between">
                        <span className="text-gray-400">Scene:</span>
                        <span className="font-mono text-white">{currentSceneId || 'None'}</span>
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
                      {typeof window !== 'undefined' && (
                        <div className="flex justify-between">
                          <span className="text-gray-400">AudioContext:</span>
                          <span className="text-white font-mono">{audioContextManager.getState()}</span>
                        </div>
                      )}
                    </div>
                    
                    {/* Error Display */}
                    {error && (
                      <div className="mb-3 p-2 bg-red-500/20 border border-red-500/50 rounded text-[11px]">
                        <div className="font-semibold text-red-400 mb-1">Error:</div>
                        <div className="text-red-300">{error}</div>
                      </div>
                    )}
                    
                    {/* Debug Log */}
                    <div className="border-t border-gray-700 pt-3">
                      <div className="font-semibold mb-2 text-[11px] text-gray-300">Recent Activity:</div>
                      <div className="space-y-1 max-h-40 overflow-y-auto">
                        {debugLogs && debugLogs.length > 0 ? (
                          debugLogs.map((log, i) => (
                            <div key={i} className="text-[10px] font-mono text-gray-300 leading-relaxed">
                              {log}
                            </div>
                          ))
                        ) : (
                          <div className="text-[10px] text-gray-500 italic">No activity yet...</div>
                        )}
                      </div>
                    </div>
                    
                    {/* Device Info */}
                    {typeof window !== 'undefined' && (
                      <div className="mt-3 pt-3 border-t border-gray-700 text-[10px] text-gray-500">
                        <div>Device: {/iPhone|iPad|iPod/i.test(navigator.userAgent) ? 'iOS' : 
                                      /Android/i.test(navigator.userAgent) ? 'Android' : 'Desktop'}</div>
                        <div>Screen: {window.innerWidth}×{window.innerHeight}</div>
                      </div>
                    )}
                    
                    {/* Test Audio Button */}
                    <div className="mt-3 pt-3 border-t border-gray-700">
                      <button
                        onClick={() => audioContextManager.testAudio()}
                        className="w-full bg-yellow-600 hover:bg-yellow-700 text-white text-xs py-2 px-3 rounded transition-colors"
                      >
                        🔊 Test Audio (Beep)
                      </button>
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

