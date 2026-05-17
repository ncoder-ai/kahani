'use client';

interface DashboardStatsProps {
  storyCount: number;
  roleplayCount: number;
}

export default function DashboardStats({ storyCount, roleplayCount }: DashboardStatsProps) {
  if (storyCount === 0 && roleplayCount === 0) return null;

  return (
    <div className="mt-8 sm:mt-16 grid grid-cols-3 gap-3 sm:gap-6">
      <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-xl p-3 sm:p-6 text-center">
        <div className="text-xl sm:text-3xl font-bold text-white mb-1">{storyCount}</div>
        <div className="text-white/70 text-xs sm:text-base">Stories</div>
      </div>
      <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-xl p-3 sm:p-6 text-center">
        <div className="text-xl sm:text-3xl font-bold text-white mb-1">{roleplayCount}</div>
        <div className="text-white/70 text-xs sm:text-base">Roleplays</div>
      </div>
      <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-xl p-3 sm:p-6 text-center">
        <div className="text-xl sm:text-3xl font-bold text-white mb-1">&infin;</div>
        <div className="text-white/70 text-xs sm:text-base">Possibilities</div>
      </div>
    </div>
  );
}
