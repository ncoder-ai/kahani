'use client';

import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/store';
import { 
  X, Settings, LogOut, User, Home, PlusCircle, BookOpen, 
  ChevronRight, Film, Trash2, Shield, FileText
} from 'lucide-react';

interface StoryActions {
  onChapters?: () => void;
  onAddCharacter?: () => void;
  onViewAllCharacters?: () => void;
  onDirectorMode?: () => void;
  onLorebook?: () => void;
  onDeleteMode?: () => void;
  onExportStory?: () => void;
  directorModeActive?: boolean;
  lorebookActive?: boolean;
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
      
      {/* Menu Modal - Bottom Left */}
      <div className="fixed left-4 bottom-20 z-50 w-80 max-w-[calc(100vw-2rem)] theme-card border border-gray-700 rounded-lg shadow-2xl overflow-hidden">
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

              {/* Lorebook */}
              {storyActions.onLorebook && (
                <button
                  onClick={() => {
                    onClose();
                    storyActions.onLorebook?.();
                  }}
                  className="w-full flex items-center gap-3 p-3 hover:bg-white/10 rounded-lg transition-colors text-left group"
                >
                  <div className={`p-2 rounded-lg transition-colors ${
                    storyActions.lorebookActive 
                      ? 'bg-yellow-600/20 group-hover:bg-yellow-600/30' 
                      : 'bg-white/10 group-hover:bg-white/20'
                  }`}>
                    <BookOpen className={`w-5 h-5 ${storyActions.lorebookActive ? 'text-yellow-400' : 'theme-accent-primary'}`} />
                  </div>
                  <div className="flex-1">
                    <div className="font-medium text-white">Lorebook</div>
                    <div className={`text-xs ${storyActions.lorebookActive ? 'text-yellow-400' : 'text-gray-400'}`}>
                      {storyActions.lorebookActive ? 'Managing lore items' : 'Manage world & characters'}
                    </div>
                  </div>
                  <ChevronRight className="w-5 h-5 text-gray-500" />
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

