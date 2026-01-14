'use client';

import { useState, useEffect } from 'react';

export const CHARACTER_ROLES = [
  { id: 'protagonist', name: 'Main Character', icon: '⭐', color: 'from-yellow-400 to-orange-500' },
  { id: 'antagonist', name: 'Antagonist', icon: '⚔️', color: 'from-red-500 to-red-700' },
  { id: 'ally', name: 'Ally/Friend', icon: '🤝', color: 'from-green-400 to-green-600' },
  { id: 'mentor', name: 'Mentor', icon: '🎓', color: 'from-blue-400 to-blue-600' },
  { id: 'love_interest', name: 'Love Interest', icon: '💕', color: 'from-pink-400 to-pink-600' },
  { id: 'comic_relief', name: 'Comic Relief', icon: '😄', color: 'from-purple-400 to-purple-600' },
  { id: 'mysterious', name: 'Mysterious Figure', icon: '🎭', color: 'from-gray-500 to-gray-700' },
  { id: 'other', name: 'Other', icon: '👤', color: 'from-indigo-400 to-indigo-600' }
];

// Check if a role is a custom role (not one of the predefined ones)
export const isCustomRole = (role: string | null | undefined): boolean => {
  if (!role) return false;
  return !CHARACTER_ROLES.some(r => r.id === role);
};

// Get role info, handling custom roles
export const getRoleInfo = (roleId: string | null | undefined) => {
  if (!roleId) return null;
  const predefinedRole = CHARACTER_ROLES.find(r => r.id === roleId);
  if (predefinedRole) return predefinedRole;
  // For custom roles, return a custom display with the "other" styling
  return {
    id: roleId,
    name: roleId, // Use the custom role text as the name
    icon: '👤',
    color: 'from-indigo-400 to-indigo-600'
  };
};

// Parse a role value - returns { selectedRole, customRole }
export const parseRoleValue = (role: string | null | undefined): { selectedRole: string; customRole: string } => {
  if (!role) return { selectedRole: '', customRole: '' };
  if (isCustomRole(role)) {
    return { selectedRole: 'other', customRole: role };
  }
  return { selectedRole: role, customRole: '' };
};

// Get the final role value to save
export const getFinalRoleValue = (selectedRole: string, customRole: string): string => {
  if (selectedRole === 'other' && customRole.trim()) {
    return customRole.trim();
  }
  return selectedRole;
};

interface RoleSelectorProps {
  value: string;
  onChange: (role: string) => void;
  layout?: 'grid' | 'compact';
  showLabel?: boolean;
  label?: string;
  className?: string;
}

export default function RoleSelector({ 
  value, 
  onChange, 
  layout = 'grid',
  showLabel = true,
  label = 'Character Role',
  className = ''
}: RoleSelectorProps) {
  const { selectedRole, customRole: initialCustomRole } = parseRoleValue(value);
  const [internalSelectedRole, setInternalSelectedRole] = useState(selectedRole);
  const [customRole, setCustomRole] = useState(initialCustomRole);

  // Update internal state when value prop changes
  useEffect(() => {
    const { selectedRole: newSelectedRole, customRole: newCustomRole } = parseRoleValue(value);
    setInternalSelectedRole(newSelectedRole);
    setCustomRole(newCustomRole);
  }, [value]);

  const handleRoleClick = (roleId: string) => {
    setInternalSelectedRole(roleId);
    if (roleId !== 'other') {
      setCustomRole('');
      onChange(roleId);
    } else {
      // If switching to "other", keep the custom role if any
      onChange(customRole || 'other');
    }
  };

  const handleCustomRoleChange = (newCustomRole: string) => {
    setCustomRole(newCustomRole);
    onChange(newCustomRole || 'other');
  };

  if (layout === 'compact') {
    return (
      <div className={className}>
        {showLabel && (
          <label className="block text-white/80 mb-2">{label}</label>
        )}
        <div className="flex flex-wrap gap-2 mb-2">
          {CHARACTER_ROLES.map((role) => (
            <button
              key={role.id}
              type="button"
              onClick={() => handleRoleClick(role.id)}
              className={`px-3 py-2 rounded-lg border transition-all text-sm ${
                internalSelectedRole === role.id
                  ? `bg-gradient-to-r ${role.color} text-white border-transparent`
                  : 'bg-white/10 border-white/30 text-white hover:bg-white/20'
              }`}
            >
              {role.icon} {role.name}
            </button>
          ))}
        </div>
        {internalSelectedRole === 'other' && (
          <div className="mt-2">
            <input
              type="text"
              value={customRole}
              onChange={(e) => handleCustomRoleChange(e.target.value)}
              placeholder="Enter custom role (e.g., Sidekick, Rival, Guardian...)"
              className="w-full p-2 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
            />
            <p className="text-xs text-white/50 mt-1">
              Specify the character's unique role in your story
            </p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={className}>
      {showLabel && (
        <label className="block text-white/80 mb-2">{label}</label>
      )}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {CHARACTER_ROLES.map((role) => (
          <button
            key={role.id}
            type="button"
            onClick={() => handleRoleClick(role.id)}
            className={`p-3 rounded-lg border transition-all duration-200 ${
              internalSelectedRole === role.id
                ? `bg-gradient-to-r ${role.color} text-white border-transparent`
                : 'bg-white/10 border-white/30 text-white hover:bg-white/20'
            }`}
          >
            <div className="text-lg mb-1">{role.icon}</div>
            <div className="text-xs font-medium">{role.name}</div>
          </button>
        ))}
      </div>
      {internalSelectedRole === 'other' && (
        <div className="mt-3">
          <input
            type="text"
            value={customRole}
            onChange={(e) => handleCustomRoleChange(e.target.value)}
            placeholder="Enter custom role (e.g., Sidekick, Rival, Guardian, Trickster...)"
            className="w-full p-3 bg-white/10 border border-white/30 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <p className="text-xs text-white/50 mt-1">
            Specify the character's unique role in your story
          </p>
        </div>
      )}
    </div>
  );
}

