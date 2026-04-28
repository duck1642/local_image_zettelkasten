<script lang="ts">
  import type { VaultItem } from './types';
  import { createEventDispatcher } from 'svelte';
  import { open } from '@tauri-apps/plugin-shell';
  import { log as uiLog } from './logger';
  import { apiFetch } from './api';

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

  let videoElement: HTMLVideoElement;

  $: if (item) {
      loadFullDetails(item.hash);
  } else {
      fullItem = null;
  }

  $: currentIndex = group ? group.items.findIndex(i => i.hash === item?.hash) : 0;

  async function loadFullDetails(hash: string) {
    if (abortController) abortController.abort();
    abortController = new AbortController();
    const signal = abortController.signal;
    fullItem = null;
    loading = true;
    try {
        const res = await fetch(`http://localhost:8000/api/items/${hash}`, { signal });
        if (!res.ok) throw new Error('API error');
        fullItem = await res.json();
        
        artist = fullItem.artist || '';
        sourceUrl = fullItem.source_url || '';
        platform = fullItem.platform || '';
        topics = fullItem.topics || [];
        isDirty = false;
    } catch (e: any) {
        if (e.name !== 'AbortError') {
            uiLog('ERROR', 'Failed to load item details', { hash, error: String(e) });
        }
    } finally {
        loading = false;
    }
  }

  function handleInput() { isDirty = true; }

  async function save() {
    if (!item) return;
    try {
      const res = await apiFetch(`/api/items/${item.hash}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ artist, source_url: sourceUrl, platform, topics })
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
          // Update topics from the new markdown note
          topics = fullItem.topics || [];
          uiLog('INFO', `Tagging complete for ${item.hash.substring(0, 12)}`);
      } catch (e) {
          uiLog('ERROR', 'Tagging failed', { error: String(e) });
          alert(`Tagging failed: ${e}`);
      } finally {
          tagging = false;
      }
  }

  function addTagToTopics(tagName: string) {
      if (!topics.includes(tagName)) {
          topics = [...topics, tagName];
          isDirty = true;
          uiLog('DEBUG', `Added tag to topics: ${tagName}`);
      }
  }

  function removeTopic(tagName: string) {
      topics = topics.filter(t => t !== tagName);
      isDirty = true;
  }

  async function openFolder() {
    if (!item) return;
    try {
        const res = await fetch(`http://localhost:8000/api/items/${item.hash}/path`);
        const data = await res.json();
        await open(data.absolute_path, 'explorer');
        uiLog('INFO', `Opened folder for ${item.hash.substring(0, 12)}`);
    } catch (e) { uiLog('ERROR', 'Failed to open folder', { error: String(e) }); }
  }

  async function openSource() {
    if (!sourceUrl) return;
    try {
        await open(sourceUrl);
        uiLog('INFO', `Opened source URL: ${sourceUrl}`);
    } catch (e) { uiLog('ERROR', 'Failed to open source URL', { error: String(e) }); }
  }

  function copyData() {
      if (!fullItem) return;
      navigator.clipboard.writeText(JSON.stringify(fullItem, null, 2));
      uiLog('INFO', `Data for ${item.hash.substring(0, 12)} copied to clipboard`);
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
    navigator.clipboard.writeText(item.hash);
    uiLog('DEBUG', 'Hash copied to clipboard');
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
      if (document.querySelector('.focus-overlay')) return; // Let MediaFocus handle it if it's open

      if (e.key.toLowerCase() === 'w') {
          e.preventDefault();
          toggleFocus('wide');
      } else if (e.key.toLowerCase() === 'f') {
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
        {#if item.mime_type.startsWith('image/')}
            <img src={`http://localhost:8000${item.url}`} alt="Preview" />
        {:else}
            <video 
                bind:this={videoElement}
                src={`http://localhost:8000${item.url}`} 
                controls 
                controlslist="nofullscreen"
                muted 
                loop 
                autoplay
            ></video>
        {/if}
        <div class="media-overlay">
            <button class="overlay-btn" title="Wide View" on:click={() => toggleFocus('wide')}>W</button>
            <button class="overlay-btn" title="Fullscreen" on:click={() => toggleFocus('fullscreen')}>F</button>
        </div>
    </div>

    <!-- Group Navigation Row -->
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
        <button class="flex-grow" on:click={openSource} disabled={!sourceUrl}>Open Source</button>
        <button class="flex-grow" on:click={copyData}>Copy Data</button>
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
              <span class="tag-chip topic" on:click={() => removeTopic(tag)} title="Click to remove">
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
                <span class="tag-chip rating" on:click={() => addTagToTopics(fullItem.wd_tags.rating)}>
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
                <span class="tag-chip character" on:click={() => addTagToTopics(tag)}>
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
                <span class="tag-chip visual" on:click={() => addTagToTopics(tag)}>
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
      cursor: pointer;
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
