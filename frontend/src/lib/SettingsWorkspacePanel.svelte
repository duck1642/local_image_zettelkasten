<script lang="ts">
  import { IconAlertTriangle, IconFolder, IconPlus, IconCheckCircle } from './icons';
  import { open as openDialog } from '@tauri-apps/plugin-dialog';

  export let workspaces: any[] = [];
  export let workspaceActive = '';
  export let workspaceBusy = false;
  export let workspaceRestartRequired = false;
  export let workspaceParentPath = '';
  export let workspaceName = 'LMZ Workspace';
  export let onSetActiveWorkspace: (id: string) => void;
  export let onCreateWorkspace: () => void;
  export let onDeleteWorkspace: (id: string, deleteFiles: boolean) => void;

  async function handleDeleteWorkspace(workspace: any) {
    if (workspaceBusy) return;
    const name = workspace.name;
    const confirmed = await confirm(`Are you sure you want to delete the workspace "${name}"?\nThis will deregister it from the list.`);
    if (!confirmed) {
      return;
    }
    const deleteFiles = await confirm(`Do you also want to delete the configuration (config.yaml) and database files associated with "${name}" from disk?\n\nWARNING: This will permanently delete the config and workspace database. Vault files will not be deleted.`);
    
    onDeleteWorkspace(workspace.id, deleteFiles);
  }

  $: isValidWorkspace = workspaceParentPath.trim() !== '';

  function defaultNameFromPath(path: string) {
    const clean = path.replace(/\\/g, '/');
    const parts = clean.split('/').filter(Boolean);
    return parts[parts.length - 1] || 'LMZ Workspace';
  }

  async function onSelectFolder() {
    if (workspaceBusy) return;
    try {
      const selection = await openDialog({
        directory: true,
        multiple: false
      });
      if (selection) {
        workspaceParentPath = String(selection);
        if (!workspaceName || workspaceName === 'LMZ Workspace') {
          workspaceName = defaultNameFromPath(workspaceParentPath);
        }
      }
    } catch (e) {
      console.error('Failed to open folder picker:', e);
    }
  }

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
</script>

<div class="workspace-actions settings-workspace-actions">
  <h4 class="settings-section-title">
    <span class="settings-title-icon">
      <IconFolder size={14} />
    </span>
    Registered Workspaces
  </h4>
  
  {#if workspaceRestartRequired}
    <div class="restart-banner settings-inline-banner">
      <IconAlertTriangle size={12} />
      <span>Restart required to apply changes to the active workspace.</span>
    </div>
  {/if}
  
  <div class="workspace-list settings-list-spacing">
    {#each workspaces as workspace}
      {@const details = getWorkspaceDetails(workspace.config_path)}
      <div class="workspace-row settings-row-compact">
        <div class="settings-row-main">
          <div class="settings-row-title">
            <strong class="settings-row-name">{workspace.name}</strong>
            <span class="settings-type-badge" class:local-badge={details.isLocal} class:external-badge={!details.isLocal}>
              {details.isLocal ? 'In-App' : 'External'}
            </span>
            {#if workspace.id === workspaceActive}
              <span class="active-badge">Active</span>
            {/if}
            {#if !workspace.exists}
              <span class="missing-badge">Missing Config</span>
            {/if}
          </div>
          <div class="settings-path-details">
            <div class="settings-path-line">
              <span class="settings-path-label">Root:</span>
              <code class="settings-code" title={details.rootDir}>{details.rootDir}</code>
            </div>
            <div class="settings-path-line">
              <span class="settings-path-label">Config:</span>
              <code class="settings-code" title={workspace.config_path}>{workspace.config_path}</code>
            </div>
          </div>
        </div>
        <div class="row-actions">
          <button
            class="settings-small-action"
            type="button"
            disabled={workspaceBusy || workspace.id === workspaceActive || !workspace.exists}
            on:click={() => onSetActiveWorkspace(workspace.id)}
          >
            {#if workspace.id === workspaceActive}
              <span class="settings-button-icon">
                <IconCheckCircle size={11} />
              </span>
              Selected
            {:else}
              <span class="settings-button-icon">
                <IconFolder size={11} />
              </span>
              Activate
            {/if}
          </button>
          
          {#if workspace.id !== 'default'}
            <button
              class="settings-small-action danger-btn"
              type="button"
              disabled={workspaceBusy || workspace.id === workspaceActive}
              on:click={() => handleDeleteWorkspace(workspace)}
              title="Delete workspace"
            >
              Delete
            </button>
          {/if}
        </div>
      </div>
    {/each}
  </div>

  <h4 class="settings-section-title settings-subsection-muted">Create LMZ Workspace</h4>
  <div class="create-vault-card">
    <div class="create-workspace-form">
      <input
        class="visually-hidden-input"
        type="text"
        placeholder="Parent folder for LMZ workspace"
        bind:value={workspaceParentPath}
      />
      <div class="create-vault-row">
        <input
          type="text"
          placeholder="Workspace label"
          bind:value={workspaceName}
        />
        <button
          class="select-folder-btn"
          type="button"
          on:click={onSelectFolder}
          disabled={workspaceBusy}
          title="Select Workspace Parent Folder"
        >
          <IconFolder size={11} />
        </button>
        <button
          class="create-vault-btn"
          class:active={isValidWorkspace}
          type="button"
          on:click={onCreateWorkspace}
          disabled={workspaceBusy || !isValidWorkspace}
        >
          <IconPlus size={11} />
          Create Workspace
        </button>
      </div>
    </div>
  </div>
</div>

<style>
  .settings-type-badge {
    display: inline-flex;
    align-items: center;
    font-size: 9px;
    font-weight: 600;
    padding: 1px 5px;
    border-radius: 4px;
    line-height: 1;
    border: 1px solid transparent;
    margin-left: 6px;
  }

  .settings-type-badge.local-badge {
    background: rgba(56, 139, 253, 0.1);
    color: #58a6ff;
    border-color: rgba(56, 139, 253, 0.15);
  }

  .settings-type-badge.external-badge {
    background: rgba(188, 142, 253, 0.1);
    color: #bc8cff;
    border-color: rgba(188, 142, 253, 0.15);
  }



  :global(.settings-workspace-actions) :global(.settings-code) {
    margin: 0;
    flex-grow: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: calc(100% - 54px);
  }
  .settings-small-action.danger-btn {
    background: rgba(248, 81, 73, 0.1);
    color: #f85149;
    border: 1px solid rgba(248, 81, 73, 0.2);
  }

  .settings-small-action.danger-btn:hover:not(:disabled) {
    background: rgba(248, 81, 73, 0.2);
    border-color: #f85149;
  }

  .settings-small-action.danger-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
