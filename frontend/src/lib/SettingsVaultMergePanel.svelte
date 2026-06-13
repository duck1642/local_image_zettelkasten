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
  <div class="micro-desc settings-block-desc">Merge media items, tags, and notes from source vaults into a target vault. Sources remain completely untouched.</div>
  
  <div class="vault-tool-row settings-row-spaced">
    <select bind:value={mergeTargetId} on:change={() => { mergeSourceIds = mergeSourceIds.filter((id) => id !== mergeTargetId); mergePreview = null; }}>
      {#each vaults as vault}
        <option value={vault.id}>Target: {vault.name}</option>
      {/each}
    </select>
    <button class="settings-bold-button" type="button" on:click={onPreviewVaultMerge} disabled={mergeBusy || !mergeTargetId || !mergeSourceIds.length}>Preview Merge</button>
    <button class="primary settings-bold-button" type="button" on:click={onConfirmVaultMerge} disabled={mergeBusy || !mergeTargetId || !mergeSourceIds.length}>Merge Vaults</button>
  </div>

  <span class="settings-mini-label settings-source-label">Select Source Vaults</span>
  <div class="chip-group">
    {#each vaults as vault}
      <label class="vault-source-chip" class:active={mergeSourceIds.includes(vault.id)} class:target-disabled={vault.id === mergeTargetId}>
        <input
          type="checkbox"
          disabled={mergeBusy || vault.id === mergeTargetId}
          checked={mergeSourceIds.includes(vault.id)}
          on:change={(event) => onToggleMergeSource(vault.id, checkedValue(event))}
        />
        <span>{vault.name}</span>
      </label>
    {/each}
  </div>

  {#if mergePreview}
    <div class="workspace-note merge-preview">
      <IconChart size={12} />
      <span>Import preview:</span>
      <strong>{Number(mergePreview.total_items || 0).toLocaleString()}</strong> total items | 
      <strong>{Number(mergePreview.duplicates || 0).toLocaleString()}</strong> duplicates | 
      <strong class="text-success">{Number(mergePreview.importable || 0).toLocaleString()}</strong> importable
    </div>
  {/if}
  
</div>
