<script lang="ts">
  import { countValues } from './settingsUtils';
  import VaultHealthDetailsModal from './VaultHealthDetailsModal.svelte';

  export let vaults: any[] = [];
  export let vaultActive = '';
  export let healthVaultId = '';
  export let healthBusy = false;
  export let healthResult = '';
  export let healthReport: any = null;
  export let healthDetailsOpen = false;
  export let repairErrors: Array<{ hash: string; storage_id: string; status: string; error: string }> = [];
  export let backupResult = '';
  export let importPackagePath = '';
  export let importVaultName = '';
  export let onAuditVaultHealth: () => void;
  export let onRepairVaultHealth: () => void;
  export let onBackupVault: (kind: 'backup' | 'export') => void;
  export let onImportVaultPackage: () => void;
</script>

<div class="vault-tool-panel">
  <h5>Vault Health</h5>
  <div class="add-workspace">
    <select bind:value={healthVaultId}>
      {#each vaults as vault}
        <option value={vault.id}>{vault.name}</option>
      {/each}
    </select>
    <button type="button" on:click={onAuditVaultHealth} disabled={healthBusy || !healthVaultId}>Audit Vault Health</button>
    <button type="button" on:click={onRepairVaultHealth} disabled={healthBusy || !healthVaultId || healthVaultId !== vaultActive}>Repair Active Vault</button>
  </div>
  {#if healthReport}
    <div class="health-summary">
      <span>{Number(healthReport.issue_count || 0).toLocaleString()} issues</span>
      <span>{countValues(healthReport.missing_files)} missing files</span>
      <span>{countValues(healthReport.orphans)} orphans</span>
      <span>{(healthReport.facet_drift || []).length} facet drift</span>
      <span>{countValues(healthReport.stale_index_rows)} stale index</span>
      <span>{(healthReport.hash_mismatches || []).length} hash mismatch</span>
      <button type="button" class="compact-action" on:click={() => healthDetailsOpen = true}>Details</button>
    </div>
  {/if}
  {#if healthDetailsOpen && healthReport}
    <VaultHealthDetailsModal {healthReport} {repairErrors} onClose={() => healthDetailsOpen = false} />
  {/if}
  {#if healthResult}
    <div class="workspace-result">{healthResult}</div>
  {/if}
  <div class="add-workspace">
    <button type="button" on:click={() => onBackupVault('backup')} disabled={healthBusy || !healthVaultId}>Backup Vault</button>
    <button type="button" on:click={() => onBackupVault('export')} disabled={healthBusy || !healthVaultId}>Export Vault</button>
  </div>
  <div class="add-workspace">
    <input type="text" placeholder="Vault package path" bind:value={importPackagePath} />
    <input type="text" placeholder="Imported vault name" bind:value={importVaultName} />
    <button type="button" on:click={onImportVaultPackage} disabled={healthBusy || !importPackagePath.trim()}>Import Vault</button>
  </div>
  {#if backupResult}
    <div class="workspace-result">{backupResult}</div>
  {/if}
</div>
