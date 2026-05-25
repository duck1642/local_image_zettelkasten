<script lang="ts">
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

  function setArtistDraft(field: keyof ArtistDraft, value: string) {
    artistDraft = { ...artistDraft, [field]: value };
  }

  function setNewLink(field: keyof ArtistLinkDraft, value: string) {
    newLink = { ...newLink, [field]: value };
  }
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
      <textarea id="artist-notes" value={artistDraft.notes} on:input={(event) => setArtistDraft('notes', (event.currentTarget as HTMLTextAreaElement).value)} rows="3"></textarea>
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
