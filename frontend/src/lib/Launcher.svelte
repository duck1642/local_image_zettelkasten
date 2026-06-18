<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import { open as openDialog } from '@tauri-apps/plugin-dialog';
  import { apiFetch } from './api';
  import { log as uiLog } from './logger';
  import { applyLauncherWindowLayout } from './windowLayout';
  import {
    IconFolder,
    IconPlus,
    IconRefresh,
    IconSettings,
    IconAlertTriangle,
    IconCheckCircle,
    IconChevronUp,
    IconServer,
    IconChevronLeft
  } from './icons';

  const dispatch = createEventDispatcher<{
    loaded: { workspace_id: string; vault_id: string | null }
  }>();

  type WorkspaceItem = {
    id: string;
    name: string;
    config_path: string;
    active: boolean;
    exists: boolean;
  };

  type VaultItem = {
    id: string;
    name: string;
    root: string;
    exists: boolean;
  };

  // Navigation state: 'workspaces' or 'vaults'
  let step: 'workspaces' | 'vaults' = 'workspaces';

  let workspaces: WorkspaceItem[] = [];
  let vaults: VaultItem[] = [];
  let activeVaultId: string | null = null;
  let selectedWorkspace: WorkspaceItem | null = null;
  let loading = true;
  let loadingVaults = false;
  let actionBusy = false;
  let statusMessage = '';
  let errorMessage = '';
  let nameDialog: 'workspace' | 'vault' | null = null;
  let pendingWorkspacePath = '';
  let pendingWorkspaceName = '';
  let pendingVaultName = 'New Vault';
  let visibleWorkspacePaths = new Set<string>();
  let visibleVaultPaths = new Set<string>();

  function getWorkspaceDetails(configPath: string) {
    const normalized = configPath.replace(/\\/g, '/');
    const isLocal = normalized.toLowerCase().endsWith('config/config.yaml');
    let rootDir = '';
    if (isLocal) {
      const suffix = 'config/config.yaml';
      rootDir = configPath.substring(0, configPath.length - suffix.length).replace(/[/\\]+$/, '');
      if (!rootDir) rootDir = '.';
    } else {
      const suffix = 'config.yaml';
      rootDir = configPath.substring(0, configPath.length - suffix.length).replace(/[/\\]+$/, '');
    }
    return { isLocal, rootDir };
  }

  // Relocation state
  let relocateState: {
    type: 'workspace' | 'vault' | null;
    id: string;
    name?: string;
    current_path?: string;
  } = { type: null, id: '' };

  async function fetchWorkspaces() {
    try {
      loading = true;
      errorMessage = '';
      const startTime = Date.now();
      const res = await apiFetch('/api/workspaces');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      workspaces = Array.isArray(data.items) ? data.items : [];
      
      // Ensure the scanning loader is visible for at least 450ms to prevent jarring flashes
      const elapsed = Date.now() - startTime;
      if (elapsed < 450) {
        await new Promise((resolve) => setTimeout(resolve, 450 - elapsed));
      }
    } catch (e) {
      uiLog('ERROR', 'Failed to fetch workspaces in launcher', { error: String(e) });
      errorMessage = 'Could not load workspaces. Make sure backend is running.';
    } finally {
      loading = false;
    }
  }

  function defaultNameFromPath(path: string) {
    const clean = path.replace(/[\\/]+$/, '');
    const parts = clean.split(/[\\/]/);
    return parts[parts.length - 1] || 'LMZ Workspace';
  }

  async function addWorkspace() {
    if (actionBusy) return;
    try {
      errorMessage = '';
      statusMessage = 'Selecting workspace parent folder...';
      const selection = await openDialog({
        directory: true,
        multiple: false
      });
      if (!selection) {
        statusMessage = '';
        return;
      }
      pendingWorkspacePath = String(selection);
      pendingWorkspaceName = defaultNameFromPath(String(selection));
      nameDialog = 'workspace';
      statusMessage = '';
    } catch (e) {
      uiLog('ERROR', 'Failed to select workspace folder from launcher', { error: String(e) });
      errorMessage = `Failed to select workspace folder: ${String(e)}`;
      statusMessage = '';
    }
  }

  async function confirmAddWorkspace() {
    const name = pendingWorkspaceName.trim();
    if (!name || !pendingWorkspacePath || actionBusy) return;
    try {
      actionBusy = true;
      statusMessage = 'Creating workspace...';
      const res = await apiFetch('/api/workspaces', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: pendingWorkspacePath, name })
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload?.detail || `HTTP ${res.status}`);
      }
      nameDialog = null;
      pendingWorkspacePath = '';
      statusMessage = 'Workspace created.';
      await fetchWorkspaces();
    } catch (e) {
      uiLog('ERROR', 'Failed to create workspace from launcher', { error: String(e) });
      errorMessage = `Failed to create workspace: ${String(e)}`;
      statusMessage = '';
    } finally {
      actionBusy = false;
    }
  }

  async function selectWorkspace(workspace: WorkspaceItem) {
    if (actionBusy) return;
    actionBusy = true;
    errorMessage = '';
    statusMessage = `Loading workspace ${workspace.name}...`;
    try {
      const res = await apiFetch(`/api/workspaces/${workspace.id}/load`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (data.status === 'relocate_workspace') {
        relocateState = {
          type: 'workspace',
          id: workspace.id,
          current_path: data.config_path
        };
        errorMessage = `Workspace configuration file is missing. Please relocate it.`;
        statusMessage = '';
      } else if (data.status === 'relocate_vault') {
        // Workspace loaded but vault needs relocation — go to vault step anyway
        selectedWorkspace = workspace;
        relocateState = {
          type: 'vault',
          id: data.vault_id,
          name: data.vault_name,
          current_path: data.vault_root
        };
        errorMessage = `Vault directory is offline or missing. Please locate it.`;
        statusMessage = '';
        step = 'vaults';
        await fetchVaults();
      } else if (data.status === 'success') {
        uiLog('INFO', 'Workspace loaded, moving to vault selection', { workspace_id: workspace.id });
        selectedWorkspace = workspace;
        statusMessage = '';
        step = 'vaults';
        await fetchVaults();
      } else {
        throw new Error(data.message || 'Unknown response status');
      }
    } catch (e) {
      uiLog('ERROR', 'Failed to load workspace', { workspace_id: workspace.id, error: String(e) });
      errorMessage = `Failed to load workspace: ${String(e)}`;
      statusMessage = '';
    } finally {
      actionBusy = false;
    }
  }

  async function fetchVaults() {
    try {
      loadingVaults = true;
      const startTime = Date.now();
      const res = await apiFetch('/api/vaults');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      vaults = Array.isArray(data.items) ? data.items : [];
      activeVaultId = data.active || null;

      const elapsed = Date.now() - startTime;
      if (elapsed < 300) {
        await new Promise((resolve) => setTimeout(resolve, 300 - elapsed));
      }
    } catch (e) {
      uiLog('ERROR', 'Failed to fetch vaults', { error: String(e) });
      errorMessage = 'Could not load vaults.';
    } finally {
      loadingVaults = false;
    }
  }

  async function addVault() {
    if (actionBusy || !selectedWorkspace) return;
    pendingVaultName = 'New Vault';
    nameDialog = 'vault';
  }

  async function confirmAddVault() {
    const name = pendingVaultName.trim();
    if (!name || actionBusy || !selectedWorkspace) return;
    try {
      actionBusy = true;
      errorMessage = '';
      statusMessage = 'Creating vault...';
      const res = await apiFetch('/api/vaults', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload?.detail || `HTTP ${res.status}`);
      }
      nameDialog = null;
      pendingVaultName = 'New Vault';
      statusMessage = 'Vault created.';
      await fetchVaults();
    } catch (e) {
      uiLog('ERROR', 'Failed to create vault from launcher', { error: String(e) });
      errorMessage = `Failed to create vault: ${String(e)}`;
      statusMessage = '';
    } finally {
      actionBusy = false;
    }
  }

  function closeNameDialog() {
    if (actionBusy) return;
    nameDialog = null;
    pendingWorkspacePath = '';
    pendingWorkspaceName = '';
    pendingVaultName = 'New Vault';
  }

  function toggleWorkspacePath(id: string, event: Event) {
    event.stopPropagation();
    const next = new Set(visibleWorkspacePaths);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    visibleWorkspacePaths = next;
  }

  function toggleVaultPath(id: string, event: Event) {
    event.stopPropagation();
    const next = new Set(visibleVaultPaths);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    visibleVaultPaths = next;
  }

  async function openVault(vault: VaultItem) {
    if (actionBusy || !selectedWorkspace) return;
    actionBusy = true;
    errorMessage = '';
    statusMessage = `Opening vault ${vault.name}...`;
    try {
      // Set the vault active if it's not already
      if (vault.id !== activeVaultId) {
        const res = await apiFetch('/api/vaults/active', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: vault.id })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
      }

      statusMessage = 'Vault ready!';
      dispatch('loaded', { workspace_id: selectedWorkspace.id, vault_id: vault.id });
    } catch (e) {
      uiLog('ERROR', 'Failed to open vault', { vault_id: vault.id, error: String(e) });
      errorMessage = `Failed to open vault: ${String(e)}`;
      statusMessage = '';
    } finally {
      actionBusy = false;
    }
  }

  function goBack() {
    step = 'workspaces';
    selectedWorkspace = null;
    vaults = [];
    activeVaultId = null;
    errorMessage = '';
    statusMessage = '';
    relocateState = { type: null, id: '' };
  }

  async function handleRelocateWorkspace() {
    try {
      errorMessage = '';
      statusMessage = 'Selecting workspace configuration file...';
      const selection = await openDialog({
        directory: false,
        multiple: false,
        filters: [{ name: 'YAML Configuration', extensions: ['yaml', 'yml'] }]
      });
      if (!selection) {
        statusMessage = '';
        return;
      }
      
      statusMessage = 'Relocating workspace path on server...';
      const res = await apiFetch('/api/workspaces/relocate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: relocateState.id,
          new_config_path: String(selection)
        })
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload?.detail || `HTTP ${res.status}`);
      }

      statusMessage = 'Relocated! Retrying...';
      const targetId = relocateState.id;
      relocateState = { type: null, id: '' };
      await fetchWorkspaces();
      const ws = workspaces.find(w => w.id === targetId);
      if (ws) {
        await selectWorkspace(ws);
      }
    } catch (e) {
      uiLog('ERROR', 'Relocation of workspace config failed', { error: String(e) });
      errorMessage = `Relocation failed: ${String(e)}`;
      statusMessage = '';
    }
  }

  async function handleRelocateVault() {
    try {
      errorMessage = '';
      statusMessage = 'Selecting vault root directory...';
      const selection = await openDialog({
        directory: true,
        multiple: false
      });
      if (!selection) {
        statusMessage = '';
        return;
      }

      statusMessage = 'Relocating vault root path on server...';
      const res = await apiFetch('/api/vaults/relocate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vault_id: relocateState.id,
          new_vault_root: String(selection)
        })
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload?.detail || `HTTP ${res.status}`);
      }

      statusMessage = 'Relocated! Refreshing vaults...';
      relocateState = { type: null, id: '' };
      await fetchVaults();
    } catch (e) {
      uiLog('ERROR', 'Relocation of vault directory failed', { error: String(e) });
      errorMessage = `Relocation failed: ${String(e)}`;
      statusMessage = '';
    }
  }

  onMount(() => {
    void applyLauncherWindowLayout();
    fetchWorkspaces();
  });
