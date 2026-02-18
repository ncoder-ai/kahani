'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { X, Plus, Check, MapPin, Clock, FileText, CheckCircle, Circle, AlertTriangle, ArrowRight, Loader2 } from 'lucide-react';
import apiClient, { StoryArc } from '@/lib/api';
import CharacterQuickAdd from '@/components/CharacterQuickAdd';

// --- Creation Progress Sub-Component ---

type StepStatus = 'pending' | 'active' | 'done' | 'warning';

interface ProgressStep {
  label: string;
  subText?: string;
  status: StepStatus;
  optional?: boolean;
}

function CreationProgress({
  steps,
  chapterCreated,
  creationError,
  enrichmentWarning,
  elapsedSeconds,
  onStartWriting,
}: {
  steps: ProgressStep[];
  chapterCreated: boolean;
  creationError: string | null;
  enrichmentWarning: string | null;
  elapsedSeconds: number;
  onStartWriting: () => void;
}) {
  const activeStepIndex = steps.findIndex(s => s.status === 'active');
  const allDone = steps.every(s => s.status === 'done' || s.status === 'warning');

  const formatTime = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`;
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}m ${s}s`;
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[300px] py-8 px-4">
      {/* Title */}
      <h3 className="text-xl font-semibold text-white mb-8">
        {creationError ? 'Something went wrong' : allDone ? 'All done!' : 'Creating chapter...'}
      </h3>

      {/* Steps */}
      <div className="w-full max-w-md space-y-4 mb-8">
        {steps.map((step, i) => (
          <div key={i} className="flex items-start gap-3">
            {/* Icon */}
            <div className="flex-shrink-0 mt-0.5">
              {step.status === 'done' ? (
                <CheckCircle className="w-5 h-5 text-emerald-400" />
              ) : step.status === 'active' ? (
                <Loader2 className="w-5 h-5 text-pink-400 animate-spin" />
              ) : step.status === 'warning' ? (
                <AlertTriangle className="w-5 h-5 text-amber-400" />
              ) : (
                <Circle className="w-5 h-5 text-white/20" />
              )}
            </div>
            {/* Text */}
            <div className="flex-1 min-w-0">
              <div className={`text-sm font-medium ${
                step.status === 'done' ? 'text-emerald-300' :
                step.status === 'active' ? 'text-white' :
                step.status === 'warning' ? 'text-amber-300' :
                'text-white/40'
              }`}>
                {step.label}
                {step.optional && <span className="text-white/30 font-normal ml-1">(optional)</span>}
              </div>
              {step.subText && step.status === 'active' && (
                <p className="text-white/50 text-xs mt-0.5">{step.subText}</p>
              )}
              {/* Elapsed time on active step */}
              {step.status === 'active' && elapsedSeconds > 0 && (
                <p className="text-white/30 text-xs mt-1">{formatTime(elapsedSeconds)}</p>
              )}
              {/* Slow hint for step 3 */}
              {step.status === 'active' && step.optional && elapsedSeconds > 30 && (
                <p className="text-amber-300/70 text-xs mt-1">
                  Taking a while? You can start writing now — this will finish in the background.
                </p>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Chapter Created Banner */}
      {chapterCreated && !creationError && (
        <div className={`w-full max-w-md rounded-lg p-4 mb-4 ${
          allDone && !enrichmentWarning
            ? 'bg-emerald-500/15 border border-emerald-500/30'
            : enrichmentWarning
            ? 'bg-amber-500/10 border border-amber-500/30'
            : 'bg-emerald-500/10 border border-emerald-500/20'
        }`}>
          <div className="flex items-center gap-2 mb-1">
            <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <span className="text-emerald-300 font-medium text-sm">Chapter created</span>
          </div>
          {enrichmentWarning && (
            <p className="text-amber-300/80 text-xs ml-6">
              Story context generation failed, but you can start writing — it can be retried later.
            </p>
          )}
          {allDone && !enrichmentWarning && (
            <p className="text-emerald-300/70 text-xs ml-6">
              Everything is ready.
            </p>
          )}
        </div>
      )}

      {/* Error Display */}
      {creationError && (
        <div className="w-full max-w-md bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-4">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
            <span className="text-red-300 font-medium text-sm">Failed to create chapter</span>
          </div>
          <p className="text-red-300/80 text-xs ml-6">{creationError}</p>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex gap-3">
        {chapterCreated && (
          <button
            onClick={onStartWriting}
            className="px-6 py-2.5 bg-pink-600 hover:bg-pink-700 text-white rounded-lg transition-colors flex items-center gap-2 font-medium"
          >
            <ArrowRight className="w-4 h-4" />
            Start Writing
          </button>
        )}
        {creationError && !chapterCreated && (
          <button
            onClick={onStartWriting}
            className="px-6 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-colors"
          >
            Close
          </button>
        )}
      </div>
    </div>
  );
}

interface Character {
  id: number;
  name: string;
  role: string | null;
  description: string | null;
  story_character_id?: number;
}

interface ChapterWizardProps {
  storyId: number;
  chapterNumber?: number;
  chapterId?: number; // If provided, indicates edit mode
  storyArc?: StoryArc | null;
  onBrainstorm?: () => void;
  brainstormSessionId?: number;  // Session ID if plot came from brainstorm
  initialData?: {
    title?: string;
    description?: string;
    characters?: Character[];
    location_name?: string;
    time_period?: string;
    scenario?: string;
    continues_from_previous?: boolean;
    arc_phase_id?: string;
    chapter_plot?: any;
    recommended_characters?: string[];  // Character names from brainstorm
    mood?: string;  // Emotional tone from brainstorm (separate from time_period)
  };
  onComplete: (data: {
    title?: string;
    description?: string;
    story_character_ids?: number[];
    character_ids?: number[];
    character_roles?: { [characterId: number]: string };
    location_name?: string;
    time_period?: string;
    scenario?: string;
    continues_from_previous?: boolean;
    arc_phase_id?: string;
    chapter_plot?: any;  // Include plot in completion data
    brainstorm_session_id?: number;
  }, onStatusUpdate?: (status: { message: string; step: string }) => void) => Promise<void> | void;
  onCancel: () => void;
  onDone?: () => void;  // Called when user clicks "Start writing" — parent handles close + chapter switch
}

export default function ChapterWizard({
  storyId,
  chapterNumber,
  chapterId,
  storyArc,
  onBrainstorm,
  brainstormSessionId,
  initialData,
  onComplete,
  onCancel,
  onDone
}: ChapterWizardProps) {
  const [title, setTitle] = useState(initialData?.title || `Chapter ${chapterNumber || 1}`);
  const [selectedArcPhaseId, setSelectedArcPhaseId] = useState<string | undefined>(initialData?.arc_phase_id);
  // Use plot summary as description if no explicit description provided
  const [description, setDescription] = useState(
    initialData?.description || initialData?.chapter_plot?.summary || ''
  );
  const [selectedCharacterIds, setSelectedCharacterIds] = useState<number[]>(
    initialData?.characters?.map(c => c.id) || []
  );
  const [newCharacterIds, setNewCharacterIds] = useState<number[]>([]); // Characters from library to add
  const [characterRoles, setCharacterRoles] = useState<{ [characterId: number]: string }>({}); // Map of character_id to role
  const [newCharacters, setNewCharacters] = useState<{ [characterId: number]: Character }>({}); // Store new character details for display
  const [availableCharacters, setAvailableCharacters] = useState<Character[]>([]);
  const [locationName, setLocationName] = useState(initialData?.location_name || '');
  const [availableLocations, setAvailableLocations] = useState<string[]>([]);
  const [timePeriod, setTimePeriod] = useState(initialData?.time_period || '');
  const [scenario, setScenario] = useState(initialData?.scenario || '');
  const [continuesFromPrevious, setContinuesFromPrevious] = useState(
    initialData?.continues_from_previous !== undefined ? initialData.continues_from_previous : true
  );
  const [showCharacterQuickAdd, setShowCharacterQuickAdd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingData, setLoadingData] = useState(true);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Creation progress state (only used for new chapter creation, not edit)
  const [creationPhase, setCreationPhase] = useState(false);
  const [creationSteps, setCreationSteps] = useState<ProgressStep[]>([]);
  const [chapterCreated, setChapterCreated] = useState(false);
  const [creationError, setCreationError] = useState<string | null>(null);
  const [enrichmentWarning, setEnrichmentWarning] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeStepStartRef = useRef<number>(Date.now());

  useEffect(() => {
    loadAvailableData();
  }, [storyId]);

  // Track previous plot to detect when a new brainstorm plot is applied
  const prevPlotRef = useRef<any>(null);
  const prevRecommendedCharsRef = useRef<string[] | undefined>(undefined);

  // Update form fields when brainstorm plot is applied or changes
  useEffect(() => {
    if (initialData?.chapter_plot) {
      const isNewPlot = prevPlotRef.current !== initialData.chapter_plot;
      
      if (isNewPlot) {
        console.log('[ChapterWizard] New brainstorm plot detected, updating fields');
        prevPlotRef.current = initialData.chapter_plot;
        
        // Update description from plot summary
        if (initialData.chapter_plot.summary) {
          setDescription(initialData.chapter_plot.summary);
        }
        
        // Update location from plot
        if (initialData.location_name) {
          setLocationName(initialData.location_name);
        } else if (initialData.chapter_plot.location) {
          setLocationName(initialData.chapter_plot.location);
        }
        
        // Update scenario from plot's opening_situation
        if (initialData.scenario) {
          setScenario(initialData.scenario);
        } else if (initialData.chapter_plot.opening_situation) {
          setScenario(initialData.chapter_plot.opening_situation);
        }
        
        // Extract character IDs from brainstorm character review
        // These are characters created or selected during the brainstorm character review phase
        if (initialData.chapter_plot._characterIds && initialData.chapter_plot._characterIds.length > 0) {
          const brainstormCharacterIds = initialData.chapter_plot._characterIds;
          console.log('[ChapterWizard] Found brainstorm character IDs:', brainstormCharacterIds);
          
          // Add these as new characters to be linked to the chapter
          setNewCharacterIds(prev => {
            const newIds = new Set([...prev, ...brainstormCharacterIds]);
            return Array.from(newIds);
          });
          
          // Fetch character details for display and extract roles from new_character_suggestions
          const fetchBrainstormCharacters = async () => {
            try {
              const characterDetails: { [characterId: number]: Character } = {};
              const roles: { [characterId: number]: string } = {};
              
              // Build a map of character names to roles from new_character_suggestions
              const nameToRole: { [name: string]: string } = {};
              if (initialData.chapter_plot.new_character_suggestions) {
                initialData.chapter_plot.new_character_suggestions.forEach((suggestion: { name: string; role: string }) => {
                  if (suggestion.name && suggestion.role) {
                    nameToRole[suggestion.name.toLowerCase()] = suggestion.role;
                  }
                });
              }
              
              // Fetch each character's details
              for (const charId of brainstormCharacterIds) {
                try {
                  const char = await apiClient.getCharacter(charId);
                  characterDetails[charId] = {
                    id: char.id,
                    name: char.name,
                    role: nameToRole[char.name.toLowerCase()] || 'other',
                    description: char.description
                  };
                  roles[charId] = nameToRole[char.name.toLowerCase()] || 'other';
                } catch (error) {
                  console.error(`[ChapterWizard] Failed to fetch character ${charId}:`, error);
                }
              }
              
              if (Object.keys(characterDetails).length > 0) {
                setNewCharacters(prev => ({ ...prev, ...characterDetails }));
                setCharacterRoles(prev => ({ ...prev, ...roles }));
                console.log('[ChapterWizard] Loaded brainstorm character details:', characterDetails);
              }
            } catch (error) {
              console.error('[ChapterWizard] Failed to fetch brainstorm characters:', error);
            }
          };
          
          fetchBrainstormCharacters();
        }
        
        // Note: mood is displayed in the plot summary section, not as time_period
        // time_period is for things like "morning", "night", "1920s" - not emotional tone
      }
    }
  }, [initialData?.chapter_plot, initialData?.location_name, initialData?.scenario]);

  // Update arc phase when it changes from brainstorm
  useEffect(() => {
    if (initialData?.arc_phase_id && initialData.arc_phase_id !== selectedArcPhaseId) {
      console.log('[ChapterWizard] Arc phase updated from brainstorm:', initialData.arc_phase_id);
      setSelectedArcPhaseId(initialData.arc_phase_id);
    }
  }, [initialData?.arc_phase_id]);

  // Auto-select characters based on recommended_characters from brainstorm
  useEffect(() => {
    if (availableCharacters.length > 0 && initialData?.recommended_characters && initialData.recommended_characters.length > 0) {
      // Check if recommended characters changed
      const prevChars = prevRecommendedCharsRef.current;
      const currentChars = initialData.recommended_characters;
      const charsChanged = !prevChars || 
        prevChars.length !== currentChars.length || 
        !prevChars.every((c, i) => c === currentChars[i]);
      
      if (charsChanged) {
        prevRecommendedCharsRef.current = currentChars;
        
        const recommendedNames = currentChars.map(name => name.toLowerCase());
        const matchingCharacterIds = availableCharacters
          .filter(char => recommendedNames.some(recName => 
            char.name.toLowerCase().includes(recName) || recName.includes(char.name.toLowerCase())
          ))
          .map(char => char.id);
        
        if (matchingCharacterIds.length > 0) {
          console.log('[ChapterWizard] Auto-selecting characters from brainstorm:', matchingCharacterIds);
          setSelectedCharacterIds(prev => {
            // Merge with existing selections, avoiding duplicates
            const newIds = new Set([...prev, ...matchingCharacterIds]);
            return Array.from(newIds);
          });
        }
      }
    }
  }, [availableCharacters, initialData?.recommended_characters]);

  // Elapsed timer for creation progress — runs while any step is active
  // Timer is cleared explicitly in the status callback when all steps complete
  useEffect(() => {
    if (creationPhase && !creationError) {
      elapsedTimerRef.current = setInterval(() => {
        setElapsedSeconds(Math.floor((Date.now() - activeStepStartRef.current) / 1000));
      }, 1000);
    }
    return () => {
      if (elapsedTimerRef.current) {
        clearInterval(elapsedTimerRef.current);
        elapsedTimerRef.current = null;
      }
    };
  }, [creationPhase, creationError]);

  const resetStepTimer = useCallback(() => {
    activeStepStartRef.current = Date.now();
    setElapsedSeconds(0);
  }, []);

  const loadAvailableData = async () => {
    try {
      setLoadingData(true);
      const [charsResponse, locsResponse] = await Promise.all([
        apiClient.getAvailableCharacters(storyId),
        apiClient.getAvailableLocations(storyId)
      ]);
      
      // Map and deduplicate by story_character_id (or character_id if story_character_id is missing)
      const characterMap = new Map<number, Character>();
      charsResponse.characters.forEach(c => {
        const key = c.story_character_id || c.character_id;
        // Only add if we haven't seen this story_character_id before
        if (!characterMap.has(key)) {
          characterMap.set(key, {
            id: c.character_id,
            name: c.name,
            role: c.role,
            description: c.description,
            story_character_id: c.story_character_id
          });
        }
      });
      
      setAvailableCharacters(Array.from(characterMap.values()));
      setAvailableLocations(locsResponse.locations);
    } catch (error) {
      console.error('Failed to load available data:', error);
    } finally {
      setLoadingData(false);
    }
  };

  const handleCharacterToggle = (characterId: number) => {
    // Toggle for characters already in the story
    setSelectedCharacterIds(prev => {
      if (prev.includes(characterId)) {
        return prev.filter(id => id !== characterId);
      } else {
        return [...prev, characterId];
      }
    });
    // Also remove from new characters if it was there
    setNewCharacterIds(prev => prev.filter(id => id !== characterId));
    setCharacterRoles(prev => {
      const newRoles = { ...prev };
      delete newRoles[characterId];
      return newRoles;
    });
    setNewCharacters(prev => {
      const newChars = { ...prev };
      delete newChars[characterId];
      return newChars;
    });
  };

  const handleCharacterAdd = async (character: { id?: number; name: string; role: string; description: string }) => {
    if (character.id) {
      // Check if character is already in the story (availableCharacters)
      const storyChar = availableCharacters.find(c => c.id === character.id);
      
      if (storyChar) {
        // Character is already in the story, add to selectedCharacterIds
        setSelectedCharacterIds(prev => {
          if (!prev.includes(character.id!)) {
            return [...prev, character.id!];
          }
          return prev;
        });
      } else {
        // Character is from library and not yet in story
        // Add to newCharacterIds and store the role and details
        setNewCharacterIds(prev => {
          if (!prev.includes(character.id!)) {
            return [...prev, character.id!];
          }
          return prev;
        });
        setCharacterRoles(prev => ({
          ...prev,
          [character.id!]: character.role
        }));
        setNewCharacters(prev => ({
          ...prev,
          [character.id!]: {
            id: character.id!,
            name: character.name,
            role: character.role,
            description: character.description
          }
        }));
      }
    }
    setShowCharacterQuickAdd(false);
  };

  const handleSubmit = async () => {
    // Disable button immediately to prevent double-clicks
    setLoading(true);
    setStatusMessage(null);

    // Get story_character_ids for characters already in the story
    const storyCharacterIds = availableCharacters
      .filter(c => selectedCharacterIds.includes(c.id))
      .map(c => c.story_character_id)
      .filter((id): id is number => id !== undefined && id !== null);

    // Prepare character_ids and character_roles for new characters from library
    const characterIds = newCharacterIds.length > 0 ? newCharacterIds : undefined;
    const characterRolesMap = newCharacterIds.length > 0
      ? Object.fromEntries(
          newCharacterIds.map(id => [id, characterRoles[id] || 'other'])
        )
      : undefined;

    const chapterData = {
      title: title.trim() || undefined,
      description: description.trim() || undefined,
      story_character_ids: storyCharacterIds.length > 0 ? storyCharacterIds : undefined,
      character_ids: characterIds,
      character_roles: characterRolesMap,
      location_name: locationName.trim() || undefined,
      time_period: timePeriod.trim() || undefined,
      scenario: scenario.trim() || undefined,
      continues_from_previous: continuesFromPrevious,
      arc_phase_id: selectedArcPhaseId,
      chapter_plot: initialData?.chapter_plot,
      brainstorm_session_id: brainstormSessionId
    };

    console.log('[ChapterWizard] Submitting chapter with plot:', {
      chapter_plot: initialData?.chapter_plot,
      climax: initialData?.chapter_plot?.climax,
      brainstorm_session_id: brainstormSessionId
    });

    // For edit mode, use the old simple flow (no progress overlay)
    if (chapterId) {
      try {
        await onComplete(chapterData, (status) => setStatusMessage(status.message));
      } catch (error) {
        setLoading(false);
        setStatusMessage(null);
        console.error('Failed to save chapter:', error);
      }
      return;
    }

    // For new chapter creation, show progress overlay
    const isFirstChapter = (chapterNumber || 1) === 1;
    const initialSteps: ProgressStep[] = isFirstChapter
      ? [{ label: 'Creating chapter', status: 'active' as StepStatus }]
      : [
          { label: 'Completing previous chapter', status: 'active' as StepStatus },
          { label: 'Creating chapter', status: 'pending' as StepStatus },
          { label: 'Generating story context', status: 'pending' as StepStatus, optional: true },
        ];

    setCreationSteps(initialSteps);
    setCreationPhase(true);
    setChapterCreated(false);
    setCreationError(null);
    setEnrichmentWarning(null);
    activeStepStartRef.current = Date.now();
    setElapsedSeconds(0);

    const handleStatusUpdate = (status: { message: string; step: string }) => {
      setStatusMessage(status.message);

      if (isFirstChapter) {
        // First chapter: single step — keep it active until onComplete resolves
        if (status.step === 'enrichment_complete' || status.step === 'enrichment_failed') {
          // Edge case: first chapter shouldn't have enrichment, but handle gracefully
        }
        return;
      }

      setCreationSteps(prev => {
        const next = [...prev];
        switch (status.step) {
          case 'completing_previous':
            // Step 1 active (already set in initial state)
            break;
          case 'generating_chapter_summary':
            // Sub-text for step 1
            next[0] = { ...next[0], subText: 'Summarizing scenes...' };
            break;
          case 'creating_chapter':
            // Step 1 done, step 2 active
            next[0] = { ...next[0], status: 'done', subText: undefined };
            next[1] = { ...next[1], status: 'active' };
            resetStepTimer();
            break;
          case 'generating_story_so_far':
            // Step 2 done, step 3 active — chapter exists at this point
            next[1] = { ...next[1], status: 'done' };
            next[2] = { ...next[2], status: 'active' };
            setChapterCreated(true);
            resetStepTimer();
            break;
          case 'enrichment_complete':
            // Step 3 done
            next[2] = { ...next[2], status: 'done' };
            // Stop the timer
            if (elapsedTimerRef.current) {
              clearInterval(elapsedTimerRef.current);
              elapsedTimerRef.current = null;
            }
            break;
          case 'enrichment_failed':
            // Step 3 warning
            next[2] = { ...next[2], status: 'warning' };
            setEnrichmentWarning(status.message);
            if (elapsedTimerRef.current) {
              clearInterval(elapsedTimerRef.current);
              elapsedTimerRef.current = null;
            }
            break;
        }
        return next;
      });

      // Mark chapter created on 'complete' event (the API client sends this as step)
      // Actually the 'complete' type is handled inside onComplete in the sidebar — we detect it via
      // the creating_chapter → generating_story_so_far transition or stream end
    };

    try {
      await onComplete(chapterData, handleStatusUpdate);
      // If we get here without error, the chapter was created successfully
      setChapterCreated(true);

      // For first chapter, mark single step as done
      if (isFirstChapter) {
        setCreationSteps([{ label: 'Creating chapter', status: 'done' as StepStatus }]);
      }

      // Stop timer
      if (elapsedTimerRef.current) {
        clearInterval(elapsedTimerRef.current);
        elapsedTimerRef.current = null;
      }
    } catch (error) {
      console.error('Failed to save chapter:', error);
      const errMsg = error instanceof Error ? error.message : 'Unknown error';
      // If the chapter was already created (step 2 done), don't show as fatal error
      // The sidebar will have already loaded the chapter
      setCreationSteps(prev => {
        const step2Done = prev.length >= 2 && prev[1]?.status === 'done';
        if (step2Done) {
          // Chapter exists — this error is from enrichment or post-creation
          setChapterCreated(true);
          setEnrichmentWarning(errMsg);
          if (prev.length >= 3) {
            const next = [...prev];
            next[2] = { ...next[2], status: 'warning' };
            return next;
          }
          return prev;
        }
        // Fatal error — chapter may not exist
        setCreationError(errMsg);
        return prev;
      });

      // Stop timer
      if (elapsedTimerRef.current) {
        clearInterval(elapsedTimerRef.current);
        elapsedTimerRef.current = null;
      }
    }
  };

  const handleStartWriting = useCallback(() => {
    if (onDone) {
      onDone();
    } else {
      onCancel();
    }
  }, [onDone, onCancel]);

  if (loadingData) {
    return (
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
        <div className="bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 p-8">
          <div className="w-16 h-16 border-4 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-white/80 text-center">Loading chapter setup...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 p-8 max-w-3xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-white">
            {chapterId ? `Edit Chapter ${chapterNumber || ''}` : (chapterNumber ? `Chapter ${chapterNumber} Setup` : 'Chapter Setup')}
          </h2>
          {/* Show close button only when not in creation progress, or when chapter is created/errored */}
          {(!creationPhase || chapterCreated || creationError) && (
            <button
              onClick={creationPhase ? handleStartWriting : onCancel}
              className="text-white/60 hover:text-white transition-colors"
            >
              <X className="w-6 h-6" />
            </button>
          )}
        </div>

        {/* Creation Progress Overlay */}
        {creationPhase ? (
          <CreationProgress
            steps={creationSteps}
            chapterCreated={chapterCreated}
            creationError={creationError}
            enrichmentWarning={enrichmentWarning}
            elapsedSeconds={elapsedSeconds}
            onStartWriting={handleStartWriting}
          />
        ) : (
        <>
        <div className="space-y-6">
          {/* Brainstorm Button / Plot Applied Indicator */}
          {onBrainstorm && (
            <div className={`border rounded-lg p-4 ${
              initialData?.chapter_plot 
                ? 'bg-gradient-to-r from-emerald-500/20 to-green-500/20 border-emerald-500/50' 
                : 'bg-gradient-to-r from-green-500/10 to-emerald-500/10 border-green-500/30'
            }`}>
              <div className="flex items-center justify-between">
                <div className="flex-1 mr-4">
                  {initialData?.chapter_plot ? (
                    <>
                      <h3 className="text-emerald-300 font-medium flex items-center gap-2">
                        ✓ Chapter Plot Applied
                      </h3>
                      <p className="text-white/60 text-sm mt-1">{initialData.chapter_plot.summary?.slice(0, 150)}...</p>
                      {initialData.mood && (
                        <p className="text-white/50 text-xs mt-1">
                          <span className="text-purple-300">Mood:</span> {initialData.mood}
                        </p>
                      )}
                      {initialData.chapter_plot.location && (
                        <p className="text-white/50 text-xs">
                          <span className="text-blue-300">Location:</span> {initialData.chapter_plot.location}
                        </p>
                      )}
                    </>
                  ) : (
                    <>
                      <h3 className="text-white font-medium">Need help planning this chapter?</h3>
                      <p className="text-white/60 text-sm">Brainstorm with AI to develop your chapter plot</p>
                    </>
                  )}
                </div>
                <button
                  onClick={onBrainstorm}
                  className={`px-4 py-2 text-white rounded-lg text-sm font-medium transition-colors flex-shrink-0 ${
                    initialData?.chapter_plot 
                      ? 'bg-emerald-600 hover:bg-emerald-700' 
                      : 'bg-green-600 hover:bg-green-700'
                  }`}
                >
                  {initialData?.chapter_plot ? '✏️ Edit Plot' : '💡 Brainstorm'}
                </button>
              </div>
            </div>
          )}

          {/* Story Arc Phase Selector */}
          {storyArc && storyArc.phases && storyArc.phases.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-white/80 mb-2">
                Story Arc Phase (optional)
              </label>
              <select
                value={selectedArcPhaseId || ''}
                onChange={(e) => setSelectedArcPhaseId(e.target.value || undefined)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-pink-500"
              >
                <option value="" className="bg-gray-800">No specific phase</option>
                {storyArc.phases.map((phase) => (
                  <option key={phase.id} value={phase.id} className="bg-gray-800">
                    {phase.name}
                  </option>
                ))}
              </select>
              {selectedArcPhaseId && storyArc.phases.find(p => p.id === selectedArcPhaseId) && (
                <p className="mt-2 text-sm text-white/60">
                  {storyArc.phases.find(p => p.id === selectedArcPhaseId)?.description}
                </p>
              )}
            </div>
          )}

          {/* Chapter Plot Display */}
          {initialData?.chapter_plot && (
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
              <h3 className="text-white font-medium mb-2 flex items-center gap-2">
                <FileText className="w-4 h-4" />
                Chapter Plot
              </h3>
              <p className="text-white/80 text-sm">
                {typeof initialData.chapter_plot === 'string' 
                  ? initialData.chapter_plot 
                  : initialData.chapter_plot.summary || 'Plot defined from brainstorming'}
              </p>
            </div>
          )}

          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-white/80 mb-2">
              Chapter Title (optional)
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-pink-500"
              placeholder={`Chapter ${chapterNumber || 1}`}
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-white/80 mb-2">
              Description (optional)
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-pink-500 resize-none"
              placeholder="Brief description of this chapter..."
            />
          </div>

          {/* Characters */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-white/80">
                Characters (select characters active in this chapter)
              </label>
              <button
                onClick={() => setShowCharacterQuickAdd(true)}
                className="flex items-center space-x-1 px-3 py-1 bg-pink-600 hover:bg-pink-700 text-white rounded-lg text-sm transition-colors"
              >
                <Plus className="w-4 h-4" />
                <span>Add Character</span>
              </button>
            </div>
            <div className="bg-white/5 rounded-lg p-4 border border-white/10">
              {availableCharacters.length === 0 && newCharacterIds.length === 0 ? (
                <p className="text-white/60 text-sm">No characters available. Add characters to your story first.</p>
              ) : (
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {/* Existing story characters */}
                  {availableCharacters.map((char, index) => (
                    <label
                      key={char.story_character_id || `char-${char.id}-${index}`}
                      className="flex items-start space-x-3 p-2 rounded hover:bg-white/5 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={selectedCharacterIds.includes(char.id)}
                        onChange={() => handleCharacterToggle(char.id)}
                        className="mt-1 w-4 h-4 text-pink-600 bg-white/10 border-white/20 rounded focus:ring-pink-500"
                      />
                      <div className="flex-1">
                        <div className="text-white font-medium">{char.name}</div>
                        {char.role && (
                          <div className="text-white/60 text-sm">{char.role}</div>
                        )}
                        {char.description && (
                          <div className="text-white/50 text-xs mt-1">{char.description}</div>
                        )}
                      </div>
                    </label>
                  ))}
                  {/* New characters from library */}
                  {newCharacterIds.map((charId) => {
                    const char = newCharacters[charId];
                    if (!char) return null;
                    return (
                      <label
                        key={`new-${charId}`}
                        className="flex items-start space-x-3 p-2 rounded hover:bg-white/5 cursor-pointer bg-pink-500/10 border border-pink-500/20"
                      >
                        <input
                          type="checkbox"
                          checked={true}
                          onChange={() => handleCharacterToggle(charId)}
                          className="mt-1 w-4 h-4 text-pink-600 bg-white/10 border-white/20 rounded focus:ring-pink-500"
                        />
                        <div className="flex-1">
                          <div className="text-white font-medium">
                            {char.name}
                            <span className="ml-2 text-xs text-pink-400">(new)</span>
                          </div>
                          {char.role && (
                            <div className="text-white/60 text-sm">{char.role}</div>
                          )}
                          {char.description && (
                            <div className="text-white/50 text-xs mt-1">{char.description}</div>
                          )}
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
            {(selectedCharacterIds.length > 0 || newCharacterIds.length > 0) && (
              <p className="mt-2 text-white/60 text-sm">
                {selectedCharacterIds.length + newCharacterIds.length} character{(selectedCharacterIds.length + newCharacterIds.length) !== 1 ? 's' : ''} selected
                {newCharacterIds.length > 0 && (
                  <span className="ml-2 text-pink-400">
                    ({newCharacterIds.length} new to story)
                  </span>
                )}
              </p>
            )}
          </div>

          {/* Location */}
          <div>
            <label className="block text-sm font-medium text-white/80 mb-2 flex items-center space-x-2">
              <MapPin className="w-4 h-4" />
              <span>Location (optional)</span>
            </label>
            <div className="flex space-x-2">
              {availableLocations.length > 0 && (
                <select
                  value={locationName}
                  onChange={(e) => setLocationName(e.target.value)}
                  className="flex-1 px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-pink-500"
                >
                  <option value="">Select or type new location...</option>
                  {availableLocations.map((loc) => (
                    <option key={loc} value={loc} className="bg-gray-800">
                      {loc}
                    </option>
                  ))}
                </select>
              )}
              <input
                type="text"
                value={locationName}
                onChange={(e) => setLocationName(e.target.value)}
                placeholder={availableLocations.length > 0 ? "Or type new location..." : "Enter location..."}
                className="flex-1 px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-pink-500"
              />
            </div>
          </div>

          {/* Time Period */}
          <div>
            <label className="block text-sm font-medium text-white/80 mb-2 flex items-center space-x-2">
              <Clock className="w-4 h-4" />
              <span>Time Period (optional)</span>
            </label>
            <input
              type="text"
              value={timePeriod}
              onChange={(e) => setTimePeriod(e.target.value)}
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-pink-500"
              placeholder="e.g., Morning, Evening, 1920s, Future..."
            />
          </div>

          {/* Scenario */}
          <div>
            <label className="block text-sm font-medium text-white/80 mb-2 flex items-center space-x-2">
              <FileText className="w-4 h-4" />
              <span>Chapter Scenario (optional)</span>
            </label>
            <textarea
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              rows={4}
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-pink-500 resize-none"
              placeholder="Describe the scenario or situation for this chapter..."
            />
          </div>

          {/* Continues from Previous Chapter */}
          <div>
            <label className="flex items-center space-x-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition-colors">
              <input
                type="checkbox"
                checked={continuesFromPrevious}
                onChange={(e) => setContinuesFromPrevious(e.target.checked)}
                className="w-5 h-5 text-pink-600 bg-white/10 border-white/20 rounded focus:ring-pink-500"
              />
              <div className="flex-1">
                <div className="text-white font-medium">Chapter directly follows previous chapter?</div>
                <div className="text-white/60 text-sm mt-1">
                  If enabled, recent scenes from the previous chapter will be included in context for continuity.
                </div>
              </div>
            </label>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end space-x-4 mt-8">
          <button
            onClick={onCancel}
            className="px-6 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-6 py-2 bg-pink-600 hover:bg-pink-700 disabled:bg-pink-800 disabled:opacity-50 text-white rounded-lg transition-colors flex items-center space-x-2"
          >
            {loading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                <span>{chapterId ? 'Updating...' : 'Creating...'}</span>
              </>
            ) : (
              <>
                <Check className="w-4 h-4" />
                <span>{chapterId ? 'Update' : 'Continue'}</span>
              </>
            )}
          </button>
          {statusMessage && (
            <div className="mt-4 p-3 bg-white/10 rounded-lg border border-white/20">
              <p className="text-white/80 text-sm">{statusMessage}</p>
            </div>
          )}
        </div>
        </>
        )}
      </div>

      {/* Character Quick Add Modal */}
      {showCharacterQuickAdd && (
        <CharacterQuickAdd
          onCharacterAdd={handleCharacterAdd}
          onClose={() => setShowCharacterQuickAdd(false)}
          existingCharacters={availableCharacters.map(c => ({
            id: c.id,
            name: c.name,
            role: c.role || '',
            description: c.description || ''
          }))}
          storyId={storyId}
        />
      )}
    </div>
  );
}

