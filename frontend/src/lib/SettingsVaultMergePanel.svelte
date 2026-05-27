<script lang="ts">
  export let vaults: any[] = [];
  export let mergeTargetId = '';
  export let mergeSourceIds: string[] = [];
  export let mergePreview: any = null;
  export let mergeBusy = false;
  export let mergeResult = '';
  export let onToggleMergeSource: (id: string, checked: boolean) => void;
  export let onPreviewVaultMerge: () => void;
  export let onConfirmVaultMerge: () => void;
  export let checkedValue: (event: Event) => boolean;
</script>

<div class="vault-tool-panel">
  <h5>Merge Vaults</h5>
  <div class="add-workspace">
    <select bind:value={mergeTargetId} on:change={() => { mergeSourceIds = mergeSourceIds.filter((id) => id !== mergeTargetId); mergePreview = null; }}>
      {#each vaults as vault}
        <option value={vault.id}>{vault.name}</option>
      {/each}
    </select>
    <button type="button" on:click={onPreviewVaultMerge} disabled={mergeBusy || !mergeTargetId || !mergeSourceIds.length}>Preview Merge</button>
    <button type="button" on:click={onConfirmVaultMerge} disabled={mergeBusy || !mergeTargetId || !mergeSourceIds.length}>Merge</button>
  </div>
  <div class="merge-source-list">
    {#each vaults as vault}
      <label>
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
    <div class="workspace-note">
      {Number(mergePreview.total_items || 0).toLocaleString()} total |
      {Number(mergePreview.duplicates || 0).toLocaleString()} duplicates |
      {Number(mergePreview.importable || 0).toLocaleString()} importable
    </div>
  {/if}
  {#if mergeResult}
    <div class="workspace-result">{mergeResult}</div>
  {/if}
</div>
