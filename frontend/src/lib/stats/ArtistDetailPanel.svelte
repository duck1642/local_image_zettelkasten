<script lang="ts">
  import type { ArtistDetail, ArtistDraft, ArtistLinkDraft } from './types';

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
        <span class="muted">{selectedArtist.item_count} items - {selectedArtist.kind}</span>
      </div>
      <button type="button" on:click={onSave} disabled={artistSaving}>{artistSaving ? 'Saving...' : 'Save'}</button>
    </div>

    <div class="detail-grid">
      <label for="artist-name">Name</label>
      <input id="artist-name" value={artistDraft.name} on:input={(event) => setArtistDraft('name', (event.currentTarget as HTMLInputElement).value)} />
      <label for="artist-kind">Kind</label>
      <select id="artist-kind" value={artistDraft.kind} on:change={(event) => setArtistDraft('kind', (event.currentTarget as HTMLSelectElement).value)}>
        <option value="artist">artist</option>
        <option value="real_person">real_person</option>
        <option value="brand">brand</option>
        <option value="other">other</option>
      </select>
      <label for="artist-notes">Notes</label>
      <textarea id="artist-notes" value={artistDraft.notes} on:input={(event) => setArtistDraft('notes', (event.currentTarget as HTMLTextAreaElement).value)} rows="3"></textarea>
    </div>

    <div class="detail-section">
      <h5>Links</h5>
      {#each selectedArtist.links as link}
        <div class="editable-row">
          <span>{link.platform}</span>
          <a href={link.url} target="_blank" rel="noreferrer">{link.handle || link.url}</a>
          <button type="button" on:click={() => onDeleteLink(link.id)} disabled={artistSaving}>Remove</button>
        </div>
      {/each}
      <div class="add-row link-add-row">
        <select value={newLink.platform} on:change={(event) => setNewLink('platform', (event.currentTarget as HTMLSelectElement).value)} aria-label="Link platform">
          <option value="">platform</option>
          {#each linkPlatformOptions as platform}
            <option value={platform}>{platform}</option>
          {/each}
        </select>
        <input value={newLink.url} on:input={(event) => setNewLink('url', (event.currentTarget as HTMLInputElement).value)} placeholder="url" />
        <input value={newLink.handle} on:input={(event) => setNewLink('handle', (event.currentTarget as HTMLInputElement).value)} placeholder="handle" />
        <button type="button" on:click={onAddLink} disabled={artistSaving}>Add</button>
      </div>
    </div>

    <div class="detail-section">
      <h5>Aliases</h5>
      <div class="alias-list">
        {#each selectedArtist.aliases as alias}
          <span class="alias-chip">
            {alias.alias}
            <button type="button" on:click={() => onDeleteAlias(alias.id)} disabled={artistSaving} title="Delete Alias">
              <svg viewBox="0 0 24 24" width="10" height="10" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </span>
        {/each}
      </div>
      <div class="add-row">
        <input bind:value={newAlias} placeholder="New alias" />
        <button type="button" on:click={onAddAlias} disabled={artistSaving}>Add Alias</button>
      </div>
      <button type="button" class="merge-button" on:click={onOpenMerge} disabled={artistSaving}>
        Merge Other Artists Into This
      </button>
    </div>
  {:else if !loading}
    <div class="empty-state">Select an artist</div>
  {/if}
</div>