</script>

<div class="launcher-layout">
  <div class="launcher-card">
    <header class="header">
      <div class="logo-wrap">
        <img src="/lmz-icon.svg" alt="" class="logo-icon" />
      </div>
      <h1 class="title">Local Media Zettelkasten</h1>
    </header>

    {#if loading}
      <div class="spinner-area">
        <div class="spinner"></div>
        <div class="loading-text">Scanning local workspaces...</div>
      </div>
    {:else}
      <div class="launcher-body sleek-scrollbar">
        {#if relocateState.type}
          <!-- Relocation Form View -->
          <div class="form-box">
            <div class="alert-header">
              <IconAlertTriangle size={18} className="alert-icon" />
              <h3>Relocation Required</h3>
            </div>
            <p class="alert-desc">
              {#if relocateState.type === 'workspace'}
                Workspace configuration is missing on this machine. Locate the <code>config.yaml</code> file to restore access.
              {:else}
                Vault directory for <strong>{relocateState.name || relocateState.id}</strong> was not found at its designated path:
              {/if}
            </p>
            <div class="missing-path-box">{relocateState.current_path}</div>
            
            <div class="form-buttons">
              {#if relocateState.type === 'workspace'}
                <button class="primary-action-btn" on:click={handleRelocateWorkspace}>Locate config.yaml File...</button>
              {:else}
                <button class="primary-action-btn" on:click={handleRelocateVault}>Locate Vault Folder...</button>
              {/if}
              <button class="row-action-btn secondary" on:click={() => {
                relocateState = { type: null, id: '' };
                errorMessage = '';
              }}>Cancel</button>
            </div>
          </div>

        {:else if step === 'workspaces'}
          <!-- Step 1: Workspace Selection -->
          <section class="launcher-section">
            <div class="section-header">
              <h3>Select a workspace</h3>
              <button class="icon-btn" on:click={fetchWorkspaces} disabled={actionBusy} title="Refresh workspaces">
                <IconRefresh size={12} />
              </button>
              <button class="icon-btn" on:click={addWorkspace} disabled={actionBusy} title="Add workspace">
                <IconPlus size={12} />
              </button>
            </div>

            {#if workspaces.length > 0}
              <div class="launcher-workspace-list sleek-scrollbar">
                {#each workspaces as w}
                  {#if w.exists}
                    {@const details = getWorkspaceDetails(w.config_path)}
                    <button
                      class="launcher-workspace-row"
                      class:active={w.active}
                      on:click={() => selectWorkspace(w)}
                      disabled={actionBusy}
                    >
                      <div class="launcher-row-info">
                        <div class="launcher-name-line">
                          <IconServer size={14} className="workspace-icon" />
                          <span class="workspace-name">{w.name}</span>
                          <span class="launcher-type-badge" class:local-badge={details.isLocal} class:external-badge={!details.isLocal}>
                            {details.isLocal ? 'In-App' : 'External'}
                          </span>
                          <span class="launcher-status-badge launcher-found">
                            <span class="dot"></span>
                            Found
                          </span>
                        </div>
                        {#if visibleWorkspacePaths.has(w.id)}
                          <div class="launcher-expanded-details">
                            <div class="launcher-path-row">
                              <span class="path-label">Workspace Root</span>
                              <code class="launcher-path-code" title={details.rootDir}>{details.rootDir}</code>
                            </div>
                            <div class="launcher-path-row">
                              <span class="path-label">Configuration File</span>
                              <code class="launcher-path-code" title={w.config_path}>{w.config_path}</code>
                            </div>
                            <div class="launcher-desc-row">
                              {details.isLocal
                                ? "Runs inside the application directory. All vaults and database files reside inside the app repository."
                                : "Isolated workspace. All vaults, logs, and database files reside directly inside this workspace folder."}
                            </div>
                          </div>
                        {/if}
                      </div>
                      <span
                        class="path-toggle-btn"
                        class:open={visibleWorkspacePaths.has(w.id)}
                        role="button"
                        tabindex="0"
                        title={visibleWorkspacePaths.has(w.id) ? 'Hide config path' : 'Show config path'}
                        on:click={(event) => toggleWorkspacePath(w.id, event)}
                        on:keydown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') toggleWorkspacePath(w.id, event);
                        }}
                      >
                        <IconChevronUp size={12} />
                      </span>
                    </button>
                  {:else}
                    {@const details = getWorkspaceDetails(w.config_path)}
                    <div class="launcher-workspace-row missing">
                      <div class="launcher-row-info">
                        <div class="launcher-name-line">
                          <IconServer size={14} className="workspace-icon" />
                          <span class="workspace-name">{w.name}</span>
                          <span class="launcher-type-badge" class:local-badge={details.isLocal} class:external-badge={!details.isLocal}>
                            {details.isLocal ? 'In-App' : 'External'}
                          </span>
                          <span class="launcher-status-badge launcher-missing">
                            <span class="dot"></span>
                            Missing
                          </span>
                        </div>
                        {#if visibleWorkspacePaths.has(w.id)}
                          <div class="launcher-expanded-details">
                            <div class="launcher-path-row">
                              <span class="path-label">Workspace Root</span>
                              <code class="launcher-path-code" title={details.rootDir}>{details.rootDir}</code>
                            </div>
                            <div class="launcher-path-row">
                              <span class="path-label">Configuration File</span>
                              <code class="launcher-path-code" title={w.config_path}>{w.config_path}</code>
                            </div>
                          </div>
                        {/if}
                      </div>
                      <div class="launcher-row-actions">
                        <button class="row-action-btn secondary relocate" on:click={() => {
                          relocateState = { type: 'workspace', id: w.id, current_path: w.config_path };
                          errorMessage = 'Configuration file missing. Please relocate it.';
                        }} disabled={actionBusy}>
                          Relocate
                        </button>
                        <button
                          class="path-toggle-btn"
                          type="button"
                          class:open={visibleWorkspacePaths.has(w.id)}
                          title={visibleWorkspacePaths.has(w.id) ? 'Hide config path' : 'Show config path'}
                          on:click={(event) => toggleWorkspacePath(w.id, event)}
                        >
                          <IconChevronUp size={12} />
                        </button>
                      </div>
                    </div>
                  {/if}
                {/each}
              </div>
            {:else}
              <div class="empty-state">
                <p>No workspaces found.</p>
              </div>
            {/if}
          </section>

        {:else if step === 'vaults'}
          <!-- Step 2: Vault Selection -->
          <section class="launcher-section">
            <div class="section-header vault-section-header">
              <button class="back-btn" on:click={goBack} disabled={actionBusy} title="Back to workspaces">
                <IconChevronLeft size={14} />
              </button>
              <h3>{selectedWorkspace?.name || 'Workspace'}</h3>
              <button class="icon-btn" on:click={fetchVaults} disabled={actionBusy || loadingVaults} title="Refresh vaults">
                <IconRefresh size={12} />
              </button>
              <button class="icon-btn" on:click={addVault} disabled={actionBusy || loadingVaults} title="Add vault">
                <IconPlus size={12} />
              </button>
            </div>

            {#if loadingVaults}
              <div class="spinner-area compact">
                <div class="spinner"></div>
                <div class="loading-text">Loading vaults...</div>
              </div>
            {:else if vaults.length > 0}
              <div class="launcher-workspace-list sleek-scrollbar">
                {#each vaults as v}
                  <button
                    class="launcher-workspace-row"
                    class:active={v.id === activeVaultId}
                    on:click={() => v.exists ? openVault(v) : null}
                    disabled={actionBusy || !v.exists}
                  >
                    <div class="launcher-row-info">
                      <div class="launcher-name-line">
                        <IconFolder size={14} className="vault-icon" />
                        <span class="workspace-name">{v.name}</span>
                        {#if v.id === activeVaultId}
                          <span class="launcher-active-badge">Active</span>
                        {/if}
                        <span class="launcher-status-badge" class:launcher-found={v.exists} class:launcher-missing={!v.exists}>
                          <span class="dot"></span>
                          {v.exists ? 'Found' : 'Missing'}
                        </span>
                      </div>
                      {#if visibleVaultPaths.has(v.id)}
                        <div class="launcher-path-line" title={v.root}>{v.root}</div>
                      {/if}
                    </div>
                    <div class="launcher-row-actions">
                      <span
                        class="path-toggle-btn"
                        class:open={visibleVaultPaths.has(v.id)}
                        role="button"
                        tabindex="0"
                        title={visibleVaultPaths.has(v.id) ? 'Hide vault path' : 'Show vault path'}
                        on:click={(event) => toggleVaultPath(v.id, event)}
                        on:keydown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') toggleVaultPath(v.id, event);
                        }}
                      >
                        <IconChevronUp size={12} />
                      </span>
                    </div>
                  </button>
                {/each}
              </div>
            {:else}
              <div class="empty-state">
                <p>No vaults in this workspace.</p>
              </div>
            {/if}
          </section>
        {/if}
      </div>
    {/if}

    <!-- Status Messages Footer -->
    {#if statusMessage || errorMessage}
      <footer class="launcher-status">
        {#if errorMessage}
          <div class="error-text">
            <IconAlertTriangle size={12} />
            <span>{errorMessage}</span>
          </div>
        {/if}
        {#if statusMessage}
          <div class="status-text">
            <span class="pulse-dot"></span>
            <span>{statusMessage}</span>
          </div>
        {/if}
      </footer>
    {/if}
  </div>

  {#if nameDialog}
    <div class="launcher-dialog-backdrop" role="presentation">
      <div class="launcher-dialog" role="dialog" aria-modal="true" aria-labelledby="launcher-name-dialog-title" tabindex="-1">
        <h3 id="launcher-name-dialog-title">
          {nameDialog === 'workspace' ? 'Create Workspace' : 'Create Vault'}
        </h3>
        {#if nameDialog === 'workspace'}
          <label class="launcher-field">
            <span>Workspace name</span>
            <input type="text" bind:value={pendingWorkspaceName} on:keydown={(event) => event.key === 'Enter' && confirmAddWorkspace()} />
          </label>
          <div class="launcher-path-line dialog-path" title={pendingWorkspacePath}>{pendingWorkspacePath}</div>
        {:else}
          <label class="launcher-field">
            <span>Vault name</span>
            <input type="text" bind:value={pendingVaultName} on:keydown={(event) => event.key === 'Enter' && confirmAddVault()} />
          </label>
        {/if}
        <div class="form-buttons dialog-buttons">
          <button class="primary-action-btn" type="button" disabled={actionBusy || (nameDialog === 'workspace' ? !pendingWorkspaceName.trim() : !pendingVaultName.trim())} on:click={nameDialog === 'workspace' ? confirmAddWorkspace : confirmAddVault}>
            Create
          </button>
          <button class="row-action-btn secondary" type="button" disabled={actionBusy} on:click={closeNameDialog}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  :global(:root) {
    --bg-launcher-gradient: linear-gradient(135deg, #090d16 0%, #111827 100%);
    --accent-glow: rgba(31, 111, 235, 0.15);
  }

  .launcher-layout {
    position: fixed;
    inset: 0;
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-launcher-gradient);
    padding: 16px;
    overflow: hidden;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }

  .launcher-card {
    width: 100%;
    max-width: 580px;
    max-height: 90vh;
    background: rgba(22, 27, 34, 0.85);
    border: 1px solid var(--border-dim);
    border-radius: 12px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5), 0 0 30px var(--accent-glow);
    backdrop-filter: blur(12px);
    display: flex;
    flex-direction: column;
    padding: 24px 32px;
    box-sizing: border-box;
    overflow: hidden;
  }

  .header {
    text-align: center;
    margin-bottom: 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
    flex-shrink: 0;
  }

  .logo-wrap {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 64px;
    height: 64px;
    margin-bottom: 12px;
  }

  .logo-icon {
    display: block;
    width: 64px;
    height: 64px;
  }

  .title {
    font-size: 24px;
    font-weight: 800;
    letter-spacing: -0.5px;
    margin: 0 0 6px 0;
    background: linear-gradient(to right, #58a6ff, #1f6feb);
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .spinner-area {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    padding: 40px 0;
  }

  .spinner-area.compact {
    padding: 24px 0;
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid rgba(255, 255, 255, 0.08);
    border-top-color: var(--accent-primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .loading-text {
    font-size: 13px;
    color: var(--text-muted);
  }

  .launcher-body {
    display: flex;
    flex-direction: column;
    gap: 20px;
    width: 100%;
    overflow-y: auto;
    max-height: calc(95vh - 140px);
    padding-right: 4px;
  }

  .launcher-section {
    display: flex;
    flex-direction: column;
    gap: 10px;
    width: 100%;
  }

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    padding-bottom: 6px;
    gap: 8px;
  }

  .vault-section-header {
    display: grid;
    grid-template-columns: 8px 1fr 20px 20px;
    column-gap: 8px;
  }

  .section-header h3 {
    font-size: 11px;
    font-weight: 700;
    color: var(--text-muted);
    margin: 0;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    flex: 1;
  }

  .back-btn {
    display: flex;
    align-items: center;
    justify-content: flex-start;
    width: 20px;
    margin-left: -4px;
    background: transparent;
    border: none;
    padding: 4px 0;
    color: var(--text-muted);
    border-radius: 4px;
    cursor: pointer;
    transition: color 0.15s ease, background 0.15s ease;
    flex-shrink: 0;
  }

  .back-btn:hover {
    color: var(--text-bright);
  }

  .icon-btn {
    background: transparent;
    border: none;
    padding: 4px;
    color: var(--text-muted);
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    flex-shrink: 0;
  }

  .icon-btn:hover {
    color: var(--text-bright);
    background: var(--bg-hover);
  }

  .launcher-workspace-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 320px;
    overflow-y: auto;
    width: 100%;
  }

  .launcher-workspace-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    background: rgba(13, 17, 23, 0.45);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    box-sizing: border-box;
    width: 100%;
    text-align: left;
    cursor: pointer;
    font-family: inherit;
    color: inherit;
    transition: border-color 0.2s ease, background-color 0.2s ease;
  }

  .launcher-workspace-row:hover:not(:disabled) {
    border-color: rgba(31, 111, 235, 0.35);
    background: rgba(13, 17, 23, 0.7);
  }

  .launcher-workspace-row:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }

  .launcher-workspace-row.active {
    border-color: rgba(31, 111, 235, 0.45);
    background: rgba(31, 111, 235, 0.03);
  }

  .launcher-row-info {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    text-align: left;
    gap: 6px;
    max-width: 75%;
    flex-grow: 1;
    min-width: 0;
  }

  .launcher-name-line {
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 8px;
    flex-wrap: wrap;
    width: 100%;
  }

  :global(.vault-icon),
  :global(.workspace-icon) {
    color: var(--text-muted);
    flex-shrink: 0;
  }

  .workspace-name {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-bright);
  }

  .path-toggle-btn {
    width: 20px;
    height: 20px;
    margin-right: -4px;
    padding: 0;
    border: 0;
    border-radius: 4px;
    background: transparent;
    color: var(--text-muted);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    flex-shrink: 0;
  }

  .path-toggle-btn:hover,
  .path-toggle-btn:focus-visible {
    color: var(--text-bright);
    outline: none;
  }

  .path-toggle-btn :global(svg) {
    transform: rotate(180deg);
    transition: transform 0.12s ease;
  }

  .path-toggle-btn.open :global(svg) {
    transform: rotate(0deg);
  }

  .launcher-active-badge {
    font-size: 9px;
    font-weight: 600;
    background: rgba(31, 111, 235, 0.16);
    color: #58a6ff;
    padding: 1px 5px;
    border-radius: 4px;
  }

  .launcher-status-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 4px;
    line-height: 1;
  }

  .launcher-status-badge.launcher-found {
    background: rgba(35, 134, 54, 0.12);
    color: #3fb950;
  }

  .launcher-status-badge.launcher-missing {
    background: rgba(210, 153, 34, 0.12);
    color: #d29922;
  }

  .launcher-status-badge .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    display: inline-block;
  }

  .launcher-status-badge.launcher-found .dot {
    background: #2ea043;
    box-shadow: 0 0 6px #2ea043;
  }

  .launcher-status-badge.launcher-missing .dot {
    background: #d29922;
    box-shadow: 0 0 6px #d29922;
  }

  .launcher-path-line {
    font-size: 11px;
    color: var(--text-muted);
    font-family: monospace;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    width: 100%;
    align-self: flex-start;
    text-align: left;
  }

  .launcher-row-actions {
    display: flex;
    align-items: center;
    flex-shrink: 0;
  }

  .row-action-btn {
    padding: 6px 18px;
    font-size: 12px;
    font-weight: 600;
    border-radius: 4px;
    cursor: pointer;
    border: 1px solid transparent;
    transition: all 0.15s ease;
  }

  .row-action-btn.secondary {
    background: #21262d;
    border-color: #30363d;
    color: #c9d1d9;
  }

  .row-action-btn.secondary:hover {
    background: #30363d;
    border-color: #8b949e;
  }

  .empty-state {
    padding: 32px 0;
    text-align: center;
    color: var(--text-muted);
    font-size: 13px;
  }

  .empty-state p {
    margin: 0;
  }

  /* Form & Dialog Boxes */
  .form-box {
    padding: 8px 0;
    display: flex;
    flex-direction: column;
    gap: 16px;
    width: 100%;
  }

  .form-box h3 {
    font-size: 16px;
    font-weight: 700;
    margin: 0;
    color: var(--text-bright);
  }

  .form-buttons {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 8px;
  }

  .launcher-dialog-backdrop {
    position: fixed;
    inset: 0;
    z-index: 1100;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(1, 4, 9, 0.64);
    padding: 16px;
  }

  .launcher-dialog {
    width: min(420px, 100%);
    background: #161b22;
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    box-shadow: 0 16px 42px rgba(0, 0, 0, 0.48);
    padding: 18px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .launcher-dialog h3 {
    margin: 0;
    font-size: 15px;
    color: var(--text-bright);
  }

  .launcher-field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 600;
  }

  .launcher-field input {
    width: 100%;
    background: #0d1117;
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    color: var(--text-main);
    padding: 8px 10px;
    font: inherit;
  }

  .launcher-field input:focus {
    outline: none;
    border-color: var(--accent-primary);
  }

  .dialog-path {
    max-width: 100%;
  }

  .dialog-buttons {
    justify-content: flex-end;
    margin-top: 0;
  }

  .primary-action-btn {
    padding: 6px 18px;
    font-size: 12px;
    font-weight: 600;
    border-radius: 4px;
    cursor: pointer;
    background: var(--accent-primary);
    border: 1px solid var(--accent-primary);
    color: white;
    transition: all 0.15s ease;
  }

  .primary-action-btn:hover:not(:disabled) {
    background: #2f81f7;
    border-color: #2f81f7;
  }

  .primary-action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .alert-header {
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--text-bright);
  }

  .alert-header h3 {
    font-size: 15px;
    font-weight: 700;
    margin: 0;
  }

  :global(.alert-icon) {
    color: var(--accent-warning);
  }

  .alert-desc {
    font-size: 13px;
    color: var(--text-muted);
    margin: 0;
    line-height: 1.5;
  }

  .missing-path-box {
    padding: 10px 12px;
    background: #0d1117;
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    font-family: monospace;
    font-size: 11px;
    word-break: break-all;
    color: var(--text-muted);
  }

  .launcher-status {
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .error-text, .status-text {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
  }

  .error-text {
    color: var(--accent-danger);
  }

  .status-text {
    color: var(--text-muted);
  }

  .pulse-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent-primary);
    box-shadow: 0 0 8px var(--accent-primary);
    animation: pulse 1.5s infinite ease-in-out;
  }

  @keyframes pulse {
    0%, 100% { opacity: 0.5; }
    50% { opacity: 1; }
  }

  .launcher-type-badge {
    display: inline-flex;
    align-items: center;
    font-size: 9px;
    font-weight: 600;
    padding: 1px 5px;
    border-radius: 4px;
    line-height: 1;
    border: 1px solid transparent;
  }

  .launcher-type-badge.local-badge {
    background: rgba(56, 139, 253, 0.1);
    color: #58a6ff;
    border-color: rgba(56, 139, 253, 0.15);
  }

  .launcher-type-badge.external-badge {
    background: rgba(188, 142, 253, 0.1);
    color: #bc8cff;
    border-color: rgba(188, 142, 253, 0.15);
  }

  .launcher-expanded-details {
    display: flex;
    flex-direction: column;
    gap: 6px;
    width: 100%;
    padding: 4px 0 2px 0;
  }

  .launcher-path-row {
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 100%;
  }

  .path-label {
    font-size: 9px;
    font-weight: 700;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }

  .launcher-path-code {
    font-size: 11px;
    color: var(--text-muted);
    font-family: monospace;
    white-space: normal;
    word-break: break-all;
    width: 100%;
    align-self: flex-start;
    text-align: left;
    background: rgba(0, 0, 0, 0.2);
    padding: 4px 6px;
    border-radius: 4px;
    border: 1px solid rgba(255, 255, 255, 0.03);
  }

  .launcher-desc-row {
    font-size: 11px;
    color: var(--text-muted);
    font-style: italic;
    line-height: 1.4;
    margin-top: 2px;
  }
</style>
