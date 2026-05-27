<script lang="ts">
  import SettingsVaultHealthPanel from './SettingsVaultHealthPanel.svelte';
  import SettingsVaultMergePanel from './SettingsVaultMergePanel.svelte';

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

<SettingsVaultMergePanel
  {vaults}
  bind:mergeTargetId
  bind:mergeSourceIds
  bind:mergePreview
  {mergeBusy}
  {mergeResult}
  {onToggleMergeSource}
  {onPreviewVaultMerge}
  {onConfirmVaultMerge}
  {checkedValue}
/>

<SettingsVaultHealthPanel
  {vaults}
  {vaultActive}
  bind:healthVaultId
  {healthBusy}
  {healthResult}
  {healthReport}
  bind:healthDetailsOpen
  {repairErrors}
  {backupResult}
  bind:importPackagePath
  bind:importVaultName
  {onAuditVaultHealth}
  {onRepairVaultHealth}
  {onBackupVault}
  {onImportVaultPackage}
/>
