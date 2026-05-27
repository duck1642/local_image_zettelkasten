<script lang="ts">
  export let workspaces: any[] = [];
  export let workspaceActive = '';
  export let workspaceBusy = false;
  export let workspaceRestartRequired = false;
  export let workspaceResult = '';
  export let obsidianPath = '';
  export let obsidianName = 'Obsidian Workspace';
  export let onSetActiveWorkspace: (id: string) => void;
  export let onAddObsidianWorkspace: () => void;
</script>

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
          on:click={() => onSetActiveWorkspace(workspace.id)}
        >
          {workspace.id === workspaceActive ? 'Active' : 'Activate'}
        </button>
      </div>
    {/each}
  </div>
  <div class="add-workspace">
    <input type="text" placeholder="Obsidian vault path" bind:value={obsidianPath} />
    <input type="text" placeholder="Workspace name" bind:value={obsidianName} />
    <button type="button" on:click={onAddObsidianWorkspace} disabled={workspaceBusy || !obsidianPath.trim()}>Add Obsidian</button>
  </div>
  {#if workspaceResult}
    <div class="workspace-result">{workspaceResult}</div>
  {/if}
</div>
