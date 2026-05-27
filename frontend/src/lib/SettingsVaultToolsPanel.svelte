<script lang="ts">
  import { countValues } from './settingsUtils';
  import VaultHealthDetailsModal from './VaultHealthDetailsModal.svelte';

  export let vaults: any[] = [];
  export let vaultActive = '';
  export let mergeTargetId = '';
  export let mergeSourceIds: string[] = [];
  export let mergePreview: any = null;
  export let mergeBusy = false;
  export let mergeResult = '';
  export let healthVaultId = '';
  export let healthBusy = false;
  export let healthResult = '';
  export let healthReport: any = null;
  export let healthDetailsOpen = false;
  export let repairErrors: Array<{ hash: string; storage_id: string; status: string; error: string }> = [];
  export let backupResult = '';
  export let importPackagePath = '';
  export let importVaultName = '';
  export let onToggleMergeSource: (id: string, checked: boolean) => void;
  export let onPreviewVaultMerge: () => void;
  export let onConfirmVaultMerge: () => void;
  export let onAuditVaultHealth: () => void;
  export let onRepairVaultHealth: () => void;
  export let onBackupVault: (kind: 'backup' | 'export') => void;
  export let onImportVaultPackage: () => void;
  export let checkedValue: (event: Event) => boolean;
</script>

<div class="vault-tool-panel">
  <h5>Merge Vaults</h5>
  <div class="add-workspace">
    <select bind:value={mergeTargetId} on:change={() => { mergeSourceIds = mergeSourceIds.filter((id) => id !== mergeTargetId); mergePreview = null; }}>
      {#each vaults as vault}
        <option value={vault.id}>{vault.name}</option>
      {/each}
    </select>
    <button type="button" on:click={onPreviewVaultMerge} disabled={mergeBusy || !mergeTargetId || !mergeSourceIds.length}>Preview Merge</button>
    <button type="button" on:click={onConfirmVaultMerge} disabled={mergeBusy || !mergeTargetId || !mergeSourceIds.length}>Merge</button>
  </div>
  <div class="merge-source-list">
    {#each vaults as vault}
      <label>
        <input
          type="checkbox"
          disabled={mergeBusy || vault.id === mergeTargetId}
          checked={mergeSourceIds.includes(vault.id)}
          on:change={(event) => onToggleMergeSource(vault.id, checkedValue(event))}
        />
        <span>{vault.name}</span>
      </label>
    {/each}
  </div>
  {#if mergePreview}
    <div class="workspace-note">
      {Number(mergePreview.total_items || 0).toLocaleString()} total |
      {Number(mergePreview.duplicates || 0).toLocaleString()} duplicates |
      {Number(mergePreview.importable || 0).toLocaleString()} importable
    </div>
  {/if}
  {#if mergeResult}
    <div class="workspace-result">{mergeResult}</div>
  {/if}
</div>

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
