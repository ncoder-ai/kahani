'use client';

import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store';
import { useEffect } from 'react';

export default function PendingApprovalPage() {
  const { user, logout } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    // If user is approved, redirect to dashboard
    if (user?.is_approved) {
      router.push('/dashboard');
    }
    // If not logged in, redirect to login
    if (!user) {
      router.push('/login');
    }
  }, [user, router]);

  const handleLogout = () => {
    logout();
    router.push('/login');
  };

  return (
    <div className="min-h-screen theme-bg-primary flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        {/* Card */}
        <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl p-8 shadow-2xl">
          {/* Icon */}
          <div className="flex justify-center mb-6">
            <div className="w-20 h-20 bg-yellow-500/20 rounded-full flex items-center justify-center">
              <svg 
                className="w-10 h-10 text-yellow-400" 
                fill="none" 
                stroke="currentColor" 
                viewBox="0 0 24 24"
              >
                <path 
                  strokeLinecap="round" 
                  strokeLinejoin="round" 
                  strokeWidth={2} 
                  d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" 
                />
              </svg>
            </div>
          </div>

          {/* Title */}
          <h1 className="text-2xl font-bold text-white text-center mb-4">
            Account Pending Approval
          </h1>

          {/* Message */}
          <div className="space-y-4 text-center">
            <p className="text-white/80 text-base">
              Thank you for registering, <span className="font-semibold text-white">{user?.display_name || user?.username}</span>!
            </p>
            
            <p className="text-white/70 text-sm">
              Your account is currently pending approval from an administrator. 
              You'll receive access to the platform once your account has been reviewed and approved.
            </p>

            <div className="bg-blue-500/20 border border-blue-400/30 rounded-lg p-4 mt-6">
              <p className="text-blue-100 text-sm">
                💡 <strong>What happens next?</strong>
                <br />
                An administrator will review your account shortly. Once approved, you'll be able to access all features of Make My Saga.
              </p>
            </div>
          </div>

          {/* Actions */}
          <div className="mt-8 space-y-3">
            <button
              onClick={handleLogout}
              className="w-full py-3 px-4 bg-white/10 hover:bg-white/20 border border-white/30 text-white rounded-lg font-medium transition-colors"
            >
              Sign Out
            </button>
            
            <p className="text-white/50 text-xs text-center">
              If you have any questions, please contact your administrator.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-6 text-center">
          <p className="text-white/40 text-sm">
            <span className="inline-flex items-center gap-1"><img src="/kahani-logo.jpg" alt="" className="h-4 w-4 object-contain inline" /> Make My Saga - Interactive Storytelling Platform</span>
          </p>
        </div>
      </div>
    </div>
  );
}

