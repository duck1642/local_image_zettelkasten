<script lang="ts">
  import { onDestroy } from 'svelte';
  import type { ArtistDetail, ArtistDraft, ArtistLinkDraft } from './types';
  import { IconPlus, IconTrash } from '../icons';

  export let selectedArtist: ArtistDetail | null = null;
  export let artistDraft: ArtistDraft;
  export let newAlias = '';
  export let newLink: ArtistLinkDraft;
  export let linkPlatformOptions: string[] = [];
  export let artistSaving = false;
  export let loading = false;
  export let error = '';
  export let onSave: () => void;
  export let onAddAlias: () => void;
  export let onDeleteAlias: (aliasId: number) => void;
  export let onAddLink: () => void;
  export let onDeleteLink: (linkId: number) => void;
  export let onOpenMerge: () => void;

  let notesHeightPx = 0;
  let notesSplitterDragging = false;
  let notesSplitterStartY = 0;
  let notesSplitterStartHeight = 0;
  let notesTextarea: HTMLTextAreaElement;
  const DEFAULT_NOTES_HEIGHT = 92;
  const MIN_NOTES_HEIGHT = 62;
  const MAX_NOTES_HEIGHT = 360;

  function setArtistDraft(field: keyof ArtistDraft, value: string) {
    artistDraft = { ...artistDraft, [field]: value };
  }

  function setNewLink(field: keyof ArtistLinkDraft, value: string) {
    newLink = { ...newLink, [field]: value };
  }

  function currentNotesHeight() {
    return notesHeightPx || notesTextarea?.getBoundingClientRect().height || DEFAULT_NOTES_HEIGHT;
  }

  function clampNotesHeight(value: number) {
    return Math.max(MIN_NOTES_HEIGHT, Math.min(MAX_NOTES_HEIGHT, Math.round(value)));
  }

  function handleNotesSplitterMove(event: PointerEvent) {
    if (!notesSplitterDragging) return;
    notesHeightPx = clampNotesHeight(notesSplitterStartHeight + event.clientY - notesSplitterStartY);
  }

  function stopNotesSplitterDrag() {
    notesSplitterDragging = false;
    window.removeEventListener('pointermove', handleNotesSplitterMove);
    window.removeEventListener('pointerup', stopNotesSplitterDrag);
  }

  function startNotesSplitterDrag(event: PointerEvent) {
    if (event.button !== 0) return;
    event.preventDefault();
    notesSplitterDragging = true;
    notesSplitterStartY = event.clientY;
    notesSplitterStartHeight = currentNotesHeight();
    window.addEventListener('pointermove', handleNotesSplitterMove);
    window.addEventListener('pointerup', stopNotesSplitterDrag);
  }

  function resetNotesHeight() {
    notesHeightPx = DEFAULT_NOTES_HEIGHT;
  }

  onDestroy(stopNotesSplitterDrag);
</script>

<div class="artist-detail">
  {#if error}
    <div class="empty-state error">{error}</div>
  {/if}
  {#if selectedArtist}
    <div class="detail-header">
      <div>
        <h4>{selectedArtist.name}</h4>
        <div class="artist-summary">
          <span>{selectedArtist.item_count} items</span>
          <span>{selectedArtist.links.length} links</span>
          <span>{selectedArtist.kind}</span>
        </div>
      </div>
      <button type="button" on:click={onSave} disabled={artistSaving}>{artistSaving ? 'Saving...' : 'Save'}</button>
    </div>

    <div class="detail-section identity-section">
      <label for="artist-name">Name</label>
      <input id="artist-name" value={artistDraft.name} on:input={(event) => setArtistDraft('name', (event.currentTarget as HTMLInputElement).value)} />
      <label for="artist-kind">Kind</label>
      <select id="artist-kind" value={artistDraft.kind} on:change={(event) => setArtistDraft('kind', (event.currentTarget as HTMLSelectElement).value)}>
        <option value="artist">artist</option>
        <option value="real_person">real_person</option>
        <option value="brand">brand</option>
        <option value="other">other</option>
      </select>
    </div>

    <div class="detail-section">
      <h5>Links</h5>
      <div class="editable-list">
        {#each selectedArtist.links as link}
          <div class="editable-row link-row">
            <span class="row-label">{link.platform}</span>
            <a href={link.url} target="_blank" rel="noreferrer">{link.handle || link.url}</a>
            <button type="button" class="icon-row-button danger" on:click={() => onDeleteLink(link.id)} disabled={artistSaving} title="Delete link" aria-label="Delete link">
              <IconTrash size={12} />
            </button>
          </div>
        {/each}
        {#if selectedArtist.links.length === 0}
          <div class="empty-inline">No links</div>
        {/if}
      </div>
      <div class="add-row link-add-row">
        <select value={newLink.platform} on:change={(event) => setNewLink('platform', (event.currentTarget as HTMLSelectElement).value)} aria-label="Link platform">
          <option value="">platform</option>
          {#each linkPlatformOptions as platform}
            <option value={platform}>{platform}</option>
          {/each}
        </select>
        <input value={newLink.url} on:input={(event) => setNewLink('url', (event.currentTarget as HTMLInputElement).value)} placeholder="url" />
        <input value={newLink.handle} on:input={(event) => setNewLink('handle', (event.currentTarget as HTMLInputElement).value)} placeholder="handle" />
        <button type="button" class="icon-row-button" on:click={onAddLink} disabled={artistSaving} title="Add link" aria-label="Add link">
          <IconPlus size={12} />
        </button>
      </div>
    </div>

    <div class="detail-section">
      <h5>Aliases</h5>
      <div class="alias-list">
        {#each selectedArtist.aliases as alias}
          <span class="alias-chip">
            {alias.alias}
            <button type="button" on:click={() => onDeleteAlias(alias.id)} disabled={artistSaving} title="Delete alias" aria-label="Delete alias">
              <IconTrash size={10} />
            </button>
          </span>
        {/each}
        {#if selectedArtist.aliases.length === 0}
          <span class="empty-inline">No aliases</span>
        {/if}
      </div>
      <div class="add-row alias-add-row">
        <input bind:value={newAlias} placeholder="New alias" />
        <button type="button" class="icon-row-button" on:click={onAddAlias} disabled={artistSaving} title="Add alias" aria-label="Add alias">
          <IconPlus size={12} />
        </button>
      </div>
    </div>

    <div class="detail-section notes-section">
      <h5>Notes</h5>
      <div class="artist-notes-wrap">
        <textarea
          id="artist-notes"
          bind:this={notesTextarea}
          value={artistDraft.notes}
          style={notesHeightPx ? `height: ${notesHeightPx}px;` : ''}
          on:input={(event) => setArtistDraft('notes', (event.currentTarget as HTMLTextAreaElement).value)}
          rows="3"
        ></textarea>
        <button
          type="button"
          class="artist-notes-splitter"
          class:dragging={notesSplitterDragging}
          title="Drag to resize notes. Double-click to reset."
          aria-label="Resize artist notes"
          on:pointerdown={startNotesSplitterDrag}
          on:dblclick={resetNotesHeight}
        ></button>
      </div>
    </div>

    <div class="detail-section maintenance-section">
      <button type="button" class="merge-button" on:click={onOpenMerge} disabled={artistSaving}>
        Merge Other Artists Into This
      </button>
    </div>
  {:else if !loading}
    <div class="empty-state">Select an artist</div>
  {/if}
</div>
