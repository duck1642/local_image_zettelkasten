<script lang="ts">
  import type { VaultItem } from './types';
  import { createEventDispatcher, onDestroy } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { log as uiLog } from './logger';
  import { apiFetch, apiUrl } from './api';
  import { isImageMedia, isVideoMedia } from './media';

  export let item: VaultItem | null = null;
  export let group: { id: string, items: VaultItem[] } | null = null;
  const dispatch = createEventDispatcher();

  let fullItem: any = null;
  let artist = '';
  let sourceUrl = '';
  let platform = '';
  let topics: string[] = [];
  let isDirty = false;
  let loading = false;
  let tagging = false;
  let abortController: AbortController | null = null;
  let lastLoadedHash: string | null = null;

  let videoElement: HTMLVideoElement | undefined;

  $: if (item) {
      if (item.hash !== lastLoadedHash) loadFullDetails(item.hash);
  } else {
      fullItem = null;
      lastLoadedHash = null;
  }

  $: currentIndex = group ? group.items.findIndex(i => i.hash === item?.hash) : 0;

  async function loadFullDetails(hash: string) {
    if (abortController) abortController.abort();
    abortController = new AbortController();
    const signal = abortController.signal;
    fullItem = null;
    loading = true;
    try {
        const res = await apiFetch(`/api/items/${hash}`, { signal });
        if (!res.ok) throw new Error('API error');
        fullItem = await res.json();

        artist = fullItem.artist || '';
        sourceUrl = fullItem.source_url || '';
        platform = fullItem.platform || '';
        topics = fullItem.topics || [];
        isDirty = false;
        lastLoadedHash = hash;
    } catch (e: any) {
        if (e.name !== 'AbortError') {
            uiLog('ERROR', 'Failed to load item details', { hash, error: String(e) });
        }
    } finally {
        if (!signal.aborted) loading = false;
    }
  }

  function handleInput() { isDirty = true; }

  async function responseErrorText(response: Response, fallback: string) {
    try {
      const data = await response.json();
      return data?.detail || data?.message || fallback;
    } catch {
      return fallback;
    }
  }

  function reportActionFailure(action: string, error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    uiLog('ERROR', `${action} failed`, { error: message });
    alert(`${action} failed: ${message}`);
  }

  async function save() {
    if (!item) return;
    try {
      const res = await apiFetch(`/api/items/${item.hash}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ artist, source_url: sourceUrl, platform })
      });
      if (!res.ok) throw new Error('Failed to save');
      isDirty = false;
      dispatch('updated', { hash: item.hash, artist, source_url: sourceUrl, platform });
      uiLog('INFO', `Metadata saved for ${item.hash.substring(0, 12)}`);
    } catch (e) {
        uiLog('ERROR', 'Save failed', { error: String(e) });
        alert('Failed to save changes.');
    }
  }

  async function runTagging() {
      if (!item || tagging) return;
      tagging = true;
      uiLog('INFO', `Manual tagging started for ${item.hash.substring(0, 12)}`);
      try {
          const res = await apiFetch(`/api/items/${item.hash}/tag`, { method: 'POST' });
          if (!res.ok) {
              const err = await res.json();
              throw new Error(err.detail || 'Tagging failed');
          }
          fullItem = await res.json();
          topics = fullItem.topics || [];
          uiLog('INFO', `Tagging complete for ${item.hash.substring(0, 12)}`);
      } catch (e) {
          uiLog('ERROR', 'Tagging failed', { error: String(e) });
          alert(`Tagging failed: ${e}`);
      } finally {
          tagging = false;
      }
  }

  async function openFolder() {
    if (!item) return;
    try {
        const res = await apiFetch(`/api/items/${item.hash}/open_folder`, { method: 'POST' });
        if (!res.ok) throw new Error(await responseErrorText(res, `HTTP ${res.status}`));
        uiLog('INFO', `Opened folder and selected ${item.hash.substring(0, 12)}`);
    } catch (e) { reportActionFailure('Open folder', e); }
  }

  async function openMarkdown() {
    if (!item) return;
    try {
        const res = await apiFetch(`/api/items/${item.hash}/open_note`, { method: 'POST' });
        if (!res.ok) throw new Error(await responseErrorText(res, `HTTP ${res.status}`));
        uiLog('INFO', `Opened markdown note for ${item.hash.substring(0, 12)}`);
    } catch (e) { reportActionFailure('Open note', e); }
  }

  async function copyFile() {
      if (!item) return;
      try {
          const res = await apiFetch(`/api/items/${item.hash}/path`);
          if (!res.ok) throw new Error(await responseErrorText(res, `HTTP ${res.status}`));
          const data = await res.json();
          await invoke('copy_file_to_clipboard', { path: data.absolute_path });
          uiLog('INFO', `File copied to clipboard: ${item.hash.substring(0, 12)}`);
      } catch (e) { reportActionFailure('Copy file', e); }
  }

  async function deleteData() {
      if (!item) return;
      if (!confirm("Are you sure you want to permanently delete this item? This will delete the file, note, and database entry.")) return;
      try {
          const res = await apiFetch(`/api/items/${item.hash}`, { method: 'DELETE' });
          if (res.ok) {
              uiLog('INFO', `Item deleted: ${item.hash}`);
              dispatch('deleted', item.hash);
          } else {
              throw new Error("Failed to delete");
          }
      } catch (e) { uiLog('ERROR', 'Delete failed', { error: String(e) }); }
  }

  function copyHash() {
    if (!item) return;
    navigator.clipboard.writeText(item.hash)
        .then(() => uiLog('DEBUG', 'Hash copied to clipboard'))
        .catch(e => uiLog('ERROR', 'Failed to copy hash', { error: String(e) }));
  }

  function toggleFocus(mode: 'wide' | 'fullscreen') {
      const startTime = videoElement ? videoElement.currentTime : 0;
      dispatch('focus', { mode, hash: item?.hash, startTime });
  }

  function handleKeydown(e: KeyboardEvent) {
      if (!item) return;
      if (e.repeat) return;
      const target = e.target as HTMLElement;
      if (['INPUT', 'TEXTAREA'].includes(target.tagName)) return;

      if (document.querySelector('.focus-overlay')) return;

      const key = e.key.toLowerCase();
      if (key === 'a') {
          e.preventDefault();
          prevItem();
      } else if (key === 'd') {
          e.preventDefault();
          nextItem();
      } else if (key === 'w') {
          e.preventDefault();
          toggleFocus('wide');
      } else if (key === 'f') {
          e.preventDefault();
          toggleFocus('fullscreen');
      }
  }

  function nextItem() {
      if (!group) return;
      const nextIdx = (currentIndex + 1) % group.items.length;
      dispatch('changeItem', group.items[nextIdx]);
  }

  function prevItem() {
      if (!group) return;
      const prevIdx = (currentIndex - 1 + group.items.length) % group.items.length;
      dispatch('changeItem', group.items[prevIdx]);
  }

  onDestroy(() => {
      abortController?.abort();
  });
</script>

<svelte:window on:keydown={handleKeydown} />

<aside class="inspector">
  {#if !item}
    <div class="empty-panel">
        <p>No item selected</p>
    </div>
  {:else}
    {#if loading}
      <div class="loading-overlay">
          <p>Loading details...</p>
      </div>
    {/if}
    {#if fullItem}
    <div class="group-container media-preview">
        {#if isImageMedia(item)}
            <img src={apiUrl(item.thumbnail_url || item.url)} alt="Preview" />
        {:else if isVideoMedia(item)}
            <video
                bind:this={videoElement}
                src={apiUrl(item.url)}
                controls
                controlslist="nofullscreen"
                muted
                loop
                autoplay
            ></video>
        {:else}
            <div class="unsupported-media">Unknown media type</div>
        {/if}
        <div class="media-overlay">
            <button class="overlay-btn" title="Wide View" on:click={() => toggleFocus('wide')}>W</button>
            <button class="overlay-btn" title="Fullscreen" on:click={() => toggleFocus('fullscreen')}>F</button>
        </div>
    </div>

    {#if group && group.items.length > 1}
        <div class="group-nav group-container horizontal">
            <button on:click={prevItem}>&lt;</button>
            <span class="counter">{currentIndex + 1} / {group.items.length}</span>
            <button on:click={nextItem}>&gt;</button>
        </div>
    {/if}

    <div class="group-container">
      <label class="section-label">Artist</label>
      <input type="text" bind:value={artist} on:input={handleInput} placeholder="Artist" />
    </div>

    <div class="group-container horizontal action-row">
        <button class="flex-grow" on:click={openFolder}>Open Folder</button>
        <button class="flex-grow" on:click={openMarkdown}>Open Note</button>
        <button class="flex-grow" on:click={copyFile}>Copy File</button>
        <button class="flex-grow delete-btn" on:click={deleteData}>Delete Data</button>
    </div>

    <div class="group-container">
      <label class="section-label">Source URL</label>
      <input type="text" bind:value={sourceUrl} on:input={handleInput} placeholder="Source URL" />
    </div>

    <div class="group-container horizontal">
      <div class="sub-group platform-col">
        <label class="section-label">Platform</label>
        <div class="value-text">{platform || 'Unknown'}</div>
      </div>
      <div class="sub-group flex-grow">
        <label class="section-label">Hash</label>
        <div class="hash-row">
            <div class="value-text truncate">{item.hash}</div>
            <button class="small-btn" on:click={copyHash}>Copy</button>
        </div>
      </div>
    </div>

    <div class="group-container">
      <label class="section-label">My Topics</label>
      <div class="tags-list">
          {#each (topics || []) as tag}
              <span class="tag-chip topic">
                  {tag}
              </span>
          {/each}
          {#if !topics || topics.length === 0}
              <div class="value-text">No topics</div>
          {/if}
      </div>
    </div>

    <div class="group-container">
      <label class="section-label">WD Suggestions</label>
      <div class="sub-section">
        <span class="muted-title">Rating</span>
        <div class="tags-list">
            {#if fullItem.wd_tags?.rating && fullItem.wd_tags.rating !== 'None'}
                <span class="tag-chip rating">
                    {fullItem.wd_tags.rating}
                </span>
            {:else}
                <div class="value-text">No rating</div>
            {/if}
        </div>
      </div>
      <div class="sub-section">
        <span class="muted-title">Character Tags</span>
        <div class="tags-list">
            {#each (fullItem.wd_tags?.characters || []) as tag}
                <span class="tag-chip character">
                    {tag}
                </span>
            {/each}
            {#if !fullItem.wd_tags?.characters || fullItem.wd_tags.characters.length === 0}
                <div class="value-text">No character tags</div>
            {/if}
        </div>
      </div>
      <div class="sub-section">
        <span class="muted-title">Visual Tags</span>
        <div class="tags-list">
            {#each (fullItem.wd_tags?.general || []) as tag}
                <span class="tag-chip visual">
                    {tag}
                </span>
            {/each}
            {#if !fullItem.wd_tags?.general || fullItem.wd_tags.general.length === 0}
                <div class="value-text">No tags</div>
            {/if}
        </div>
      </div>
    </div>

    <div class="action-footer">
        <button class="tag-btn" on:click={runTagging} disabled={tagging}>
            {tagging ? 'Tagging...' : 'Tag Media'}
        </button>
        <button class="save-btn primary" on:click={save} disabled={!isDirty}>
            Save Changes
        </button>
    </div>
    {/if}
  {/if}
</aside>

<style>
  .inspector {
    width: 400px;
    min-width: 400px;
    background: var(--bg-main);
    border-left: 1px solid var(--border-dim);
    display: flex;
    flex-direction: column;
    padding: 15px;
    gap: 12px;
    overflow-y: auto;
    position: relative;
  }

  .group-container {
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .group-container.media-preview {
    padding: 0;
    overflow: hidden;
    position: relative;
    min-height: 200px;
    max-height: 400px;
    background: #000;
  }

  .media-preview img, .media-preview video {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
  .unsupported-media { min-height: 200px; display: flex; align-items: center; justify-content: center; color: var(--text-muted); font-size: 12px; }

  .media-overlay {
      position: absolute;
      top: 10px;
      right: 10px;
      display: flex;
      gap: 5px;
      opacity: 0;
      transition: opacity 0.2s;
  }
  .media-preview:hover .media-overlay { opacity: 1; }

  .overlay-btn {
      width: 30px;
      height: 30px;
      padding: 0;
      background: rgba(0,0,0,0.6);
      border: 1px solid rgba(255,255,255,0.2);
      color: white;
      font-weight: bold;
      font-size: 11px;
      cursor: pointer;
  }
  .overlay-btn:hover { background: var(--accent-primary); border-color: var(--accent-primary); }

  .group-nav { align-items: center; justify-content: center; gap: 20px; }
  .group-nav button { padding: 4px 20px; font-weight: bold; }
  .counter { font-size: 12px; font-weight: bold; color: var(--text-muted); }

  .section-label { font-size: 11px; color: var(--text-muted); font-weight: 500; }
  .muted-title { font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; }

  .value-text {
    color: #6a737d;
    font-style: italic;
    font-weight: normal;
    font-size: 13px;
    padding: 2px 0;
  }

  .truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-family: monospace; font-size: 11px; }
  .horizontal { flex-direction: row; gap: 20px; }
  .sub-group { display: flex; flex-direction: column; gap: 4px; }
  .platform-col { width: 60px; flex-shrink: 0; }
  .flex-grow { flex-grow: 1; min-width: 0; }

  .hash-row {
    display: flex;
    align-items: center;
    gap: 10px;
    background: var(--bg-input);
    padding: 4px 8px;
    border-radius: 4px;
    border: 1px solid var(--border-dim);
  }

  .small-btn { padding: 2px 8px; font-size: 11px; background: var(--bg-hover); cursor: pointer; }

  .tags-list { display: flex; flex-wrap: wrap; gap: 6px; }

  .tag-chip {
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      background: var(--bg-hover);
      color: var(--text-main);
      border: 1px solid var(--border-dim);
      user-select: none;
  }

  .tag-chip:hover { border-color: var(--border-hover); background: var(--bg-main); }

  .tag-chip.topic { color: var(--accent-purple); border-color: var(--accent-purple); background: rgba(163, 113, 247, 0.1); }
  .tag-chip.rating { color: var(--accent-warning); }
  .tag-chip.character { color: var(--accent-primary); }

  .sub-section {
    margin-top: 5px;
    padding-top: 5px;
    border-top: 1px solid rgba(255,255,255,0.05);
  }

  input { background: var(--bg-input); border: 1px solid #30363d; font-weight: 500; }

  .action-footer {
      display: flex;
      gap: 10px;
      margin-top: 10px;
  }
  .action-footer button { flex: 1; padding: 10px; font-weight: bold; }

  .loading-overlay {
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
    border-radius: 8px;
    color: var(--text-muted);
  }

  .empty-panel {
    flex-grow: 1;
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    background: var(--bg-panel);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
  }

  .action-row button { background: var(--bg-input); border-color: var(--border-dim); font-size: 12px; font-weight: 600; padding: 6px; }
  .action-row button:hover { border-color: var(--border-hover); color: var(--text-bright); }
  .action-row button.delete-btn:hover { border-color: var(--accent-danger); color: var(--accent-danger); }
</style>

