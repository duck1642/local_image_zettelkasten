<script lang="ts">
  import { IconChart, IconChevronUp, IconMerge } from './icons';
  import SettingsSection from './SettingsSection.svelte';

  export let vaults: any[] = [];
  export let mergedVaultName = '';
  export let mergeSourceIds: string[] = [];
  export let mergePreview: any = null;
  export let mergeBusy = false;
  export let mergePreviewCurrent = false;
  export let onToggleMergeSource: (id: string, checked: boolean) => void;
  export let onPreviewVaultMerge: () => void;
  export let onConfirmVaultMerge: () => void;
  export let onMergeInputChanged: () => void;
  export let checkedValue: (event: Event) => boolean;

  let expandedVaultIds: string[] = [];

  $: selectedCount = mergeSourceIds.length;
  $: canPreview = Boolean(mergedVaultName.trim()) && selectedCount >= 2 && !mergeBusy;
  $: canCreate = canPreview && mergePreviewCurrent;

  function toggleVaultDetails(id: string) {
    expandedVaultIds = expandedVaultIds.includes(id)
      ? expandedVaultIds.filter((value) => value !== id)
      : [...expandedVaultIds, id];
  }

  function statusLabel(vault: any) {
    if (vault.active) return 'Active';
    return vault.exists === false ? 'Missing' : 'Found';
  }
</script>

<SettingsSection title="Merge Vaults" description="Create a new vault from selected source vaults. Source vaults are not changed.">
  {#snippet icon()}
    <IconMerge size={14} />
  {/snippet}
  <label class="settings-mini-label" for="merged-vault-name">Merged vault name</label>
  <input
    id="merged-vault-name"
    class="merged-vault-name-input"
    type="text"
    bind:value={mergedVaultName}
    on:input={onMergeInputChanged}
    placeholder="Merged Vault"
    disabled={mergeBusy}
  />

  <span class="settings-mini-label">Vaults to merge</span>
  <div class="merge-flow-layout">
    <div class="merge-sources-box">
      {#each vaults as vault}
        <div class="merge-vault-row" class:active={mergeSourceIds.includes(vault.id)}>
          <label class="merge-vault-main">
            <input
              type="checkbox"
              disabled={mergeBusy}
              checked={mergeSourceIds.includes(vault.id)}
              on:change={(event) => onToggleMergeSource(vault.id, checkedValue(event))}
            />
            <span class="merge-source-name">{vault.name}</span>
            <span class="status-pill" class:active={vault.active} class:missing={vault.exists === false}>
              {statusLabel(vault)}
            </span>
            <span class="merge-source-count">{Number(vault.item_count || 0).toLocaleString()} items</span>
          </label>
          <button
            class="merge-row-toggle"
            type="button"
            aria-label={`Toggle details for ${vault.name}`}
            aria-expanded={expandedVaultIds.includes(vault.id)}
            on:click={() => toggleVaultDetails(vault.id)}
          >
            <IconChevronUp size={11} />
          </button>
          {#if expandedVaultIds.includes(vault.id)}
            <div class="merge-vault-path">{vault.root}</div>
          {/if}
        </div>
      {/each}
    </div>
  </div>

  <div class="merge-preview-action-row">
    <div class="merge-preview-box" class:stale={mergePreview && !mergePreviewCurrent}>
      {#if mergePreview && mergePreviewCurrent}
        <div class="merge-preview-grid">
          <IconChart size={12} />
          <span>Selected vaults <strong>{selectedCount}</strong></span>
          <span>Total <strong>{Number(mergePreview.total_items || 0).toLocaleString()}</strong></span>
          <span>Duplicates <strong>{Number(mergePreview.duplicates || 0).toLocaleString()}</strong></span>
          <span>Importable <strong class="text-success">{Number(mergePreview.importable || 0).toLocaleString()}</strong></span>
          <span>Sources changed <strong>No</strong></span>
        </div>
      {:else if mergePreview && !mergePreviewCurrent}
        <span>Preview needs refresh.</span>
      {:else}
        <span>No preview yet.</span>
      {/if}
    </div>

    <div class="merge-buttons">
      <button
        class="select-folder-btn"
        type="button"
        on:click={onPreviewVaultMerge}
        disabled={!canPreview}
      >
        Preview
      </button>
      <button
        class="create-vault-btn"
        class:active={canCreate}
        type="button"
        title="Create merged vault"
        on:click={onConfirmVaultMerge}
        disabled={!canCreate}
      >
        Create
      </button>
    </div>
  </div>
</SettingsSection>
