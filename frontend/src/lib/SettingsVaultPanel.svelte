<script lang="ts">
  import { IconFolder, IconPlus, IconPencil, IconTrash } from './icons';
  export let vaults: any[] = [];
  export let vaultActive = '';
  export let vaultBusy = false;
  export let vaultRestartRequired = false;
  export let vaultResult = '';
  export let vaultName = 'New Vault';
  export let onRenameVault: (id: string, currentName: string) => void;
  export let onSetActiveVault: (id: string) => void;
  export let onDeleteVault: (id: string) => void;
  export let onAddVault: () => void;
</script>

<div class="workspace-actions" style="margin-top: 0; padding-top: 0; border-top: 0;">
  <h4 class="settings-section-title">
    <span style="margin-right: 6px; display: inline-block; vertical-align: text-bottom;">
      <IconFolder size={14} />
    </span>
    Managed Vaults
  </h4>
  
  {#if vaultRestartRequired}
    <div class="restart-banner" style="margin-bottom: 12px; padding: 8px 12px; background: rgba(210, 153, 34, 0.05); border: 1px solid rgba(210, 153, 34, 0.15); border-radius: 6px;">
      ⚠️ Restart required to load the newly selected media vault.
    </div>
  {/if}
  
  <div class="workspace-list" style="margin-bottom: 16px;">
    {#each vaults as vault}
      <div class="workspace-row" style="padding: 10px 12px; border-radius: 6px;">
        <div style="gap: 6px;">
          <div style="display: flex; align-items: center; gap: 8px; flex-direction: row; min-width: 0; flex-wrap: wrap;">
            {#if vault.id === vaultActive}
              <span style="color: var(--accent-primary); display: inline-block; vertical-align: middle; margin-right: 4px;">
                <IconFolder size={12} />
              </span>
            {/if}
            <strong style="color: var(--text-bright); font-size: 13px;">{vault.name}</strong>
            <span class="item-count-badge">{Number(vault.item_count || 0).toLocaleString()} items</span>
            {#if vault.id === vaultActive}
              <span class="active-badge">Active</span>
            {/if}
            {#if !vault.exists}
              <span class="missing-badge">Missing Vault Directory</span>
            {/if}
          </div>
          <code style="font-family: 'Consolas', monospace; font-size: 11px; color: var(--text-muted);">{vault.root}</code>
        </div>
        <div class="row-actions" style="align-items: center;">
          <button
            type="button"
            disabled={vaultBusy}
            on:click={() => onRenameVault(vault.id, vault.name)}
            style="padding: 5px 12px; font-size: 11px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;"
          >
            <IconPencil size={11} />
            Rename
          </button>
          <button
            type="button"
            disabled={vaultBusy || vault.id === vaultActive || !vault.exists}
            on:click={() => onSetActiveVault(vault.id)}
            style="padding: 5px 12px; font-size: 11px; font-weight: 600;"
          >
            {vault.id === vaultActive ? 'Selected' : 'Activate'}
          </button>
          <button
            type="button"
            class="btn-danger"
            disabled={vaultBusy || vault.id === vaultActive}
            on:click={() => onDeleteVault(vault.id)}
            style="padding: 5px 12px; font-size: 11px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;"
          >
            <IconTrash size={11} />
            Delete
          </button>
        </div>
      </div>
    {/each}
  </div>

  <h4 class="settings-section-title" style="margin-top: 20px; color: var(--text-muted);">Create New Vault</h4>
  <div class="add-workspace" style="background: rgba(255, 255, 255, 0.01); border: 1px dashed var(--border-dim); border-radius: 6px; padding: 12px; margin-top: 4px; grid-template-columns: minmax(0, 1.4fr) 130px;">
    <input type="text" placeholder="Desired vault folder name" bind:value={vaultName} />
    <button type="button" on:click={onAddVault} disabled={vaultBusy || !vaultName.trim()} style="font-weight: 600; display: inline-flex; align-items: center; gap: 4px; justify-content: center;">
      <IconPlus size={11} />
      Create Vault
    </button>
  </div>
  
  {#if vaultResult}
    <div class="workspace-result" style="margin-top: 10px; padding: 6px 12px; border-radius: 4px; background: var(--bg-panel); border: 1px solid var(--border-dim); color: var(--text-bright); font-family: 'Consolas', monospace; font-size: 11px;">
      {vaultResult}
    </div>
  {/if}
  <slot />
</div>

