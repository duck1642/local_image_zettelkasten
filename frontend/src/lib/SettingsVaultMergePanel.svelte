<script lang="ts">
  import { IconChart, IconMerge } from './icons';
  export let vaults: any[] = [];
  export let mergeTargetId = '';
  export let mergeSourceIds: string[] = [];
  export let mergePreview: any = null;
  export let mergeBusy = false;
  export let onToggleMergeSource: (id: string, checked: boolean) => void;
  export let onPreviewVaultMerge: () => void;
  export let onConfirmVaultMerge: () => void;
  export let checkedValue: (event: Event) => boolean;
</script>

<div class="vault-tool-panel vault-tool-panel-first">
  <h4 class="settings-section-title">
    <span class="settings-title-icon">
      <IconMerge size={14} />
    </span>
    Merge Vaults
  </h4>
  <div class="micro-desc settings-block-desc">Combine media items, tags, and notes into a target vault. Sources remain completely untouched.</div>

  <div class="merge-flow-layout">
    <!-- Left Column: Source select list -->
    <div class="merge-column merge-sources-column">
      <span class="settings-mini-label">Select Source Vaults</span>
      <div class="merge-sources-box">
        {#each vaults as vault}
          <label
            class="merge-source-item vault-source-chip"
            class:active={mergeSourceIds.includes(vault.id)}
            class:target-disabled={vault.id === mergeTargetId}
          >
            <input
              type="checkbox"
              disabled={mergeBusy || vault.id === mergeTargetId}
              checked={mergeSourceIds.includes(vault.id)}
              on:change={(event) => onToggleMergeSource(vault.id, checkedValue(event))}
            />
            <span class="merge-source-name">{vault.name}</span>
            <span class="merge-source-count">{Number(vault.item_count || 0).toLocaleString()} items</span>
          </label>
        {/each}
      </div>
    </div>

    <!-- Center Column: Visual flow direction arrow -->
    <div class="merge-flow-arrow-container">
      <div class="merge-flow-arrow">âž” âž” âž”</div>
    </div>

    <!-- Right Column: Target vault selector -->
    <div class="merge-column merge-target-column">
      <span class="settings-mini-label">Target Vault</span>
      <select
        class="merge-target-select"
        bind:value={mergeTargetId}
        on:change={() => {
          mergeSourceIds = mergeSourceIds.filter((id) => id !== mergeTargetId);
          mergePreview = null;
        }}
      >
        {#each vaults as vault}
          <option value={vault.id}>{vault.name}</option>
        {/each}
      </select>
    </div>
  </div>

  <!-- Bottom Option: Conflict policies -->
  <div class="merge-options-section">
    <span class="settings-mini-label">Conflict Resolution Policies</span>
    <div class="merge-options-grid">
      <div class="merge-option-item">
        <label for="dup-media-select">Duplicate Media Files</label>
        <select id="dup-media-select">
          <option value="union">Union (Combine tags & notes)</option>
          <option value="skip">Skip (Keep target metadata)</option>
          <option value="overwrite">Overwrite (Take source metadata)</option>
        </select>
      </div>
      <div class="merge-option-item">
        <label for="tag-conflict-select">Tag Category Clashes</label>
        <select id="tag-conflict-select">
          <option value="keep-target">Keep Target Category</option>
          <option value="take-source">Overwrite with Source Category</option>
        </select>
      </div>
    </div>
  </div>

  <!-- Actions and Preview -->
  <div class="merge-action-bar">
    {#if mergePreview}
      <div class="workspace-note merge-preview">
        <IconChart size={12} />
        <span>Import preview:</span>
        <strong>{Number(mergePreview.total_items || 0).toLocaleString()}</strong> total items |
        <strong>{Number(mergePreview.duplicates || 0).toLocaleString()}</strong> duplicates |
        <strong class="text-success">{Number(mergePreview.importable || 0).toLocaleString()}</strong> importable
      </div>
    {/if}

    <div class="merge-buttons">
      <button
        class="select-folder-btn"
        type="button"
        on:click={onPreviewVaultMerge}
        disabled={mergeBusy || !mergeTargetId || !mergeSourceIds.length}
      >
        Preview Merge
      </button>
      <button
        class="create-vault-btn"
        class:active={mergeTargetId && mergeSourceIds.length > 0}
        type="button"
        on:click={onConfirmVaultMerge}
        disabled={mergeBusy || !mergeTargetId || !mergeSourceIds.length}
      >
        Merge Vaults
      </button>
    </div>
  </div>
</div>
