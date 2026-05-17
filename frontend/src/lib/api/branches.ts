/**
 * Branches API module
 *
 * Handles story branching and branch management.
 */

import { BaseApiClient } from './base';
import { Branch } from './types';

export interface BranchCreateData {
  name: string;
  description?: string;
  fork_from_scene_sequence: number;
}

export interface BranchUpdateData {
  name?: string;
  description?: string;
}

export interface BranchStats {
  branch_id: number;
  branch_name: string;
  total_scenes: number;
  total_chapters: number;
  fork_point: number | null;
  created_at: string;
}

export class BranchesApi extends BaseApiClient {
  /**
   * Get all branches for a story
   */
  async getBranches(storyId: number): Promise<{
    branches: Branch[];
    current_branch_id: number | null;
  }> {
    return this.request(`/api/stories/${storyId}/branches`);
  }

  /**
   * Get the active branch for a story
   */
  async getActiveBranch(storyId: number): Promise<{
    branch: Branch | null;
    total_branches: number;
  }> {
    return this.request(`/api/stories/${storyId}/branches/active`);
  }

  /**
   * Create a new branch (fork)
   */
  async createBranch(
    storyId: number,
    data: BranchCreateData
  ): Promise<{
    branch: Branch;
    message: string;
  }> {
    return this.request(`/api/stories/${storyId}/branches`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /**
   * Activate a branch (switch to it)
   */
  async activateBranch(
    storyId: number,
    branchId: number
  ): Promise<{
    branch: Branch;
    message: string;
  }> {
    return this.request(`/api/stories/${storyId}/branches/${branchId}/activate`, {
      method: 'POST',
    });
  }

  /**
   * Update branch details
   */
  async updateBranch(
    storyId: number,
    branchId: number,
    data: BranchUpdateData
  ): Promise<{
    branch: Branch;
    message: string;
  }> {
    return this.request(`/api/stories/${storyId}/branches/${branchId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  /**
   * Delete a branch
   */
  async deleteBranch(
    storyId: number,
    branchId: number
  ): Promise<{ message: string }> {
    return this.request(`/api/stories/${storyId}/branches/${branchId}`, {
      method: 'DELETE',
    });
  }

  /**
   * Get statistics for a branch
   */
  async getBranchStats(storyId: number, branchId: number): Promise<BranchStats> {
    return this.request(`/api/stories/${storyId}/branches/${branchId}/stats`);
  }
}
