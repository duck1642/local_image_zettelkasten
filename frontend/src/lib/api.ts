export const DEFAULT_API_BASE = 'http://127.0.0.1:8000';
const configuredApiBase = import.meta.env.VITE_API_BASE;
const API_BASE = import.meta.env.DEV && configuredApiBase === undefined ? '' : (configuredApiBase || DEFAULT_API_BASE);
const STARTUP_RETRY_MS = 60000;
const STARTUP_RETRY_INITIAL_DELAY_MS = 250;
const STARTUP_RETRY_MAX_DELAY_MS = 1000;

let apiKeyPromise: Promise<string> | null = null;

export type SidecarStatus = {
  state: string;
  ready: boolean;
  message: string;
  port: number;
};

export class SidecarStartupError extends Error {
  readonly state: string;
  readonly port: number;

  constructor(status: SidecarStatus) {
    super(status.message || `LMZ backend startup failed (${status.state})`);
    this.name = 'SidecarStartupError';
    this.state = status.state;
    this.port = status.port;
  }
}

export async function waitForSidecarReady(): Promise<SidecarStatus> {
  if (!(window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__) {
    return {
      state: 'dev',
      ready: true,
      message: 'Development backend is managed externally.',
      port: 8000,
    };
  }
  const { invoke } = await import('@tauri-apps/api/core');
  let status: SidecarStatus;
  try {
    status = await invoke<SidecarStatus>('wait_for_sidecar_ready');
  } catch (error) {
    throw new SidecarStartupError({
      state: 'startup_failed',
      ready: false,
      message: `Native LMZ readiness check failed: ${String(error)}`,
      port: 8000,
    });
  }
  if (!status.ready) throw new SidecarStartupError(status);
  return status;
}

export function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

function shouldRetryStartupFetch(error: unknown, signal?: AbortSignal | null) {
  if (import.meta.env.DEV) return false;
  if (signal?.aborted) return false;
  if (error instanceof DOMException && error.name === 'AbortError') return false;
  return error instanceof TypeError;
}

function delay(ms: number, signal?: AbortSignal | null) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('The operation was aborted.', 'AbortError'));
      return;
    }
    let timer: number;
    const onAbort = () => {
      window.clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
      reject(new DOMException('The operation was aborted.', 'AbortError'));
    };
    timer = window.setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

async function fetchWithStartupRetry(path: string, init: RequestInit = {}) {
  const started = Date.now();
  let waitMs = STARTUP_RETRY_INITIAL_DELAY_MS;
  while (true) {
    try {
      return await fetch(apiUrl(path), init);
    } catch (error) {
      const elapsed = Date.now() - started;
      if (!shouldRetryStartupFetch(error, init.signal) || elapsed >= STARTUP_RETRY_MS) throw error;
      await delay(Math.min(waitMs, STARTUP_RETRY_MS - elapsed), init.signal);
      waitMs = Math.min(STARTUP_RETRY_MAX_DELAY_MS, Math.round(waitMs * 1.5));
    }
  }
}

async function getApiKey() {
  if (!apiKeyPromise) {
    apiKeyPromise = fetchWithStartupRetry('/api/session-key')
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load API session key');
        return res.json();
      })
      .then((data) => data.key || '')
      .catch((error) => {
        apiKeyPromise = null;
        throw error;
      });
  }
  return apiKeyPromise;
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const method = (init.method || 'GET').toUpperCase();
  const headers = new Headers(init.headers || {});
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    headers.set('X-LMZ-API-KEY', await getApiKey());
  }
  return fetchWithStartupRetry(path, { ...init, headers });
}
