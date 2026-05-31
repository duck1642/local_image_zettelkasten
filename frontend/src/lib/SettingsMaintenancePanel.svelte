<script lang="ts">
  import { metadataProgressPercent, type MetadataRebuildJob } from './settingsUtils';
  import { IconEye, IconActivity, IconFolder, IconTrash, IconClose } from './icons';

  type MaintenanceAction = 'auth' | 'metadata' | 'workspaceMetadata' | 'workspacePrune' | 'review';

  export let maintenanceBusy: Record<MaintenanceAction, boolean>;
  export let maintenanceResult: Record<MaintenanceAction, string>;
  export let metadataRebuildJob: MetadataRebuildJob | null = null;
  export let onRunMaintenance: (action: MaintenanceAction) => void;
</script>

<div class="maintenance-panel">
  <h4 class="settings-section-title">System Maintenance</h4>
  
  <div class="maintenance-cards">
    <!-- Auth Card -->
    <div class="maintenance-card">
      <button class="settings-icon-button" on:click={() => onRunMaintenance('auth')} disabled={maintenanceBusy.auth}>
        <IconEye size={11} />
        {maintenanceBusy.auth ? 'Scanning...' : 'Auth Scan'}
      </button>
      <div class="maintenance-card-copy">
        <span class="maintenance-card-title">Cookie Session Ingest</span>
        <span class="maintenance-status">{maintenanceResult.auth || 'Status: Ready to audit cookies.'}</span>
      </div>
    </div>

    <!-- Metadata Card -->
    <div class="maintenance-card expanded">
      <button class="settings-icon-button" on:click={() => onRunMaintenance('metadata')} disabled={maintenanceBusy.metadata}>
        <IconActivity size={11} />
        {maintenanceBusy.metadata ? 'Rebuilding...' : 'Rebuild Index'}
      </button>
      <div class="maintenance-card-copy wide">
        <span class="maintenance-card-title">Full Metadata SQL Index Rebuild</span>
        <div class="maintenance-status metadata-progress-cell">
          <span>{maintenanceResult.metadata || 'Status: Ready to rebuild database indexing.'}</span>
          {#if metadataRebuildJob?.running}
            <div class="metadata-progress" aria-label="Metadata rebuild progress">
              <div class="metadata-progress-fill" style={`width: ${metadataProgressPercent(metadataRebuildJob)}%`}></div>
            </div>
          {/if}
        </div>
      </div>
    </div>

    <!-- Workspace Metadata Card -->
    <div class="maintenance-card">
      <button class="settings-icon-button" on:click={() => onRunMaintenance('workspaceMetadata')} disabled={maintenanceBusy.workspaceMetadata}>
        <IconFolder size={11} />
        {maintenanceBusy.workspaceMetadata ? 'Syncing...' : 'Sync Workspace'}
      </button>
      <div class="maintenance-card-copy">
        <span class="maintenance-card-title">Rebuild Workspace Metadata</span>
        <span class="maintenance-status">{maintenanceResult.workspaceMetadata || 'Status: Sync and import Obsidian Zettel tags.'}</span>
      </div>
    </div>

    <!-- Workspace Prune Card -->
    <div class="maintenance-card">
      <button class="settings-icon-button" on:click={() => onRunMaintenance('workspacePrune')} disabled={maintenanceBusy.workspacePrune}>
        <IconTrash size={11} />
        {maintenanceBusy.workspacePrune ? 'Pruning...' : 'Prune Registry'}
      </button>
      <div class="maintenance-card-copy">
        <span class="maintenance-card-title">Prune Workspace Registry</span>
        <span class="maintenance-status">{maintenanceResult.workspacePrune || 'Status: Prune dead tags that no longer exist in your vault.'}</span>
      </div>
    </div>

    <!-- Cleanup Review Card -->
    <div class="maintenance-card">
      <button class="settings-icon-button" on:click={() => onRunMaintenance('review')} disabled={maintenanceBusy.review}>
        <IconClose size={11} />
        {maintenanceBusy.review ? 'Cleaning...' : 'Cleanup Review'}
      </button>
      <div class="maintenance-card-copy">
        <span class="maintenance-card-title">Cleanup Review Queues</span>
        <span class="maintenance-status">{maintenanceResult.review || 'Status: Clear duplicates or successfully ingested items in Review.'}</span>
      </div>
    </div>
  </div>
</div>
