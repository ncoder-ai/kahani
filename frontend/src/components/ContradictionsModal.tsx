'use client';

import { useState, useEffect, useCallback } from 'react';
import { X, AlertTriangle, AlertCircle, Info, CheckCircle, MapPin, Clock, ArrowRight, ChevronDown, ChevronRight, RefreshCw } from 'lucide-react';
import apiClient from '@/lib/api';

interface Contradiction {
  id: number;
  story_id: number;
  branch_id: number | null;
  scene_sequence: number;
  contradiction_type: string;
  character_name: string | null;
  previous_value: string | null;
  current_value: string | null;
  severity: string;
  resolved: boolean;
  resolution_note: string | null;
  detected_at: string | null;
  resolved_at: string | null;
}

interface ContradictionsSummary {
  total: number;
  unresolved: number;
  resolved: number;
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
}

interface ContradictionsModalProps {
  isOpen: boolean;
  onClose: () => void;
  storyId: number;
  branchId?: number;
  storyTitle: string;
}

type TabType = 'unresolved' | 'resolved';

const CONTRADICTION_TYPE_CONFIG: Record<string, { label: string; color: string; bgColor: string; icon: typeof MapPin }> = {
  location_jump: { label: 'Location Jump', color: 'text-red-400', bgColor: 'bg-red-900/30 border-red-700/50', icon: MapPin },
  knowledge_leak: { label: 'Knowledge Leak', color: 'text-orange-400', bgColor: 'bg-orange-900/30 border-orange-700/50', icon: AlertCircle },
  state_regression: { label: 'State Regression', color: 'text-yellow-400', bgColor: 'bg-yellow-900/30 border-yellow-700/50', icon: Clock },
  timeline_error: { label: 'Timeline Error', color: 'text-purple-400', bgColor: 'bg-purple-900/30 border-purple-700/50', icon: Clock },
};

const SEVERITY_CONFIG: Record<string, { label: string; color: string; bgColor: string; icon: typeof AlertTriangle }> = {
  error: { label: 'Error', color: 'text-red-400', bgColor: 'bg-red-900/40 border-red-600/50', icon: AlertTriangle },
  warning: { label: 'Warning', color: 'text-yellow-400', bgColor: 'bg-yellow-900/40 border-yellow-600/50', icon: AlertCircle },
  info: { label: 'Info', color: 'text-blue-400', bgColor: 'bg-blue-900/40 border-blue-600/50', icon: Info },
};

