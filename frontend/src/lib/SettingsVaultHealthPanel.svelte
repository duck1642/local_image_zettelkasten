<script lang="ts">
  import { countValues } from './settingsUtils';
  import VaultHealthDetailsModal from './VaultHealthDetailsModal.svelte';
  import { IconAlertTriangle, IconCheckCircle, IconCopy, IconFileText, IconPlus } from './icons';

  export let vaults: any[] = [];
  export let vaultActive = '';
  export let healthVaultId = '';
  export let healthBusy = false;
  export let healthReport: any = null;
  export let healthDetailsOpen = false;
  export let repairErrors: Array<{ hash: string; storage_id: string; status: string; error: string }> = [];
  export let importPackagePath = '';
  export let importVaultName = '';
  export let importPreview: any = null;
  export let importPreviewCurrent = false;
  export let onAuditVaultHealth: () => void;
  export let onRepairVaultHealth: () => void;
  export let onBackupVault: (kind: 'backup' | 'export') => void;
  export let onPreviewImportVaultPackage: () => void;
  export let onConfirmImportVaultPackage: () => void;
  export let onImportInputChanged: () => void;

  $: hasIssues = healthReport ? (healthReport.issue_count > 0) : false;
</script>

<div class="vault-tool-panel">
  <h4 class="settings-section-title">
    <span class="settings-title-icon">
      <IconAlertTriangle size={14} />
    </span>
    Vault Health & Portability
  </h4>
  <div class="vault-tool-row settings-row-spaced-large">
    <select bind:value={healthVaultId}>
      {#each vaults as vault}
        <option value={vault.id}>Vault: {vault.name}</option>
      {/each}
    </select>
    <button class="settings-bold-button" type="button" on:click={onAuditVaultHealth} disabled={healthBusy || !healthVaultId}>Audit Health</button>
    <button class="primary settings-bold-button" type="button" on:click={onRepairVaultHealth} disabled={healthBusy || !healthVaultId || healthVaultId !== vaultActive}>Repair Active Vault</button>
  </div>

  {#if healthReport}
    <div class="health-scorecard">
      <div class="health-scorecard-header" class:healthy={!hasIssues} class:warning={hasIssues && healthReport.issue_count < 10} class:danger={hasIssues && healthReport.issue_count >= 10}>
        <span class="health-status-text">
          {#if !hasIssues}
            <span class="health-status-icon healthy">
              <IconCheckCircle size={14} />
            </span>
            Vault Health Check: Healthy & Consistent
          {:else}
            <span class="health-status-icon" class:warning={healthReport.issue_count < 10} class:danger={healthReport.issue_count >= 10}>
              <IconAlertTriangle size={14} />
            </span>
            Vault Health Check: Attention Required ({Number(healthReport.issue_count || 0).toLocaleString()} issue{healthReport.issue_count === 1 ? '' : 's'} found)
          {/if}
        </span>
        <button type="button" class="compact-action settings-bold-button" on:click={() => healthDetailsOpen = true}>
          Inspect Issues
        </button>
      </div>

      <div class="health-scorecard-grid">
        <div class="health-metric-tile" class:has-issues={countValues(healthReport.missing_files) > 0}>
          <span class="metric-num">{countValues(healthReport.missing_files)}</span>
          <span class="metric-label">Missing Files</span>
        </div>
        <div class="health-metric-tile" class:has-issues={countValues(healthReport.orphans) > 0}>
          <span class="metric-num">{countValues(healthReport.orphans)}</span>
          <span class="metric-label">Orphan Media</span>
        </div>
        <div class="health-metric-tile" class:has-issues={(healthReport.facet_drift || []).length > 0}>
          <span class="metric-num">{(healthReport.facet_drift || []).length}</span>
          <span class="metric-label">Facet Drift</span>
        </div>
        <div class="health-metric-tile" class:has-issues={countValues(healthReport.stale_index_rows) > 0}>
          <span class="metric-num">{countValues(healthReport.stale_index_rows)}</span>
          <span class="metric-label">Stale Rows</span>
        </div>
      </div>
    </div>
  {/if}

  {#if healthDetailsOpen && healthReport}
    <VaultHealthDetailsModal {healthReport} {repairErrors} onClose={() => healthDetailsOpen = false} />
  {/if}


  <span class="settings-mini-label">Backup & Portability Packager</span>
  
  <div class="vault-tool-row vault-package-row settings-row-spaced">
    <button class="settings-icon-button" type="button" on:click={() => onBackupVault('backup')} disabled={healthBusy || !healthVaultId}>
      <IconCopy size={11} />
      Backup Vault Folder
    </button>
    <button class="settings-icon-button" type="button" on:click={() => onBackupVault('export')} disabled={healthBusy || !healthVaultId}>
      <IconFileText size={11} />
      Export Vault Package
    </button>
  </div>

  <div class="vault-tool-row settings-import-row">
    <input
      class="settings-mono-input"
      type="text"
      placeholder="Path to imported .lmzvault.zip package"
      bind:value={importPackagePath}
      on:input={onImportInputChanged}
    />
    <input
      type="text"
      placeholder="Imported vault display name"
      bind:value={importVaultName}
      on:input={onImportInputChanged}
    />
    <button class="settings-icon-button" type="button" on:click={onPreviewImportVaultPackage} disabled={healthBusy || !importPackagePath.trim()}>
      <IconFileText size={11} />
      Preview
    </button>
    <button class="settings-icon-button" type="button" on:click={onConfirmImportVaultPackage} disabled={healthBusy || !importPreviewCurrent || !importVaultName.trim() || importPreview?.target_exists}>
      <IconPlus size={11} />
      Import Vault
    </button>
  </div>

  {#if importPreview}
    <div class="import-preview-box" class:stale={!importPreviewCurrent} class:warning={importPreview?.target_exists}>
      <span>
        {importPreviewCurrent ? 'Preview' : 'Preview stale'}:
        {importPreview?.source_vault?.name || importPreview?.source_vault?.id || 'Vault'}
      </span>
      <span>{Number(importPreview?.counts?.items || 0).toLocaleString()} items</span>
      <span>Target: {importPreview?.target_id || '-'}</span>
      {#if importPreview?.target_exists}
        <span>Target already exists</span>
      {/if}
    </div>
  {/if}

</div>
