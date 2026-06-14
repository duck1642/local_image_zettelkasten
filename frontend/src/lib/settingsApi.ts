import { apiFetch } from './api';

async function readJson(response: Response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
  return payload;
}

export async function fetchWorkspaces() {
  return readJson(await apiFetch('/api/workspaces'));
}

export async function activateWorkspace(id: string) {
  return readJson(await apiFetch('/api/workspaces/active', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id })
  }));
}

export async function createWorkspace(path: string, name: string) {
  return readJson(await apiFetch('/api/workspaces', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, name })
  }));
}

export async function fetchVaults() {
  return readJson(await apiFetch('/api/vaults'));
}

export async function createVault(name: string) {
  return readJson(await apiFetch('/api/vaults', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name })
  }));
}

export async function activateVault(id: string) {
  return readJson(await apiFetch('/api/vaults/active', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id })
  }));
}

export async function updateVaultName(id: string, name: string) {
  return readJson(await apiFetch(`/api/vaults/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name })
  }));
}

export async function removeVault(id: string) {
  return readJson(await apiFetch(`/api/vaults/${encodeURIComponent(id)}?confirm=true`, { method: 'DELETE' }));
}

export async function previewVaultMergeApi(targetId: string, sourceVaultIds: string[]) {
  return readJson(await apiFetch(`/api/vaults/${encodeURIComponent(targetId)}/merge-preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_vault_ids: sourceVaultIds })
  }));
}

export async function previewMergedVaultApi(name: string, sourceVaultIds: string[]) {
  return readJson(await apiFetch('/api/vaults/merge-preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, source_vault_ids: sourceVaultIds })
  }));
}

export async function mergeVaultsApi(targetId: string, sourceVaultIds: string[]) {
  return readJson(await apiFetch(`/api/vaults/${encodeURIComponent(targetId)}/merge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_vault_ids: sourceVaultIds, delete_sources: false })
  }));
}

export async function createMergedVaultApi(name: string, sourceVaultIds: string[]) {
  return readJson(await apiFetch('/api/vaults/merge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, source_vault_ids: sourceVaultIds })
  }));
}

export async function fetchVaultHealth(id: string) {
  return readJson(await apiFetch(`/api/vaults/${encodeURIComponent(id)}/health`));
}

export async function repairVaultHealthApi(id: string, confirmDestructive = false) {
  return readJson(await apiFetch(`/api/vaults/${encodeURIComponent(id)}/repair`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      actions: ['metadata', 'thumbnails', 'wd_tagging', 'derived_cache', 'review_sidecars', 'quarantine_orphans'],
      confirm_destructive: confirmDestructive
    })
  }));
}

export async function packageVault(id: string, kind: 'backup' | 'export') {
  return readJson(await apiFetch(`/api/vaults/${encodeURIComponent(id)}/${kind}`, { method: 'POST' }));
}

export async function importVaultPackageApi(packagePath: string, name: string) {
  return readJson(await apiFetch('/api/vaults/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ package_path: packagePath, name: name || undefined })
  }));
}

export async function scanAuth() {
  return readJson(await apiFetch('/api/auth/scan', { method: 'POST' }));
}

export async function startMetadataRebuild() {
  return readJson(await apiFetch('/api/metadata-index/rebuild', { method: 'POST' }));
}

export async function fetchMetadataIndexStatus() {
  return readJson(await apiFetch('/api/metadata-index/status'));
}

export async function rebuildWorkspaceMetadata() {
  return readJson(await apiFetch('/api/workspace-metadata/rebuild', { method: 'POST' }));
}

export async function pruneWorkspaceMetadata() {
  return readJson(await apiFetch('/api/workspace-metadata/prune', { method: 'POST' }));
}

export async function cleanupReview() {
  return readJson(await apiFetch('/api/review/cleanup', { method: 'POST' }));
}
