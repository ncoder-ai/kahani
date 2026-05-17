/**
 * Admin API module
 *
 * Handles administrative operations.
 */

import { BaseApiClient } from './base';

export class AdminApi extends BaseApiClient {
  /**
   * Get list of users (admin only)
   */
  async getUsers(skip = 0, limit = 50): Promise<{
    users: Array<{
      id: number;
      email: string;
      username: string;
      display_name?: string;
      role: string;
      is_approved: boolean;
      allow_nsfw: boolean;
      created_at: string;
    }>;
    total: number;
  }> {
    return this.request(`/api/admin/users?skip=${skip}&limit=${limit}`);
  }

  /**
   * Update user role
   */
  async updateUserRole(
    userId: number,
    role: string
  ): Promise<{ message: string }> {
    return this.request(`/api/admin/users/${userId}/role`, {
      method: 'PUT',
      body: JSON.stringify({ role }),
    });
  }

  /**
   * Approve or reject a user
   */
  async updateUserApproval(
    userId: number,
    isApproved: boolean
  ): Promise<{ message: string }> {
    return this.request(`/api/admin/users/${userId}/approval`, {
      method: 'PUT',
      body: JSON.stringify({ is_approved: isApproved }),
    });
  }

  /**
   * Update user NSFW permission
   */
  async updateUserNsfw(
    userId: number,
    allowNsfw: boolean
  ): Promise<{ message: string }> {
    return this.request(`/api/admin/users/${userId}/nsfw`, {
      method: 'PUT',
      body: JSON.stringify({ allow_nsfw: allowNsfw }),
    });
  }

  /**
   * Get system settings
   */
  async getSystemSettings(): Promise<{
    settings: Record<string, any>;
  }> {
    return this.request('/api/admin/settings');
  }

  /**
   * Update system settings
   */
  async updateSystemSettings(
    settings: Record<string, any>
  ): Promise<{ message: string }> {
    return this.request('/api/admin/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    });
  }
}
