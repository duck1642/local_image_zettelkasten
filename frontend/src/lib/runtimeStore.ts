import { get, writable } from 'svelte/store';
import { apiFetch } from './api';
import { clearSharedStats, refreshSharedStats } from './statsStore';
import { log as uiLog } from './logger';

export type RuntimeSession = {
  loaded: boolean;
  workspace: { root: string; topics_root: string } | null;
  vault: { id: string; name: string; root: string; database: string } | null;
  env_override: boolean;
};

const emptySession: RuntimeSession = { loaded: false, workspace: null, vault: null, env_override: false };
export const runtimeSession = writable<RuntimeSession>(emptySession);
export const runtimeSessionKey = writable('');
export const runtimeSwitching = writable(false);

function keyFor(session: RuntimeSession) {
  if (!session.loaded || !session.workspace || !session.vault) return '';
  return `${session.workspace.root}|${session.vault.id}|${session.vault.database}`;
}

function applyRuntimeSession(session: RuntimeSession) {
  const key = keyFor(session);
  runtimeSession.set(session);
  runtimeSessionKey.set(key);
  return { session, key };
}

export async function refreshRuntimeSession() {
  const response = await apiFetch('/api/runtime/session');
  if (!response.ok) throw new Error(`Failed to load runtime session: HTTP ${response.status}`);
  return applyRuntimeSession(await response.json());
}

export async function handleRuntimeSwitch(payload: any = {}) {
  runtimeSwitching.set(true);
  try {
    const previousKey = get(runtimeSessionKey);
    const result = await refreshRuntimeSession();
    clearSharedStats();
    await refreshSharedStats().catch((error) => {
      uiLog('ERROR', 'Failed to refresh shared stats after runtime switch', { error: String(error) });
    });
    window.dispatchEvent(new CustomEvent('lmz:runtime-switched', {
      detail: { payload, previousKey, sessionKey: result.key, session: result.session }
    }));
    return result;
  } finally {
    runtimeSwitching.set(false);
  }
}
