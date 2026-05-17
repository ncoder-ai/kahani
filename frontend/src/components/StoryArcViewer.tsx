'use client';

import React, { useState } from 'react';
import { StoryArc, ArcPhase } from '@/lib/api';

interface StoryArcViewerProps {
  arc: StoryArc | null;
  currentPhaseId?: string;
  onPhaseClick?: (phase: ArcPhase) => void;
  compact?: boolean;
}

export default function StoryArcViewer({
  arc,
  currentPhaseId,
  onPhaseClick,
  compact = false
}: StoryArcViewerProps) {
  const [expandedPhase, setExpandedPhase] = useState<string | null>(null);

  if (!arc || !arc.phases || arc.phases.length === 0) {
    return (
      <div className="bg-white/5 rounded-xl p-4 text-center">
        <p className="text-white/60 text-sm">No story arc generated yet</p>
      </div>
    );
  }

  const handlePhaseClick = (phase: ArcPhase) => {
    if (onPhaseClick) {
      onPhaseClick(phase);
    } else {
      setExpandedPhase(expandedPhase === phase.id ? null : phase.id);
    }
  };

  if (compact) {
    // Compact horizontal progress bar view
    return (
      <div className="bg-white/5 rounded-xl p-3">
        <div className="flex items-center gap-1 mb-2">
          <span className="text-white/60 text-xs">Story Arc</span>
          <span className="text-purple-400 text-xs">
            ({arc.structure_type.replace('_', ' ')})
          </span>
        </div>
        
        <div className="flex gap-1">
          {arc.phases.map((phase, index) => {
            const isCurrentPhase = phase.id === currentPhaseId;
            const isPastPhase = currentPhaseId && 
              arc.phases.findIndex(p => p.id === currentPhaseId) > index;
            
            return (
              <button
                key={phase.id}
                onClick={() => handlePhaseClick(phase)}
                className={`flex-1 h-2 rounded-full transition-all ${
                  isCurrentPhase
                    ? 'bg-gradient-to-r from-purple-500 to-pink-500'
                    : isPastPhase
                    ? 'bg-purple-500/50'
                    : 'bg-white/20 hover:bg-white/30'
                }`}
                title={phase.name}
              />
            );
          })}
        </div>

        {/* Current phase indicator */}
        {currentPhaseId && (
          <div className="mt-2 text-center">
            <span className="text-purple-300 text-xs">
              {arc.phases.find(p => p.id === currentPhaseId)?.name || 'Unknown Phase'}
            </span>
          </div>
        )}
      </div>
    );
  }

  // Full vertical timeline view
  return (
    <div className="bg-white/5 rounded-xl p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-white font-semibold">Story Arc</h3>
        <span className="text-purple-400 text-xs capitalize">
          {arc.structure_type.replace('_', ' ')}
        </span>
      </div>

      <div className="relative">
        {/* Timeline line */}
        <div className="absolute left-3 top-2 bottom-2 w-0.5 bg-gradient-to-b from-purple-500 via-pink-500 to-purple-500" />

        <div className="space-y-3">
          {arc.phases.map((phase, index) => {
            const isCurrentPhase = phase.id === currentPhaseId;
            const isPastPhase = currentPhaseId && 
              arc.phases.findIndex(p => p.id === currentPhaseId) > index;
            const isExpanded = expandedPhase === phase.id;

            return (
              <div key={phase.id} className="relative pl-8">
                {/* Timeline node */}
                <div className={`absolute left-1.5 top-2 w-3 h-3 rounded-full border-2 ${
                  isCurrentPhase
                    ? 'bg-gradient-to-r from-purple-500 to-pink-500 border-white animate-pulse'
                    : isPastPhase
                    ? 'bg-purple-500/50 border-purple-300'
                    : 'bg-white/20 border-white/40'
                }`} />

                <button
                  onClick={() => handlePhaseClick(phase)}
                  className={`w-full text-left p-2 rounded-lg transition-all ${
                    isCurrentPhase
                      ? 'bg-purple-500/20 border border-purple-500/50'
                      : 'hover:bg-white/5'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className={`text-sm font-medium ${
                      isCurrentPhase ? 'text-purple-300' : 'text-white/80'
                    }`}>
                      {phase.name}
                    </span>
                    <span className="text-white/40 text-xs">
                      {phase.estimated_chapters}ch
                    </span>
                  </div>

                  {isExpanded && (
                    <div className="mt-2 space-y-2">
                      <p className="text-white/60 text-xs">
                        {phase.description}
                      </p>
                      
                      {phase.key_events.length > 0 && (
                        <div>
                          <span className="text-white/40 text-xs">Key events:</span>
                          <ul className="mt-1 space-y-0.5">
                            {phase.key_events.slice(0, 3).map((event, i) => (
                              <li key={i} className="text-white/50 text-xs flex items-start gap-1">
                                <span className="text-purple-400">•</span>
                                <span className="line-clamp-1">{event}</span>
                              </li>
                            ))}
                            {phase.key_events.length > 3 && (
                              <li className="text-white/40 text-xs">
                                +{phase.key_events.length - 3} more...
                              </li>
                            )}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

