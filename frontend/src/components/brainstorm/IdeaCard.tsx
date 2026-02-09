'use client';

interface IdeaCardProps {
  title: string;
  icon: string;
  children: React.ReactNode;
  onEdit?: () => void;
}

export default function IdeaCard({ title, icon, children, onEdit }: IdeaCardProps) {
  return (
    <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-xl p-6">
      <div className="flex justify-between items-start mb-4">
        <div className="flex items-center space-x-2">
          <span className="text-2xl">{icon}</span>
          <h3 className="text-lg font-semibold text-white">{title}</h3>
        </div>
        {onEdit && (
          <button
            onClick={onEdit}
            className="text-white/60 hover:text-white transition-colors"
            title="Edit"
          >
            ✏️
          </button>
        )}
      </div>
      <div className="text-white/80">
        {children}
      </div>
    </div>
  );
}

