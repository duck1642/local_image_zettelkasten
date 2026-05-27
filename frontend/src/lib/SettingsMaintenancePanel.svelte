<script lang="ts">
  import { metadataProgressPercent, type MetadataRebuildJob } from './settingsUtils';

  type MaintenanceAction = 'auth' | 'metadata' | 'workspaceMetadata' | 'workspacePrune' | 'review';

  export let maintenanceBusy: Record<MaintenanceAction, boolean>;
  export let maintenanceResult: Record<MaintenanceAction, string>;
  export let metadataRebuildJob: MetadataRebuildJob | null = null;
  export let onRunMaintenance: (action: MaintenanceAction) => void;
</script>

<div class="maintenance-panel">
  <h4>Maintenance</h4>
  <div class="maintenance-grid">
    <button on:click={() => onRunMaintenance('auth')} disabled={maintenanceBusy.auth}>
      {maintenanceBusy.auth ? 'Running...' : 'Auth Scan'}
    </button>
    <span class="maintenance-status">{maintenanceResult.auth}</span>
    <button on:click={() => onRunMaintenance('metadata')} disabled={maintenanceBusy.metadata}>
      {maintenanceBusy.metadata ? 'Running...' : 'Rebuild Metadata Index'}
    </button>
    <div class="maintenance-status metadata-progress-cell">
      <span>{maintenanceResult.metadata}</span>
      {#if metadataRebuildJob?.running}
        <div class="metadata-progress" aria-label="Metadata rebuild progress">
          <div class="metadata-progress-fill" style={`width: ${metadataProgressPercent(metadataRebuildJob)}%`}></div>
        </div>
      {/if}
    </div>
    <button on:click={() => onRunMaintenance('workspaceMetadata')} disabled={maintenanceBusy.workspaceMetadata}>
      {maintenanceBusy.workspaceMetadata ? 'Running...' : 'Rebuild Workspace Metadata'}
    </button>
    <span class="maintenance-status">{maintenanceResult.workspaceMetadata}</span>
    <button on:click={() => onRunMaintenance('workspacePrune')} disabled={maintenanceBusy.workspacePrune}>
      {maintenanceBusy.workspacePrune ? 'Running...' : 'Prune Workspace Metadata'}
    </button>
    <span class="maintenance-status">{maintenanceResult.workspacePrune}</span>
    <button on:click={() => onRunMaintenance('review')} disabled={maintenanceBusy.review}>
      {maintenanceBusy.review ? 'Running...' : 'Cleanup Review'}
    </button>
    <span class="maintenance-status">{maintenanceResult.review}</span>
  </div>
</div>
