'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';

interface SearchableSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: string[];
  placeholder?: string;
  className?: string;
}

export default function SearchableSelect({
  value,
  onChange,
  options,
  placeholder = 'Select...',
  className = '',
}: SearchableSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [highlightIndex, setHighlightIndex] = useState(0);

  const filtered = search
    ? options.filter((o) => o.toLowerCase().includes(search.toLowerCase()))
    : options;

  // Reset highlight when filtered list changes
  useEffect(() => {
    setHighlightIndex(0);
  }, [filtered.length, search]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (isOpen && listRef.current) {
      const item = listRef.current.children[highlightIndex] as HTMLElement | undefined;
      item?.scrollIntoView({ block: 'nearest' });
    }
  }, [highlightIndex, isOpen]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setSearch('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const open = useCallback(() => {
    setIsOpen(true);
    setSearch('');
    setTimeout(() => inputRef.current?.focus(), 0);
  }, []);

  const select = useCallback(
    (val: string) => {
      onChange(val);
      setIsOpen(false);
      setSearch('');
    },
    [onChange]
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filtered[highlightIndex]) {
        select(filtered[highlightIndex]);
      }
    } else if (e.key === 'Escape') {
      setIsOpen(false);
      setSearch('');
    }
  };

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {/* Closed state - shows selected value */}
      {!isOpen && (
        <button
          type="button"
          onClick={open}
          className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-left text-white flex items-center justify-between"
        >
          <span className={value ? 'text-white' : 'text-gray-400'}>
            {value || placeholder}
          </span>
          <svg className="w-4 h-4 text-gray-400 ml-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      )}

      {/* Open state - search input + dropdown */}
      {isOpen && (
        <>
          <input
            ref={inputRef}
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type to filter..."
            className="w-full bg-gray-700 border border-gray-600 rounded-md px-3 py-2 text-white placeholder-gray-400 outline-none focus:border-blue-500"
          />
          <ul
            ref={listRef}
            className="absolute z-50 mt-1 w-full bg-gray-700 border border-gray-600 rounded-md max-h-60 overflow-y-auto shadow-lg"
          >
            {filtered.length === 0 ? (
              <li className="px-3 py-2 text-gray-400 text-sm">No models found</li>
            ) : (
              filtered.map((option, i) => (
                <li
                  key={option}
                  onClick={() => select(option)}
                  onMouseEnter={() => setHighlightIndex(i)}
                  className={`px-3 py-1.5 text-sm cursor-pointer ${
                    i === highlightIndex
                      ? 'bg-blue-600 text-white'
                      : option === value
                        ? 'bg-gray-600 text-white'
                        : 'text-gray-200 hover:bg-gray-600'
                  }`}
                >
                  {option}
                </li>
              ))
            )}
          </ul>
        </>
      )}
    </div>
  );
}
