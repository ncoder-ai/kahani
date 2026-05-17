'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useRealtimeSTT } from '../../hooks/useRealtimeSTT';
import { useConfig } from '@/contexts/ConfigContext';

interface PerformanceMetrics {
  latency: number | null;
  totalTranscriptions: number;
  averageLatency: number;
  startTime: number | null;
  endTime: number | null;
}

export default function STTTestPage() {
  const config = useConfig(); // Use config from React context
  const [metrics, setMetrics] = useState<PerformanceMetrics>({
    latency: null,
    totalTranscriptions: 0,
    averageLatency: 0,
    startTime: null,
    endTime: null
  });

  const [deviceInfo, setDeviceInfo] = useState<{
    device: string;
    computeType: string;
    model: string;
  } | null>(null);

  const latencyHistoryRef = useRef<number[]>([]);
  const testStartTimeRef = useRef<number | null>(null);

  const {
    isConnected,
    isRecording,
    isTranscribing,
    transcript,
    partialTranscript,
    error,
    latency,
    startTranscription,
    stopTranscription,
    clearTranscript,
    isReady
  } = useRealtimeSTT({
    onTranscript: (text, isPartial) => {
      if (!isPartial) {
        // Update metrics for final transcriptions
        setMetrics(prev => ({
          ...prev,
          totalTranscriptions: prev.totalTranscriptions + 1,
          latency: latency
        }));

        if (latency) {
          latencyHistoryRef.current.push(latency);
          const avgLatency = latencyHistoryRef.current.reduce((a, b) => a + b, 0) / latencyHistoryRef.current.length;
          setMetrics(prev => ({
            ...prev,
            averageLatency: avgLatency
          }));
        }
      }
    },
    onError: (error) => {
      console.error('[STT Test] Error:', error);
    },
    onStatusChange: (recording, transcribing) => {
    }
  });

  // Fetch device info on mount
  useEffect(() => {
    fetchDeviceInfo();
  }, []);

  const fetchDeviceInfo = async () => {
    try {
      const apiBaseUrl = await config.getApiBaseUrl();
      const sttPath = await config.getSTTWebSocketPath();
      const response = await fetch(`${apiBaseUrl}${sttPath}/device-info`);
      if (response.ok) {
        const info = await response.json();
        setDeviceInfo(info);
      }
    } catch (error) {
      console.error('Failed to fetch device info:', error);
    }
  };

  const handleStartTest = useCallback(() => {
    testStartTimeRef.current = Date.now();
    setMetrics(prev => ({
      ...prev,
      startTime: Date.now(),
      endTime: null,
      totalTranscriptions: 0,
      latency: null
    }));
    latencyHistoryRef.current = [];
    clearTranscript();
    startTranscription();
  }, [startTranscription, clearTranscript]);

  const handleStopTest = useCallback(() => {
    stopTranscription();
    setMetrics(prev => ({
      ...prev,
      endTime: Date.now()
    }));
  }, [stopTranscription]);

  const handleClear = useCallback(() => {
    clearTranscript();
    setMetrics({
      latency: null,
      totalTranscriptions: 0,
      averageLatency: 0,
      startTime: null,
      endTime: null
    });
    latencyHistoryRef.current = [];
  }, [clearTranscript]);

  const copyToClipboard = useCallback(() => {
    navigator.clipboard.writeText(transcript);
  }, [transcript]);

  const getStatusColor = () => {
    if (error) return 'text-red-500';
    if (isTranscribing) return 'text-yellow-500';
    if (isRecording) return 'text-green-500';
    if (isConnected) return 'text-blue-500';
    return 'text-gray-500';
  };

  const getStatusText = () => {
    if (error) return 'Error';
    if (isTranscribing) return 'Transcribing...';
    if (isRecording) return 'Recording...';
    if (isConnected) return 'Connected';
    return 'Disconnected';
  };

  const formatLatency = (latency: number | null) => {
    if (latency === null) return 'N/A';
    return `${latency.toFixed(0)}ms`;
  };

  const formatDuration = (start: number | null, end: number | null) => {
    if (!start) return '0s';
    const endTime = end || Date.now();
    const duration = Math.floor((endTime - start) / 1000);
    return `${duration}s`;
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Real-time STT Test</h1>
          <p className="text-gray-400">
            Test Whisper-based Speech-to-Text performance with real-time metrics
          </p>
        </div>

        {/* Device Info */}
        {deviceInfo && (
          <div className="bg-gray-800 rounded-lg p-4 mb-6">
            <h2 className="text-lg font-semibold mb-2">Device Configuration</h2>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-gray-400">Device:</span>
                <span className="ml-2 font-mono">{deviceInfo.device}</span>
              </div>
              <div>
                <span className="text-gray-400">Compute Type:</span>
                <span className="ml-2 font-mono">{deviceInfo.computeType}</span>
              </div>
              <div>
                <span className="text-gray-400">Model:</span>
                <span className="ml-2 font-mono">{deviceInfo.model}</span>
              </div>
            </div>
          </div>
        )}

        {/* Status and Controls */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* Status Panel */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold mb-4">Status</h2>
            
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-gray-400">Connection:</span>
                <span className={`font-mono ${getStatusColor()}`}>
                  {getStatusText()}
                </span>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="text-gray-400">Recording:</span>
                <span className={isRecording ? 'text-green-500' : 'text-gray-500'}>
                  {isRecording ? 'Yes' : 'No'}
                </span>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="text-gray-400">Transcribing:</span>
                <span className={isTranscribing ? 'text-yellow-500' : 'text-gray-500'}>
                  {isTranscribing ? 'Yes' : 'No'}
                </span>
              </div>
              
              {deviceInfo && (
                <>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400">Model:</span>
                    <span className="text-blue-400 font-semibold">{deviceInfo.model}</span>
                  </div>
                  
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400">Device:</span>
                    <span className="text-blue-400">{deviceInfo.device} ({deviceInfo.computeType})</span>
                  </div>
                </>
              )}
            </div>

            {error && (
              <div className="mt-4 p-3 bg-red-900/20 border border-red-500/30 rounded">
                <p className="text-red-400 text-sm">{error}</p>
              </div>
            )}
          </div>

          {/* Controls Panel */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold mb-4">Controls</h2>
            
            <div className="space-y-4">
              <div className="flex gap-2">
                <button
                  onClick={handleStartTest}
                  disabled={!isReady || isRecording}
                  className="flex-1 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:opacity-50 text-white px-4 py-2 rounded-lg font-medium transition-colors"
                >
                  {isRecording ? 'Recording...' : 'Start Test'}
                </button>
                
                <button
                  onClick={handleStopTest}
                  disabled={!isRecording}
                  className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 disabled:opacity-50 text-white px-4 py-2 rounded-lg font-medium transition-colors"
                >
                  Stop
                </button>
              </div>
              
              <div className="flex gap-2">
                <button
                  onClick={handleClear}
                  className="flex-1 bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
                >
                  Clear
                </button>
                
                <button
                  onClick={copyToClipboard}
                  disabled={!transcript}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:opacity-50 text-white px-4 py-2 rounded-lg font-medium transition-colors"
                >
                  Copy Text
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Performance Metrics */}
        <div className="bg-gray-800 rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Performance Metrics</h2>
          
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-400">
                {formatLatency(metrics.latency)}
              </div>
              <div className="text-sm text-gray-400">Current Latency</div>
            </div>
            
            <div className="text-center">
              <div className="text-2xl font-bold text-green-400">
                {formatLatency(metrics.averageLatency)}
              </div>
              <div className="text-sm text-gray-400">Avg Latency</div>
            </div>
            
            <div className="text-center">
              <div className="text-2xl font-bold text-purple-400">
                {metrics.totalTranscriptions}
              </div>
              <div className="text-sm text-gray-400">Transcriptions</div>
            </div>
            
            <div className="text-center">
              <div className="text-2xl font-bold text-orange-400">
                {formatDuration(metrics.startTime, metrics.endTime)}
              </div>
              <div className="text-sm text-gray-400">Test Duration</div>
            </div>
          </div>
        </div>

        {/* Transcription Display */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">Transcription</h2>
          
          <div className="min-h-[200px] bg-gray-900 rounded-lg p-4 border border-gray-700">
            {/* Final transcript */}
            {transcript && (
              <div className="text-white whitespace-pre-wrap mb-2">
                {transcript}
              </div>
            )}
            
            {/* Partial transcript */}
            {partialTranscript && (
              <div className="text-gray-400 italic">
                {partialTranscript}
                <span className="animate-pulse">|</span>
              </div>
            )}
            
            {/* Empty state */}
            {!transcript && !partialTranscript && (
              <div className="text-gray-500 text-center py-8">
                {isRecording ? 'Listening...' : 'Click "Start Test" to begin transcription'}
              </div>
            )}
          </div>
          
          {/* Word count */}
          <div className="mt-2 text-sm text-gray-400">
            Words: {transcript.split(/\s+/).filter(word => word.length > 0).length}
          </div>
        </div>

        {/* Instructions */}
        <div className="mt-6 bg-blue-900/20 border border-blue-500/30 rounded-lg p-4">
          <h3 className="font-semibold text-blue-400 mb-2">Test Instructions</h3>
          <ul className="text-sm text-gray-300 space-y-1">
            <li>• Click "Start Test" and speak continuously without pauses</li>
            <li>• Transcription updates every 2 seconds with real-time accumulation</li>
            <li>• Current model: <span className="text-blue-400 font-semibold">{deviceInfo?.model || 'loading...'}</span> (check Status panel)</li>
            <li>• To switch models: Go to Settings → Voice Settings → Change STT Model Quality</li>
            <li>• Compare quality: "base" (fast) vs "small" (better) vs "medium" (best)</li>
            <li>• Use "Copy Text" to save results for comparison</li>
            <li>• <strong>New:</strong> Microphone buttons now appear in Continue Scene and Director Mode!</li>
            <li>• <strong>New:</strong> STT can be enabled/disabled per-user in Voice Settings</li>
            <li>• <strong>New:</strong> Each user can choose their own model preference</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
