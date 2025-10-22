'use client';

import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/store';
import { X, Settings, LogOut, User, Home, Volume2, VolumeX } from 'lucide-react';
import { useAutoplayPermission } from '@/hooks/useAutoplayPermission';

interface GlobalMenuProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function GlobalMenu({ isOpen, onClose }: GlobalMenuProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, logout } = useAuthStore();
  const { isEnabled, toggleAutoplay } = useAutoplayPermission();

  if (!isOpen) return null;

  const handleLogout = () => {
    onClose();
    logout();
    router.push('/login');
  };

  const handleSettings = () => {
    onClose();
    router.push('/settings');
  };

  const handleDashboard = () => {
    onClose();
    router.push('/dashboard');
  };

  const handleCharacters = () => {
    onClose();
    router.push('/characters');
  };

  return (
    <>
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[60]"
        onClick={onClose}
      />
      
      {/* Menu Modal - Top Right */}
      <div className="fixed right-4 top-16 z-[70] w-80 max-w-[calc(100vw-2rem)] bg-slate-900 border border-slate-700 rounded-lg shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700 bg-gradient-to-r from-purple-900/50 to-pink-900/50">
          <div>
            <h2 className="text-lg font-semibold text-white">Menu</h2>
            {user && <p className="text-xs text-white/60">{user.display_name}</p>}
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-slate-700 rounded transition-colors"
          >
            <X className="w-5 h-5 text-white" />
          </button>
        </div>
        
        {/* Menu Items */}
        <div className="p-2 max-h-[calc(100vh-8rem)] overflow-y-auto">
          {/* Dashboard */}
          {pathname !== '/dashboard' && (
            <button
              onClick={handleDashboard}
              className="w-full flex items-center gap-3 p-3 hover:bg-slate-800 rounded-lg transition-colors text-left group"
            >
              <div className="p-2 bg-indigo-600/20 rounded-lg group-hover:bg-indigo-600/30 transition-colors">
                <Home className="w-5 h-5 text-indigo-400" />
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
            className="w-full flex items-center gap-3 p-3 hover:bg-slate-800 rounded-lg transition-colors text-left group"
          >
            <div className="p-2 bg-blue-600/20 rounded-lg group-hover:bg-blue-600/30 transition-colors">
              <User className="w-5 h-5 text-blue-400" />
            </div>
            <div className="flex-1">
              <div className="font-medium text-white">Characters</div>
              <div className="text-xs text-gray-400">Manage character library</div>
            </div>
          </button>

          {/* Divider */}
          <div className="my-2 border-t border-slate-700"></div>

          {/* Audio Toggle */}
          <button
            onClick={() => {
              toggleAutoplay();
            }}
            className="w-full flex items-center gap-3 p-3 hover:bg-slate-800 rounded-lg transition-colors text-left group"
          >
            <div className={`p-2 rounded-lg transition-colors ${
              isEnabled 
                ? 'bg-green-600/20 group-hover:bg-green-600/30' 
                : 'bg-gray-600/20 group-hover:bg-gray-600/30'
            }`}>
              {isEnabled ? (
                <Volume2 className="w-5 h-5 text-green-400" />
              ) : (
                <VolumeX className="w-5 h-5 text-gray-400" />
              )}
            </div>
            <div className="flex-1">
              <div className="font-medium text-white">Audio Autoplay</div>
              <div className={`text-xs ${isEnabled ? 'text-green-400' : 'text-gray-400'}`}>
                {isEnabled ? 'Audio enabled' : 'Audio disabled'}
              </div>
            </div>
            <div className={`px-2 py-1 rounded text-xs font-medium ${
              isEnabled 
                ? 'bg-green-600/20 text-green-400' 
                : 'bg-gray-600/20 text-gray-400'
            }`}>
              {isEnabled ? 'ON' : 'OFF'}
            </div>
          </button>

          {/* Settings */}
          <button
            onClick={handleSettings}
            className="w-full flex items-center gap-3 p-3 hover:bg-slate-800 rounded-lg transition-colors text-left group"
          >
            <div className="p-2 bg-purple-600/20 rounded-lg group-hover:bg-purple-600/30 transition-colors">
              <Settings className="w-5 h-5 text-purple-400" />
            </div>
            <div className="flex-1">
              <div className="font-medium text-white">Settings</div>
              <div className="text-xs text-gray-400">TTS, LLM & app preferences</div>
            </div>
          </button>

          {/* Divider */}
          <div className="my-2 border-t border-slate-700"></div>
          
          {/* Profile */}
          <button
            onClick={() => {
              onClose();
              // Add profile page route when ready
            }}
            disabled
            className="w-full flex items-center gap-3 p-3 opacity-50 cursor-not-allowed rounded-lg text-left group"
          >
            <div className="p-2 bg-blue-600/20 rounded-lg">
              <User className="w-5 h-5 text-blue-400" />
            </div>
            <div className="flex-1">
              <div className="font-medium text-white">Profile</div>
              <div className="text-xs text-gray-400">{user?.email || 'Coming soon'}</div>
            </div>
          </button>
          
          {/* Logout */}
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 p-3 hover:bg-slate-800 rounded-lg transition-colors text-left group"
          >
            <div className="p-2 bg-red-600/20 rounded-lg group-hover:bg-red-600/30 transition-colors">
              <LogOut className="w-5 h-5 text-red-400" />
            </div>
            <div className="flex-1">
              <div className="font-medium text-white">Logout</div>
              <div className="text-xs text-gray-400">Sign out of your account</div>
            </div>
          </button>
        </div>
      </div>
    </>
  );
}

