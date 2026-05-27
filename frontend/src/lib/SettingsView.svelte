<script lang="ts">
  import { onMount } from 'svelte';
  import { TILE_MIN_WIDTH_CEILING, TILE_MIN_WIDTH_FLOOR } from './layout';
  import { config, configDirty, configLoading, configSaving, loadConfig, saveCurrentConfig, updateConfig } from './configStore';
  import { log as uiLog } from './logger';
  import { apiFetch } from './api';
  import { handleRuntimeSwitch } from './runtimeStore';

  type MaintenanceAction = 'auth' | 'metadata' | 'workspaceMetadata' | 'workspacePrune' | 'review';
  let maintenanceBusy: Record<MaintenanceAction, boolean> = {
    auth: false,
    metadata: false,
    workspaceMetadata: false,
    workspacePrune: false,
    review: false
  };
  let maintenanceResult: Record<MaintenanceAction, string> = {
    auth: '',
    metadata: '',
    workspaceMetadata: '',
    workspacePrune: '',
    review: ''
  };
  type MetadataRebuildJob = {
    running?: boolean;
    status?: string;
    mode?: string;
    stage?: string;
    items_total?: number;
    items_done?: number;
    errors?: number;
    duration_ms?: number;
    message?: string;
  };
  let metadataRebuildJob: MetadataRebuildJob | null = null;
  let metadataRebuildPollTimer: number | null = null;
  let workspaces: any[] = [];
  let workspaceActive = '';
  let workspaceBusy = false;
  let workspaceResult = '';
  let obsidianPath = '';
  let obsidianName = 'Obsidian Workspace';
  let workspaceRestartRequired = false;
  let vaults: any[] = [];
  let vaultActive = '';
  let vaultBusy = false;
  let vaultResult = '';
  let vaultName = 'New Vault';
  let vaultRestartRequired = false;
  let mergeTargetId = '';
  let mergeSourceIds: string[] = [];
  let mergePreview: any = null;
  let mergeBusy = false;
  let mergeResult = '';
  let healthVaultId = '';
  let healthBusy = false;
  let healthResult = '';
  let healthReport: any = null;
  let healthDetailsOpen = false;
  let repairErrors: Array<{ hash: string; storage_id: string; status: string; error: string }> = [];
  let backupResult = '';
  let importPackagePath = '';
  let importVaultName = '';

  $: if (!mergeTargetId && vaultActive) mergeTargetId = vaultActive;
  $: if (!healthVaultId && vaultActive) healthVaultId = vaultActive;

  function setConfig(mutator: (draft: any) => void) {
    updateConfig(mutator, false);
  }

  function textValue(event: Event) {
    return (event.currentTarget as HTMLInputElement | HTMLSelectElement).value;
  }

  function numberValue(event: Event) {
    return Number((event.currentTarget as HTMLInputElement).value);
  }

  function checkedValue(event: Event) {
    return (event.currentTarget as HTMLInputElement).checked;
  }

  function handleGlobalRefresh(event: Event) {
    const detail = (event as CustomEvent).detail || {};
    if (detail.tab !== 'settings') return;
    if ($configDirty && !confirm('You have unsaved settings. Discard them and refresh?')) return;
    uiLog('INFO', 'Settings view refresh requested');
    loadConfig();
  }

  onMount(() => {
    window.addEventListener('lmz:refresh', handleGlobalRefresh);
    loadConfig();
    loadWorkspaces();
    loadVaults();
    return () => {
      window.removeEventListener('lmz:refresh', handleGlobalRefresh);
      stopMetadataRebuildPolling();
    };
  });

  async function loadWorkspaces() {
    try {
      const response = await apiFetch('/api/workspaces');
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      workspaceActive = String(payload?.active || '');
      workspaces = Array.isArray(payload?.items) ? payload.items : [];
    } catch (error) {
      workspaceResult = `error: ${String(error)}`;
    }
  }

  async function setActiveWorkspace(id: string) {
    if (!id || workspaceBusy) return;
    workspaceBusy = true;
    workspaceResult = '';
    try {
      const response = await apiFetch('/api/workspaces/active', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      workspaceActive = String(payload?.active || id);
      workspaces = Array.isArray(payload?.items) ? payload.items : workspaces;
      if (payload?.restart_required !== false) {
        workspaceRestartRequired = true;
        workspaceResult = 'active on next restart';
      } else {
        workspaceRestartRequired = false;
        workspaceResult = 'Workspace switched dynamically!';
        await handleRuntimeSwitch(payload);
        await Promise.all([loadWorkspaces(), loadVaults()]);
      }
      uiLog('INFO', 'Workspace active changed', { id });
    } catch (error) {
      workspaceResult = `error: ${String(error)}`;
      uiLog('ERROR', 'Workspace active change failed', { id, error: String(error) });
    } finally {
      workspaceBusy = false;
    }
  }

  async function addObsidianWorkspace() {
    const path = obsidianPath.trim();
    if (!path || workspaceBusy) return;
    workspaceBusy = true;
    workspaceResult = '';
    try {
      const response = await apiFetch('/api/workspaces/obsidian', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, name: obsidianName.trim() || 'Obsidian Workspace' })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      workspaceActive = String(payload?.active || workspaceActive);
      workspaces = Array.isArray(payload?.items) ? payload.items : workspaces;
      workspaceResult = 'workspace registered';
      obsidianPath = '';
      uiLog('INFO', 'Obsidian workspace registered', { path });
    } catch (error) {
      workspaceResult = `error: ${String(error)}`;
      uiLog('ERROR', 'Obsidian workspace registration failed', { path, error: String(error) });
    } finally {
      workspaceBusy = false;
    }
  }

  async function loadVaults() {
    try {
      const response = await apiFetch('/api/vaults');
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      vaultActive = String(payload?.active || '');
      vaults = Array.isArray(payload?.items) ? payload.items : [];
      if (!mergeTargetId && vaultActive) mergeTargetId = vaultActive;
      if (!healthVaultId && vaultActive) healthVaultId = vaultActive;
    } catch (error) {
      vaultResult = `error: ${String(error)}`;
    }
  }

  async function addVault() {
    const name = vaultName.trim();
    if (!name || vaultBusy) return;
    vaultBusy = true;
    vaultResult = '';
    try {
      const response = await apiFetch('/api/vaults', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      vaults = Array.isArray(payload?.items) ? payload.items : vaults;
      vaultName = 'New Vault';
      vaultResult = 'vault created';
      uiLog('INFO', 'Vault created', { name });
    } catch (error) {
      vaultResult = `error: ${String(error)}`;
      uiLog('ERROR', 'Vault create failed', { name, error: String(error) });
    } finally {
      vaultBusy = false;
    }
  }

  async function setActiveVault(id: string) {
    if (!id || vaultBusy) return;
    vaultBusy = true;
    vaultResult = '';
    try {
      const response = await apiFetch('/api/vaults/active', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      vaultActive = String(payload?.active || id);
      vaults = Array.isArray(payload?.items) ? payload.items : vaults;
      if (payload?.restart_required !== false) {
        vaultRestartRequired = true;
        vaultResult = 'active on next restart';
      } else {
        vaultRestartRequired = false;
        vaultResult = 'Vault switched dynamically!';
        await handleRuntimeSwitch(payload);
        await Promise.all([loadWorkspaces(), loadVaults()]);
      }
      uiLog('INFO', 'Vault active changed', { id });
    } catch (error) {
      vaultResult = `error: ${String(error)}`;
      uiLog('ERROR', 'Vault active change failed', { id, error: String(error) });
    } finally {
      vaultBusy = false;
    }
  }

  async function renameVault(id: string, currentName: string) {
    const name = prompt('Vault name', currentName || id)?.trim();
    if (!name || vaultBusy) return;
    vaultBusy = true;
    vaultResult = '';
    try {
      const response = await apiFetch(`/api/vaults/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      vaults = Array.isArray(payload?.items) ? payload.items : vaults;
      vaultResult = 'vault renamed';
    } catch (error) {
      vaultResult = `error: ${String(error)}`;
    } finally {
      vaultBusy = false;
    }
  }

  async function deleteVault(id: string) {
    if (!id || vaultBusy) return;
    if (!confirm(`Delete vault "${id}"? This removes that vault folder.`)) return;
    vaultBusy = true;
    vaultResult = '';
    try {
      const response = await apiFetch(`/api/vaults/${encodeURIComponent(id)}?confirm=true`, { method: 'DELETE' });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      vaults = Array.isArray(payload?.items) ? payload.items : vaults;
      vaultResult = 'vault deleted';
      mergeSourceIds = mergeSourceIds.filter((value) => value !== id);
      if (mergeTargetId === id) mergeTargetId = vaultActive;
      if (healthVaultId === id) healthVaultId = vaultActive;
    } catch (error) {
      vaultResult = `error: ${String(error)}`;
    } finally {
      vaultBusy = false;
    }
  }

  function toggleMergeSource(id: string, checked: boolean) {
    mergePreview = null;
    if (checked) {
      mergeSourceIds = Array.from(new Set([...mergeSourceIds, id])).filter((value) => value !== mergeTargetId);
    } else {
      mergeSourceIds = mergeSourceIds.filter((value) => value !== id);
    }
  }

  async function previewVaultMerge() {
    if (!mergeTargetId || !mergeSourceIds.length || mergeBusy) return;
    mergeBusy = true;
    mergeResult = '';
    mergePreview = null;
    try {
      const response = await apiFetch(`/api/vaults/${encodeURIComponent(mergeTargetId)}/merge-preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_vault_ids: mergeSourceIds })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      mergePreview = payload;
      mergeResult = `preview: ${Number(payload.importable || 0).toLocaleString()} importable`;
    } catch (error) {
      mergeResult = `error: ${String(error)}`;
    } finally {
      mergeBusy = false;
    }
  }

  async function confirmVaultMerge() {
    if (!mergeTargetId || !mergeSourceIds.length || mergeBusy) return;
    if (!mergePreview && !confirm('Merge without preview?')) return;
    if (!confirm(`Merge ${mergeSourceIds.length} source vault(s) into "${mergeTargetId}"? Sources stay intact.`)) return;
    mergeBusy = true;
    mergeResult = '';
    try {
      const response = await apiFetch(`/api/vaults/${encodeURIComponent(mergeTargetId)}/merge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_vault_ids: mergeSourceIds })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      mergePreview = payload;
      mergeResult = `merged ${Number(payload.imported || 0).toLocaleString()} items`;
      await loadVaults();
    } catch (error) {
      mergeResult = `error: ${String(error)}`;
    } finally {
      mergeBusy = false;
    }
  }

  function healthSummary(report: any) {
    if (!report) return '';
    return `${Number(report.issue_count || 0).toLocaleString()} issues`;
  }

  function countValues(value: any) {
    if (!value || typeof value !== 'object') return 0;
    return Object.values(value).reduce<number>((total, item: any) => {
      if (Array.isArray(item)) return total + item.length;
      if (typeof item === 'number') return total + item;
      return total;
    }, 0);
  }

  function repairSummary(payload: any) {
    const fixed = Number(payload?.fixed_issue_count || 0);
    const after = Number(payload?.after_issue_count ?? payload?.after?.issue_count ?? 0);
    const manual = countValues(payload?.manual_remaining);
    const tagged = Number(payload?.wd_tagging?.tagged || 0);
    const base = payload?.message || (fixed ? `Fixed ${fixed} issues` : 'No repairable issues changed');
    const wdText = tagged ? `; tagged ${tagged.toLocaleString()} items` : '';
    if (manual) return `${base}${wdText}; ${manual.toLocaleString()} need manual review; ${after.toLocaleString()} total remain`;
    return `${base}${wdText}; ${after.toLocaleString()} total remain`;
  }

  function firstValues(value: any, limit = 5) {
    if (!value || typeof value !== 'object') return [];
    const rows: Array<{ kind: string; value: string }> = [];
    for (const [kind, raw] of Object.entries(value)) {
      if (Array.isArray(raw)) {
        for (const item of raw) {
          rows.push({ kind, value: String(typeof item === 'object' && item ? (item as any).path || JSON.stringify(item) : item) });
          if (rows.length >= limit) return rows;
        }
      } else if (typeof raw === 'number' && raw) {
        rows.push({ kind, value: String(raw) });
      }
      if (rows.length >= limit) return rows;
    }
    return rows;
  }

  function detailValues(value: any, limit = 100) {
    return firstValues(value, limit);
  }

  function closeHealthDetailsOnBackdrop(event: MouseEvent) {
    if (event.target === event.currentTarget) healthDetailsOpen = false;
  }

  function healthKindLabel(kind: string) {
    const labels: Record<string, string> = {
      asset: 'Asset',
      note: 'Note',
      wd: 'WD cache',
      thumb: 'Thumbnail',
      assets: 'Asset',
      notes: 'Note',
      wd_cache: 'WD cache',
      thumbnails: 'Thumbnail',
      topics: 'Topics',
      wd_tags: 'WD tags',
      metadata_files: 'Metadata rows'
    };
    return labels[kind] || kind.replace(/_/g, ' ');
  }

  async function auditVaultHealth() {
    if (!healthVaultId || healthBusy) return;
    healthBusy = true;
    healthResult = 'auditing...';
      healthReport = null;
      healthDetailsOpen = false;
    try {
      const response = await apiFetch(`/api/vaults/${encodeURIComponent(healthVaultId)}/health`);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      healthReport = payload;
      healthResult = healthSummary(payload);
      uiLog('INFO', 'Vault health audit completed', {
        vault: healthVaultId,
        issues: payload?.issue_count || 0,
        missing_files: countValues(payload?.missing_files),
        orphans: countValues(payload?.orphans),
        facet_drift: payload?.facet_drift?.length || 0
      });
    } catch (error) {
      healthResult = `error: ${String(error)}`;
      uiLog('ERROR', 'Vault health audit failed', { vault: healthVaultId, error: String(error) });
    } finally {
      healthBusy = false;
    }
  }

  async function repairVaultHealth() {
    if (!healthVaultId || healthBusy) return;
    if (!confirm(`Repair vault "${healthVaultId}"? Orphan assets/notes are quarantined, not deleted.`)) return;
    healthBusy = true;
    healthResult = 'repairing...';
    try {
      const response = await apiFetch(`/api/vaults/${encodeURIComponent(healthVaultId)}/repair`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          actions: ['metadata', 'thumbnails', 'wd_tagging', 'derived_cache', 'review_sidecars', 'quarantine_orphans']
        })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      healthReport = payload.after || null;
      repairErrors = payload.wd_tagging?.errors || [];
      // Keep details panel openable (don't force-close after repair)
      healthResult = repairSummary(payload);
      uiLog('INFO', 'Vault repair completed', {
        vault: healthVaultId,
        fixed: payload?.fixed_issue_count || 0,
        before: payload?.before_issue_count || 0,
        after: payload?.after_issue_count || 0,
        manual_remaining: payload?.manual_remaining || {},
        actions: payload?.actions || []
      });
      await loadVaults();
    } catch (error) {
      healthResult = `error: ${String(error)}`;
      uiLog('ERROR', 'Vault repair failed', { vault: healthVaultId, error: String(error) });
    } finally {
      healthBusy = false;
    }
  }

  async function backupVault(kind: 'backup' | 'export') {
    const id = healthVaultId || vaultActive;
    if (!id || healthBusy) return;
    healthBusy = true;
    backupResult = '';
    try {
      const response = await apiFetch(`/api/vaults/${encodeURIComponent(id)}/${kind}`, { method: 'POST' });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      backupResult = `${kind}: ${payload.package_path || 'created'}`;
    } catch (error) {
      backupResult = `error: ${String(error)}`;
    } finally {
      healthBusy = false;
    }
  }

  async function importVaultPackage() {
    const path = importPackagePath.trim();
    if (!path || healthBusy) return;
    healthBusy = true;
    backupResult = '';
    try {
      const response = await apiFetch('/api/vaults/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ package_path: path, name: importVaultName.trim() || undefined })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      vaults = Array.isArray(payload?.items) ? payload.items : vaults;
      importPackagePath = '';
      importVaultName = '';
      backupResult = `imported ${payload.vault || 'vault'}`;
    } catch (error) {
      backupResult = `error: ${String(error)}`;
    } finally {
      healthBusy = false;
    }
  }

  function setMaintenanceBusy(action: MaintenanceAction, busy: boolean) {
    maintenanceBusy = { ...maintenanceBusy, [action]: busy };
  }

  function setMaintenanceResult(action: MaintenanceAction, message: string) {
    maintenanceResult = { ...maintenanceResult, [action]: message };
  }

  function metadataProgressPercent(job: MetadataRebuildJob | null) {
    const total = Number(job?.items_total || 0);
    if (!total) return 0;
    return Math.max(0, Math.min(100, Math.round((Number(job?.items_done || 0) / total) * 100)));
  }

  function metadataProgressText(job: MetadataRebuildJob | null) {
    if (!job) return '';
    const total = Number(job.items_total || 0);
    const done = Number(job.items_done || 0);
    const stage = String(job.stage || job.status || 'running');
    if (total > 0) return `${stage}: ${done.toLocaleString()} / ${total.toLocaleString()}`;
    return stage;
  }

  function stopMetadataRebuildPolling() {
    if (metadataRebuildPollTimer !== null) {
      window.clearTimeout(metadataRebuildPollTimer);
      metadataRebuildPollTimer = null;
    }
  }

  async function pollMetadataRebuildStatus() {
    try {
      const response = await apiFetch('/api/metadata-index/status');
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      metadataRebuildJob = payload?.maintenance_rebuild || null;
      if (metadataRebuildJob?.running) {
        setMaintenanceBusy('metadata', true);
        setMaintenanceResult('metadata', metadataProgressText(metadataRebuildJob));
        stopMetadataRebuildPolling();
        metadataRebuildPollTimer = window.setTimeout(pollMetadataRebuildStatus, 1200);
      } else {
        stopMetadataRebuildPolling();
        setMaintenanceBusy('metadata', false);
        if (metadataRebuildJob?.status === 'completed') {
          setMaintenanceResult('metadata', 'completed');
          uiLog('INFO', 'Maintenance metadata rebuild completed', {
            errors: metadataRebuildJob.errors || 0,
            duration_ms: metadataRebuildJob.duration_ms || 0
          });
        } else if (metadataRebuildJob?.status === 'error') {
          const message = String(metadataRebuildJob.message || 'metadata rebuild failed');
          setMaintenanceResult('metadata', `error: ${message}`);
          uiLog('ERROR', 'Maintenance metadata rebuild failed', { error: message });
        }
      }
    } catch (error) {
      stopMetadataRebuildPolling();
      setMaintenanceBusy('metadata', false);
      const text = String(error);
      setMaintenanceResult('metadata', `error: ${text}`);
      uiLog('ERROR', 'Maintenance metadata rebuild status failed', { error: text });
    }
  }

  function startMetadataRebuildPolling() {
    stopMetadataRebuildPolling();
    metadataRebuildPollTimer = window.setTimeout(pollMetadataRebuildStatus, 500);
  }

  async function runMaintenance(action: MaintenanceAction) {
    if (maintenanceBusy[action]) return;
    setMaintenanceResult(action, '');
    setMaintenanceBusy(action, true);
    try {
      if (action === 'auth') {
        const response = await apiFetch('/api/auth/scan', { method: 'POST' });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
        const cookies = String(payload?.auth?.cookies || 'unknown');
        setMaintenanceResult(action, `OK (${cookies})`);
        uiLog('INFO', 'Maintenance action completed', { action: 'auth_scan', cookies });
      } else if (action === 'metadata') {
        const response = await apiFetch('/api/metadata-index/rebuild', { method: 'POST' });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
        const status = String(payload?.status || 'started');
        metadataRebuildJob = payload?.maintenance_rebuild || null;
        setMaintenanceResult(action, metadataProgressText(metadataRebuildJob) || status);
        uiLog('INFO', 'Maintenance action completed', { action: 'metadata_rebuild', status });
        if (status === 'started' || metadataRebuildJob?.running) {
          startMetadataRebuildPolling();
          return;
        }
      } else if (action === 'workspaceMetadata') {
        const response = await apiFetch('/api/workspace-metadata/rebuild', { method: 'POST' });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
        const after = payload?.after || {};
        setMaintenanceResult(action, `artists ${after.artists || 0}, platforms ${after.platforms || 0}, WD ${after.wd_tags || 0}`);
        uiLog('INFO', 'Maintenance action completed', { action: 'workspace_metadata_rebuild', after });
      } else if (action === 'workspacePrune') {
        const response = await apiFetch('/api/workspace-metadata/prune', { method: 'POST' });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
        const pruned = payload?.pruned || {};
        setMaintenanceResult(action, `pruned artists ${pruned.artists || 0}, platforms ${pruned.platforms || 0}, WD ${pruned.wd_tags || 0}`);
        uiLog('INFO', 'Maintenance action completed', { action: 'workspace_metadata_prune', pruned });
      } else {
        const response = await apiFetch('/api/review/cleanup', { method: 'POST' });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
        const cleaned = Number(payload?.cleaned || 0);
        const failed = Number(payload?.failed || 0);
        setMaintenanceResult(action, `cleaned ${cleaned}, failed ${failed}`);
        uiLog('INFO', 'Maintenance action completed', { action: 'review_cleanup', cleaned, failed });
      }
    } catch (error) {
      const text = String(error);
      setMaintenanceResult(action, `error: ${text}`);
      uiLog('ERROR', 'Maintenance action failed', { action, error: text });
    } finally {
      if (action !== 'metadata' || !metadataRebuildJob?.running) {
        setMaintenanceBusy(action, false);
      }
    }
  }
</script>

<div class="settings-container">
  {#if $configLoading || !$config}
    <div class="centered">Loading...</div>
  {:else}
    <div class="header-row">
      <h3>System Settings</h3>
      {#if $configDirty}
        <span class="status-label unsaved">Unsaved Changes</span>
      {/if}
    </div>

    {#if $config._runtime}
      <div class="workspace-panel">
        <h4>Workspace</h4>
        <div class="workspace-grid">
          <span>Mode</span>
          <strong>{$config._runtime.workspace_label || $config._runtime.workspace_mode || 'Default workspace'}</strong>
          <span>Config</span>
          <code>{$config._runtime.config_path}</code>
          <span>Root</span>
          <code>{$config._runtime.config_root}</code>
          <span>Topics</span>
          <code>{$config._runtime.topic_root}</code>
          <span>Vault</span>
          <strong>{$config._runtime.active_vault_name || $config._runtime.active_vault || 'Default'}</strong>
          <span>Vault Root</span>
          <code>{$config._runtime.active_vault_root}</code>
        </div>
        {#if $config._runtime.env_override}
          <div class="workspace-note">Environment override is active. Registry changes apply only after restarting without LMZ_CONFIG_PATH.</div>
        {/if}
        <div class="workspace-actions">
          <h5>Registered Workspaces</h5>
          {#if workspaceRestartRequired}
            <div class="restart-banner">Restart required to use the selected workspace.</div>
          {/if}
          <div class="workspace-list">
            {#each workspaces as workspace}
              <div class="workspace-row">
                <div>
                  <strong>{workspace.name}</strong>
                  <code>{workspace.config_path}</code>
                  {#if !workspace.exists}
                    <span class="missing">missing config</span>
                  {/if}
                </div>
                <button
                  type="button"
                  disabled={workspaceBusy || workspace.id === workspaceActive || !workspace.exists}
                  on:click={() => setActiveWorkspace(workspace.id)}
                >
                  {workspace.id === workspaceActive ? 'Active' : 'Activate'}
                </button>
              </div>
            {/each}
          </div>
          <div class="add-workspace">
            <input type="text" placeholder="Obsidian vault path" bind:value={obsidianPath} />
            <input type="text" placeholder="Workspace name" bind:value={obsidianName} />
            <button type="button" on:click={addObsidianWorkspace} disabled={workspaceBusy || !obsidianPath.trim()}>Add Obsidian</button>
          </div>
          {#if workspaceResult}
            <div class="workspace-result">{workspaceResult}</div>
          {/if}
        </div>
        <div class="workspace-actions">
          <h5>Vaults</h5>
          {#if vaultRestartRequired}
            <div class="restart-banner">Restart required to use the selected vault.</div>
          {/if}
          <div class="workspace-list">
            {#each vaults as vault}
              <div class="workspace-row">
                <div>
                  <strong>{vault.name}</strong>
                  <code>{vault.root}</code>
                  <span class="workspace-note">{Number(vault.item_count || 0).toLocaleString()} items</span>
                  {#if !vault.exists}
                    <span class="missing">missing vault</span>
                  {/if}
                </div>
                <div class="row-actions">
                  <button type="button" disabled={vaultBusy} on:click={() => renameVault(vault.id, vault.name)}>Rename</button>
                  <button
                    type="button"
                    disabled={vaultBusy || vault.id === vaultActive || !vault.exists}
                    on:click={() => setActiveVault(vault.id)}
                  >
                    {vault.id === vaultActive ? 'Active' : 'Activate'}
                  </button>
                  <button type="button" disabled={vaultBusy || vault.id === vaultActive} on:click={() => deleteVault(vault.id)}>Delete</button>
                </div>
              </div>
            {/each}
          </div>
          <div class="add-workspace">
            <input type="text" placeholder="Vault name" bind:value={vaultName} />
            <button type="button" on:click={addVault} disabled={vaultBusy || !vaultName.trim()}>Create Vault</button>
          </div>
          {#if vaultResult}
            <div class="workspace-result">{vaultResult}</div>
          {/if}
          <div class="vault-tool-panel">
            <h5>Merge Vaults</h5>
            <div class="add-workspace">
              <select bind:value={mergeTargetId} on:change={() => { mergeSourceIds = mergeSourceIds.filter((id) => id !== mergeTargetId); mergePreview = null; }}>
                {#each vaults as vault}
                  <option value={vault.id}>{vault.name}</option>
                {/each}
              </select>
              <button type="button" on:click={previewVaultMerge} disabled={mergeBusy || !mergeTargetId || !mergeSourceIds.length}>Preview Merge</button>
              <button type="button" on:click={confirmVaultMerge} disabled={mergeBusy || !mergeTargetId || !mergeSourceIds.length}>Merge</button>
            </div>
            <div class="merge-source-list">
              {#each vaults as vault}
                <label>
                  <input
                    type="checkbox"
                    disabled={mergeBusy || vault.id === mergeTargetId}
                    checked={mergeSourceIds.includes(vault.id)}
                    on:change={(event) => toggleMergeSource(vault.id, checkedValue(event))}
                  />
                  <span>{vault.name}</span>
                </label>
              {/each}
            </div>
            {#if mergePreview}
              <div class="workspace-note">
                {Number(mergePreview.total_items || 0).toLocaleString()} total |
                {Number(mergePreview.duplicates || 0).toLocaleString()} duplicates |
                {Number(mergePreview.importable || 0).toLocaleString()} importable
              </div>
            {/if}
            {#if mergeResult}
              <div class="workspace-result">{mergeResult}</div>
            {/if}
          </div>
          <div class="vault-tool-panel">
            <h5>Vault Health</h5>
            <div class="add-workspace">
              <select bind:value={healthVaultId}>
                {#each vaults as vault}
                  <option value={vault.id}>{vault.name}</option>
                {/each}
              </select>
              <button type="button" on:click={auditVaultHealth} disabled={healthBusy || !healthVaultId}>Audit Vault Health</button>
              <button type="button" on:click={repairVaultHealth} disabled={healthBusy || !healthVaultId || healthVaultId !== vaultActive}>Repair Active Vault</button>
            </div>
            {#if healthReport}
              <div class="health-summary">
                <span>{Number(healthReport.issue_count || 0).toLocaleString()} issues</span>
                <span>{countValues(healthReport.missing_files)} missing files</span>
                <span>{countValues(healthReport.orphans)} orphans</span>
                <span>{(healthReport.facet_drift || []).length} facet drift</span>
                <span>{countValues(healthReport.stale_index_rows)} stale index</span>
                <span>{(healthReport.hash_mismatches || []).length} hash mismatch</span>
                <button type="button" class="compact-action" on:click={() => healthDetailsOpen = true}>Details</button>
              </div>
            {/if}
            {#if healthDetailsOpen && healthReport}
              <div class="modal-backdrop" role="presentation" on:click={closeHealthDetailsOnBackdrop}>
                <div class="health-modal" role="dialog" aria-modal="true" aria-label="Vault Health Details" tabindex="-1">
                  <div class="modal-header">
                    <h4>Vault Health Details</h4>
                    <button type="button" on:click={() => healthDetailsOpen = false}>Close</button>
                  </div>
                  <div class="health-detail">
                {#if countValues(healthReport.missing_files)}
                  <div class="health-section-title">Missing Files</div>
                  {#each detailValues(healthReport.details?.missing_files || healthReport.missing_files) as row}
                    <div class="health-row">
                      <span>{healthKindLabel(row.kind)}</span>
                      <code title={row.value}>{row.value}</code>
                    </div>
                  {/each}
                {/if}
                {#if countValues(healthReport.orphans)}
                  <div class="health-section-title">Orphans</div>
                  {#each detailValues(healthReport.orphans) as row}
                    <div class="health-row">
                      <span>{healthKindLabel(row.kind)}</span>
                      <code title={row.value}>{row.value}</code>
                    </div>
                  {/each}
                {/if}
                {#if countValues(healthReport.stale_index_rows)}
                  <div class="health-section-title">Stale Index Rows</div>
                  {#each detailValues(healthReport.stale_index_rows) as row}
                    <div class="health-row">
                      <span>{healthKindLabel(row.kind)}</span>
                      <code>{row.value}</code>
                    </div>
                  {/each}
                {/if}
                    {#if (healthReport.facet_drift || []).length}
                      <div class="health-section-title">Facet Drift</div>
                      {#each healthReport.facet_drift as row}
                        <div class="health-row"><span>Facet</span><code>{row}</code></div>
                      {/each}
                    {/if}
                    {#if (healthReport.hash_mismatches || []).length}
                      <div class="health-section-title">Hash Mismatches</div>
                      {#each healthReport.hash_mismatches as row}
                        <div class="health-row"><span>Asset</span><code title={row}>{row}</code></div>
                      {/each}
                    {/if}
                    {#if (healthReport.bad_storage_ids || []).length}
                      <div class="health-section-title">Bad Storage IDs</div>
                      {#each healthReport.bad_storage_ids as row}
                        <div class="health-row"><span>Item hash</span><code title={row}>{row}</code></div>
                      {/each}
                    {/if}
                    {#if (healthReport.broken_topic_links || []).length}
                      <div class="health-section-title">Broken Topic Links</div>
                      {#each healthReport.broken_topic_links as row}
                        <div class="health-row"><span>Topic</span><code title={row}>{row}</code></div>
                      {/each}
                    {/if}
                    {#if countValues(healthReport.review_mismatches)}
                      <div class="health-section-title">Review Mismatches</div>
                      {#each detailValues(healthReport.review_mismatches) as row}
                        <div class="health-row"><span>{healthKindLabel(row.kind)}</span><code title={row.value}>{row.value}</code></div>
                      {/each}
                    {/if}
                    {#if (healthReport.workspace_dictionary_drift?.missing_in_dictionary || 0) + (healthReport.workspace_dictionary_drift?.unused_in_vault || 0) > 0}
                      <div class="health-section-title">Dictionary Drift</div>
                      {#if healthReport.workspace_dictionary_drift?.missing_in_dictionary}
                        <div class="health-row"><span>Missing in dict</span><code>{healthReport.workspace_dictionary_drift.missing_in_dictionary} tags</code></div>
                      {/if}
                      {#if healthReport.workspace_dictionary_drift?.unused_in_vault}
                        <div class="health-row"><span>Unused in vault</span><code>{healthReport.workspace_dictionary_drift.unused_in_vault} tags</code></div>
                      {/if}
                    {/if}
                    {#if repairErrors.length}
                      <div class="health-section-title">WD Tagging Errors ({repairErrors.length})</div>
                      {#each repairErrors as err}
                        <div class="health-row">
                          <span>{err.status || 'error'}</span>
                          <code title={err.error}>{err.error}</code>
                        </div>
                      {/each}
                    {/if}
                  </div>
                </div>
              </div>
            {/if}
            {#if healthResult}
              <div class="workspace-result">{healthResult}</div>
            {/if}
            <div class="add-workspace">
              <button type="button" on:click={() => backupVault('backup')} disabled={healthBusy || !healthVaultId}>Backup Vault</button>
              <button type="button" on:click={() => backupVault('export')} disabled={healthBusy || !healthVaultId}>Export Vault</button>
            </div>
            <div class="add-workspace">
              <input type="text" placeholder="Vault package path" bind:value={importPackagePath} />
              <input type="text" placeholder="Imported vault name" bind:value={importVaultName} />
              <button type="button" on:click={importVaultPackage} disabled={healthBusy || !importPackagePath.trim()}>Import Vault</button>
            </div>
            {#if backupResult}
              <div class="workspace-result">{backupResult}</div>
            {/if}
          </div>
        </div>
      </div>
    {/if}

    <div class="form-grid">
      <label for="settings-layout-mode">Vault Layout Mode</label>
      <select id="settings-layout-mode" value={$config.ui.vault_layout_mode} on:change={(event) => setConfig((draft) => draft.ui.vault_layout_mode = textValue(event))}>
        <option value="masonry">Masonry</option>
        <option value="grid">Grid</option>
      </select>

      <label for="settings-tile-min-width">Vault Min Tile Width</label>
      <input
        id="settings-tile-min-width"
        type="number"
        min={TILE_MIN_WIDTH_FLOOR}
        max={TILE_MIN_WIDTH_CEILING}
        step="10"
        value={$config.ui.vault_tile_min_width}
        on:input={(event) => setConfig((draft) => draft.ui.vault_tile_min_width = numberValue(event))}
      />

      <div class="grid-spacer"></div>
      <div class="checkbox-group">
        <label class="check-label">
          <input type="checkbox" checked={$config.processing.flatten_transparency} on:change={(event) => setConfig((draft) => draft.processing.flatten_transparency = checkedValue(event))} />
          Flatten Transparency
        </label>
        <label class="check-label">
          <input type="checkbox" checked={$config.tagging.enabled} on:change={(event) => setConfig((draft) => draft.tagging.enabled = checkedValue(event))} />
          Enable Tagging
        </label>
      </div>

      <label for="settings-model-repo">Tag Model Repo</label>
      <input id="settings-model-repo" type="text" value={$config.tagging.model_repo} on:input={(event) => setConfig((draft) => draft.tagging.model_repo = textValue(event))} />

      <label for="settings-tag-device">Tag Device</label>
      <select id="settings-tag-device" value={$config.tagging.device} on:change={(event) => setConfig((draft) => draft.tagging.device = textValue(event))}>
        <option value="cpu">cpu</option>
        <option value="cuda">cuda</option>
        <option value="auto">auto</option>
      </select>

      <label for="settings-tag-threshold">Tag Threshold</label>
      <div class="multi-input">
        <input id="settings-tag-threshold" type="number" step="0.05" value={$config.tagging.threshold} on:input={(event) => setConfig((draft) => draft.tagging.threshold = numberValue(event))} />
        <label class="inline-label" for="settings-max-tags">Max Tags</label>
        <input id="settings-max-tags" type="number" value={$config.tagging.max_tags} on:input={(event) => setConfig((draft) => draft.tagging.max_tags = numberValue(event))} />
      </div>

      <div class="grid-spacer"></div>
      <button class="save-large" class:primary={$configDirty} on:click={saveCurrentConfig} disabled={!$configDirty || $configSaving}>
        {$configSaving ? 'Saving...' : 'Save Settings'}
      </button>
    </div>

    <div class="maintenance-panel">
      <h4>Maintenance</h4>
      <div class="maintenance-grid">
        <button on:click={() => runMaintenance('auth')} disabled={maintenanceBusy.auth}>
          {maintenanceBusy.auth ? 'Running...' : 'Auth Scan'}
        </button>
        <span class="maintenance-status">{maintenanceResult.auth}</span>
        <button on:click={() => runMaintenance('metadata')} disabled={maintenanceBusy.metadata}>
          {maintenanceBusy.metadata ? 'Running...' : 'Rebuild Metadata Index'}
        </button>
        <div class="maintenance-status metadata-progress-cell">
          <span>{maintenanceResult.metadata}</span>
          {#if metadataRebuildJob?.running}
            <div class="metadata-progress" aria-label="Metadata rebuild progress">
              <div class="metadata-progress-fill" style={`width: ${metadataProgressPercent(metadataRebuildJob)}%`}></div>
            </div>
          {/if}
        </div>
        <button on:click={() => runMaintenance('workspaceMetadata')} disabled={maintenanceBusy.workspaceMetadata}>
          {maintenanceBusy.workspaceMetadata ? 'Running...' : 'Rebuild Workspace Metadata'}
        </button>
        <span class="maintenance-status">{maintenanceResult.workspaceMetadata}</span>
        <button on:click={() => runMaintenance('workspacePrune')} disabled={maintenanceBusy.workspacePrune}>
          {maintenanceBusy.workspacePrune ? 'Running...' : 'Prune Workspace Metadata'}
        </button>
        <span class="maintenance-status">{maintenanceResult.workspacePrune}</span>
        <button on:click={() => runMaintenance('review')} disabled={maintenanceBusy.review}>
          {maintenanceBusy.review ? 'Running...' : 'Cleanup Review'}
        </button>
        <span class="maintenance-status">{maintenanceResult.review}</span>
      </div>
    </div>

    <div class="shortcuts-guide">
      <h4>Keyboard Shortcuts & Search Prefixes</h4>
      <div class="shortcuts-grid">
        <div class="shortcut-row">
          <span class="key">Enter</span>
          <span class="desc">Execute Search</span>
        </div>
        <div class="shortcut-row">
          <span class="key">F5</span>
          <span class="desc">Refresh Active View</span>
        </div>
        <div class="shortcut-row">
          <span class="key">Ctrl+F5</span>
          <span class="desc">Full App Reload</span>
        </div>
        <div class="shortcut-row">
          <span class="key">Esc</span>
          <span class="desc">Close Media Focus</span>
        </div>
        <div class="shortcut-row">
          <span class="key">W</span>
          <span class="desc">Toggle Wide View</span>
        </div>
        <div class="shortcut-row">
          <span class="key">F</span>
          <span class="desc">Toggle Fullscreen</span>
        </div>
        <div class="shortcut-row">
          <span class="key">A</span>
          <span class="desc">Previous Item in Group</span>
        </div>
        <div class="shortcut-row">
          <span class="key">D</span>
          <span class="desc">Next Item in Group</span>
        </div>
        <div class="shortcut-row">
          <span class="key">I</span>
          <span class="desc">Toggle Inspector Panel</span>
        </div>
        <div class="divider"></div>
        <div class="shortcut-row">
          <span class="key">/grid</span>
          <span class="desc">Switch Vault to Grid Layout</span>
        </div>
        <div class="shortcut-row">
          <span class="key">/masonry</span>
          <span class="desc">Switch Vault to Masonry Layout</span>
        </div>
        <div class="shortcut-row">
          <span class="key">/zoom-in</span>
          <span class="desc">Increase Vault Tile Size</span>
        </div>
        <div class="shortcut-row">
          <span class="key">/zoom-out</span>
          <span class="desc">Decrease Vault Tile Size</span>
        </div>
        <div class="shortcut-row">
          <span class="key">/toggle-inspector</span>
          <span class="desc">Toggle Inspector Panel</span>
        </div>
        <div class="shortcut-row">
          <span class="key">/ram-track</span>
          <span class="desc">Toggle RAM Tracker Footer</span>
        </div>
        <div class="shortcut-row">
          <span class="key">/scan-auth</span>
          <span class="desc">Run Auth Status Scan</span>
        </div>
        <div class="shortcut-row">
          <span class="key">/cleanup-review</span>
          <span class="desc">Retry Review Cleanup</span>
        </div>
        <div class="shortcut-row">
          <span class="key">/sort-newest</span>
          <span class="desc">Sort Vault by Newest</span>
        </div>
        <div class="shortcut-row">
          <span class="key">/sort-oldest</span>
          <span class="desc">Sort Vault by Oldest</span>
        </div>
        <div class="shortcut-row">
          <span class="key">/sort-artist</span>
          <span class="desc">Sort Vault by Artist</span>
        </div>
        <div class="shortcut-row">
          <span class="key">/media-all</span>
          <span class="desc">Show All Media Types</span>
        </div>
        <div class="shortcut-row">
          <span class="key">/media-image</span>
          <span class="desc">Filter Images Only</span>
        </div>
        <div class="shortcut-row">
          <span class="key">/media-video</span>
          <span class="desc">Filter Videos Only</span>
        </div>
        <div class="divider"></div>
        <div class="shortcut-row">
          <span class="key">/</span>
          <span class="desc">Command Prefix</span>
        </div>
        <div class="shortcut-row">
          <span class="key">a:</span>
          <span class="desc">Artist Prefix</span>
        </div>
        <div class="shortcut-row">
          <span class="key">p:</span>
          <span class="desc">Platform Prefix</span>
        </div>
        <div class="shortcut-row">
          <span class="key">t:</span>
          <span class="desc">Topic Prefix</span>
        </div>
        <div class="shortcut-row">
          <span class="key">#</span>
          <span class="desc">WD Tag Prefix</span>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .settings-container {
    flex-grow: 1;
    padding: 20px 15px;
    background: var(--bg-main);
    overflow-y: auto;
  }

  h3 { color: var(--text-bright); margin: 0; }

  .header-row {
    display: flex;
    align-items: center;
    gap: 15px;
    margin-bottom: 25px;
  }

  .status-label.unsaved {
    color: var(--accent-warning);
    font-size: 12px;
    font-weight: 600;
  }

  .form-grid {
    display: grid;
    grid-template-columns: 180px 1fr;
    gap: 15px;
    align-items: center;
    max-width: 600px;
  }

  .workspace-panel {
    max-width: 900px;
    margin-bottom: 24px;
    border: 1px solid var(--border-dim);
    background: var(--bg-panel);
    border-radius: 8px;
    padding: 14px;
  }

  .workspace-panel h4 {
    margin: 0 0 12px 0;
    color: var(--text-bright);
    font-size: 14px;
  }

  .workspace-grid {
    display: grid;
    grid-template-columns: 90px minmax(0, 1fr);
    gap: 8px 12px;
    align-items: center;
    color: var(--text-muted);
    font-size: 12px;
  }

  .workspace-grid strong {
    color: var(--text-main);
  }

  .workspace-grid code {
    color: var(--text-main);
    background: var(--bg-main);
    border: 1px solid var(--border-dim);
    border-radius: 4px;
    padding: 4px 6px;
    overflow-wrap: anywhere;
  }

  .workspace-note,
  .workspace-result,
  .restart-banner {
    margin-top: 10px;
    color: var(--text-muted);
    font-size: 12px;
  }

  .restart-banner {
    color: var(--accent-warning);
    font-weight: 600;
  }

  .workspace-actions {
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid var(--border-dim);
  }

  .workspace-actions h5 {
    margin: 0 0 10px 0;
    color: var(--text-bright);
    font-size: 13px;
  }

  .workspace-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .workspace-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 10px;
    align-items: center;
    padding: 8px;
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    background: var(--bg-main);
  }

  .workspace-row div {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .row-actions {
    display: flex;
    flex-direction: row;
    gap: 6px;
    justify-content: flex-end;
  }

  .row-actions button {
    white-space: nowrap;
  }

  .workspace-row code {
    color: var(--text-muted);
    overflow-wrap: anywhere;
  }

  .missing {
    color: var(--accent-danger);
    font-size: 12px;
  }

  .add-workspace {
    display: grid;
    grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr) 130px;
    gap: 8px;
    margin-top: 10px;
  }

  label { font-size: 13px; color: var(--text-main); }

  input[type="text"], input[type="number"], select {
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    padding: 8px 12px;
    color: var(--text-main);
    border-radius: 6px;
    font-size: 13px;
    width: 100%;
    box-sizing: border-box;
  }

  .grid-spacer { display: block; }

  .checkbox-group { display: flex; flex-direction: column; gap: 10px; }
  .check-label { display: flex; align-items: center; gap: 10px; cursor: pointer; }

  .multi-input { display: flex; gap: 15px; align-items: center; }
  .inline-label { margin-left: 10px; }

  .save-large {
    margin-top: 10px;
    padding: 12px;
    width: 100%;
    font-size: 14px;
  }

  .centered { flex-grow: 1; display: flex; align-items: center; justify-content: center; color: var(--text-muted); }

  .shortcuts-guide {
    margin-top: 40px;
    padding-top: 25px;
    border-top: 1px solid var(--border-dim);
    max-width: 600px;
  }

  .maintenance-panel {
    margin-top: 26px;
    max-width: 600px;
    border-top: 1px solid var(--border-dim);
    padding-top: 18px;
  }

  .maintenance-panel h4 {
    margin: 0 0 12px 0;
    color: var(--text-bright);
    font-size: 14px;
  }

  .vault-tool-panel {
    margin-top: 14px;
    border-top: 1px solid var(--border-dim);
    padding-top: 12px;
  }

  .vault-tool-panel h5 {
    margin: 0 0 8px 0;
    color: var(--text-bright);
    font-size: 13px;
  }

  .merge-source-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 12px;
    margin: 8px 0;
  }

  .merge-source-list label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--text-muted);
    font-size: 12px;
  }

  .health-summary {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 8px 0;
    color: var(--text-muted);
    font-size: 12px;
  }

  .health-detail {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin: 8px 0;
    color: var(--text-muted);
    font-size: 12px;
  }

  .health-section-title {
    color: var(--text-bright);
    font-size: 13px;
    font-weight: 700;
    margin-top: 8px;
  }

  .health-section-title:first-child {
    margin-top: 0;
  }

  .health-row {
    display: grid;
    grid-template-columns: 92px minmax(0, 1fr);
    gap: 10px;
    align-items: baseline;
    min-height: 20px;
  }

  .health-row span {
    color: var(--text-muted);
    font-size: 12px;
  }

  .health-row code {
    display: block;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-bright);
    font-size: 12px;
  }

  .compact-action {
    padding: 2px 8px;
    min-height: 22px;
    font-size: 12px;
  }

  .modal-backdrop {
    position: fixed;
    inset: 0;
    z-index: 60;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.55);
  }

  .health-modal {
    width: min(900px, calc(100vw - 32px));
    height: min(720px, calc(100vh - 32px));
    display: flex;
    flex-direction: column;
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    box-shadow: 0 18px 60px rgba(0, 0, 0, 0.45);
    padding: 14px;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 10px;
  }

  .modal-header h4 {
    margin: 0;
    color: var(--text-bright);
    font-size: 14px;
  }

  .health-modal .health-detail {
    overflow: auto;
    min-height: 0;
    flex: 1;
    margin: 0;
    padding: 2px 8px 2px 0;
    scrollbar-width: thin;
  }

  .maintenance-grid {
    display: grid;
    grid-template-columns: 210px 1fr;
    gap: 8px 12px;
    align-items: center;
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    padding: 12px;
  }

  .maintenance-status {
    color: var(--text-muted);
    font-size: 12px;
    min-height: 18px;
    overflow-wrap: anywhere;
  }

  .metadata-progress-cell {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .metadata-progress {
    height: 6px;
    width: 100%;
    overflow: hidden;
    border-radius: 999px;
    background: var(--bg-main);
    border: 1px solid var(--border-dim);
  }

  .metadata-progress-fill {
    height: 100%;
    min-width: 2px;
    background: var(--accent-primary);
  }

  .shortcuts-guide h4 {
    margin: 0 0 15px 0;
    color: var(--text-bright);
    font-size: 14px;
  }

  .shortcuts-grid {
    display: flex;
    flex-direction: column;
    gap: 8px;
    background: var(--bg-panel);
    padding: 15px;
    border-radius: 8px;
    border: 1px solid var(--border-dim);
  }

  .shortcut-row {
    display: flex;
    align-items: center;
    gap: 15px;
  }

  .shortcut-row .key {
    background: var(--bg-main);
    border: 1px solid var(--border-dim);
    padding: 4px 8px;
    border-radius: 4px;
    font-family: 'Consolas', monospace;
    font-size: 11px;
    font-weight: bold;
    color: var(--text-bright);
    min-width: 60px;
    text-align: center;
  }

  .shortcut-row .desc {
    font-size: 13px;
    color: var(--text-muted);
  }

  .divider {
    height: 1px;
    background: var(--border-dim);
    margin: 5px 0;
  }
</style>
