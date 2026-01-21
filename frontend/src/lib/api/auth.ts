/**
 * Authentication API module
 *
 * Handles user authentication, registration, and token management.
 */

import { BaseApiClient } from './base';

export interface LoginResponse {
  access_token: string;
  token_type: string;
  refresh_token?: string;
  user: {
    id: number;
    email: string;
    username: string;
    display_name?: string;
    role: string;
    is_approved: boolean;
    allow_nsfw: boolean;
  };
}

export interface RegisterData {
  email: string;
  username: string;
  password: string;
  display_name?: string;
}

export interface RefreshTokenResponse {
  access_token: string;
  token_type: string;
}

export interface User {
  id: number;
  email: string;
  username: string;
  display_name?: string;
  role: string;
  is_approved: boolean;
  allow_nsfw: boolean;
  created_at: string;
}

export class AuthApi extends BaseApiClient {
  /**
   * Login with email or username and password
   */
  async login(identifier: string, password: string, rememberMe: boolean = false): Promise<LoginResponse> {
    return this.request<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ identifier, password, remember_me: rememberMe }),
    });
  }

  /**
   * Refresh the access token using a refresh token
   */
  async refreshToken(refreshToken: string): Promise<RefreshTokenResponse> {
    return this.request<RefreshTokenResponse>('/api/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  }

  /**
   * Register a new user account
   */
  async register(data: RegisterData): Promise<LoginResponse> {
    return this.request<LoginResponse>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /**
   * Get the currently authenticated user
   */
  async getCurrentUser(): Promise<User> {
    return this.request<User>('/api/auth/me');
  }
}
