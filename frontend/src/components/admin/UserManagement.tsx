'use client';

import { useState, useEffect } from 'react';
import { API_BASE_URL } from '@/lib/api';
import { useAuthStore } from '@/store';

interface User {
  id: number;
  username: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  is_approved: boolean;
  allow_nsfw: boolean;
  can_change_llm_provider: boolean;
  can_change_tts_settings: boolean;
  can_use_stt: boolean;
  can_use_image_generation: boolean;
  can_export_stories: boolean;
  can_import_stories: boolean;
  max_stories: number | null;
  max_images_per_story: number | null;
  max_stt_minutes_per_month: number | null;
  created_at: string;
  approved_at?: string;
}

interface EditingUser extends User {
  // Add any additional fields needed for editing
}

export default function UserManagement() {
  const { token } = useAuthStore();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filter, setFilter] = useState<'all' | 'approved' | 'pending' | 'admins'>('all');
  const [editingUser, setEditingUser] = useState<EditingUser | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/api/admin/users`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) throw new Error('Failed to fetch users');
      
      const data = await response.json();
      const fetchedUsers = data.users || [];
      setUsers(fetchedUsers);
      
      // Count pending users
      const pending = fetchedUsers.filter((u: User) => !u.is_approved).length;
      setPendingCount(pending);
    } catch (error) {
      console.error('Error fetching users:', error);
      showMessage('error', 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const approveUser = async (userId: number) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/admin/users/${userId}/approve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) throw new Error('Failed to approve user');
      
      showMessage('success', 'User approved successfully');
      fetchUsers();
    } catch (error) {
      console.error('Error approving user:', error);
      showMessage('error', 'Failed to approve user');
    }
  };

  const revokeApproval = async (userId: number) => {
    if (!confirm('Are you sure you want to revoke approval for this user?')) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/admin/users/${userId}/revoke`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) throw new Error('Failed to revoke approval');
      
      showMessage('success', 'Approval revoked successfully');
      fetchUsers();
    } catch (error) {
      console.error('Error revoking approval:', error);
      showMessage('error', 'Failed to revoke approval');
    }
  };

  const deleteUser = async (userId: number) => {
    if (!confirm('Are you sure you want to delete this user? This action cannot be undone.')) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/admin/users/${userId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to delete user');
      }
      
      showMessage('success', 'User deleted successfully');
      fetchUsers();
    } catch (error) {
      console.error('Error deleting user:', error);
      showMessage('error', error instanceof Error ? error.message : 'Failed to delete user');
    }
  };

  const openEditModal = (user: User) => {
    setEditingUser({ ...user });
    setShowEditModal(true);
  };

  const saveUserEdits = async () => {
    if (!editingUser) return;

    try {
      const response = await fetch(`${API_BASE_URL}/api/admin/users/${editingUser.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          is_admin: editingUser.is_admin,
          is_approved: editingUser.is_approved,
          allow_nsfw: editingUser.allow_nsfw,
          can_change_llm_provider: editingUser.can_change_llm_provider,
          can_change_tts_settings: editingUser.can_change_tts_settings,
          can_use_stt: editingUser.can_use_stt,
          can_use_image_generation: editingUser.can_use_image_generation,
          can_export_stories: editingUser.can_export_stories,
          can_import_stories: editingUser.can_import_stories,
          max_stories: editingUser.max_stories,
          max_images_per_story: editingUser.max_images_per_story,
          max_stt_minutes_per_month: editingUser.max_stt_minutes_per_month,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to update user');
      }
      
      showMessage('success', 'User updated successfully');
      setShowEditModal(false);
      fetchUsers();
    } catch (error) {
      console.error('Error updating user:', error);
      showMessage('error', error instanceof Error ? error.message : 'Failed to update user');
    }
  };

  // Filter and search users
  const filteredUsers = users.filter((user) => {
    const matchesSearch = 
      user.username.toLowerCase().includes(searchTerm.toLowerCase()) ||
      user.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
      user.display_name.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesFilter = 
      filter === 'all' ||
      (filter === 'approved' && user.is_approved) ||
      (filter === 'pending' && !user.is_approved) ||
      (filter === 'admins' && user.is_admin);

    return matchesSearch && matchesFilter;
  });

  return (
    <div className="space-y-6">
      {/* Pending Users Alert */}
      {pendingCount > 0 && (
        <div className="bg-yellow-500/20 border border-yellow-400/30 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="text-2xl">⚠️</div>
              <div>
                <div className="font-semibold text-yellow-100">
                  {pendingCount} user{pendingCount !== 1 ? 's' : ''} waiting for approval
                </div>
                <div className="text-sm text-yellow-200/80">
                  New users need your approval before they can access the platform
                </div>
              </div>
            </div>
            <button
              onClick={() => setFilter('pending')}
              className="px-4 py-2 rounded-lg bg-yellow-500 hover:bg-yellow-600 text-black font-medium transition-colors"
            >
              View Pending Users
            </button>
          </div>
        </div>
      )}

      {/* Message */}
      {message && (
        <div className={`p-4 rounded-lg border ${
          message.type === 'success'
            ? 'bg-green-500/20 border-green-400/30 text-green-100'
            : 'bg-red-500/20 border-red-400/30 text-red-100'
        }`}>
          {message.text}
        </div>
      )}

      {/* Filters and Search */}
      <div className="flex flex-col md:flex-row gap-4">
        <div className="flex-1">
          <input
            type="text"
            placeholder="Search users..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-white/10 border border-white/30 rounded-lg px-4 py-2 text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>
        <div className="flex gap-2">
          {(['all', 'approved', 'pending', 'admins'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-2 rounded-lg font-medium transition-colors capitalize relative ${
                filter === f
                  ? 'bg-purple-500 text-white'
                  : 'bg-white/10 text-white/70 hover:bg-white/20'
              }`}
            >
              {f}
              {f === 'pending' && pendingCount > 0 && (
                <span className="ml-2 inline-flex items-center justify-center w-5 h-5 text-xs font-bold text-black bg-yellow-400 rounded-full">
                  {pendingCount}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Users Table */}
      {loading ? (
        <div className="text-center py-12">
          <div className="w-12 h-12 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-white/70">Loading users...</p>
        </div>
      ) : filteredUsers.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-white/70">No users found</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/20">
                <th className="text-left py-3 px-4 text-white/80 font-medium">User</th>
                <th className="text-left py-3 px-4 text-white/80 font-medium">Status</th>
                <th className="text-left py-3 px-4 text-white/80 font-medium">Permissions</th>
                <th className="text-left py-3 px-4 text-white/80 font-medium">Joined</th>
                <th className="text-right py-3 px-4 text-white/80 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((user) => (
                <tr key={user.id} className="border-b border-white/10 hover:bg-white/5">
                  <td className="py-4 px-4">
                    <div>
                      <div className="font-medium text-white">{user.display_name}</div>
                      <div className="text-sm text-white/60">@{user.username}</div>
                      <div className="text-xs text-white/50">{user.email}</div>
                    </div>
                  </td>
                  <td className="py-4 px-4">
                    <div className="flex flex-col gap-1">
                      {user.is_admin && (
                        <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-purple-500/20 text-purple-200 border border-purple-400/30 w-fit">
                          👑 Admin
                        </span>
                      )}
                      {user.is_approved ? (
                        <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-green-500/20 text-green-200 border border-green-400/30 w-fit">
                          ✓ Approved
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-yellow-500/20 text-yellow-200 border border-yellow-400/30 w-fit">
                          ⏳ Pending
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-4 px-4">
                    <div className="flex flex-wrap gap-1 max-w-xs">
                      {user.allow_nsfw && (
                        <span className="text-xs px-2 py-0.5 rounded bg-red-500/20 text-red-200 border border-red-400/30">NSFW</span>
                      )}
                      {user.can_change_llm_provider && (
                        <span className="text-xs px-2 py-0.5 rounded bg-blue-500/20 text-blue-200 border border-blue-400/30">LLM</span>
                      )}
                      {user.can_change_tts_settings && (
                        <span className="text-xs px-2 py-0.5 rounded bg-green-500/20 text-green-200 border border-green-400/30">TTS</span>
                      )}
                      {user.can_use_stt && (
                        <span className="text-xs px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-200 border border-cyan-400/30">STT</span>
                      )}
                      {user.can_use_image_generation && (
                        <span className="text-xs px-2 py-0.5 rounded bg-purple-500/20 text-purple-200 border border-purple-400/30">IMG</span>
                      )}
                      {user.can_export_stories && (
                        <span className="text-xs px-2 py-0.5 rounded bg-amber-500/20 text-amber-200 border border-amber-400/30">Export</span>
                      )}
                      {user.can_import_stories && (
                        <span className="text-xs px-2 py-0.5 rounded bg-amber-500/20 text-amber-200 border border-amber-400/30">Import</span>
                      )}
                      {user.max_stories && (
                        <span className="text-xs px-2 py-0.5 rounded bg-orange-500/20 text-orange-200 border border-orange-400/30">
                          {user.max_stories} stories max
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-4 px-4">
                    <div className="text-sm text-white/70">
                      {new Date(user.created_at).toLocaleDateString()}
                    </div>
                  </td>
                  <td className="py-4 px-4">
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => openEditModal(user)}
                        className="px-3 py-1 rounded bg-blue-500/20 text-blue-200 hover:bg-blue-500/30 transition-colors text-sm"
                      >
                        Edit
                      </button>
                      {!user.is_approved ? (
                        <button
                          onClick={() => approveUser(user.id)}
                          className="px-3 py-1 rounded bg-green-500/20 text-green-200 hover:bg-green-500/30 transition-colors text-sm"
                        >
                          Approve
                        </button>
                      ) : (
                        <button
                          onClick={() => revokeApproval(user.id)}
                          className="px-3 py-1 rounded bg-yellow-500/20 text-yellow-200 hover:bg-yellow-500/30 transition-colors text-sm"
                        >
                          Revoke
                        </button>
                      )}
                      <button
                        onClick={() => deleteUser(user.id)}
                        className="px-3 py-1 rounded bg-red-500/20 text-red-200 hover:bg-red-500/30 transition-colors text-sm"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Edit User Modal */}
      {showEditModal && editingUser && (
        <div 
          className="fixed inset-0 bg-black/70 flex items-center justify-center p-4" 
          style={{ 
            zIndex: 99999,
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0
          }}
        >
          <div className="bg-gray-900 rounded-2xl border border-white/20 p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto relative">
            <h2 className="text-2xl font-bold text-white mb-6">
              Edit User: {editingUser.display_name}
            </h2>

            <div className="space-y-6">
              {/* Core Permissions Section */}
              <div className="pb-4 border-b border-white/20">
                <h3 className="text-lg font-semibold text-white mb-4">Core Permissions</h3>
                
                {/* Admin Status */}
                <div className="mb-4">
                  <label className="flex items-center space-x-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editingUser.is_admin}
                      onChange={(e) => setEditingUser({ ...editingUser, is_admin: e.target.checked })}
                      className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-purple-500 focus:ring-purple-500"
                    />
                    <div>
                      <span className="text-white font-medium">Admin Status</span>
                      <p className="text-white/60 text-sm">Grant administrative privileges (full access)</p>
                    </div>
                  </label>
                </div>

                {/* Approval Status */}
                <div>
                  <label className="flex items-center space-x-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editingUser.is_approved}
                      onChange={(e) => setEditingUser({ ...editingUser, is_approved: e.target.checked })}
                      className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-green-500 focus:ring-green-500"
                    />
                    <div>
                      <span className="text-white font-medium">Approved Status</span>
                      <p className="text-white/60 text-sm">Allow user to access the application</p>
                    </div>
                  </label>
                </div>
              </div>

              {/* Content Permissions Section */}
              <div className="pb-4 border-b border-white/20">
                <h3 className="text-lg font-semibold text-white mb-4">Content Permissions</h3>
                
                {/* NSFW Permission */}
                <div>
                  <label className="flex items-center space-x-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editingUser.allow_nsfw}
                      onChange={(e) => setEditingUser({ ...editingUser, allow_nsfw: e.target.checked })}
                      className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-red-500 focus:ring-red-500"
                    />
                    <div>
                      <span className="text-white font-medium">Allow NSFW Content</span>
                      <p className="text-white/60 text-sm">Enable adult content creation and viewing</p>
                    </div>
                  </label>
                </div>
              </div>

              {/* Feature Permissions Section */}
              <div className="pb-4 border-b border-white/20">
                <h3 className="text-lg font-semibold text-white mb-4">Feature Permissions</h3>
                
                <div className="space-y-3">
                  {/* LLM Provider Permission */}
                  <div>
                    <label className="flex items-center space-x-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editingUser.can_change_llm_provider}
                        onChange={(e) => setEditingUser({ ...editingUser, can_change_llm_provider: e.target.checked })}
                        className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-blue-500 focus:ring-blue-500"
                      />
                      <div>
                        <span className="text-white font-medium">Can Change LLM Provider</span>
                        <p className="text-white/60 text-sm">Allow modification of LLM API settings</p>
                      </div>
                    </label>
                  </div>

                  {/* TTS Settings Permission */}
                  <div>
                    <label className="flex items-center space-x-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editingUser.can_change_tts_settings}
                        onChange={(e) => setEditingUser({ ...editingUser, can_change_tts_settings: e.target.checked })}
                        className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-blue-500 focus:ring-blue-500"
                      />
                      <div>
                        <span className="text-white font-medium">Can Change TTS Settings</span>
                        <p className="text-white/60 text-sm">Allow modification of TTS provider settings</p>
                      </div>
                    </label>
                  </div>

                  {/* STT Permission (Future) */}
                  <div>
                    <label className="flex items-center space-x-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editingUser.can_use_stt}
                        onChange={(e) => setEditingUser({ ...editingUser, can_use_stt: e.target.checked })}
                        className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-blue-500 focus:ring-blue-500"
                      />
                      <div>
                        <span className="text-white font-medium">Can Use Speech-to-Text</span>
                        <p className="text-white/60 text-sm">Enable voice input (future feature)</p>
                      </div>
                    </label>
                  </div>

                  {/* Image Generation Permission (Future) */}
                  <div>
                    <label className="flex items-center space-x-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editingUser.can_use_image_generation}
                        onChange={(e) => setEditingUser({ ...editingUser, can_use_image_generation: e.target.checked })}
                        className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-blue-500 focus:ring-blue-500"
                      />
                      <div>
                        <span className="text-white font-medium">Can Use Image Generation</span>
                        <p className="text-white/60 text-sm">Enable AI image creation (future feature)</p>
                      </div>
                    </label>
                  </div>

                  {/* Export Permission */}
                  <div>
                    <label className="flex items-center space-x-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editingUser.can_export_stories}
                        onChange={(e) => setEditingUser({ ...editingUser, can_export_stories: e.target.checked })}
                        className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-blue-500 focus:ring-blue-500"
                      />
                      <div>
                        <span className="text-white font-medium">Can Export Stories</span>
                        <p className="text-white/60 text-sm">Allow story export functionality (future feature)</p>
                      </div>
                    </label>
                  </div>

                  {/* Import Permission */}
                  <div>
                    <label className="flex items-center space-x-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editingUser.can_import_stories}
                        onChange={(e) => setEditingUser({ ...editingUser, can_import_stories: e.target.checked })}
                        className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-blue-500 focus:ring-blue-500"
                      />
                      <div>
                        <span className="text-white font-medium">Can Import Stories</span>
                        <p className="text-white/60 text-sm">Allow story import functionality (future feature)</p>
                      </div>
                    </label>
                  </div>
                </div>
              </div>

              {/* Resource Limits Section */}
              <div>
                <h3 className="text-lg font-semibold text-white mb-4">Resource Limits</h3>
                
                <div className="space-y-4">
                  {/* Max Stories Limit */}
                  <div>
                    <label className="block text-white font-medium mb-2">Maximum Stories</label>
                    <input
                      type="number"
                      value={editingUser.max_stories || ''}
                      onChange={(e) => setEditingUser({ ...editingUser, max_stories: e.target.value ? parseInt(e.target.value) : null })}
                      placeholder="Unlimited"
                      min="0"
                      className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                    />
                    <p className="text-white/60 text-sm mt-1">Leave empty for unlimited stories</p>
                  </div>

                  {/* Max Images Limit (Future) */}
                  <div>
                    <label className="block text-white font-medium mb-2">Maximum Images per Story</label>
                    <input
                      type="number"
                      value={editingUser.max_images_per_story || ''}
                      onChange={(e) => setEditingUser({ ...editingUser, max_images_per_story: e.target.value ? parseInt(e.target.value) : null })}
                      placeholder="Unlimited"
                      min="0"
                      className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                    />
                    <p className="text-white/60 text-sm mt-1">Limit for AI-generated images (future feature)</p>
                  </div>

                  {/* Max STT Minutes Limit (Future) */}
                  <div>
                    <label className="block text-white font-medium mb-2">Maximum STT Minutes per Month</label>
                    <input
                      type="number"
                      value={editingUser.max_stt_minutes_per_month || ''}
                      onChange={(e) => setEditingUser({ ...editingUser, max_stt_minutes_per_month: e.target.value ? parseInt(e.target.value) : null })}
                      placeholder="Unlimited"
                      min="0"
                      className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                    />
                    <p className="text-white/60 text-sm mt-1">Monthly voice input quota (future feature)</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex justify-end gap-3 mt-6 pt-6 border-t border-white/20">
              <button
                onClick={() => setShowEditModal(false)}
                className="px-6 py-2 rounded-lg bg-white/10 text-white hover:bg-white/20 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={saveUserEdits}
                className="px-6 py-2 rounded-lg bg-gradient-to-r from-purple-500 to-pink-500 text-white hover:from-purple-600 hover:to-pink-600 transition-all"
              >
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

