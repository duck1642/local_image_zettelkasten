<script lang="ts">
  import { onMount } from 'svelte';
  import { apiFetch } from './api';
  import { log as uiLog } from './logger';

  type FacetKind = 'wd_tag' | 'artist' | 'platform' | 'topic';
  type FacetItem = { value: string; count: number };
  type ArtistListItem = { id: number; name: string; kind: string; item_count: number; link_count: number; alias_count: number };
  type ArtistAlias = { id: number; alias: string; alias_norm: string };
  type ArtistLink = { id: number; platform: string; url: string; handle: string; is_primary: boolean };
  type PlatformListItem = { id: number; key_norm: string; display_name: string; kind: string; item_count: number; alias_count: number };
  type ArtistDetail = {
    id: number;
    name: string;
    name_norm: string;
    kind: string;
    notes: string;
    item_count: number;
    aliases: ArtistAlias[];
    links: ArtistLink[];
  };

  const kinds: { label: string; value: FacetKind }[] = [
    { label: 'WD Tags', value: 'wd_tag' },
    { label: 'Artists', value: 'artist' },
    { label: 'Platforms', value: 'platform' },
    { label: 'Topics', value: 'topic' }
  ];

  let activeKind: FacetKind = 'wd_tag';
  let searchText = '';
  let items: FacetItem[] = [];
  let artists: ArtistListItem[] = [];
  let selectedArtistId: number | null = null;
  let selectedArtist: ArtistDetail | null = null;
  let artistDraft = { name: '', kind: 'artist', notes: '' };
  let newAlias = '';
  let newLink = { platform: '', url: '', handle: '' };
  let platformOptions: PlatformListItem[] = [];
  let linkPlatformOptions: string[] = [];
  let loading = false;
  let artistSaving = false;
  let error = '';
  let debounceTimer: number | null = null;
  let requestSeq = 0;

  $: {
    const values = new Set<string>();
    for (const platform of platformOptions) {
      if (platform.display_name) values.add(platform.display_name);
    }
    for (const link of selectedArtist?.links || []) {
      if (link.platform) values.add(link.platform);
    }
    if (newLink.platform) values.add(newLink.platform);
    linkPlatformOptions = [...values];
  }

  async function loadPlatformOptions() {
    try {
      const response = await apiFetch('/api/platforms?limit=200');
      if (!response.ok) throw new Error(`Platform request failed: ${response.status}`);
      const data = await response.json();
      platformOptions = Array.isArray(data.items) ? data.items : [];
    } catch (err) {
      uiLog('ERROR', 'Failed to load platform options', { error: String(err) });
    }
  }

  async function loadArtistDetail(id: number, seq = requestSeq) {
    const response = await apiFetch(`/api/artists/${id}`);
    if (seq !== requestSeq) return;
    if (!response.ok) throw new Error(`Artist detail failed: ${response.status}`);
    selectedArtist = await response.json();
    artistDraft = {
      name: selectedArtist?.name || '',
      kind: selectedArtist?.kind || 'artist',
      notes: selectedArtist?.notes || ''
    };
  }

  async function loadFacets() {
    const seq = ++requestSeq;
    loading = true;
    error = '';
    try {
      if (activeKind === 'artist') {
        const params = new URLSearchParams({ q: searchText.trim(), limit: '200' });
        const response = await apiFetch(`/api/artists?${params.toString()}`);
        if (seq !== requestSeq) return;
        if (!response.ok) throw new Error(`Artist request failed: ${response.status}`);
        const data = await response.json();
        if (seq !== requestSeq) return;
        artists = Array.isArray(data.items) ? data.items : [];
        if (!selectedArtistId || !artists.some((artist) => artist.id === selectedArtistId)) {
          selectedArtistId = artists[0]?.id ?? null;
        }
        if (selectedArtistId) await loadArtistDetail(selectedArtistId, seq);
        else selectedArtist = null;
        return;
      }
      const params = new URLSearchParams({
        kind: activeKind,
        q: searchText.trim(),
        limit: '200'
      });
      const response = await apiFetch(`/api/facets?${params.toString()}`);
      if (seq !== requestSeq) return;
      if (!response.ok) throw new Error(`Facet request failed: ${response.status}`);
      const data = await response.json();
      if (seq !== requestSeq) return;
      items = Array.isArray(data.items) ? data.items : [];
    } catch (err) {
      if (seq !== requestSeq) return;
      error = 'Failed to load stats';
      uiLog('ERROR', 'Failed to load stats', { error: String(err), kind: activeKind });
    } finally {
      if (seq === requestSeq) loading = false;
    }
  }

  function setKind(kind: FacetKind) {
    activeKind = kind;
    error = '';
    loadFacets();
  }

  async function selectArtist(id: number) {
    selectedArtistId = id;
    loading = true;
    error = '';
    const seq = ++requestSeq;
    try {
      await loadArtistDetail(id, seq);
    } catch (err) {
      if (seq !== requestSeq) return;
      error = 'Failed to load artist';
      uiLog('ERROR', 'Failed to load artist detail', { id, error: String(err) });
    } finally {
      if (seq === requestSeq) loading = false;
    }
  }

  function handleSearchInput() {
    if (debounceTimer !== null) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(loadFacets, 200);
  }

  async function saveArtist() {
    if (!selectedArtist) return;
    artistSaving = true;
    error = '';
    try {
      const response = await apiFetch(`/api/artists/${selectedArtist.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(artistDraft)
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      const updated = payload as ArtistDetail;
      selectedArtist = updated;
      await loadFacets();
      uiLog('INFO', 'Artist updated', { id: updated.id, name: updated.name });
    } catch (err) {
      error = `Failed to save artist: ${String(err)}`;
      uiLog('ERROR', 'Failed to save artist', { error: String(err) });
    } finally {
      artistSaving = false;
    }
  }

  async function addAlias() {
    if (!selectedArtist || !newAlias.trim()) return;
    artistSaving = true;
    error = '';
    try {
      const response = await apiFetch(`/api/artists/${selectedArtist.id}/aliases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alias: newAlias.trim() })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      newAlias = '';
      await loadArtistDetail(selectedArtist.id);
      await loadFacets();
    } catch (err) {
      error = `Failed to add alias: ${String(err)}`;
      uiLog('ERROR', 'Failed to add artist alias', { error: String(err) });
    } finally {
      artistSaving = false;
    }
  }

  async function deleteAlias(aliasId: number) {
    if (!selectedArtist) return;
    artistSaving = true;
    error = '';
    try {
      const response = await apiFetch(`/api/artists/${selectedArtist.id}/aliases/${aliasId}`, { method: 'DELETE' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await loadArtistDetail(selectedArtist.id);
      await loadFacets();
    } catch (err) {
      error = `Failed to delete alias: ${String(err)}`;
      uiLog('ERROR', 'Failed to delete artist alias', { error: String(err) });
    } finally {
      artistSaving = false;
    }
  }

  async function addLink() {
    if (!selectedArtist || !newLink.platform.trim() || !newLink.url.trim()) return;
    artistSaving = true;
    error = '';
    try {
      const response = await apiFetch(`/api/artists/${selectedArtist.id}/links`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          platform: newLink.platform.trim(),
          url: newLink.url.trim(),
          handle: newLink.handle.trim()
        })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail || `HTTP ${response.status}`);
      newLink = { platform: '', url: '', handle: '' };
      await loadArtistDetail(selectedArtist.id);
      await loadFacets();
    } catch (err) {
      error = `Failed to add link: ${String(err)}`;
      uiLog('ERROR', 'Failed to add artist link', { error: String(err) });
    } finally {
      artistSaving = false;
    }
  }

  async function deleteLink(linkId: number) {
    if (!selectedArtist) return;
    artistSaving = true;
    error = '';
    try {
      const response = await apiFetch(`/api/artists/${selectedArtist.id}/links/${linkId}`, { method: 'DELETE' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await loadArtistDetail(selectedArtist.id);
      await loadFacets();
    } catch (err) {
      error = `Failed to delete link: ${String(err)}`;
      uiLog('ERROR', 'Failed to delete artist link', { error: String(err) });
    } finally {
      artistSaving = false;
    }
  }

  function handleGlobalRefresh(event: Event) {
    const detail = (event as CustomEvent).detail || {};
    if (detail.tab !== 'stats') return;
    uiLog('INFO', 'Stats view refresh requested', { kind: activeKind });
    loadFacets();
  }

  onMount(() => {
    window.addEventListener('lmz:refresh', handleGlobalRefresh);
    loadFacets();
    loadPlatformOptions();
    return () => {
      window.removeEventListener('lmz:refresh', handleGlobalRefresh);
      if (debounceTimer !== null) clearTimeout(debounceTimer);
    };
  });
</script>

<div class="stats-container">
  <div class="stats-header">
    <h3>Vault Stats</h3>
    <span class="muted">{activeKind === 'artist' ? artists.length : items.length} values</span>
  </div>

  <div class="kind-tabs">
    {#each kinds as kind}
      <button type="button" class:active={activeKind === kind.value} on:click={() => setKind(kind.value)}>
        {kind.label}
      </button>
    {/each}
  </div>

  <input
    class="stats-search"
    type="text"
    bind:value={searchText}
    on:input={handleSearchInput}
    placeholder="Search stats..."
  />

  {#if activeKind === 'artist'}
    <div class="artist-layout">
      <div class="artist-list">
        {#if loading && artists.length === 0}
          <div class="empty-state">Loading...</div>
        {:else if artists.length === 0}
          <div class="empty-state">No artists</div>
        {:else}
          {#each artists as artist}
            <button type="button" class="artist-row" class:active={selectedArtistId === artist.id} on:click={() => selectArtist(artist.id)}>
              <span class="value" title={artist.name}>{artist.name}</span>
              <span class="artist-meta">{artist.item_count} items - {artist.link_count} links</span>
            </button>
          {/each}
        {/if}
      </div>

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
            <button type="button" on:click={saveArtist} disabled={artistSaving}>{artistSaving ? 'Saving...' : 'Save'}</button>
          </div>

          <div class="detail-grid">
            <label for="artist-name">Name</label>
            <input id="artist-name" bind:value={artistDraft.name} />
            <label for="artist-kind">Kind</label>
            <select id="artist-kind" bind:value={artistDraft.kind}>
              <option value="artist">artist</option>
              <option value="real_person">real_person</option>
            </select>
            <label for="artist-notes">Notes</label>
            <textarea id="artist-notes" bind:value={artistDraft.notes} rows="3"></textarea>
          </div>

          <div class="detail-section">
            <h5>Links</h5>
            {#each selectedArtist.links as link}
              <div class="editable-row">
                <span>{link.platform}</span>
                <a href={link.url} target="_blank" rel="noreferrer">{link.handle || link.url}</a>
                <button type="button" on:click={() => deleteLink(link.id)} disabled={artistSaving}>Remove</button>
              </div>
            {/each}
            <div class="add-row link-add-row">
              <select bind:value={newLink.platform} aria-label="Link platform">
                <option value="">platform</option>
                {#each linkPlatformOptions as platform}
                  <option value={platform}>{platform}</option>
                {/each}
              </select>
              <input bind:value={newLink.url} placeholder="url" />
              <input bind:value={newLink.handle} placeholder="handle" />
              <button type="button" on:click={addLink} disabled={artistSaving}>Add</button>
            </div>
          </div>

          <div class="detail-section">
            <h5>Aliases</h5>
            <div class="alias-list">
              {#each selectedArtist.aliases as alias}
                <span class="alias-chip">
                  {alias.alias}
                  <button type="button" on:click={() => deleteAlias(alias.id)} disabled={artistSaving}>x</button>
                </span>
              {/each}
            </div>
            <div class="add-row">
              <input bind:value={newAlias} placeholder="New alias" />
              <button type="button" on:click={addAlias} disabled={artistSaving}>Add Alias</button>
            </div>
          </div>
        {:else if !loading}
          <div class="empty-state">Select an artist</div>
        {/if}
      </div>
    </div>
  {:else}
    <div class="stats-list">
      {#if loading}
        <div class="empty-state">Loading...</div>
      {:else if error}
        <div class="empty-state error">{error}</div>
      {:else if items.length === 0}
        <div class="empty-state">No values</div>
      {:else}
        {#each items as item}
          <div class="stats-row">
            <span class="value" title={item.value}>{item.value}</span>
            <span class="count">{item.count}</span>
          </div>
        {/each}
      {/if}
    </div>
  {/if}
</div>

<style>
  .stats-container {
    flex-grow: 1;
    padding: 25px;
    background: var(--bg-main);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .stats-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }

  h3 {
    color: var(--text-bright);
    margin: 0;
  }

  .muted {
    color: var(--text-muted);
    font-size: 12px;
  }

  .kind-tabs {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .kind-tabs button.active {
    background: var(--accent-primary);
    border-color: var(--accent-primary);
    color: white;
  }

  .stats-search {
    width: 100%;
    max-width: 520px;
  }

  .stats-list,
  .artist-list,
  .artist-detail {
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    background: var(--bg-panel);
    overflow-y: auto;
    min-height: 0;
  }

  .stats-list {
    flex-grow: 1;
  }

  .stats-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 80px;
    gap: 16px;
    align-items: center;
    padding: 9px 12px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }

  .stats-row:last-child {
    border-bottom: 0;
  }

  .value {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text-main);
  }

  .count {
    text-align: right;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }

  .empty-state {
    padding: 24px;
    color: var(--text-muted);
  }

  .empty-state.error {
    color: var(--accent-danger);
  }

  .artist-layout {
    display: grid;
    grid-template-columns: minmax(230px, 320px) minmax(0, 1fr);
    gap: 14px;
    min-height: 0;
    flex-grow: 1;
  }

  .artist-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 3px;
    width: 100%;
    padding: 10px 12px;
    border: 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 0;
    background: transparent;
    text-align: left;
  }

  .artist-row.active,
  .artist-row:hover {
    background: rgba(31, 111, 235, 0.16);
  }

  .artist-meta {
    color: var(--text-muted);
    font-size: 11px;
  }

  .artist-detail {
    padding: 14px;
  }

  .detail-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 16px;
  }

  .detail-header h4 {
    margin: 0 0 4px 0;
    color: var(--text-bright);
  }

  .detail-grid {
    display: grid;
    grid-template-columns: 80px minmax(0, 1fr);
    gap: 10px 12px;
    align-items: center;
  }

  input,
  select,
  textarea {
    width: 100%;
    box-sizing: border-box;
    background: var(--bg-main);
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    color: var(--text-main);
    padding: 8px 10px;
    font-size: 13px;
  }

  textarea {
    resize: vertical;
    min-height: 70px;
  }

  .detail-section {
    margin-top: 18px;
  }

  .detail-section h5 {
    margin: 0 0 8px 0;
    color: var(--text-bright);
    font-size: 13px;
  }

  .editable-row,
  .add-row {
    display: grid;
    grid-template-columns: 90px minmax(0, 1fr) auto;
    gap: 8px;
    align-items: center;
    margin-bottom: 8px;
  }

  .editable-row a {
    color: var(--text-main);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .link-add-row {
    grid-template-columns: 120px minmax(0, 1fr) 120px auto;
  }

  .alias-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 8px;
  }

  .alias-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    color: var(--text-main);
    background: var(--bg-main);
  }

  .alias-chip button {
    padding: 0 4px;
    border: 0;
    background: transparent;
    color: var(--text-muted);
  }

  @media (max-width: 820px) {
    .artist-layout,
    .link-add-row {
      grid-template-columns: 1fr;
    }
  }
</style>
