<script lang="ts">
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

<div class="workspace-actions">
  <h5>Vaults</h5>
  {#if vaultRestartRequired}
    <div class="restart-banner">Restart required to use the selected vault.</div>
  {/if}
  <div class="workspace-list">
    {#each vaults as vault}
      <div class="workspace-row">
        <div>
          <strong>{vault.name}</strong>
          <code>{vault.root}</code>
          <span class="workspace-note">{Number(vault.item_count || 0).toLocaleString()} items</span>
          {#if !vault.exists}
            <span class="missing">missing vault</span>
          {/if}
        </div>
        <div class="row-actions">
          <button type="button" disabled={vaultBusy} on:click={() => onRenameVault(vault.id, vault.name)}>Rename</button>
          <button
            type="button"
            disabled={vaultBusy || vault.id === vaultActive || !vault.exists}
            on:click={() => onSetActiveVault(vault.id)}
          >
            {vault.id === vaultActive ? 'Active' : 'Activate'}
          </button>
          <button type="button" disabled={vaultBusy || vault.id === vaultActive} on:click={() => onDeleteVault(vault.id)}>Delete</button>
        </div>
      </div>
    {/each}
  </div>
  <div class="add-workspace">
    <input type="text" placeholder="Vault name" bind:value={vaultName} />
    <button type="button" on:click={onAddVault} disabled={vaultBusy || !vaultName.trim()}>Create Vault</button>
  </div>
  {#if vaultResult}
    <div class="workspace-result">{vaultResult}</div>
  {/if}
  <slot />
</div>
