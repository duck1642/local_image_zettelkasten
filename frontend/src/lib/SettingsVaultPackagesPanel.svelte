<script lang="ts">
  import { open as openDialog } from '@tauri-apps/plugin-dialog';
  import { IconCopy, IconDownload, IconFileText, IconFolder, IconPlus } from './icons';

  export let healthVaultId = '';
  export let healthBusy = false;
  export let importPackagePath = '';
  export let importVaultName = '';
  export let importPreview: any = null;
  export let importPreviewCurrent = false;
  export let onBackupVault: (kind: 'backup' | 'export') => void;
  export let onPreviewImportVaultPackage: () => void;
  export let onConfirmImportVaultPackage: () => void;
  export let onImportInputChanged: () => void;

  async function onSelectImportPackage() {
    if (healthBusy) return;
    try {
      const selection = await openDialog({
        directory: false,
        multiple: false,
        filters: [{ name: 'LMZ vault package', extensions: ['lmzvault.zip', 'zip'] }]
      });
      if (selection) {
        importPackagePath = String(selection);
        onImportInputChanged();
      }
    } catch (error) {
      console.error('Failed to open package picker:', error);
    }
  }
</script>

<h4 class="settings-section-title">
  <span class="settings-title-icon">
    <IconFileText size={14} />
  </span>
  Backup / Import / Export
</h4>

<div class="vault-package-grid">
  <div class="vault-package-card vault-package-import-card">
    <div class="vault-package-card-title">
      <IconPlus size={12} />
      Import
    </div>
    <div class="vault-package-import-row">
      <input
        class="vault-package-test-path-input"
        data-testid="import-package-path"
        type="text"
        bind:value={importPackagePath}
        on:input={onImportInputChanged}
        tabindex="-1"
        aria-hidden="true"
      />
      <button class="settings-icon-button vault-package-file-button" type="button" on:click={onSelectImportPackage} disabled={healthBusy} aria-label="Select import package" title="Select import package">
        <IconFolder size={13} />
      </button>
      <div class="vault-package-path-label" title={importPackagePath || 'No package selected'}>
        {importPackagePath || 'No package selected'}
      </div>
      <input
        class="vault-package-name-input"
        type="text"
        placeholder="Imported vault display name"
        bind:value={importVaultName}
        on:input={onImportInputChanged}
      />
      <div class="vault-package-import-actions">
        <button class="settings-icon-button vault-package-icon-button" type="button" on:click={onPreviewImportVaultPackage} disabled={healthBusy || !importPackagePath.trim()} aria-label="Preview" title="Preview">
          <IconFileText size={11} />
        </button>
        <button class="settings-icon-button vault-package-icon-button" type="button" on:click={onConfirmImportVaultPackage} disabled={healthBusy || !importPreviewCurrent || !importVaultName.trim() || importPreview?.target_exists} aria-label="Import Vault" title="Import Vault">
          <IconPlus size={11} />
        </button>
      </div>
    </div>
  </div>

  <div class="vault-package-card vault-package-small-card">
    <div class="vault-package-card-title">
      <IconFileText size={12} />
      Export
    </div>
    <button class="settings-icon-button vault-package-icon-button" type="button" on:click={() => onBackupVault('export')} disabled={healthBusy || !healthVaultId} aria-label="Export Vault Package" title="Export Vault Package">
      <IconDownload size={13} />
    </button>
  </div>

  <div class="vault-package-card vault-package-small-card">
    <div class="vault-package-card-title">
      <IconCopy size={12} />
      Backup
    </div>
    <button class="settings-icon-button vault-package-icon-button" type="button" on:click={() => onBackupVault('backup')} disabled={healthBusy || !healthVaultId} aria-label="Backup Vault Folder" title="Backup Vault Folder">
      <IconCopy size={13} />
    </button>
  </div>
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
