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

<div class="vault-tool-panel" style="margin-top: 0;">
  <h4 class="settings-section-title">Merge Vaults</h4>
  <div class="micro-desc" style="margin-bottom: 12px;">Merge media items, tags, and notes from source vaults into a target vault. Sources remain completely untouched.</div>
  
  <div class="vault-tool-row" style="margin-bottom: 12px;">
    <select bind:value={mergeTargetId} on:change={() => { mergeSourceIds = mergeSourceIds.filter((id) => id !== mergeTargetId); mergePreview = null; }}>
      {#each vaults as vault}
        <option value={vault.id}>Target: {vault.name}</option>
      {/each}
    </select>
    <button type="button" on:click={onPreviewVaultMerge} disabled={mergeBusy || !mergeTargetId || !mergeSourceIds.length} style="font-weight: 600;">Preview Merge</button>
    <button type="button" class="primary" on:click={onConfirmVaultMerge} disabled={mergeBusy || !mergeTargetId || !mergeSourceIds.length} style="font-weight: 600;">Merge Vaults</button>
  </div>

  <span style="font-size: 11px; letter-spacing: 0.5px; color: var(--text-muted);">Select Source Vaults</span>
  <div class="chip-group">
    {#each vaults as vault}
      <label class="tag-chip" class:active={mergeSourceIds.includes(vault.id)} style={vault.id === mergeTargetId ? 'opacity: 0.45; cursor: not-allowed; pointer-events: none;' : ''}>
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
    <div class="workspace-note" style="padding: 10px 12px; background: rgba(31, 111, 235, 0.04); border: 1px solid rgba(31, 111, 235, 0.15); border-radius: 6px; color: var(--text-bright); font-family: 'Consolas', monospace; font-size: 11px; display: inline-block;">
      📊 Import preview: 
      <strong>{Number(mergePreview.total_items || 0).toLocaleString()}</strong> total items | 
      <strong>{Number(mergePreview.duplicates || 0).toLocaleString()}</strong> duplicates | 
      <strong style="color: var(--accent-success);">{Number(mergePreview.importable || 0).toLocaleString()}</strong> importable
    </div>
  {/if}
  
  {#if mergeResult}
    <div class="workspace-result" style="margin-top: 10px; padding: 6px 12px; border-radius: 4px; background: var(--bg-panel); border: 1px solid var(--border-dim); color: var(--text-bright); font-family: 'Consolas', monospace; font-size: 11px;">
      {mergeResult}
    </div>
  {/if}
</div>
