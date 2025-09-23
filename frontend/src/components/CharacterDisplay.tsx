'use client';

interface Character {
  name: string;
  role: string;
  description: string;
  id?: number;
}

interface CharacterDisplayProps {
  characters: Character[];
  onAddCharacter?: () => void;
  showAddButton?: boolean;
}

const CHARACTER_ROLES = [
  { id: 'protagonist', name: 'Main Character', icon: '⭐', color: 'from-yellow-400 to-orange-500' },
  { id: 'antagonist', name: 'Antagonist', icon: '⚔️', color: 'from-red-500 to-red-700' },
  { id: 'ally', name: 'Ally/Friend', icon: '🤝', color: 'from-green-400 to-green-600' },
  { id: 'mentor', name: 'Mentor', icon: '🎓', color: 'from-blue-400 to-blue-600' },
  { id: 'love_interest', name: 'Love Interest', icon: '💕', color: 'from-pink-400 to-pink-600' },
  { id: 'comic_relief', name: 'Comic Relief', icon: '😄', color: 'from-purple-400 to-purple-600' },
  { id: 'mysterious', name: 'Mysterious Figure', icon: '🎭', color: 'from-gray-500 to-gray-700' },
  { id: 'other', name: 'Other', icon: '👤', color: 'from-indigo-400 to-indigo-600' }
];

export default function CharacterDisplay({ characters, onAddCharacter, showAddButton = false }: CharacterDisplayProps) {
  const getRoleInfo = (roleId: string) => {
    return CHARACTER_ROLES.find(role => role.id === roleId) || CHARACTER_ROLES[CHARACTER_ROLES.length - 1];
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
            className="px-3 py-1 bg-purple-500 hover:bg-purple-600 text-white text-sm rounded-lg transition-colors"
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
            const roleInfo = getRoleInfo(character.role);
            return (
              <div key={index} className="flex items-center space-x-3 p-2 bg-white/5 rounded">
                <div className={`w-8 h-8 rounded-full bg-gradient-to-r ${roleInfo.color} flex items-center justify-center text-white text-sm`}>
                  {roleInfo.icon}
                </div>
                <div className="flex-1">
                  <div className="text-white font-medium">{character.name}</div>
                  <div className="text-white/60 text-xs">{roleInfo.name}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}