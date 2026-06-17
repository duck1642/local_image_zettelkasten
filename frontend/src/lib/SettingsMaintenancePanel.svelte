<script lang="ts">
  import { metadataProgressPercent, type MetadataRebuildJob } from './settingsUtils';
  import { IconEye, IconActivity, IconFolder, IconTrash, IconClose } from './icons';
  import SettingsActionRow from './SettingsActionRow.svelte';
  import SettingsSection from './SettingsSection.svelte';

  type MaintenanceAction = 'auth' | 'metadata' | 'workspaceMetadata' | 'workspacePrune' | 'review';

  export let maintenanceBusy: Record<MaintenanceAction, boolean>;
  export let maintenanceResult: Record<MaintenanceAction, string>;
  export let metadataRebuildJob: MetadataRebuildJob | null = null;
  export let onRunMaintenance: (action: MaintenanceAction) => void;
</script>

<SettingsSection title="System Maintenance" description="Local checks and rebuilds for the active workspace.">
  {#snippet icon()}
    <IconActivity size={14} />
  {/snippet}
  <div class="maintenance-cards">
    <SettingsActionRow
      title="Auth"
      status={maintenanceResult.auth || 'Ready to scan downloader credentials.'}
      actionLabel="Scan"
      busyLabel="Scanning..."
      busy={maintenanceBusy.auth}
      onAction={() => onRunMaintenance('auth')}
    >
      {#snippet actionIcon()}
        <IconEye size={11} />
      {/snippet}
    </SettingsActionRow>

    <SettingsActionRow
      title="Metadata index"
      status={maintenanceResult.metadata || 'Ready to rebuild search and facet metadata.'}
      actionLabel="Rebuild"
      busyLabel="Rebuilding..."
      busy={maintenanceBusy.metadata}
      onAction={() => onRunMaintenance('metadata')}
    >
      {#snippet actionIcon()}
        <IconActivity size={11} />
      {/snippet}
      {#snippet details()}
        {#if metadataRebuildJob?.running}
          <div class="metadata-progress" aria-label="Metadata rebuild progress">
            <div class="metadata-progress-fill" style={`width: ${metadataProgressPercent(metadataRebuildJob)}%`}></div>
          </div>
        {/if}
      {/snippet}
    </SettingsActionRow>

    <SettingsActionRow
      title="Workspace metadata"
      status={maintenanceResult.workspaceMetadata || 'Ready to sync workspace dictionaries from vault usage.'}
      actionLabel="Sync"
      busyLabel="Syncing..."
      busy={maintenanceBusy.workspaceMetadata}
      onAction={() => onRunMaintenance('workspaceMetadata')}
    >
      {#snippet actionIcon()}
        <IconFolder size={11} />
      {/snippet}
    </SettingsActionRow>

    <SettingsActionRow
      title="Metadata registry"
      status={maintenanceResult.workspacePrune || 'Ready to prune unused workspace dictionary entries.'}
      actionLabel="Prune"
      busyLabel="Pruning..."
      busy={maintenanceBusy.workspacePrune}
      danger={true}
      onAction={() => onRunMaintenance('workspacePrune')}
    >
      {#snippet actionIcon()}
        <IconTrash size={11} />
      {/snippet}
    </SettingsActionRow>

    <SettingsActionRow
      title="Review queue"
      status={maintenanceResult.review || 'Ready to clear resolved review files.'}
      actionLabel="Clean"
      busyLabel="Cleaning..."
      busy={maintenanceBusy.review}
      danger={true}
      onAction={() => onRunMaintenance('review')}
    >
      {#snippet actionIcon()}
        <IconClose size={11} />
      {/snippet}
    </SettingsActionRow>
  </div>
</SettingsSection>
