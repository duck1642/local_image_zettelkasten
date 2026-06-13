<script lang="ts">
  import { onMount } from 'svelte';
  import ConfirmationModal from './ConfirmationModal.svelte';
  import { config, configDirty, configLoading, loadConfig } from './configStore';
  import { log as uiLog } from './logger';
  import { toastStore } from './toastStore';
  import { handleRuntimeSwitch } from './runtimeStore';
  import SettingsCoreConfigPanel from './SettingsCoreConfigPanel.svelte';
  import SettingsMaintenancePanel from './SettingsMaintenancePanel.svelte';
  import SettingsRuntimePanel from './SettingsRuntimePanel.svelte';
  import SettingsShortcutsPanel from './SettingsShortcutsPanel.svelte';
  import SettingsVaultPanel from './SettingsVaultPanel.svelte';
  import SettingsVaultMergePanel from './SettingsVaultMergePanel.svelte';
  import SettingsVaultHealthPanel from './SettingsVaultHealthPanel.svelte';
  import SettingsWorkspacePanel from './SettingsWorkspacePanel.svelte';
  import { IconSettings, IconMerge, IconAlertTriangle } from './icons';
  import {
    activateVault,
    activateWorkspace,
    cleanupReview,
    createVault,
    fetchMetadataIndexStatus,
    fetchVaultHealth,
    fetchVaults,
    fetchWorkspaces,
    importVaultPackageApi,
    mergeVaultsApi,
    packageVault,
    previewVaultMergeApi,
    pruneWorkspaceMetadata,
    rebuildWorkspaceMetadata,
    createWorkspace as createWorkspaceApi,
    removeVault,
    repairVaultHealthApi,
    scanAuth,
    startMetadataRebuild,
    updateVaultName
  } from './settingsApi';
  import './settings.css';
  import {
    countValues,
    healthSummary,
    metadataProgressText,
    repairSummary,
    type MetadataRebuildJob
  } from './settingsUtils';

  type MaintenanceAction = 'auth' | 'metadata' | 'workspaceMetadata' | 'workspacePrune' | 'review';
  type SettingsTab = 'general' | 'workspace' | 'vaults' | 'maintenance' | 'shortcuts';
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
  let metadataRebuildJob: MetadataRebuildJob | null = null;
  let metadataRebuildPollTimer: number | null = null;
  let workspaces: any[] = [];
  let workspaceActive = '';
  let workspaceBusy = false;
  let workspaceResult = '';
  let workspaceParentPath = '';
  let workspaceName = 'LMZ Workspace';
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
  let activeSettingsTab: SettingsTab = 'general';
  const settingsTabs: Array<{ value: SettingsTab; label: string }> = [
    { value: 'general', label: 'General' },
    { value: 'workspace', label: 'Workspace' },
    { value: 'vaults', label: 'Vaults' },
    { value: 'maintenance', label: 'Maintenance' },
    { value: 'shortcuts', label: 'Shortcuts' }
  ];

  $: if (!mergeTargetId && vaultActive) mergeTargetId = vaultActive;
  $: if (!healthVaultId && vaultActive) healthVaultId = vaultActive;

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
      const payload = await fetchWorkspaces();
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
      const payload = await activateWorkspace(id);
      workspaceActive = String(payload?.active || id);
      workspaces = Array.isArray(payload?.items) ? payload.items : workspaces;
      if (payload?.restart_required !== false) {
        workspaceRestartRequired = true;
        workspaceResult = 'active on next restart';
        toastStore.add({
          type: 'info',
          title: 'Restart Required',
          message: `Workspace "${id}" will activate on next restart.`
        });
      } else {
        workspaceRestartRequired = false;
        workspaceResult = 'Workspace switched dynamically!';
        toastStore.add({
          type: 'success',
          title: 'Workspace Activated',
          message: `Switched to workspace "${id}" dynamically.`
        });
        await handleRuntimeSwitch(payload);
        await Promise.all([loadWorkspaces(), loadVaults()]);
      }
      uiLog('INFO', 'Workspace active changed', { id });
    } catch (error) {
      const errMsg = String(error);
      workspaceResult = `error: ${errMsg}`;
      toastStore.add({
        type: 'error',
        title: 'Workspace Switch Failed',
        message: errMsg
      });
      uiLog('ERROR', 'Workspace active change failed', { id, error: errMsg });
    } finally {
      workspaceBusy = false;
    }
  }

  async function createWorkspace() {
    const path = workspaceParentPath.trim();
    if (!path || workspaceBusy) return;
    workspaceBusy = true;
    workspaceResult = '';
    try {
      const payload = await createWorkspaceApi(path, workspaceName.trim() || 'LMZ Workspace');
      workspaceActive = String(payload?.active || workspaceActive);
      workspaces = Array.isArray(payload?.items) ? payload.items : workspaces;
      workspaceResult = 'workspace registered';
      toastStore.add({
        type: 'success',
        title: 'Workspace Created',
        message: `Successfully registered workspace "${workspaceName.trim() || 'LMZ Workspace'}".`
      });
      workspaceParentPath = '';
      uiLog('INFO', 'Workspace registered', { path });
    } catch (error) {
      const errMsg = String(error);
      workspaceResult = `error: ${errMsg}`;
      toastStore.add({
        type: 'error',
        title: 'Workspace Creation Failed',
        message: errMsg
      });
      uiLog('ERROR', 'Workspace registration failed', { path, error: errMsg });
    } finally {
      workspaceBusy = false;
    }
  }

  async function loadVaults() {
    try {
      const payload = await fetchVaults();
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
      const payload = await createVault(name);
      vaults = Array.isArray(payload?.items) ? payload.items : vaults;
      vaultName = 'New Vault';
      vaultResult = 'vault created';
      toastStore.add({
        type: 'success',
        title: 'Vault Created',
        message: `Successfully created vault "${name}".`
      });
      uiLog('INFO', 'Vault created', { name });
    } catch (error) {
      const errMsg = String(error);
      vaultResult = `error: ${errMsg}`;
      toastStore.add({
        type: 'error',
        title: 'Vault Creation Failed',
        message: errMsg
      });
      uiLog('ERROR', 'Vault create failed', { name, error: errMsg });
    } finally {
      vaultBusy = false;
    }
  }

  async function setActiveVault(id: string) {
    if (!id || vaultBusy) return;
    vaultBusy = true;
    vaultResult = '';
    try {
      const payload = await activateVault(id);
      vaultActive = String(payload?.active || id);
      vaults = Array.isArray(payload?.items) ? payload.items : vaults;
      if (payload?.restart_required !== false) {
        vaultRestartRequired = true;
        vaultResult = 'active on next restart';
        toastStore.add({
          type: 'info',
          title: 'Restart Required',
          message: `Vault "${id}" will activate on next restart.`
        });
      } else {
        vaultRestartRequired = false;
        vaultResult = 'Vault switched dynamically!';
        toastStore.add({
          type: 'success',
          title: 'Vault Activated',
          message: `Switched to vault "${id}" dynamically.`
        });
        await handleRuntimeSwitch(payload);
        await Promise.all([loadWorkspaces(), loadVaults()]);
      }
      uiLog('INFO', 'Vault active changed', { id });
    } catch (error) {
      const errMsg = String(error);
      vaultResult = `error: ${errMsg}`;
      toastStore.add({
        type: 'error',
        title: 'Vault Activation Failed',
        message: errMsg
      });
      uiLog('ERROR', 'Vault active change failed', { id, error: errMsg });
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
      const payload = await updateVaultName(id, name);
      vaults = Array.isArray(payload?.items) ? payload.items : vaults;
      vaultResult = 'vault renamed';
      toastStore.add({
        type: 'success',
        title: 'Vault Renamed',
        message: `Renamed "${currentName || id}" to "${name}".`
      });
    } catch (error) {
      const errMsg = String(error);
      vaultResult = `error: ${errMsg}`;
      toastStore.add({
        type: 'error',
        title: 'Rename Failed',
        message: errMsg
      });
    } finally {
      vaultBusy = false;
    }
  }

  let deleteVaultConfirmOpen = false;
  let deleteVaultConfirmId = '';

  function deleteVault(id: string) {
    if (!id || vaultBusy) return;
    deleteVaultConfirmId = id;
    deleteVaultConfirmOpen = true;
  }

  async function confirmDeleteVault() {
    const id = deleteVaultConfirmId;
    deleteVaultConfirmOpen = false;
    if (!id || vaultBusy) return;
    vaultBusy = true;
    vaultResult = '';
    try {
      const payload = await removeVault(id);
      vaults = Array.isArray(payload?.items) ? payload.items : vaults;
      vaultResult = 'vault deleted';
      toastStore.add({
        type: 'success',
        title: 'Vault Deleted',
        message: `Successfully deleted vault "${id}".`
      });
      mergeSourceIds = mergeSourceIds.filter((value) => value !== id);
      if (mergeTargetId === id) mergeTargetId = vaultActive;
      if (healthVaultId === id) healthVaultId = vaultActive;
    } catch (error) {
      const errMsg = String(error);
      vaultResult = `error: ${errMsg}`;
      toastStore.add({
        type: 'error',
        title: 'Delete Failed',
        message: errMsg
      });
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
      const payload = await previewVaultMergeApi(mergeTargetId, mergeSourceIds);
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
      const payload = await mergeVaultsApi(mergeTargetId, mergeSourceIds);
      mergePreview = payload;
      const importedCount = Number(payload.imported || 0);
      mergeResult = `merged ${importedCount.toLocaleString()} items`;
      toastStore.add({
        type: 'success',
        title: 'Vault Merge Completed',
        message: `Successfully merged ${importedCount.toLocaleString()} items into "${mergeTargetId}".`
      });
      await loadVaults();
    } catch (error) {
      const errMsg = String(error);
      mergeResult = `error: ${errMsg}`;
      toastStore.add({
        type: 'error',
        title: 'Merge Failed',
        message: errMsg
      });
    } finally {
      mergeBusy = false;
    }
  }

  async function auditVaultHealth() {
    if (!healthVaultId || healthBusy) return;
    healthBusy = true;
    healthResult = 'auditing...';
    healthReport = null;
    healthDetailsOpen = false;
    try {
      const payload = await fetchVaultHealth(healthVaultId);
      healthReport = payload;
      healthResult = healthSummary(payload);
      toastStore.add({
        type: 'success',
        title: 'Audit Complete',
        message: `Audit finished: ${healthSummary(payload)}.`
      });
      uiLog('INFO', 'Vault health audit completed', {
        vault: healthVaultId,
        issues: payload?.issue_count || 0,
        missing_files: countValues(payload?.missing_files),
        orphans: countValues(payload?.orphans),
        facet_drift: payload?.facet_drift?.length || 0
      });
    } catch (error) {
      const errMsg = String(error);
      healthResult = `error: ${errMsg}`;
      toastStore.add({
        type: 'error',
        title: 'Audit Failed',
        message: errMsg
      });
      uiLog('ERROR', 'Vault health audit failed', { vault: healthVaultId, error: errMsg });
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
      const payload = await repairVaultHealthApi(healthVaultId, true);
      healthReport = payload.after || null;
      repairErrors = payload.wd_tagging?.errors || [];
      healthResult = repairSummary(payload);
      toastStore.add({
        type: 'success',
        title: 'Repair Complete',
        message: repairSummary(payload)
      });
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
      const errMsg = String(error);
      healthResult = `error: ${errMsg}`;
      toastStore.add({
        type: 'error',
        title: 'Repair Failed',
        message: errMsg
      });
      uiLog('ERROR', 'Vault repair failed', { vault: healthVaultId, error: errMsg });
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
      const payload = await packageVault(id, kind);
      backupResult = `${kind}: ${payload.package_path || 'created'}`;
      toastStore.add({
        type: 'success',
        title: kind === 'backup' ? 'Backup Successful' : 'Export Successful',
        message: `${kind === 'backup' ? 'Backup' : 'Export'} created at: ${payload.package_path || 'default location'}.`
      });
    } catch (error) {
      const errMsg = String(error);
      backupResult = `error: ${errMsg}`;
      toastStore.add({
        type: 'error',
        title: kind === 'backup' ? 'Backup Failed' : 'Export Failed',
        message: errMsg
      });
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
      const payload = await importVaultPackageApi(path, importVaultName.trim());
      vaults = Array.isArray(payload?.items) ? payload.items : vaults;
      importPackagePath = '';
      importVaultName = '';
      backupResult = `imported ${payload.vault || 'vault'}`;
      toastStore.add({
        type: 'success',
        title: 'Vault Imported',
        message: `Successfully imported vault "${payload.vault || 'vault'}".`
      });
    } catch (error) {
      const errMsg = String(error);
      backupResult = `error: ${errMsg}`;
      toastStore.add({
        type: 'error',
        title: 'Import Failed',
        message: errMsg
      });
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

  function stopMetadataRebuildPolling() {
    if (metadataRebuildPollTimer !== null) {
      window.clearTimeout(metadataRebuildPollTimer);
      metadataRebuildPollTimer = null;
    }
  }

  async function pollMetadataRebuildStatus() {
    try {
      const payload = await fetchMetadataIndexStatus();
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
          toastStore.add({
            type: 'success',
            title: 'Metadata Rebuilt',
            message: `Rebuild finished. Errors: ${metadataRebuildJob.errors || 0}.`
          });
          uiLog('INFO', 'Maintenance metadata rebuild completed', {
            errors: metadataRebuildJob.errors || 0,
            duration_ms: metadataRebuildJob.duration_ms || 0
          });
        } else if (metadataRebuildJob?.status === 'error') {
          const message = String(metadataRebuildJob.message || 'metadata rebuild failed');
          setMaintenanceResult('metadata', `error: ${message}`);
          toastStore.add({
            type: 'error',
            title: 'Metadata Rebuild Failed',
            message
          });
          uiLog('ERROR', 'Maintenance metadata rebuild failed', { error: message });
        }
      }
    } catch (error) {
      stopMetadataRebuildPolling();
      setMaintenanceBusy('metadata', false);
      const text = String(error);
      setMaintenanceResult('metadata', `error: ${text}`);
      toastStore.add({
        type: 'error',
        title: 'Metadata Rebuild Failed',
        message: text
      });
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
        const payload = await scanAuth();
        const cookies = String(payload?.auth?.cookies || 'unknown');
        setMaintenanceResult(action, `OK (${cookies})`);
        toastStore.add({
          type: 'success',
          title: 'Auth Scan Complete',
          message: `Authenticated successfully. Cookies: ${cookies}.`
        });
        uiLog('INFO', 'Maintenance action completed', { action: 'auth_scan', cookies });
      } else if (action === 'metadata') {
        const payload = await startMetadataRebuild();
        const status = String(payload?.status || 'started');
        metadataRebuildJob = payload?.maintenance_rebuild || null;
        setMaintenanceResult(action, metadataProgressText(metadataRebuildJob) || status);
        uiLog('INFO', 'Maintenance action completed', { action: 'metadata_rebuild', status });
        if (status === 'started' || metadataRebuildJob?.running) {
          startMetadataRebuildPolling();
          return;
        }
      } else if (action === 'workspaceMetadata') {
        const payload = await rebuildWorkspaceMetadata();
        const after = payload?.after || {};
        setMaintenanceResult(action, `artists ${after.artists || 0}, platforms ${after.platforms || 0}, WD ${after.wd_tags || 0}`);
        toastStore.add({
          type: 'success',
          title: 'Workspace Synced',
          message: `Synced ${after.artists || 0} artists, ${after.platforms || 0} platforms, and ${after.wd_tags || 0} tags.`
        });
        uiLog('INFO', 'Maintenance action completed', { action: 'workspace_metadata_rebuild', after });
      } else if (action === 'workspacePrune') {
        const payload = await pruneWorkspaceMetadata();
        const pruned = payload?.pruned || {};
        setMaintenanceResult(action, `pruned artists ${pruned.artists || 0}, platforms ${pruned.platforms || 0}, WD ${pruned.wd_tags || 0}`);
        toastStore.add({
          type: 'success',
          title: 'Registry Pruned',
          message: `Pruned ${pruned.artists || 0} artists, ${pruned.platforms || 0} platforms, and ${pruned.wd_tags || 0} tags.`
        });
        uiLog('INFO', 'Maintenance action completed', { action: 'workspace_metadata_prune', pruned });
      } else {
        const payload = await cleanupReview();
        const cleaned = Number(payload?.cleaned || 0);
        const failed = Number(payload?.failed || 0);
        setMaintenanceResult(action, `cleaned ${cleaned}, failed ${failed}`);
        toastStore.add({
          type: 'success',
          title: 'Review Cleaned Up',
          message: `Cleaned up ${cleaned} items (${failed} failed).`
        });
        uiLog('INFO', 'Maintenance action completed', { action: 'review_cleanup', cleaned, failed });
      }
    } catch (error) {
      const text = String(error);
      setMaintenanceResult(action, `error: ${text}`);
      toastStore.add({
        type: 'error',
        title: 'Action Failed',
        message: text
      });
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
      <h3 class="settings-page-title">
        <span class="settings-status-icon">
          <IconSettings size={18} />
        </span>
        System Settings
      </h3>
      {#if $configDirty}
        <span class="status-label unsaved">Unsaved Changes</span>
      {/if}
      <div class="settings-tabs">
        {#each settingsTabs as tab}
          <button
            type="button"
            class:active={activeSettingsTab === tab.value}
            on:click={() => activeSettingsTab = tab.value}
          >
            {tab.label}
          </button>
        {/each}
      </div>
    </div>

    {#if activeSettingsTab === 'general'}
      <SettingsCoreConfigPanel />
    {:else if activeSettingsTab === 'workspace' && $config._runtime}
      <SettingsRuntimePanel runtime={$config._runtime} />
      <div class="workspace-panel">
        <SettingsWorkspacePanel
          {workspaces}
          {workspaceActive}
          {workspaceBusy}
          {workspaceRestartRequired}
          bind:workspaceParentPath
          bind:workspaceName
          onSetActiveWorkspace={setActiveWorkspace}
          onCreateWorkspace={createWorkspace}
        />
      </div>
    {:else if activeSettingsTab === 'vaults'}
      <div class="workspace-panel">
        <SettingsVaultPanel
          {vaults}
          {vaultActive}
          {vaultBusy}
          {vaultRestartRequired}
          bind:vaultName
          onRenameVault={renameVault}
          onSetActiveVault={setActiveVault}
          onDeleteVault={deleteVault}
          onAddVault={addVault}
        />
      </div>
    {:else if activeSettingsTab === 'maintenance'}
      <h4 class="settings-section-title">
        <span class="settings-title-icon">
          <IconMerge size={14} />
        </span>
        Vault Tools
      </h4>
      <div class="workspace-panel">
        <SettingsVaultMergePanel
          {vaults}
          bind:mergeTargetId
          bind:mergeSourceIds
          bind:mergePreview
          {mergeBusy}
          onToggleMergeSource={toggleMergeSource}
          onPreviewVaultMerge={previewVaultMerge}
          onConfirmVaultMerge={confirmVaultMerge}
          {checkedValue}
        />
      </div>
      <div class="workspace-panel">
        <SettingsVaultHealthPanel
          {vaults}
          {vaultActive}
          bind:healthVaultId
          {healthBusy}
          {healthReport}
          bind:healthDetailsOpen
          {repairErrors}
          bind:importPackagePath
          bind:importVaultName
          onAuditVaultHealth={auditVaultHealth}
          onRepairVaultHealth={repairVaultHealth}
          onBackupVault={backupVault}
          onImportVaultPackage={importVaultPackage}
        />
      </div>
      <SettingsMaintenancePanel
        {maintenanceBusy}
        {maintenanceResult}
        {metadataRebuildJob}
        onRunMaintenance={runMaintenance}
      />
    {:else if activeSettingsTab === 'shortcuts'}
      <SettingsShortcutsPanel />
    {/if}
  {/if}

  <ConfirmationModal
    open={deleteVaultConfirmOpen}
    title="Delete Vault"
    confirmLabel="Delete"
    danger={true}
    busy={vaultBusy}
    on:cancel={() => deleteVaultConfirmOpen = false}
    on:confirm={confirmDeleteVault}
  >
    <div class="delete-warning-box">
      <span class="warning-icon">
        <IconAlertTriangle size={14} />
      </span>
      <span class="warning-message">
        Permanently delete vault directory <code>{deleteVaultConfirmId}</code>? All files, notes, and database entries will be erased.
      </span>
    </div>
  </ConfirmationModal>
</div>
