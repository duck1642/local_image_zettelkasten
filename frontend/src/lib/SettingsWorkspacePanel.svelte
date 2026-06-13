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
      <div class="workspace-row settings-row-compact">
        <div class="settings-row-main">
          <div class="settings-row-title">
            <strong class="settings-row-name">{workspace.name}</strong>
            {#if workspace.id === workspaceActive}
              <span class="active-badge">Active</span>
            {/if}
            {#if !workspace.exists}
              <span class="missing-badge">Missing Config</span>
            {/if}
          </div>
          <code class="settings-code" title={workspace.config_path}>{workspace.config_path}</code>
        </div>
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
