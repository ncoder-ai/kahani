'use client';

import { useState } from 'react';
import { StoryData } from '@/app/create-story/page';
import apiClient from '@/lib/api';
import CharacterDisplay from '@/components/CharacterDisplay';

interface TitleInputProps {
  storyData: StoryData;
  onUpdate: (data: Partial<StoryData>) => void;
  onNext: () => void;
  onBack: () => void;
}

const TITLE_SUGGESTIONS = [
  'The Last {genre}',
  'Secrets of {setting}',
  'Beyond the {setting}',
  'The {character} Chronicles',
  'Quest for {goal}',
  'The {adjective} {noun}',
  'When {action} Calls',
  'The {time} of {setting}'
];

export default function TitleInput({ storyData, onUpdate, onNext, onBack }: TitleInputProps) {
  const [title, setTitle] = useState(storyData.title || '');
  const [description, setDescription] = useState(storyData.description || '');
  const [suggestedTitles, setSuggestedTitles] = useState<string[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);

  const generateLLMTitles = async () => {
    setIsGenerating(true);
    try {
      const response = await apiClient.generateTitles({
        genre: storyData.genre,
        tone: storyData.tone,
        scenario: storyData.scenario,
        characters: storyData.characters || [],
        story_elements: {
          world_setting: storyData.world_setting,
          plot_points: storyData.plot_points
        }
      });

      if (response && response.titles) {
        setSuggestedTitles(response.titles);
      } else {
        // Fallback to template-based generation
        generateTitleSuggestion();
      }
    } catch (error) {
      console.error('Failed to generate LLM titles:', error);
      // Fallback to template-based generation
      generateTitleSuggestion();
    } finally {
      setIsGenerating(false);
    }
  };

  const generateTitleSuggestion = () => {
    const templates = TITLE_SUGGESTIONS;
    const template = templates[Math.floor(Math.random() * templates.length)];
    
    // Simple replacements based on genre
    const replacements: Record<string, string[]> = {
      '{genre}': ['Wizard', 'Warrior', 'Dragon', 'Mystery', 'Adventure', 'Hero'],
      '{setting}': ['Realm', 'Kingdom', 'City', 'Forest', 'Mountain', 'Ocean'],
      '{character}': ['Shadow', 'Silver', 'Golden', 'Ancient', 'Lost', 'Hidden'],
      '{goal}': ['Freedom', 'Truth', 'Power', 'Love', 'Peace', 'Justice'],
      '{adjective}': ['Ancient', 'Forgotten', 'Hidden', 'Sacred', 'Lost', 'Eternal'],
      '{noun}': ['Crown', 'Sword', 'Key', 'Stone', 'Star', 'Heart'],
      '{action}': ['Destiny', 'Adventure', 'Magic', 'Danger', 'Love', 'War'],
      '{time}': ['Dawn', 'Age', 'Era', 'Time', 'Season', 'Hour']
    };

    let suggestion = template;
    Object.entries(replacements).forEach(([placeholder, options]) => {
      if (suggestion.includes(placeholder)) {
        const option = options[Math.floor(Math.random() * options.length)];
        suggestion = suggestion.replace(placeholder, option);
      }
    });

    setTitle(suggestion);
    onUpdate({ title: suggestion });
  };

  const selectSuggestedTitle = (selectedTitle: string) => {
    setTitle(selectedTitle);
    onUpdate({ title: selectedTitle });
  };

  const handleTitleChange = (value: string) => {
    setTitle(value);
    onUpdate({ title: value });
  };

  const handleDescriptionChange = (value: string) => {
    setDescription(value);
    onUpdate({ description: value });
  };

  const canProceed = title.trim().length > 2;

  return (
    <div className="space-y-8">
      <div className="text-center">
        <h2 className="text-3xl font-bold text-white mb-4">Give Your Story a Title</h2>
        <p className="text-white/80 text-lg">
          Choose a title that captures the essence of your story
        </p>
      </div>

      {/* Character Display */}
      <CharacterDisplay characters={storyData.characters} />

      {/* Title Input */}
      <div className="space-y-4">
        <div className="relative">
          <input
            type="text"
            value={title}
            onChange={(e) => handleTitleChange(e.target.value)}
            placeholder="Enter your story title..."
            className="w-full p-6 text-2xl font-bold bg-white/10 border border-white/30 rounded-2xl text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent text-center"
          />
          {title && (
            <div className="absolute top-2 right-2">
              <button
                onClick={() => handleTitleChange('')}
                className="p-2 text-white/60 hover:text-white transition-colors"
              >
                ✕
              </button>
            </div>
          )}
        </div>

        <div className="flex justify-center space-x-4">
          <button
            onClick={generateLLMTitles}
            disabled={isGenerating}
            className="px-6 py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-xl hover:from-purple-600 hover:to-pink-600 transition-colors font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isGenerating ? (
              <>
                <span className="animate-spin inline-block mr-2">⚡</span>
                Generating AI Titles...
              </>
            ) : (
              <>
                ✨ Generate AI Titles
              </>
            )}
          </button>
          <button
            onClick={generateTitleSuggestion}
            className="px-4 py-2 bg-white/20 border border-white/30 text-white rounded-lg hover:bg-white/30 transition-colors text-sm"
          >
            🎲 Random Title
          </button>
        </div>

        {/* AI-Generated Title Suggestions */}
        {suggestedTitles.length > 0 && (
          <div className="mt-6">
            <h3 className="text-lg font-semibold text-white mb-3">AI-Generated Suggestions:</h3>
            <div className="grid grid-cols-1 gap-2">
              {suggestedTitles.map((suggestedTitle, index) => (
                <button
                  key={index}
                  onClick={() => selectSuggestedTitle(suggestedTitle)}
                  className="p-3 bg-white/10 border border-white/20 rounded-lg text-white hover:bg-white/20 transition-colors text-left font-medium"
                >
                  {suggestedTitle}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Genre and Tone Display */}
      <div className="bg-white/5 rounded-xl p-6 text-center">
        <p className="text-white/80 mb-2">Your story will be:</p>
        <div className="flex justify-center space-x-4">
          <span className="bg-gradient-to-r from-purple-500 to-pink-500 text-white px-4 py-2 rounded-lg font-semibold">
            {storyData.genre?.charAt(0).toUpperCase() + storyData.genre?.slice(1)}
          </span>
          <span className="bg-gradient-to-r from-blue-500 to-cyan-500 text-white px-4 py-2 rounded-lg font-semibold">
            {storyData.tone?.charAt(0).toUpperCase() + storyData.tone?.slice(1)}
          </span>
        </div>
      </div>

      {/* Description Input */}
      <div className="space-y-3">
        <h3 className="text-xl font-semibold text-white">Story Description (Optional)</h3>
        <textarea
          value={description}
          onChange={(e) => handleDescriptionChange(e.target.value)}
          placeholder="Write a brief description of your story..."
          rows={3}
          className="w-full p-4 bg-white/10 border border-white/30 rounded-xl text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
        />
      </div>

      {/* Navigation */}
      <div className="flex justify-between pt-6">
        <button
          onClick={onBack}
          className="px-8 py-3 rounded-xl font-semibold bg-white/20 text-white hover:bg-white/30 transition-colors"
        >
          ← Back
        </button>
        <button
          onClick={onNext}
          disabled={!canProceed}
          className={`px-8 py-3 rounded-xl font-semibold transition-all duration-200 ${
            canProceed
              ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white hover:from-purple-600 hover:to-pink-600'
              : 'bg-white/20 text-white/50 cursor-not-allowed'
          }`}
        >
          Continue →
        </button>
      </div>
    </div>
  );
}