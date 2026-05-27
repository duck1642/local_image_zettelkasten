<script lang="ts">
  import { IconFolder, IconPlus } from './icons';
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

<div class="workspace-actions" style="margin-top: 18px; padding-top: 16px;">
  <h4 class="settings-section-title">
    <span style="margin-right: 6px; display: inline-block; vertical-align: text-bottom;">
      <IconFolder size={14} />
    </span>
    Registered Workspaces
  </h4>
  
  {#if workspaceRestartRequired}
    <div class="restart-banner" style="margin-bottom: 12px; padding: 8px 12px; background: rgba(210, 153, 34, 0.05); border: 1px solid rgba(210, 153, 34, 0.15); border-radius: 6px;">
      ⚠️ Restart required to apply changes to the active workspace.
    </div>
  {/if}
  
  <div class="workspace-list" style="margin-bottom: 16px;">
    {#each workspaces as workspace}
      <div class="workspace-row" style="padding: 10px 12px; border-radius: 6px;">
        <div style="gap: 6px;">
          <div style="display: flex; align-items: center; gap: 8px; flex-direction: row; min-width: 0;">
            <strong style="color: var(--text-bright); font-size: 13px;">{workspace.name}</strong>
            {#if workspace.id === workspaceActive}
              <span class="active-badge">Active</span>
            {/if}
            {#if !workspace.exists}
              <span class="missing-badge">Missing Config</span>
            {/if}
          </div>
          <code style="font-family: 'Consolas', monospace; font-size: 11px; color: var(--text-muted);">{workspace.config_path}</code>
        </div>
        <button
          type="button"
          disabled={workspaceBusy || workspace.id === workspaceActive || !workspace.exists}
          on:click={() => onSetActiveWorkspace(workspace.id)}
          style="padding: 5px 12px; font-size: 11px; font-weight: 600;"
        >
          {workspace.id === workspaceActive ? 'Selected' : 'Activate'}
        </button>
      </div>
    {/each}
  </div>

  <h4 class="settings-section-title" style="margin-top: 20px; color: var(--text-muted);">Register Obsidian Workspace</h4>
  <div class="add-workspace" style="background: rgba(255, 255, 255, 0.01); border: 1px dashed var(--border-dim); border-radius: 6px; padding: 12px; margin-top: 4px;">
    <input type="text" placeholder="Full path to Obsidian vault" bind:value={obsidianPath} style="font-family: 'Consolas', monospace;" />
    <input type="text" placeholder="Workspace label" bind:value={obsidianName} />
    <button type="button" on:click={onAddObsidianWorkspace} disabled={workspaceBusy || !obsidianPath.trim()} style="font-weight: 600; display: inline-flex; align-items: center; gap: 4px; justify-content: center;">
      <IconPlus size={11} />
      Add Obsidian
    </button>
  </div>
  
  {#if workspaceResult}
    <div class="workspace-result" style="margin-top: 10px; padding: 6px 12px; border-radius: 4px; background: var(--bg-panel); border: 1px solid var(--border-dim); color: var(--text-bright); font-family: 'Consolas', monospace; font-size: 11px;">
      {workspaceResult}
    </div>
  {/if}
</div>

