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

  $: hasIssues = healthReport ? (healthReport.issue_count > 0) : false;
</script>

<div class="vault-tool-panel" style="margin-top: 24px; padding-top: 18px; border-top: 1px solid var(--border-dim);">
  <h4 class="settings-section-title">Vault Health & Portability</h4>
  <div class="micro-desc" style="margin-bottom: 12px;">Audit files, detect stale entries, quarantine orphaned records, and perform backups/restores.</div>
  
  <div class="vault-tool-row" style="margin-bottom: 16px;">
    <select bind:value={healthVaultId}>
      {#each vaults as vault}
        <option value={vault.id}>Vault: {vault.name}</option>
      {/each}
    </select>
    <button type="button" on:click={onAuditVaultHealth} disabled={healthBusy || !healthVaultId} style="font-weight: 600;">Audit Health</button>
    <button type="button" class="primary" on:click={onRepairVaultHealth} disabled={healthBusy || !healthVaultId || healthVaultId !== vaultActive} style="font-weight: 600;">Repair Active Vault</button>
  </div>

  {#if healthReport}
    <div class="health-scorecard">
      <div class="health-scorecard-header" class:healthy={!hasIssues} class:warning={hasIssues && healthReport.issue_count < 10} class:danger={hasIssues && healthReport.issue_count >= 10}>
        <span>
          {#if !hasIssues}
            🟢 Vault Health Check: Healthy & Consistent
          {:else}
            ⚠️ Vault Health Check: Attention Required ({Number(healthReport.issue_count || 0).toLocaleString()} issue{healthReport.issue_count === 1 ? '' : 's'} found)
          {/if}
        </span>
        <button type="button" class="compact-action" on:click={() => healthDetailsOpen = true} style="font-weight: 600;">
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

  {#if healthResult}
    <div class="workspace-result" style="margin-bottom: 14px; padding: 6px 12px; border-radius: 4px; background: var(--bg-panel); border: 1px solid var(--border-dim); color: var(--text-bright); font-family: 'Consolas', monospace; font-size: 11px;">
      {healthResult}
    </div>
  {/if}

  <span style="font-size: 11px; letter-spacing: 0.5px; color: var(--text-muted); display: block; margin-top: 18px; margin-bottom: 6px;">Backup & Portability Packager</span>
  
  <div class="vault-tool-row vault-package-row" style="margin-bottom: 12px;">
    <button type="button" on:click={() => onBackupVault('backup')} disabled={healthBusy || !healthVaultId} style="font-weight: 600;">Backup Vault Folder</button>
    <button type="button" on:click={() => onBackupVault('export')} disabled={healthBusy || !healthVaultId} style="font-weight: 600;">Export Vault Database</button>
  </div>

  <div class="vault-tool-row" style="background: rgba(255, 255, 255, 0.01); border: 1px dashed var(--border-dim); border-radius: 6px; padding: 12px;">
    <input type="text" placeholder="Path to imported .zip vault package" bind:value={importPackagePath} style="font-family: 'Consolas', monospace;" />
    <input type="text" placeholder="Imported vault display name" bind:value={importVaultName} />
    <button type="button" on:click={onImportVaultPackage} disabled={healthBusy || !importPackagePath.trim()} style="font-weight: 600;">Import Vault</button>
  </div>

  {#if backupResult}
    <div class="workspace-result" style="margin-top: 10px; padding: 6px 12px; border-radius: 4px; background: var(--bg-panel); border: 1px solid var(--border-dim); color: var(--text-bright); font-family: 'Consolas', monospace; font-size: 11px;">
      {backupResult}
    </div>
  {/if}
</div>
