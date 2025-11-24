'use client';

import React, { useState, useEffect } from 'react';
import { useConfig } from '@/contexts/ConfigContext';

export default function STTDebugPage() {
  const config = useConfig(); // Use config from React context
  const [logs, setLogs] = useState<string[]>([]);
  const [deviceInfo, setDeviceInfo] = useState<any>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [wsStatus, setWsStatus] = useState<string>('disconnected');

  const addLog = (message: string) => {
    setLogs(prev => [...prev, `${new Date().toLocaleTimeString()}: ${message}`]);
  };

  useEffect(() => {
    const loadConfigAndTest = async () => {
      try {
        const apiBaseUrl = await config.getApiBaseUrl();
        const sttPath = await config.getSTTWebSocketPath();
        const backendPort = await config.getBackendPort();
        
        addLog('Page loaded, testing API endpoints...');
        
        // Test device info
        fetch(`${apiBaseUrl}${sttPath}/device-info`)
          .then(response => {
            addLog(`Device info response: ${response.status}`);
            return response.json();
          })
          .then(data => {
            addLog(`Device info data: ${JSON.stringify(data)}`);
            setDeviceInfo(data);
          })
          .catch(error => {
            addLog(`Device info error: ${error.message}`);
          });

        // Test session creation
        fetch(`${apiBaseUrl}${sttPath}/create-session`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        })
          .then(response => {
            addLog(`Session creation response: ${response.status}`);
            return response.json();
          })
          .then(data => {
            addLog(`Session creation data: ${JSON.stringify(data)}`);
            setSessionId(data.session_id);
            
            // Test WebSocket connection
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const hostname = window.location.hostname;
            const wsUrl = `${protocol}//${hostname}:${backendPort}${sttPath}/${data.session_id}`;
            addLog(`Attempting WebSocket connection to: ${wsUrl}`);
            
            const ws = new WebSocket(wsUrl);
            
            ws.onopen = () => {
              addLog('WebSocket connected successfully!');
              setWsStatus('connected');
            };
            
            ws.onerror = (error) => {
          addLog(`WebSocket error: ${error}`);
          setWsStatus('error');
        };
        
        ws.onclose = (event) => {
          addLog(`WebSocket closed: ${event.code} - ${event.reason}`);
          setWsStatus('disconnected');
        };
        
        ws.onmessage = (event) => {
          addLog(`WebSocket message: ${event.data}`);
        };
        
        // Close after 5 seconds
        setTimeout(() => {
          ws.close();
          addLog('WebSocket closed after 5 seconds');
        }, 5000);
      })
      .catch(error => {
        addLog(`Session creation error: ${error.message}`);
      });
      } catch (error) {
        addLog(`Failed to load config: ${error instanceof Error ? error.message : 'Unknown error'}`);
      }
    };
    
    loadConfigAndTest();
  }, []);

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-6">STT Debug Page</h1>
        
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold mb-4">Status</h2>
            <div className="space-y-2">
              <div>Device Info: {deviceInfo ? '✅ Loaded' : '❌ Failed'}</div>
              <div>Session ID: {sessionId || '❌ Not created'}</div>
              <div>WebSocket: {wsStatus}</div>
            </div>
          </div>
          
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold mb-4">Device Info</h2>
            <pre className="text-sm text-gray-300">
              {deviceInfo ? JSON.stringify(deviceInfo, null, 2) : 'Loading...'}
            </pre>
          </div>
        </div>
        
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">Debug Logs</h2>
          <div className="bg-gray-900 rounded p-4 max-h-96 overflow-y-auto">
            {logs.map((log, index) => (
              <div key={index} className="text-sm text-gray-300 mb-1">
                {log}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
