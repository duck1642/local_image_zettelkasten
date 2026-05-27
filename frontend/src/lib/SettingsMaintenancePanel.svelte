<script lang="ts">
  import { metadataProgressPercent, type MetadataRebuildJob } from './settingsUtils';

  type MaintenanceAction = 'auth' | 'metadata' | 'workspaceMetadata' | 'workspacePrune' | 'review';

  export let maintenanceBusy: Record<MaintenanceAction, boolean>;
  export let maintenanceResult: Record<MaintenanceAction, string>;
  export let metadataRebuildJob: MetadataRebuildJob | null = null;
  export let onRunMaintenance: (action: MaintenanceAction) => void;
</script>

<div class="maintenance-panel" style="margin-top: 20px; display: block; width: 100%;">
  <h4 class="settings-section-title">System Maintenance</h4>
  
  <div class="maintenance-cards">
    <!-- Auth Card -->
    <div class="maintenance-card">
      <button on:click={() => onRunMaintenance('auth')} disabled={maintenanceBusy.auth}>
        {maintenanceBusy.auth ? 'Scanning...' : 'Auth Scan'}
      </button>
      <div style="display: flex; flex-direction: column; gap: 4px;">
        <span style="font-weight: 600; color: var(--text-bright); font-size: 12px;">Cookie Session Ingest</span>
        <span class="maintenance-status">{maintenanceResult.auth || 'Status: Ready to audit cookies.'}</span>
      </div>
    </div>

    <!-- Metadata Card -->
    <div class="maintenance-card" style="align-items: flex-start; padding-top: 14px; padding-bottom: 14px;">
      <button on:click={() => onRunMaintenance('metadata')} disabled={maintenanceBusy.metadata}>
        {maintenanceBusy.metadata ? 'Rebuilding...' : 'Rebuild Index'}
      </button>
      <div style="display: flex; flex-direction: column; gap: 4px; width: 100%;">
        <span style="font-weight: 600; color: var(--text-bright); font-size: 12px;">Full Metadata SQL Index Rebuild</span>
        <div class="maintenance-status metadata-progress-cell" style="width: 100%;">
          <span>{maintenanceResult.metadata || 'Status: Ready to rebuild database indexing.'}</span>
          {#if metadataRebuildJob?.running}
            <div class="metadata-progress" aria-label="Metadata rebuild progress" style="margin-top: 4px;">
              <div class="metadata-progress-fill" style={`width: ${metadataProgressPercent(metadataRebuildJob)}%`}></div>
            </div>
          {/if}
        </div>
      </div>
    </div>

    <!-- Workspace Metadata Card -->
    <div class="maintenance-card">
      <button on:click={() => onRunMaintenance('workspaceMetadata')} disabled={maintenanceBusy.workspaceMetadata}>
        {maintenanceBusy.workspaceMetadata ? 'Syncing...' : 'Sync Workspace'}
      </button>
      <div style="display: flex; flex-direction: column; gap: 4px;">
        <span style="font-weight: 600; color: var(--text-bright); font-size: 12px;">Rebuild Workspace Metadata</span>
        <span class="maintenance-status">{maintenanceResult.workspaceMetadata || 'Status: Sync and import Obsidian Zettel tags.'}</span>
      </div>
    </div>

    <!-- Workspace Prune Card -->
    <div class="maintenance-card">
      <button on:click={() => onRunMaintenance('workspacePrune')} disabled={maintenanceBusy.workspacePrune}>
        {maintenanceBusy.workspacePrune ? 'Pruning...' : 'Prune Registry'}
      </button>
      <div style="display: flex; flex-direction: column; gap: 4px;">
        <span style="font-weight: 600; color: var(--text-bright); font-size: 12px;">Prune Workspace Registry</span>
        <span class="maintenance-status">{maintenanceResult.workspacePrune || 'Status: Prune dead tags that no longer exist in your vault.'}</span>
      </div>
    </div>

    <!-- Cleanup Review Card -->
    <div class="maintenance-card">
      <button on:click={() => onRunMaintenance('review')} disabled={maintenanceBusy.review}>
        {maintenanceBusy.review ? 'Cleaning...' : 'Cleanup Review'}
      </button>
      <div style="display: flex; flex-direction: column; gap: 4px;">
        <span style="font-weight: 600; color: var(--text-bright); font-size: 12px;">Cleanup Review Queues</span>
        <span class="maintenance-status">{maintenanceResult.review || 'Status: Clear duplicates or successfully ingested items in Review.'}</span>
      </div>
    </div>
  </div>
</div>
