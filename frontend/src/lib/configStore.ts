import { derived, get, writable } from 'svelte/store';
import { apiFetch } from './api';
import { normalizeLayoutMode, normalizeTileMinWidth, type VaultLayoutMode } from './layout';
import { log as uiLog } from './logger';

export const DEFAULT_INSPECTOR_WIDTH = 400;
export const MIN_INSPECTOR_WIDTH = 320;
export const MAX_INSPECTOR_WIDTH = 760;

export const config = writable<any>(null);
export const configLoading = writable(false);
export const configSaving = writable(false);
const savedConfigText = writable('');

let loadPromise: Promise<any> | null = null;

function cloneConfig(value: any) {
  return JSON.parse(JSON.stringify(value || {}));
}

function normalizeConfig(value: any) {
  const next = cloneConfig(value);
  if (!next.ui) next.ui = {};
  next.ui.vault_layout_mode = normalizeLayoutMode(next);
  next.ui.vault_tile_min_width = normalizeTileMinWidth(next.ui.vault_tile_min_width);
  next.ui.ram_track_enabled = Boolean(next.ui.ram_track_enabled);
  next.ui.inspector_width = normalizeInspectorWidth(next.ui.inspector_width);
  return next;
}

export function normalizeInspectorWidth(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return DEFAULT_INSPECTOR_WIDTH;
  return Math.max(MIN_INSPECTOR_WIDTH, Math.min(MAX_INSPECTOR_WIDTH, Math.round(numeric)));
}

export const configDirty = derived(
  [config, savedConfigText],
  ([$config, $savedConfigText]) => Boolean($config) && JSON.stringify($config) !== $savedConfigText
);

export async function loadConfig(force = false) {
  const current = get(config);
  if (current && !force) return current;
  if (loadPromise && !force) return loadPromise;
  configLoading.set(true);
  loadPromise = apiFetch('/api/config')
    .then((response) => response.json())
    .then((data) => {
      const next = normalizeConfig(data);
      config.set(next);
      savedConfigText.set(JSON.stringify(next));
      return next;
    })
    .catch((error) => {
      uiLog('ERROR', 'Failed to load config', { error: String(error) });
      throw error;
    })
    .finally(() => {
      configLoading.set(false);
      loadPromise = null;
    });
  return loadPromise;
}

export async function saveConfig(nextConfig: any = get(config)) {
  if (!nextConfig) return null;
  const next = normalizeConfig(nextConfig);
  configSaving.set(true);
  try {
    await apiFetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(next)
    });
    config.set(next);
    savedConfigText.set(JSON.stringify(next));
    return next;
  } finally {
    configSaving.set(false);
  }
}

export async function updateConfig(mutator: (draft: any) => void, save = false) {
  const base = get(config) || await loadConfig();
  const draft = cloneConfig(base);
  mutator(draft);
  const next = normalizeConfig(draft);
  config.set(next);
  if (save) await saveConfig(next);
  return next;
}

export async function setVaultLayoutMode(mode: VaultLayoutMode) {
  return updateConfig((draft) => {
    if (!draft.ui) draft.ui = {};
    draft.ui.vault_layout_mode = mode;
  }, true);
}

export async function setRamTrackEnabled(enabled: boolean) {
  return updateConfig((draft) => {
    if (!draft.ui) draft.ui = {};
    draft.ui.ram_track_enabled = enabled;
  }, true);
}

export async function setInspectorWidth(width: number) {
  return updateConfig((draft) => {
    if (!draft.ui) draft.ui = {};
    draft.ui.inspector_width = normalizeInspectorWidth(width);
  }, true);
}

export function setVaultTileMinWidthLocal(width: number) {
  const base = get(config);
  if (!base) return null;
  const next = cloneConfig(base);
  if (!next.ui) next.ui = {};
  next.ui.vault_tile_min_width = normalizeTileMinWidth(width);
  config.set(next);
  return next;
}

export async function saveCurrentConfig() {
  return saveConfig(get(config));
}
