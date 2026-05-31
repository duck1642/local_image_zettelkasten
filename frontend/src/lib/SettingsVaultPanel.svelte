<script lang="ts">
  import { IconAlertTriangle, IconFolder, IconPlus, IconPencil, IconTrash, IconCheckCircle } from './icons';
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

<div class="workspace-actions settings-flat-actions">
  <h4 class="settings-section-title">
    <span class="settings-title-icon">
      <IconFolder size={14} />
    </span>
    Managed Vaults
  </h4>
  
  {#if vaultRestartRequired}
    <div class="restart-banner settings-inline-banner">
      <IconAlertTriangle size={12} />
      <span>Restart required to load the newly selected media vault.</span>
    </div>
  {/if}
  
  <div class="workspace-list settings-list-spacing">
    {#each vaults as vault}
      <div class="workspace-row settings-row-compact">
        <div class="settings-row-main">
          <div class="settings-row-title">
            {#if vault.id === vaultActive}
              <span class="settings-status-icon success">
                <IconFolder size={12} />
              </span>
            {/if}
            <strong class="settings-row-name">{vault.name}</strong>
            <span class="item-count-badge">{Number(vault.item_count || 0).toLocaleString()} items</span>
            {#if vault.id === vaultActive}
              <span class="active-badge">Active</span>
            {/if}
            {#if !vault.exists}
              <span class="missing-badge">Missing Vault Directory</span>
            {/if}
          </div>
          <code class="settings-code">{vault.root}</code>
        </div>
        <div class="row-actions row-actions-centered">
          <button
            class="settings-small-action"
            type="button"
            disabled={vaultBusy}
            on:click={() => onRenameVault(vault.id, vault.name)}
          >
            <IconPencil size={11} />
            Rename
          </button>
          <button
            class="settings-small-action"
            type="button"
            disabled={vaultBusy || vault.id === vaultActive || !vault.exists}
            on:click={() => onSetActiveVault(vault.id)}
          >
            {#if vault.id === vaultActive}
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
          <button
            class="btn-danger settings-small-action"
            type="button"
            disabled={vaultBusy || vault.id === vaultActive}
            on:click={() => onDeleteVault(vault.id)}
          >
            <IconTrash size={11} />
            Delete
          </button>
        </div>
      </div>
    {/each}
  </div>

  <h4 class="settings-section-title settings-subsection-muted">Create New Vault</h4>
  <div class="add-workspace settings-dashed-panel settings-add-vault">
    <input type="text" placeholder="Desired vault folder name" bind:value={vaultName} />
    <button class="settings-icon-button" type="button" on:click={onAddVault} disabled={vaultBusy || !vaultName.trim()}>
      <IconPlus size={11} />
      Create Vault
    </button>
  </div>
  
  {#if vaultResult}
    <div class="workspace-result settings-result">
      {vaultResult}
    </div>
  {/if}
  <slot />
</div>
