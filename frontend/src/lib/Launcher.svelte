<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import { open as openDialog } from '@tauri-apps/plugin-dialog';
  import { apiFetch } from './api';
  import { log as uiLog } from './logger';
  import {
    IconFolder,
    IconPlus,
    IconRefresh,
    IconSettings,
    IconAlertTriangle,
    IconCheckCircle,
    IconServer,
    IconDownload
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

  let workspaces: WorkspaceItem[] = [];
  let loading = true;
  let actionBusy = false;
  let statusMessage = '';
  let errorMessage = '';

  // Relocation state
  let relocateState: {
    type: 'workspace' | 'vault' | null;
    id: string;
    name?: string;
    current_path?: string;
  } = { type: null, id: '' };

  // Form states
  let activeForm: 'obsidian' | 'create_vault' | 'import_vault' | null = null;
  let obsidianForm = { name: '', path: '' };
  let vaultForm = { name: '', id: '' };
  let importForm = { package_path: '', name: '', id: '' };

  async function fetchWorkspaces() {
    try {
      loading = true;
      errorMessage = '';
      const res = await apiFetch('/api/workspaces');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      workspaces = Array.isArray(data.items) ? data.items : [];
    } catch (e) {
      uiLog('ERROR', 'Failed to fetch workspaces in launcher', { error: String(e) });
      errorMessage = 'Could not load workspaces. Make sure backend is running.';
    } finally {
      loading = false;
    }
  }

  async function loadWorkspace(workspaceId: string) {
    if (actionBusy) return;
    actionBusy = true;
    errorMessage = '';
    statusMessage = `Initializing workspace ${workspaceId}...`;
    try {
      const res = await apiFetch(`/api/workspaces/${workspaceId}/load`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (data.status === 'relocate_workspace') {
        relocateState = {
          type: 'workspace',
          id: workspaceId,
          current_path: data.config_path
        };
        errorMessage = `Workspace configuration file is missing. Please relocate it.`;
        statusMessage = '';
      } else if (data.status === 'relocate_vault') {
        relocateState = {
          type: 'vault',
          id: data.vault_id,
          name: data.vault_name,
          current_path: data.vault_root
        };
        errorMessage = `Vault directory is offline or missing. Please locate it.`;
        statusMessage = '';
      } else if (data.status === 'success') {
        uiLog('INFO', 'Workspace loaded successfully via launcher', { workspace_id: workspaceId, vault_id: data.active_vault });
        statusMessage = 'Workspace ready!';
        dispatch('loaded', { workspace_id: workspaceId, vault_id: data.active_vault });
      } else {
        throw new Error(data.message || 'Unknown response status');
      }
    } catch (e) {
      uiLog('ERROR', 'Failed to load workspace', { workspace_id: workspaceId, error: String(e) });
      errorMessage = `Failed to load workspace: ${String(e)}`;
      statusMessage = '';
    } finally {
      actionBusy = false;
    }
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

      statusMessage = 'Relocated! Retrying workspace initialization...';
      const targetId = relocateState.id;
      relocateState = { type: null, id: '' };
      await fetchWorkspaces();
      await loadWorkspace(targetId);
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

      statusMessage = 'Relocated! Retrying workspace initialization...';
      // Find active or selected workspace ID
      const activeItem = workspaces.find(w => w.active) || workspaces[0];
      relocateState = { type: null, id: '' };
      if (activeItem) {
        await loadWorkspace(activeItem.id);
      } else {
        await fetchWorkspaces();
      }
    } catch (e) {
      uiLog('ERROR', 'Relocation of vault directory failed', { error: String(e) });
      errorMessage = `Relocation failed: ${String(e)}`;
      statusMessage = '';
    }
  }

  async function pickObsidianPath() {
    try {
      const selection = await openDialog({ directory: true, multiple: false });
      if (selection) {
        obsidianForm.path = String(selection);
      }
    } catch (e) {
      uiLog('ERROR', 'Folder picker failed for Obsidian', { error: String(e) });
    }
  }

  async function pickImportPackage() {
    try {
      const selection = await openDialog({
        directory: false,
        multiple: false,
        filters: [{ name: 'LMZ Package', extensions: ['tar', 'zip'] }]
      });
      if (selection) {
        importForm.package_path = String(selection);
      }
    } catch (e) {
      uiLog('ERROR', 'File picker failed for Package import', { error: String(e) });
    }
  }

  async function submitObsidianForm() {
    if (!obsidianForm.path) return;
    actionBusy = true;
    errorMessage = '';
    statusMessage = 'Setting up Obsidian workspace...';
    try {
      const res = await apiFetch('/api/workspaces/obsidian', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: obsidianForm.path,
          name: obsidianForm.name || 'Obsidian Vault',
          set_active: true
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      
      statusMessage = 'Workspace created! Loading workspace services...';
      obsidianForm = { name: '', path: '' };
      activeForm = null;
      await fetchWorkspaces();
      // Load the newly created workspace (which is marked active)
      const activeItem = workspaces.find(w => w.active);
      if (activeItem) {
        await loadWorkspace(activeItem.id);
      }
    } catch (e) {
      errorMessage = `Setup failed: ${String(e)}`;
      statusMessage = '';
    } finally {
      actionBusy = false;
    }
  }

  async function submitCreateVault() {
    if (!vaultForm.name) return;
    actionBusy = true;
    errorMessage = '';
    statusMessage = 'Creating vault folder...';
    try {
      const res = await apiFetch('/api/vaults', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(vaultForm)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      
      statusMessage = 'Vault created! Reloading active workspace...';
      vaultForm = { name: '', id: '' };
      activeForm = null;
      // Reload active workspace to pick up new vault
      const activeItem = workspaces.find(w => w.active);
      if (activeItem) {
        await loadWorkspace(activeItem.id);
      } else {
        await fetchWorkspaces();
      }
    } catch (e) {
      errorMessage = `Creation failed: ${String(e)}`;
      statusMessage = '';
    } finally {
      actionBusy = false;
    }
  }

  async function submitImportVault() {
    if (!importForm.package_path) return;
    actionBusy = true;
    errorMessage = '';
    statusMessage = 'Importing vault archive...';
    try {
      const res = await apiFetch('/api/vaults/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(importForm)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      
      statusMessage = 'Vault imported! Reloading active workspace...';
      importForm = { package_path: '', name: '', id: '' };
      activeForm = null;
      // Reload active workspace
      const activeItem = workspaces.find(w => w.active);
      if (activeItem) {
        await loadWorkspace(activeItem.id);
      } else {
        await fetchWorkspaces();
      }
    } catch (e) {
      errorMessage = `Import failed: ${String(e)}`;
      statusMessage = '';
    } finally {
      actionBusy = false;
    }
  }

  onMount(() => {
    fetchWorkspaces();
  });
</script>

<div class="launcher-layout">
  <div class="launcher-card">
    <header class="header">
      <div class="logo-wrap">
        <IconServer size={32} class="logo-icon" />
      </div>
      <h1 class="title">Local Media Zettelkasten</h1>
      <p class="subtitle">Secure, portable, agent-assisted media archive manager</p>
    </header>

    {#if loading}
      <div class="spinner-area">
        <div class="spinner"></div>
        <div class="loading-text">Scanning local workspaces...</div>
      </div>
    {:else}
      <div class="launcher-body">
        {#if relocateState.type}
          <!-- Relocation Form View -->
          <div class="form-box">
            <div class="alert-header">
              <IconAlertTriangle size={18} class="alert-icon" />
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
              <button class="row-action-btn secondary" on:click={() => relocateState = { type: null, id: '' }}>Cancel</button>
            </div>
          </div>

        {:else if activeForm === 'obsidian'}
          <!-- Link Obsidian Form View -->
          <div class="form-box">
            <h3>Link Obsidian Vault</h3>
            <p class="form-desc">Creates a workspace configuration that allows LMZ notes to live natively alongside Obsidian md notes.</p>
            
            <div class="form-group">
              <label for="obsidian-name">Workspace Name</label>
              <input id="obsidian-name" type="text" bind:value={obsidianForm.name} placeholder="e.g. Personal Knowledge Base" />
            </div>

            <div class="form-group">
              <label for="obsidian-path">Obsidian Vault Folder</label>
              <div class="input-with-button">
                <input id="obsidian-path" type="text" readonly bind:value={obsidianForm.path} placeholder="Choose folder path..." />
                <button type="button" class="row-action-btn secondary" on:click={pickObsidianPath}>Browse...</button>
              </div>
            </div>

            <div class="form-buttons">
              <button class="primary-action-btn" on:click={submitObsidianForm} disabled={!obsidianForm.path || actionBusy}>Link Vault</button>
              <button class="row-action-btn secondary" on:click={() => activeForm = null} disabled={actionBusy}>Cancel</button>
            </div>
          </div>

        {:else if activeForm === 'create_vault'}
          <!-- Create Vault Form View -->
          <div class="form-box">
            <h3>Create New Vault</h3>
            <p class="form-desc">Initializes a new media vault inside the active workspace directory.</p>
            
            <div class="form-group">
              <label for="vault-name">Vault Display Name</label>
              <input id="vault-name" type="text" bind:value={vaultForm.name} placeholder="e.g. Gameplay Recordings" />
            </div>

            <div class="form-group">
              <label for="vault-slug">Vault ID (Slug, optional)</label>
              <input id="vault-slug" type="text" bind:value={vaultForm.id} placeholder="e.g. gameplay-vault" />
            </div>

            <div class="form-buttons">
              <button class="primary-action-btn" on:click={submitCreateVault} disabled={!vaultForm.name || actionBusy}>Create Vault</button>
              <button class="row-action-btn secondary" on:click={() => activeForm = null} disabled={actionBusy}>Cancel</button>
            </div>
          </div>

        {:else if activeForm === 'import_vault'}
          <!-- Import Vault Form View -->
          <div class="form-box">
            <h3>Import Vault Package</h3>
            <p class="form-desc">Imports a shared LMZ vault archive (.tar or .zip package) into the current workspace registry.</p>
            
            <div class="form-group">
              <label for="package-path">Package Archive File</label>
              <div class="input-with-button">
                <input id="package-path" type="text" readonly bind:value={importForm.package_path} placeholder="Choose archive package..." />
                <button type="button" class="row-action-btn secondary" on:click={pickImportPackage}>Browse...</button>
              </div>
            </div>

            <div class="form-group">
              <label for="import-name">New Vault Name (optional)</label>
              <input id="import-name" type="text" bind:value={importForm.name} placeholder="Leave blank to use package name" />
            </div>

            <div class="form-buttons">
              <button class="primary-action-btn" on:click={submitImportVault} disabled={!importForm.package_path || actionBusy}>Import Package</button>
              <button class="row-action-btn secondary" on:click={() => activeForm = null} disabled={actionBusy}>Cancel</button>
            </div>
          </div>

        {:else}
          <!-- Main Startup Selector View (Obsidian Switcher Style) -->
          {#if workspaces.length > 0}
            <section class="launcher-section">
              <div class="section-header">
                <h3>Open recent workspace</h3>
                <button class="icon-btn" on:click={fetchWorkspaces} disabled={actionBusy} title="Refresh workspaces">
                  <IconRefresh size={12} />
                </button>
              </div>
              
              <div class="workspace-list">
                {#each workspaces as w}
                  <div class="workspace-row" class:active={w.active}>
                    <div class="row-info">
                      <div class="name-line">
                        <span class="workspace-name">{w.name}</span>
                        {#if w.active}
                          <span class="active-badge">Active</span>
                        {/if}
                        <span class="status-indicator {w.exists ? 'online' : 'offline'}" title={w.exists ? 'Online' : 'Offline'}>
                          <span class="dot"></span>
                        </span>
                      </div>
                      <div class="path-line" title={w.config_path}>{w.config_path}</div>
                    </div>
                    
                    <div class="row-actions">
                      {#if !w.exists}
                        <button class="row-action-btn secondary relocate" on:click={() => {
                          relocateState = { type: 'workspace', id: w.id, current_path: w.config_path };
                          errorMessage = 'Configuration file missing. Please relocate it.';
                        }} disabled={actionBusy}>
                          Relocate
                        </button>
                      {:else}
                        <button class="row-action-btn secondary open" on:click={() => loadWorkspace(w.id)} disabled={actionBusy}>
                          Open
                        </button>
                      {/if}
                    </div>
                  </div>
                {/each}
              </div>
            </section>
          {/if}

          <section class="launcher-section">
            <div class="section-header">
              <h3>Get started</h3>
            </div>
            
            <div class="action-rows-list">
              <!-- Link Obsidian Vault Row -->
              <div class="action-row">
                <div class="action-row-info">
                  <div class="action-row-title">Link Obsidian Vault</div>
                  <div class="action-row-desc">Open an existing Obsidian vault containing LMZ notes.</div>
                </div>
                <button class="row-action-btn secondary" on:click={() => activeForm = 'obsidian'} disabled={actionBusy}>
                  Link
                </button>
              </div>

              <!-- Create New Vault Row -->
              <div class="action-row">
                <div class="action-row-info">
                  <div class="action-row-title">Create New Vault</div>
                  <div class="action-row-desc">Initialize a new media vault under a folder.</div>
                </div>
                <button class="row-action-btn primary" on:click={() => activeForm = 'create_vault'} disabled={actionBusy}>
                  Create
                </button>
              </div>

              <!-- Import Vault Package Row -->
              <div class="action-row">
                <div class="action-row-info">
                  <div class="action-row-title">Import Vault Package</div>
                  <div class="action-row-desc">Import a shared vault package (.tar or .zip archive).</div>
                </div>
                <button class="row-action-btn secondary" on:click={() => activeForm = 'import_vault'} disabled={actionBusy}>
                  Import
                </button>
              </div>
            </div>
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
    padding: 24px;
    overflow-y: auto;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }

  .launcher-card {
    width: 100%;
    max-width: 580px;
    min-height: auto;
    background: rgba(22, 27, 34, 0.85);
    border: 1px solid var(--border-dim);
    border-radius: 12px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5), 0 0 30px var(--accent-glow);
    backdrop-filter: blur(12px);
    display: flex;
    flex-direction: column;
    padding: 36px;
    box-sizing: border-box;
  }

  .header {
    text-align: center;
    margin-bottom: 28px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  .logo-wrap {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 64px;
    height: 64px;
    border-radius: 16px;
    background: rgba(31, 111, 235, 0.12);
    border: 1px solid rgba(31, 111, 235, 0.35);
    margin-bottom: 16px;
    box-shadow: 0 0 15px rgba(31, 111, 235, 0.25);
  }

  :global(.logo-icon) {
    color: var(--accent-primary);
  }

  .title {
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -0.5px;
    margin: 0 0 6px 0;
    background: linear-gradient(to right, #58a6ff, #1f6feb);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .subtitle {
    font-size: 13px;
    color: var(--text-muted);
    margin: 0;
  }

  .spinner-area {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    padding: 40px 0;
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
    gap: 28px;
    width: 100%;
  }

  .launcher-section {
    display: flex;
    flex-direction: column;
    gap: 12px;
    width: 100%;
  }

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    padding-bottom: 6px;
  }

  .section-header h3 {
    font-size: 11px;
    font-weight: 700;
    color: var(--text-muted);
    margin: 0;
    text-transform: uppercase;
    letter-spacing: 0.5px;
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
  }

  .icon-btn:hover {
    color: var(--text-bright);
    background: var(--bg-hover);
  }

  .workspace-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 180px;
    overflow-y: auto;
    width: 100%;
    padding-right: 4px;
  }

  .workspace-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    background: rgba(13, 17, 23, 0.45);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    box-sizing: border-box;
    width: 100%;
    transition: border-color 0.2s ease, background-color 0.2s ease;
  }

  .workspace-row:hover {
    border-color: rgba(31, 111, 235, 0.35);
    background: rgba(13, 17, 23, 0.7);
  }

  .workspace-row.active {
    border-color: rgba(31, 111, 235, 0.45);
    background: rgba(31, 111, 235, 0.03);
  }

  .row-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-width: 70%;
  }

  .name-line {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .workspace-name {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-bright);
  }

  .active-badge {
    font-size: 9px;
    font-weight: 600;
    background: rgba(31, 111, 235, 0.16);
    color: #58a6ff;
    padding: 1px 5px;
    border-radius: 4px;
  }

  .status-indicator {
    display: inline-flex;
    align-items: center;
  }

  .status-indicator .dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    display: inline-block;
  }

  .status-indicator.online .dot {
    background: var(--accent-success);
    box-shadow: 0 0 6px var(--accent-success);
  }

  .status-indicator.offline .dot {
    background: var(--accent-warning);
    box-shadow: 0 0 6px var(--accent-warning);
  }

  .path-line {
    font-size: 11px;
    color: var(--text-muted);
    font-family: monospace;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .row-actions {
    display: flex;
    align-items: center;
  }

  /* Action Rows (Obsidian-Style) */
  .action-rows-list {
    display: flex;
    flex-direction: column;
    width: 100%;
  }

  .action-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }

  .action-row:last-child {
    border-bottom: none;
  }

  .action-row-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-width: 75%;
  }

  .action-row-title {
    font-size: 14px;
    font-weight: 500;
    color: #c9d1d9;
  }

  .action-row-desc {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.4;
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

  .row-action-btn.primary {
    background: #58a6ff;
    color: #0d1117;
  }

  .row-action-btn.primary:hover {
    background: #79c0ff;
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

  .form-desc {
    font-size: 12px;
    color: var(--text-muted);
    margin: 0;
    line-height: 1.4;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .form-group label {
    font-size: 10px;
    font-weight: 700;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .form-group input {
    font-size: 13px;
    padding: 9px 12px;
    background: #0d1117;
    border: 1px solid var(--border-dim);
    color: var(--text-main);
    border-radius: 6px;
  }

  .form-group input:focus {
    border-color: var(--accent-primary);
    outline: none;
  }

  .input-with-button {
    display: flex;
    gap: 8px;
  }

  .input-with-button input {
    flex-grow: 1;
  }

  .form-buttons {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 8px;
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
</style>
