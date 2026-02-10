'use client';

import { CHARACTER_ROLES, getRoleInfo } from '@/components/RoleSelector';

interface Character {
  name: string;
  role: string;
  description: string;
  gender?: string | null;
  id?: number;
}

interface CharacterDisplayProps {
  characters: Character[];
  onAddCharacter?: () => void;
  showAddButton?: boolean;
}

export default function CharacterDisplay({ characters, onAddCharacter, showAddButton = false }: CharacterDisplayProps) {
  const getCharacterRoleInfo = (roleId: string) => {
    return getRoleInfo(roleId) || CHARACTER_ROLES[CHARACTER_ROLES.length - 1];
  };

  if (characters.length === 0 && !showAddButton) {
    return null;
  }

  return (
    <div className="bg-white/5 rounded-lg p-4 border border-white/10">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-lg font-semibold text-white">
          Story Characters ({characters.length})
        </h4>
        {showAddButton && onAddCharacter && (
          <button
            onClick={onAddCharacter}
            className="px-3 py-1 theme-btn-primary text-white text-sm rounded-lg transition-colors"
          >
            + Add
          </button>
        )}
      </div>
      
      {characters.length === 0 ? (
        <p className="text-white/60 text-sm">No characters added yet</p>
      ) : (
        <div className="space-y-2">
          {characters.map((character, index) => {
            const roleInfo = getCharacterRoleInfo(character.role);
            return (
              <div key={index} className="flex items-center space-x-3 p-2 bg-white/5 rounded">
                <div className={`w-8 h-8 rounded-full bg-gradient-to-r ${roleInfo.color} flex items-center justify-center text-white text-sm`}>
                  {roleInfo.icon}
                </div>
                <div className="flex-1">
                  <div className="text-white font-medium">{character.name}</div>
                  <div className="text-white/60 text-xs">
                    {roleInfo.name}{character.gender ? ` · ${character.gender}` : ''}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}