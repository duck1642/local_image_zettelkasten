<script lang="ts">
  import { countValues } from './settingsUtils';
  import VaultHealthDetailsModal from './VaultHealthDetailsModal.svelte';
  import { IconAlertTriangle, IconCheckCircle } from './icons';

  export let vaults: any[] = [];
  export let vaultActive = '';
  export let healthVaultId = '';
  export let healthBusy = false;
  export let healthReport: any = null;
  export let healthDetailsOpen = false;
  export let repairErrors: Array<{ hash: string; storage_id: string; status: string; error: string }> = [];
  export let onAuditVaultHealth: () => void;
  export let onRepairVaultHealth: () => void;

  $: hasIssues = healthReport ? (healthReport.issue_count > 0) : false;
</script>

<h4 class="settings-section-title">
  <span class="settings-title-icon">
    <IconAlertTriangle size={14} />
  </span>
  Vault Health
</h4>

<div class="vault-health-controls">
  <label class="vault-health-select">
    <span class="settings-mini-label inline">Vault</span>
    <select bind:value={healthVaultId}>
      {#each vaults as vault}
        <option value={vault.id}>{vault.name}</option>
      {/each}
    </select>
  </label>
  <div class="vault-health-actions">
    <button class="settings-bold-button" type="button" on:click={onAuditVaultHealth} disabled={healthBusy || !healthVaultId}>Audit Health</button>
    <button class="primary settings-bold-button" type="button" on:click={onRepairVaultHealth} disabled={healthBusy || !healthVaultId || healthVaultId !== vaultActive}>Repair Active Vault</button>
  </div>
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
