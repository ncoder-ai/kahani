/**
 * Server-Sent Events (SSE) streaming utilities.
 *
 * This module provides reusable functions for processing SSE streams from the backend.
 * It handles buffer management, line parsing, and callback dispatching.
 *
 * Example usage:
 *
 * ```typescript
 * import { processSSEStream, SSECallbacks } from '@/lib/http/streaming';
 *
 * const callbacks: SSECallbacks = {
 *   onContent: (chunk) => setContent(prev => prev + chunk),
 *   onComplete: (data) => console.log('Stream complete', data),
 *   onError: (error) => console.error('Stream error', error),
 * };
 *
 * await processSSEStream(response, callbacks);
 * ```
 */

export interface SSEEvent {
  type: string;
  chunk?: string;
  [key: string]: unknown;
}

export interface SSECallbacks {
  /** Called when a content chunk is received */
  onContent?: (chunk: string) => void;
  /** Called when thinking/reasoning starts */
  onThinkingStart?: () => void;
  /** Called when a thinking chunk is received */
  onThinkingChunk?: (chunk: string) => void;
  /** Called when thinking/reasoning ends */
  onThinkingEnd?: (totalChars: number) => void;
  /** Called when auto-play is ready */
  onAutoPlayReady?: (sessionId: string, sceneId: number) => void;
  /** Called when the stream completes */
  onComplete?: (data: SSEEvent) => void;
  /** Called on any error */
  onError?: (error: Error) => void;
  /** Called for any custom event type not handled above */
  onCustomEvent?: (event: SSEEvent) => void;
}

/**
 * Parse a single SSE line and extract the data.
 *
 * @param line - The raw SSE line (e.g., "data: {...}")
 * @returns The parsed JSON data, or null if the line is invalid or [DONE]
 */
export function parseSSELine(line: string): SSEEvent | null | 'DONE' {
  if (!line.startsWith('data: ')) {
    return null;
  }

  const data = line.slice(6).trim();

  if (data === '[DONE]') {
    return 'DONE';
  }

  if (!data) {
    return null;
  }

  try {
    return JSON.parse(data) as SSEEvent;
  } catch (error) {
    console.warn('[SSE] Failed to parse line:', data, error);
    return null;
  }
}

/**
 * Process an SSE stream from a fetch response.
 *
 * @param response - The fetch response with a readable stream body
 * @param callbacks - Callbacks for different event types
 * @param options - Additional options
 * @returns Promise that resolves when the stream is complete
 */
export async function processSSEStream(
  response: Response,
  callbacks: SSECallbacks,
  options: {
    /** Timeout in milliseconds (default: 300000 = 5 minutes) */
    timeout?: number;
    /** Abort signal for cancellation */
    signal?: AbortSignal;
  } = {}
): Promise<void> {
  const { timeout = 300000, signal } = options;

  if (!response.body) {
    throw new Error('No response body');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let timeoutId: ReturnType<typeof setTimeout> | undefined;

  // Set up timeout
  if (timeout > 0) {
    timeoutId = setTimeout(() => {
      reader.cancel('Timeout');
      callbacks.onError?.(new Error(`SSE stream timeout after ${timeout}ms`));
    }, timeout);
  }

  // Handle abort signal
  if (signal) {
    signal.addEventListener('abort', () => {
      reader.cancel('Aborted');
      if (timeoutId) clearTimeout(timeoutId);
    });
  }

  try {
    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        // Process any remaining data in buffer
        if (buffer.trim()) {
          const result = parseSSELine(buffer);
          if (result && result !== 'DONE') {
            dispatchEvent(result, callbacks);
          }
        }
        break;
      }

      // Decode and add to buffer
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      // Keep the last potentially incomplete line in buffer
      buffer = lines.pop() || '';

      // Process complete lines
      for (const line of lines) {
        const result = parseSSELine(line);

        if (result === 'DONE') {
          if (timeoutId) clearTimeout(timeoutId);
          return;
        }

        if (result) {
          dispatchEvent(result, callbacks);

          // Check for completion events
          if (result.type === 'complete' || result.type === 'multi_complete') {
            if (timeoutId) clearTimeout(timeoutId);
            return;
          }
        }
      }
    }
  } catch (error) {
    if (timeoutId) clearTimeout(timeoutId);
    const err = error instanceof Error ? error : new Error(String(error));
    callbacks.onError?.(err);
    throw err;
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}

/**
 * Dispatch an SSE event to the appropriate callback.
 */
function dispatchEvent(event: SSEEvent, callbacks: SSECallbacks): void {
  switch (event.type) {
    case 'content':
      if (event.chunk && callbacks.onContent) {
        callbacks.onContent(event.chunk);
      }
      break;

    case 'thinking_start':
      callbacks.onThinkingStart?.();
      break;

    case 'thinking_chunk':
      if (event.chunk && callbacks.onThinkingChunk) {
        callbacks.onThinkingChunk(event.chunk);
      }
      break;

    case 'thinking_end':
      callbacks.onThinkingEnd?.(event.total_chars as number || 0);
      break;

    case 'auto_play_ready':
      if (callbacks.onAutoPlayReady) {
        callbacks.onAutoPlayReady(
          event.auto_play_session_id as string,
          event.scene_id as number
        );
      }
      break;

    case 'complete':
    case 'multi_complete':
      callbacks.onComplete?.(event);
      break;

    case 'error':
      callbacks.onError?.(new Error(event.message as string || 'Unknown error'));
      break;

    default:
      callbacks.onCustomEvent?.(event);
      break;
  }
}

/**
 * Create a simple streaming reader from a response.
 * For cases where you need more control over the streaming process.
 *
 * @param response - The fetch response
 * @returns An async generator yielding SSE events
 */
export async function* createSSEEventGenerator(
  response: Response
): AsyncGenerator<SSEEvent | 'DONE', void, unknown> {
  if (!response.body) {
    throw new Error('No response body');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        if (buffer.trim()) {
          const result = parseSSELine(buffer);
          if (result) yield result;
        }
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const result = parseSSELine(line);
        if (result) yield result;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
