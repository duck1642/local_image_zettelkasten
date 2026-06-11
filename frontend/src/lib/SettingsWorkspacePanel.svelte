<script lang="ts">
  import { IconAlertTriangle, IconFolder, IconPlus, IconCheckCircle } from './icons';
  export let workspaces: any[] = [];
  export let workspaceActive = '';
  export let workspaceBusy = false;
  export let workspaceRestartRequired = false;
  export let workspaceResult = '';
  export let workspaceParentPath = '';
  export let workspaceName = 'LMZ Workspace';
  export let onSetActiveWorkspace: (id: string) => void;
  export let onCreateWorkspace: () => void;
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
          <code class="settings-code">{workspace.config_path}</code>
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
  <div class="add-workspace settings-dashed-panel">
    <input class="settings-mono-input" type="text" placeholder="Parent folder for LMZ workspace" bind:value={workspaceParentPath} />
    <input type="text" placeholder="Workspace label" bind:value={workspaceName} />
    <button class="settings-icon-button" type="button" on:click={onCreateWorkspace} disabled={workspaceBusy || !workspaceParentPath.trim()}>
      <IconPlus size={11} />
      Create Workspace
    </button>
  </div>
  
  {#if workspaceResult}
    <div class="workspace-result settings-result">
      {workspaceResult}
    </div>
  {/if}
</div>
