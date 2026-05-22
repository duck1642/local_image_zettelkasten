import { get, writable } from 'svelte/store';
import { config, loadConfig } from './configStore';
import { clearSharedStats, refreshSharedStats } from './statsStore';
import { log as uiLog } from './logger';

export type RuntimeSession = {
  workspace: string;
  configPath: string;
  configRoot: string;
  activeVault: string;
  activeVaultRoot: string;
  dbPath: string;
};

const emptySession: RuntimeSession = {
  workspace: '',
  configPath: '',
  configRoot: '',
  activeVault: '',
  activeVaultRoot: '',
  dbPath: ''
};

export const runtimeSession = writable<RuntimeSession>(emptySession);
export const runtimeSessionKey = writable('');
export const runtimeSwitching = writable(false);

function sessionFromConfig(value: any): RuntimeSession {
  const runtime = value?._runtime || {};
  return {
    workspace: String(runtime.workspace_label || runtime.workspace_mode || ''),
    configPath: String(runtime.config_path || ''),
    configRoot: String(runtime.config_root || ''),
    activeVault: String(runtime.active_vault || ''),
    activeVaultRoot: String(runtime.active_vault_root || ''),
    dbPath: String(runtime.db_path || '')
  };
}

function keyFor(session: RuntimeSession) {
  if (!session.configPath && !session.activeVault && !session.dbPath) return '';
  return `${session.configPath}|${session.activeVault}|${session.dbPath}`;
}

function applyRuntimeSession(session: RuntimeSession) {
  const key = keyFor(session);
  runtimeSession.set(session);
  runtimeSessionKey.set(key);
  return { session, key };
}

config.subscribe((value) => {
  if (!value?._runtime) return;
  const next = sessionFromConfig(value);
  if (keyFor(next) !== get(runtimeSessionKey)) {
    applyRuntimeSession(next);
  } else {
    runtimeSession.set(next);
  }
});

export async function refreshRuntimeSession(force = false) {
  const loaded = await loadConfig(force);
  return applyRuntimeSession(sessionFromConfig(loaded));
}

export async function handleRuntimeSwitch(payload: any = {}) {
  runtimeSwitching.set(true);
  try {
    const previousKey = get(runtimeSessionKey);
    const result = await refreshRuntimeSession(true);
    clearSharedStats();
    await refreshSharedStats().catch((error) => {
      uiLog('ERROR', 'Failed to refresh shared stats after runtime switch', { error: String(error) });
    });
    window.dispatchEvent(new CustomEvent('lmz:runtime-switched', {
      detail: {
        payload,
        previousKey,
        sessionKey: result.key,
        session: result.session
      }
    }));
    return result;
  } finally {
    runtimeSwitching.set(false);
  }
}
