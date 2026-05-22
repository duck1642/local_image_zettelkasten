<script lang="ts">
  import ArtistDetailPanel from './ArtistDetailPanel.svelte';
  import type { ArtistDetail, ArtistDraft, ArtistLinkDraft, ArtistListItem, FacetItem } from './types';

  export let visibleArtists: ArtistListItem[] = [];
  export let visiblePlaceholderArtists: FacetItem[] = [];
  export let selectedArtistId: number | null = null;
  export let selectedArtist: ArtistDetail | null = null;
  export let artistDraft: ArtistDraft;
  export let newAlias = '';
  export let newLink: ArtistLinkDraft;
  export let linkPlatformOptions: string[] = [];
  export let loading = false;
  export let error = '';
  export let artistSaving = false;
  export let artistListWidth = 320;
  export let isResizingArtistList = false;
  export let onSelectArtist: (id: number) => void;
  export let onStartResize: (event: PointerEvent) => void;
  export let onResizeKeydown: (event: KeyboardEvent) => void;
  export let onSaveArtist: () => void;
  export let onAddAlias: () => void;
  export let onDeleteAlias: (aliasId: number) => void;
  export let onAddLink: () => void;
  export let onDeleteLink: (linkId: number) => void;
  export let onOpenMerge: () => void;
</script>

<div class="artist-layout">
  <div class="artist-list" style={`width: ${artistListWidth}px;`}>
    {#if loading && visibleArtists.length === 0}
      <div class="empty-state">Loading...</div>
    {:else if visibleArtists.length === 0}
      <div class="empty-state">No artists</div>
    {:else}
      <div class="artist-group-label">Known Artists</div>
      {#each visibleArtists as artist}
        <button type="button" class="artist-row" class:active={selectedArtistId === artist.id} on:click={() => onSelectArtist(artist.id)}>
          <span class="value" title={artist.name}>{artist.name}</span>
          <span class="artist-meta">{artist.item_count} items - {artist.link_count} links</span>
        </button>
      {/each}
    {/if}
    {#if visiblePlaceholderArtists.length > 0}
      <div class="artist-group-label">Placeholders</div>
      {#each visiblePlaceholderArtists as artist}
        <div class="artist-row placeholder-row">
          <span class="value" title={artist.value}>{artist.value}</span>
          <span class="artist-meta">{artist.count} items - read only</span>
        </div>
      {/each}
    {/if}
  </div>
  <button
    type="button"
    class="artist-resize-handle"
    class:active={isResizingArtistList}
    aria-label="Resize artist list"
    on:pointerdown={onStartResize}
    on:keydown={onResizeKeydown}
  ></button>

  <ArtistDetailPanel
    {selectedArtist}
    bind:artistDraft
    bind:newAlias
    bind:newLink
    {linkPlatformOptions}
    {artistSaving}
    {loading}
    {error}
    onSave={onSaveArtist}
    {onAddAlias}
    {onDeleteAlias}
    {onAddLink}
    {onDeleteLink}
    {onOpenMerge}
  />
</div>
