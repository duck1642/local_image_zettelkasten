<script lang="ts">
  import type { ArtistDetail, ArtistListItem, ArtistMergePreview } from './types';

  export let open = false;
  export let selectedArtist: ArtistDetail | null = null;
  export let mergeSearch = '';
  export let mergeCandidates: ArtistListItem[] = [];
  export let selectedMergeSourceIds: number[] = [];
  export let mergePreview: ArtistMergePreview | null = null;
  export let mergeBusy = false;
  export let mergeError = '';
  export let onSearchInput: () => void;
  export let onToggleSource: (id: number) => void;
  export let onConfirm: () => void;
  export let onClose: () => void;
</script>

{#if open && selectedArtist}
  <div class="modal-backdrop" role="presentation">
    <div class="merge-modal" role="dialog" aria-modal="true" aria-labelledby="artist-merge-title" tabindex="-1">
      <div class="modal-header">
        <div>
          <h4 id="artist-merge-title">Merge Into {selectedArtist.name}</h4>
          <span class="muted">Selected sources will be absorbed into this artist.</span>
        </div>
        <button type="button" on:click={onClose} disabled={mergeBusy}>Close</button>
      </div>

      <input
        class="stats-search"
        type="text"
        bind:value={mergeSearch}
        on:input={onSearchInput}
        placeholder="Search source artists..."
      />

      {#if mergeError}
        <div class="empty-state error">{mergeError}</div>
      {/if}

      <div class="merge-source-list sleek-scrollbar">
        {#each mergeCandidates as artist}
          <button
            type="button"
            class="merge-source-row"
            class:active={selectedMergeSourceIds.includes(artist.id)}
            on:click={() => onToggleSource(artist.id)}
          >
            <span class="value">{artist.name}</span>
            <span class="artist-meta">{artist.item_count} items - {artist.link_count} links</span>
          </button>
        {/each}
      </div>

      <div class="merge-preview">
        <h5>Preview</h5>
        {#if mergePreview}
          <div class="preview-grid">
            <span>Affected items</span><strong>{mergePreview.affected_items}</strong>
            <span>Aliases added/moved</span><strong>{mergePreview.aliases.add.length + mergePreview.aliases.move.length}</strong>
            <span>Alias conflicts skipped</span><strong>{mergePreview.aliases.conflicts.length}</strong>
            <span>Links moved</span><strong>{mergePreview.links.move.length}</strong>
            <span>Duplicate links skipped</span><strong>{mergePreview.links.duplicates.length}</strong>
            <span>Notes appended</span><strong>{mergePreview.notes_appended}</strong>
          </div>
        {:else}
          <div class="empty-state">Select source artists to preview merge impact.</div>
        {/if}
      </div>

      <div class="modal-actions">
        <button type="button" on:click={onClose} disabled={mergeBusy}>Cancel</button>
        <button type="button" class="danger-button" on:click={onConfirm} disabled={mergeBusy || selectedMergeSourceIds.length === 0}>
          {mergeBusy ? 'Merging...' : 'Merge into target'}
        </button>
      </div>
    </div>
  </div>
{/if}
