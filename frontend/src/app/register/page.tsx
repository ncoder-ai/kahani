'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore } from '@/store';
import apiClient from '@/lib/api';
import { applyTheme } from '@/lib/themes';

export default function RegisterPage() {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
    displayName: '',
  });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  
  // Refs to handle mobile autofill race condition
  const formRef = useRef<HTMLFormElement>(null);
  
  const router = useRouter();
  const { login } = useAuthStore();

  useEffect(() => {
    // Apply default theme for register page
    applyTheme('pure-dark');
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
    
    // Clear password error when user types in password fields
    if (e.target.name === 'password' || e.target.name === 'confirmPassword') {
      setPasswordError('');
    }
  };

  const validatePasswords = () => {
    if (formData.password !== formData.confirmPassword) {
      setPasswordError('Passwords do not match');
      return false;
    }
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    
    // CRITICAL: Read values directly from form to handle mobile autofill
    // On iOS/mobile browsers, password managers may autofill without triggering onChange
    const form = formRef.current;
    const actualFormData = {
      username: (form?.querySelector('#username') as HTMLInputElement)?.value || formData.username,
      email: (form?.querySelector('#email') as HTMLInputElement)?.value || formData.email,
      password: (form?.querySelector('#password') as HTMLInputElement)?.value || formData.password,
      confirmPassword: (form?.querySelector('#confirmPassword') as HTMLInputElement)?.value || formData.confirmPassword,
      displayName: (form?.querySelector('#displayName') as HTMLInputElement)?.value || formData.displayName,
    };
    
    // Sync React state with actual values
    setFormData(actualFormData);
    
    // Validate required fields
    if (!actualFormData.email || !actualFormData.password || !actualFormData.username) {
      setError('Please fill in all required fields.');
      setIsLoading(false);
      return;
    }
    
    // Validate passwords before submitting
    if (actualFormData.password !== actualFormData.confirmPassword) {
      setPasswordError('Passwords do not match');
      setIsLoading(false);
      return;
    }

    try {
      const response = await apiClient.register({
        username: actualFormData.username,
        email: actualFormData.email,
        password: actualFormData.password,
        display_name: actualFormData.displayName,
      });
      
      // Update auth store with user and token
      login(response.user, response.access_token);
      
      // Check if user needs approval
      if (response.user.is_approved || response.user.is_admin) {
        // First user (admin) or pre-approved user - go to dashboard
        router.push('/dashboard');
      } else {
        // User needs admin approval - show pending screen
        router.push('/pending-approval');
      }
    } catch (err) {
      console.error('Registration error:', err);
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Registration failed. Please try again.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen theme-bg-primary flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center mb-8">
        <img src="/kahani-logo.jpg" alt="Make My Saga" className="h-48 w-48 md:h-44 md:w-44 object-contain mx-auto mb-4" />
      </div>

      {/* Register Form */}
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white/10 backdrop-blur-md border border-white/20 py-8 px-6 shadow-2xl rounded-2xl">
          <h2 className="text-center text-2xl font-bold text-white mb-8">
            Create Your Account
          </h2>

          {error && (
            <div className="mb-6 bg-red-500/20 border border-red-400/30 text-red-100 px-4 py-3 rounded-lg">
              {error}
            </div>
          )}

          <form ref={formRef} onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="displayName" className="block text-sm font-medium text-white/80 mb-2">
                Display Name
              </label>
              <input
                id="displayName"
                name="displayName"
                type="text"
                autoComplete="name"
                required
                value={formData.displayName}
                onChange={handleChange}
                className="w-full px-4 py-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:border-transparent"
                placeholder="Your display name"
              />
            </div>

            <div>
              <label htmlFor="username" className="block text-sm font-medium text-white/80 mb-2">
                Username
              </label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                required
                value={formData.username}
                onChange={handleChange}
                className="w-full px-4 py-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:border-transparent"
                placeholder="Choose a username"
              />
            </div>

            <div>
              <label htmlFor="email" className="block text-sm font-medium text-white/80 mb-2">
                Email address
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={formData.email}
                onChange={handleChange}
                className="w-full px-4 py-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:border-transparent"
                placeholder="Enter your email"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-white/80 mb-2">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="new-password"
                required
                value={formData.password}
                onChange={handleChange}
                className="w-full px-4 py-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:border-transparent"
                placeholder="Create a password"
              />
            </div>

            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-white/80 mb-2">
                Confirm Password
              </label>
              <input
                id="confirmPassword"
                name="confirmPassword"
                type="password"
                autoComplete="new-password"
                required
                value={formData.confirmPassword}
                onChange={handleChange}
                className={`w-full px-4 py-3 bg-white/10 border ${
                  passwordError ? 'border-red-400/50' : 'border-white/30'
                } rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:border-transparent`}
                placeholder="Confirm your password"
              />
              {passwordError && (
                <div className="mt-1 text-red-300 text-sm">{passwordError}</div>
              )}
            </div>

            <div className="pt-4">
              <button
                type="submit"
                disabled={isLoading}
                className={`w-full py-3 px-4 rounded-lg font-semibold transition-all duration-200 ${
                  isLoading
                    ? 'bg-white/20 text-white/50 cursor-not-allowed'
                    : 'theme-btn-primary transform hover:scale-105'
                }`}
              >
                {isLoading ? (
                  <div className="flex items-center justify-center space-x-2">
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                    <span>Creating account...</span>
                  </div>
                ) : (
                  'Create Account'
                )}
              </button>
            </div>
          </form>

          {/* Divider */}
          <div className="mt-8">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-white/30" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-3 bg-white/10 text-white/80 rounded">Already have an account?</span>
              </div>
            </div>

            <div className="mt-6">
              <Link
                href="/login"
                className="w-full flex justify-center py-3 px-4 border border-white/30 rounded-lg text-white hover:bg-white/10 transition-colors font-medium"
              >
                Sign In Instead
              </Link>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center">
          <p className="text-white/60 text-sm">
            Join thousands of creators telling amazing stories
          </p>
        </div>
      </div>
    </div>
  );
}
