<script lang="ts">
  import type { FacetKind, MetadataActionKind } from './types';

  export let open = false;
  export let kind: FacetKind = 'topic';
  export let action: MetadataActionKind = 'rename';
  export let value = '';
  export let newValue = '';
  export let targetValue = '';
  export let tagType = '';
  export let busy = false;
  export let result = '';
  export let error = '';
  export let onClose: () => void;
  export let onConfirm: () => void;

  $: kindLabel = kind === 'wd_tag' ? 'WD Tag' : 'Topic';
  $: actionLabel = action === 'rename' ? 'Rename' : action === 'merge' ? 'Merge' : 'Delete';
  $: title = `${actionLabel} ${kindLabel}`;
  $: confirmLabel = busy
    ? `${actionLabel}...`
    : actionLabel;
  $: disabled = busy
    || (action === 'rename' && !newValue.trim())
    || (action === 'merge' && !targetValue.trim());
</script>

{#if open}
  <div class="modal-backdrop" role="presentation">
    <div class="rename-modal" role="dialog" aria-modal="true" aria-labelledby="metadata-action-title" tabindex="-1">
      <div class="modal-header">
        <div>
          <h4 id="metadata-action-title">{title}</h4>
          <span class="muted">
            {#if kind === 'topic' && action === 'rename'}
              Renames the shared topic file and updates references in all vaults.
            {:else if kind === 'topic' && action === 'merge'}
              Moves source topic references to an existing target topic.
            {:else if kind === 'topic'}
              Removes the shared topic and clears references in all vaults.
            {:else if action === 'rename'}
              Renames matching WD tags in item notes and metadata indexes.
            {:else}
              Removes matching WD tags from item notes and metadata indexes.
            {/if}
          </span>
        </div>
        <button type="button" on:click={onClose} disabled={busy}>Close</button>
      </div>

      <div class="detail-grid">
        <label for="metadata-source">Current</label>
        <input id="metadata-source" value={value} readonly />

        {#if action === 'rename'}
          <label for="metadata-new">New</label>
          <input id="metadata-new" bind:value={newValue} disabled={busy} />
        {:else if action === 'merge'}
          <label for="metadata-target">Target</label>
          <input id="metadata-target" bind:value={targetValue} disabled={busy} />
        {/if}

        {#if kind === 'wd_tag'}
          <label for="metadata-tag-type">Scope</label>
          <select id="metadata-tag-type" bind:value={tagType} disabled={busy}>
            <option value="">All WD fields</option>
            <option value="general">General tags</option>
            <option value="character">Character tags</option>
            <option value="rating">Rating</option>
          </select>
        {/if}
      </div>

      {#if error}
        <div class="empty-state error">{error}</div>
      {/if}
      {#if result}
        <div class="empty-state success">{result}</div>
      {/if}

      <div class="modal-actions">
        <button type="button" on:click={onClose} disabled={busy}>Cancel</button>
        <button type="button" class="primary" on:click={onConfirm} disabled={disabled}>
          {confirmLabel}
        </button>
      </div>
    </div>
  </div>
{/if}
