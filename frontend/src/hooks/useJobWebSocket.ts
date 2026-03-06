/**
 * useJobWebSocket
 *
 * React hook that opens a WebSocket to the backend /ws/jobs/{jobId} endpoint
 * and dispatches incoming events to the caller via callbacks.
 *
 * The WebSocket is only opened while the job is in an active state
 * (queued / instance_creating / running).  It closes automatically once a
 * `job_finished` event is received.
 *
 * Authentication uses the JWT stored in localStorage under `access_token`,
 * passed as a query parameter because WebSocket handshakes cannot carry
 * custom HTTP headers.
 *
 * Reconnection: on unexpected close the hook retries after 5 s (up to the
 * component being unmounted or `jobId` changing).
 */

import { useEffect, useRef, useCallback, useState } from 'react';

// ── Event payload types ────────────────────────────────────────────────────────

export interface JobUpdateData {
  status: string;
  progress: number;
  status_message: string | null;
  error_message: string | null;
  time_started: string | null;
  time_finished: string | null;
  actual_cost: number;
  estimated_time: number | null;
}

export interface JobFinishedData extends JobUpdateData {
  total_cracked: number;
}

export interface LogUpdateData {
  lines: string[];
  append: boolean;
}

export interface PotUpdateData {
  total_cracked: number;
  preview: string[];
  truncated: boolean;
}

export interface WsEvent {
  event: string;
  job_id: string;
  data: Record<string, unknown>;
}

// ── Hook interface ─────────────────────────────────────────────────────────────

export interface UseJobWebSocketOptions {
  /** UUID of the job to subscribe to */
  jobId: string;
  /** Whether the job is currently in an active state */
  active: boolean;
  onJobUpdate?: (data: JobUpdateData) => void;
  onJobFinished?: (data: JobFinishedData) => void;
  onLogUpdate?: (data: LogUpdateData) => void;
  onPotUpdate?: (data: PotUpdateData) => void;
  onError?: (message: string) => void;
}

export interface UseJobWebSocketResult {
  connected: boolean;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function getWsBaseUrl(): string {
  if (typeof window === 'undefined') return '';
  const isLocal = window.location.hostname === 'localhost';
  const apiOrigin = isLocal
    ? 'http://localhost:8000'
    : `${window.location.protocol}//${window.location.host}`;
  // Convert http(s) → ws(s)
  return apiOrigin.replace(/^http/, 'ws');
}

// ── Hook ───────────────────────────────────────────────────────────────────────

export function useJobWebSocket({
  jobId,
  active,
  onJobUpdate,
  onJobFinished,
  onLogUpdate,
  onPotUpdate,
  onError,
}: UseJobWebSocketOptions): UseJobWebSocketResult {
  const [connected, setConnected] = useState(false);

  // Keep latest callbacks in refs so the WS handler closure never stales
  const cbJobUpdate = useRef(onJobUpdate);
  const cbJobFinished = useRef(onJobFinished);
  const cbLogUpdate = useRef(onLogUpdate);
  const cbPotUpdate = useRef(onPotUpdate);
  const cbError = useRef(onError);

  useEffect(() => { cbJobUpdate.current = onJobUpdate; }, [onJobUpdate]);
  useEffect(() => { cbJobFinished.current = onJobFinished; }, [onJobFinished]);
  useEffect(() => { cbLogUpdate.current = onLogUpdate; }, [onLogUpdate]);
  useEffect(() => { cbPotUpdate.current = onPotUpdate; }, [onPotUpdate]);
  useEffect(() => { cbError.current = onError; }, [onError]);

  // Stable reference to the "should reconnect" flag
  const shouldReconnect = useRef(true);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      cbError.current?.('No access token – cannot open WebSocket');
      return;
    }

    const wsBase = getWsBaseUrl();
    if (!wsBase) return;

    const url = `${wsBase}/api/v1/ws/jobs/${jobId}?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);

    ws.onopen = () => {
      console.log('[WS] connected:', url);
      setConnected(true);
    };

    ws.onmessage = (evt) => {
      let parsed: WsEvent;
      try {
        parsed = JSON.parse(evt.data as string);
      } catch {
        console.warn('[WS] failed to parse message:', evt.data);
        return;
      }

      const { event, data } = parsed;

      switch (event) {
        case 'job_update':
          cbJobUpdate.current?.(data as unknown as JobUpdateData);
          break;
        case 'job_finished':
          cbJobFinished.current?.(data as unknown as JobFinishedData);
          // Server will close the connection; prevent reconnect for this job
          shouldReconnect.current = false;
          break;
        case 'log_update':
          cbLogUpdate.current?.(data as unknown as LogUpdateData);
          break;
        case 'pot_update':
          cbPotUpdate.current?.(data as unknown as PotUpdateData);
          break;
        case 'error':
          cbError.current?.((data as { message?: string }).message ?? 'Unknown error from server');
          shouldReconnect.current = false;
          break;
        default:
          console.debug('[WS] unknown event type:', event);
      }
    };

    ws.onerror = (evt) => {
      console.error('[WS] error:', evt);
    };

    ws.onclose = (evt) => {
      console.log('[WS] closed:', evt.code, evt.reason);
      setConnected(false);

      // 1000 = normal close; 4001 = auth error; 4004 = job not found
      const isAuthError = evt.code === 4001 || evt.code === 4004;
      if (!isAuthError && shouldReconnect.current) {
        console.log('[WS] reconnecting in 5 s…');
        retryTimer.current = setTimeout(() => {
          if (shouldReconnect.current) connect();
        }, 5000);
      }
    };

    // Return a cleanup function that closes this socket
    return () => {
      ws.onclose = null; // suppress reconnect on intentional close
      ws.close();
    };
  }, [jobId]);

  useEffect(() => {
    if (!active || !jobId) {
      setConnected(false);
      return;
    }

    shouldReconnect.current = true;

    const cleanup = connect();

    return () => {
      shouldReconnect.current = false;
      if (retryTimer.current) {
        clearTimeout(retryTimer.current);
        retryTimer.current = null;
      }
      cleanup?.();
      setConnected(false);
    };
  }, [jobId, active, connect]);

  return { connected };
}