export default function ContradictionsModal({
  isOpen,
  onClose,
  storyId,
  branchId,
  storyTitle
}: ContradictionsModalProps) {
  const [activeTab, setActiveTab] = useState<TabType>('unresolved');
  const [allData, setAllData] = useState<Contradiction[]>([]);
  const [summary, setSummary] = useState<ContradictionsSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [resolvingId, setResolvingId] = useState<number | null>(null);
  const [resolveNote, setResolveNote] = useState('');
  const [resolveLoading, setResolveLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [allContradictions, summaryData] = await Promise.all([
        apiClient.getContradictions(storyId, { resolved: true, branchId }),
        apiClient.getContradictionsSummary(storyId, branchId),
      ]);

      setAllData(allContradictions);
      setSummary(summaryData);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load contradictions';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [storyId, branchId]);

  // Filter based on active tab
  const contradictions = activeTab === 'resolved'
    ? allData.filter(c => c.resolved)
    : allData.filter(c => !c.resolved);

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen, loadData]);

  const toggleExpanded = (id: number) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleStartResolve = (id: number) => {
    setResolvingId(id);
    setResolveNote('');
  };

  const handleCancelResolve = () => {
    setResolvingId(null);
    setResolveNote('');
  };

  const handleResolve = async (id: number) => {
    if (!resolveNote.trim()) return;
    setResolveLoading(true);
    try {
      await apiClient.resolveContradiction(id, resolveNote.trim());
      setResolvingId(null);
      setResolveNote('');
      // Reload data
      await loadData();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to resolve contradiction';
      setError(message);
    } finally {
      setResolveLoading(false);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  const getTypeConfig = (type: string) => {
    return CONTRADICTION_TYPE_CONFIG[type] || {
      label: type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
      color: 'text-gray-400',
      bgColor: 'bg-gray-900/30 border-gray-700/50',
      icon: AlertCircle,
    };
  };

  const getSeverityConfig = (severity: string) => {
    return SEVERITY_CONFIG[severity] || SEVERITY_CONFIG.info;
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50" onClick={onClose} />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4">
        <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-2xl w-full max-w-4xl max-h-[95vh] sm:max-h-[85vh] flex flex-col overflow-hidden">
          {/* Header */}
          <div className="bg-gradient-to-r from-red-900/50 to-orange-900/50 border-b border-slate-700 p-3 sm:p-5 flex items-center justify-between flex-shrink-0">
            <div className="flex items-center gap-2 sm:gap-3 min-w-0">
              <div className="p-1.5 sm:p-2 bg-red-600/20 rounded-lg flex-shrink-0">
                <AlertTriangle className="w-4 h-4 sm:w-5 sm:h-5 text-red-400" />
              </div>
              <div className="min-w-0">
                <h2 className="text-base sm:text-lg font-semibold text-white">Contradictions</h2>
                <p className="text-xs sm:text-sm text-gray-300 mt-0.5 truncate">{storyTitle}</p>
              </div>
            </div>
            <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0">
              <button
                onClick={loadData}
                disabled={loading}
                className="p-2 text-gray-300 hover:text-white active:bg-white/20 hover:bg-white/10 rounded-lg transition-colors"
                title="Refresh"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
              <button
                onClick={onClose}
                className="p-2 text-gray-300 hover:text-white active:bg-white/20 hover:bg-white/10 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Summary Bar */}
          {summary && (
            <div className="px-3 sm:px-5 py-2 sm:py-3 border-b border-slate-700/50 flex-shrink-0 bg-slate-800/80">
              <div className="flex flex-wrap items-center gap-2 sm:gap-4 text-xs sm:text-sm">
                <span className="text-gray-300">
                  Total: <span className="text-white font-medium">{summary.total}</span>
                </span>
                {summary.unresolved > 0 && (
                  <span className="text-yellow-400">
                    {summary.unresolved} unresolved
                  </span>
                )}
                {summary.resolved > 0 && (
                  <span className="text-green-400">
                    {summary.resolved} resolved
                  </span>
                )}
              </div>
              {Object.keys(summary.by_type).length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 mt-2">
                  {Object.entries(summary.by_type).map(([type, count]) => {
                    const config = getTypeConfig(type);
                    return (
                      <span key={type} className={`text-[10px] sm:text-xs px-1.5 sm:px-2 py-0.5 rounded border ${config.bgColor} ${config.color}`}>
                        {config.label}: {count}
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Tabs */}
          <div className="flex border-b border-slate-700/50 flex-shrink-0">
            <button
              onClick={() => setActiveTab('unresolved')}
              className={`flex-1 px-3 sm:px-4 py-2.5 sm:py-3 text-xs sm:text-sm font-medium transition-colors ${
                activeTab === 'unresolved'
                  ? 'text-red-400 border-b-2 border-red-400 bg-red-900/10'
                  : 'text-gray-300 hover:text-gray-200 active:bg-white/10 hover:bg-white/5'
              }`}
            >
              Unresolved
              {summary && summary.unresolved > 0 && (
                <span className="ml-1.5 sm:ml-2 px-1.5 py-0.5 text-[10px] sm:text-xs rounded-full bg-red-900/50 text-red-300">
                  {summary.unresolved}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveTab('resolved')}
              className={`flex-1 px-3 sm:px-4 py-2.5 sm:py-3 text-xs sm:text-sm font-medium transition-colors ${
                activeTab === 'resolved'
                  ? 'text-green-400 border-b-2 border-green-400 bg-green-900/10'
                  : 'text-gray-300 hover:text-gray-200 active:bg-white/10 hover:bg-white/5'
              }`}
            >
              Resolved
              {summary && summary.resolved > 0 && (
                <span className="ml-1.5 sm:ml-2 px-1.5 py-0.5 text-[10px] sm:text-xs rounded-full bg-green-900/50 text-green-300">
                  {summary.resolved}
                </span>
              )}
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-3 sm:p-5">
            {error && (
              <div className="mb-3 sm:mb-4 p-2.5 sm:p-3 bg-red-900/30 border border-red-700/50 rounded-lg text-red-300 text-xs sm:text-sm">
                {error}
              </div>
            )}

            {loading ? (
              <div className="flex items-center justify-center py-12">
                <RefreshCw className="w-5 h-5 sm:w-6 sm:h-6 text-gray-400 animate-spin" />
                <span className="ml-3 text-gray-300 text-sm">Loading contradictions...</span>
              </div>
            ) : contradictions.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 sm:py-12 text-gray-400">
                <CheckCircle className="w-10 h-10 sm:w-12 sm:h-12 mb-3 text-green-600/50" />
                <p className="text-base sm:text-lg font-medium text-center">
                  {activeTab === 'unresolved'
                    ? 'No unresolved contradictions'
                    : 'No resolved contradictions'}
                </p>
                <p className="text-xs sm:text-sm mt-1 text-gray-500 text-center">
                  {activeTab === 'unresolved'
                    ? 'Your story continuity looks good!'
                    : 'No contradictions have been resolved yet.'}
                </p>
              </div>
            ) : (
              <div className="space-y-2 sm:space-y-3">
                {contradictions.map((c) => {
                  const typeConfig = getTypeConfig(c.contradiction_type);
                  const severityConfig = getSeverityConfig(c.severity);
                  const isExpanded = expandedIds.has(c.id);
                  const isResolving = resolvingId === c.id;
                  const SeverityIcon = severityConfig.icon;

                  return (
                    <div
                      key={c.id}
                      className={`rounded-lg border transition-colors ${
                        c.resolved
                          ? 'bg-slate-900/30 border-slate-700/30'
                          : `bg-slate-900/50 border-slate-700/50 hover:border-slate-600/50`
                      }`}
                    >
                      {/* Contradiction Header */}
                      <button
                        onClick={() => toggleExpanded(c.id)}
                        className="w-full p-3 sm:p-4 text-left"
                      >
                        {/* Mobile: stacked layout, Desktop: row layout */}
                        <div className="flex items-start sm:items-center gap-2 sm:gap-3">
                          {isExpanded ? (
                            <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0 mt-0.5 sm:mt-0" />
                          ) : (
                            <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0 mt-0.5 sm:mt-0" />
                          )}

                          <div className="flex-1 min-w-0">
                            {/* First row: type, severity, character */}
                            <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 mb-1 sm:mb-0">
                              {/* Severity icon */}
                              <SeverityIcon className={`w-3.5 h-3.5 sm:w-4 sm:h-4 flex-shrink-0 ${severityConfig.color}`} />

                              {/* Type badge */}
                              <span className={`text-[10px] sm:text-xs px-1.5 sm:px-2 py-0.5 rounded border ${typeConfig.bgColor} ${typeConfig.color}`}>
                                {typeConfig.label}
                              </span>

                              {/* Character name */}
                              {c.character_name && (
                                <span className="text-xs sm:text-sm text-white font-medium">
                                  {c.character_name}
                                </span>
                              )}

                              {/* Scene number */}
                              <span className="text-[10px] sm:text-xs text-gray-400">
                                Scene {c.scene_sequence}
                              </span>

                              {/* Resolved badge */}
                              {c.resolved && (
                                <span className="text-[10px] sm:text-xs px-1.5 sm:px-2 py-0.5 rounded bg-green-900/40 border border-green-700/50 text-green-400">
                                  Resolved
                                </span>
                              )}
                            </div>

                            {/* Second row: summary - only on mobile when not expanded */}
                            <p className="text-xs sm:text-sm text-gray-300 truncate mt-1">
                              {c.previous_value && c.current_value
                                ? `${truncateValue(c.previous_value, 30)} → ${truncateValue(c.current_value, 30)}`
                                : c.current_value || c.previous_value || ''}
                            </p>
                          </div>

                          {/* Date - hidden on mobile */}
                          {c.detected_at && (
                            <span className="text-[10px] sm:text-xs text-gray-500 flex-shrink-0 hidden sm:block">
                              {formatDate(c.detected_at)}
                            </span>
                          )}
                        </div>
                      </button>

                      {/* Expanded Details */}
                      {isExpanded && (
                        <div className="px-3 sm:px-4 pb-3 sm:pb-4 pt-0 border-t border-slate-700/30">
                          <div className="mt-3 space-y-3">
                            {/* Previous → Current values */}
                            {(c.previous_value || c.current_value) && (
                              <div className="flex flex-col sm:flex-row items-stretch sm:items-start gap-2 sm:gap-3">
                                {c.previous_value && (
                                  <div className="flex-1 p-2.5 sm:p-3 bg-slate-800/80 rounded-lg border border-slate-700/30">
                                    <div className="text-[10px] sm:text-xs text-gray-400 mb-1 uppercase tracking-wide">Previous</div>
                                    <div className="text-xs sm:text-sm text-gray-200">{c.previous_value}</div>
                                  </div>
                                )}
                                {c.previous_value && c.current_value && (
                                  <ArrowRight className="w-4 h-4 text-gray-500 flex-shrink-0 self-center rotate-90 sm:rotate-0" />
                                )}
                                {c.current_value && (
                                  <div className="flex-1 p-2.5 sm:p-3 bg-slate-800/80 rounded-lg border border-slate-700/30">
                                    <div className="text-[10px] sm:text-xs text-gray-400 mb-1 uppercase tracking-wide">Current</div>
                                    <div className="text-xs sm:text-sm text-gray-200">{c.current_value}</div>
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Meta info */}
                            <div className="flex flex-wrap items-center gap-2 sm:gap-4 text-[10px] sm:text-xs text-gray-400">
                              <span>Scene {c.scene_sequence}</span>
                              {c.branch_id && <span>Branch {c.branch_id}</span>}
                              {c.detected_at && <span>Detected {formatDate(c.detected_at)}</span>}
                              {c.resolved_at && <span>Resolved {formatDate(c.resolved_at)}</span>}
                            </div>

                            {/* Resolution note (for resolved items) */}
                            {c.resolved && c.resolution_note && (
                              <div className="p-2.5 sm:p-3 bg-green-900/20 border border-green-700/30 rounded-lg">
                                <div className="text-[10px] sm:text-xs text-green-500 mb-1 uppercase tracking-wide">Resolution Note</div>
                                <div className="text-xs sm:text-sm text-green-300">{c.resolution_note}</div>
                              </div>
                            )}

                            {/* Resolve action (for unresolved items) */}
                            {!c.resolved && !isResolving && (
                              <button
                                onClick={() => handleStartResolve(c.id)}
                                className="text-xs sm:text-sm px-3 py-1.5 sm:py-2 bg-green-900/30 border border-green-700/50 text-green-400 rounded-lg hover:bg-green-900/50 active:bg-green-900/70 transition-colors"
                              >
                                Mark as Resolved
                              </button>
                            )}

                            {/* Resolution form */}
                            {isResolving && (
                              <div className="space-y-2">
                                <div>
                                  <label className="block text-xs font-medium text-gray-300 mb-1">Resolution Note</label>
                                  <textarea
                                    value={resolveNote}
                                    onChange={(e) => setResolveNote(e.target.value)}
                                    placeholder="Why is this resolved? (e.g., intentional plot decision, fixed in later scene)"
                                    className="w-full p-2.5 bg-slate-900 border border-slate-500 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-green-600 resize-none"
                                    rows={2}
                                    autoFocus
                                  />
                                </div>
                                <div className="flex items-center gap-2">
                                  <button
                                    onClick={() => handleResolve(c.id)}
                                    disabled={!resolveNote.trim() || resolveLoading}
                                    className="text-xs sm:text-sm px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 active:bg-green-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                  >
                                    {resolveLoading ? 'Resolving...' : 'Resolve'}
                                  </button>
                                  <button
                                    onClick={handleCancelResolve}
                                    className="text-xs sm:text-sm px-3 py-1.5 bg-slate-700 text-gray-200 rounded-lg hover:bg-slate-600 active:bg-slate-500 transition-colors"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function truncateValue(value: string, maxLen = 40): string {
  if (value.length <= maxLen) return value;
  return value.slice(0, maxLen) + '...';
}
