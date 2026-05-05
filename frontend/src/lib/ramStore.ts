import { get, writable } from 'svelte/store';
import { apiFetch } from './api';
import { config, loadConfig, setRamTrackEnabled } from './configStore';
import { log as uiLog } from './logger';

type RamStats = {
  enabled: boolean;
  backendMb: number | null;
  frontendMb: number | null;
  totalMb: number | null;
  error: string | null;
};

export const ramStats = writable<RamStats>({
  enabled: false,
  backendMb: null,
  frontendMb: null,
  totalMb: null,
  error: null
});

let pollTimer: number | null = null;
let unsubscribeConfig: (() => void) | null = null;
let refreshInFlight = false;

function frontendMemoryMb() {
  const memory = (performance as any).memory;
  if (!memory?.usedJSHeapSize) return null;
  return Math.round((memory.usedJSHeapSize / 1024 / 1024) * 10) / 10;
}

async function refreshRamStats() {
  if (refreshInFlight) return;
  refreshInFlight = true;
  try {
    const response = await apiFetch('/api/system/memory');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const backendMb = Number(data.backend_mb);
    const frontendMb = frontendMemoryMb();
    ramStats.set({
      enabled: true,
      backendMb: Number.isFinite(backendMb) ? backendMb : null,
      frontendMb,
      totalMb: Number.isFinite(backendMb) && frontendMb !== null ? Math.round((backendMb + frontendMb) * 10) / 10 : null,
      error: null
    });
  } catch (error) {
    uiLog('ERROR', 'RAM tracker refresh failed', { error: String(error) });
    ramStats.update((current) => ({ ...current, enabled: true, error: String(error) }));
  } finally {
    refreshInFlight = false;
  }
}

function startPolling() {
  if (pollTimer !== null) return;
  refreshRamStats();
  pollTimer = window.setInterval(refreshRamStats, 2000);
}

function stopPolling() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
  ramStats.set({ enabled: false, backendMb: null, frontendMb: null, totalMb: null, error: null });
}

export function startRamTracker() {
  if (unsubscribeConfig) return unsubscribeConfig;
  unsubscribeConfig = config.subscribe((value) => {
    if (value?.ui?.ram_track_enabled) startPolling();
    else stopPolling();
  });
  loadConfig().catch((error) => uiLog('ERROR', 'RAM tracker failed to load config', { error: String(error) }));
  return () => {
    unsubscribeConfig?.();
    unsubscribeConfig = null;
    stopPolling();
  };
}

export async function toggleRamTracking() {
  const loaded = get(config) || await loadConfig();
  const enabled = !Boolean(loaded?.ui?.ram_track_enabled);
  await setRamTrackEnabled(enabled);
  uiLog('INFO', `RAM tracker ${enabled ? 'enabled' : 'disabled'}`);
  return enabled;
}
