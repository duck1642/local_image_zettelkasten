<script lang="ts">
  export let open = false;
  export let oldLabel = '';
  export let newLabel = '';
  export let busy = false;
  export let result = '';
  export let error = '';
  export let onClose: () => void;
  export let onConfirm: () => void;
</script>

{#if open}
  <div class="modal-backdrop" role="presentation">
    <div class="rename-modal" role="dialog" aria-modal="true" aria-labelledby="topic-rename-title" tabindex="-1">
      <div class="modal-header">
        <div>
          <h4 id="topic-rename-title">Rename Topic</h4>
          <span class="muted">Renames the shared topic file and updates references in all vaults.</span>
        </div>
        <button type="button" on:click={onClose} disabled={busy}>Close</button>
      </div>

      <div class="detail-grid">
        <label for="topic-old">Old</label>
        <input id="topic-old" value={oldLabel} readonly />
        <label for="topic-new">New</label>
        <input id="topic-new" bind:value={newLabel} disabled={busy} />
      </div>

      {#if error}
        <div class="empty-state error">{error}</div>
      {/if}
      {#if result}
        <div class="empty-state success">{result}</div>
      {/if}

      <div class="modal-actions">
        <button type="button" on:click={onClose} disabled={busy}>Cancel</button>
        <button type="button" class="primary" on:click={onConfirm} disabled={busy || !newLabel.trim()}>
          {busy ? 'Renaming...' : 'Rename'}
        </button>
      </div>
    </div>
  </div>
{/if}
