<script lang="ts">
  import { onMount } from 'svelte';
  import type { VaultItem } from './lib/types';
  import Inspector from './lib/Inspector.svelte';
  import LogsView from './lib/LogsView.svelte';
  import Ingestion from './lib/Ingestion.svelte';
  import ReviewView from './lib/ReviewView.svelte';
  import SettingsView from './lib/SettingsView.svelte';
  import VaultGroupTile from './lib/VaultGroupTile.svelte';
  import MediaFocus from './lib/MediaFocus.svelte';
  import { log as uiLog } from './lib/logger';

  let items: VaultItem[] = [];
  let stats = { total_items: 0 };
  let queueStats = { normal: 0, force: 0, failed: 0 };
  let reviewCount = 0;
  let loading = true;
  let selectedItem: VaultItem | null = null;
  let selectedGroup: { id: string, items: VaultItem[] } | null = null;
  let activeTab: 'vault' | 'logs' | 'ingest' | 'review' | 'settings' = 'vault';
  let searchQuery = '';
  
  let focusMode: 'normal' | 'wide' | 'fullscreen' = 'normal';
  let focusStartTime = 0;
  let currentLayout: 'masonry' | 'grid' = 'masonry';
  let configCache: any = null;

  let currentSort = 'newest';
  let currentMediaType = 'all';
  let currentSearchField = '';
  let currentSearchValue = '';

  async function fetchConfig() {
    try {
      const res = await fetch('http://localhost:8000/api/config');
      configCache = await res.json();
      if (configCache?.ui?.vault_layout) {
          currentLayout = configCache.ui.vault_layout;
      }
    } catch(e) {}
  }

  // GROUPING LOGIC
  $: groupedItems = (() => {
    const groups: { [key: string]: VaultItem[] } = {};
    const orderedKeys: string[] = [];
    items.forEach(item => {
      const key = item.source_url && item.source_url.trim() !== '' ? item.source_url : `single-${item.hash}`;
      if (!groups[key]) { groups[key] = []; orderedKeys.push(key); }
      groups[key].push(item);
    });
    // The sorting is now handled primarily by the backend, but we still group them.
    return orderedKeys.map(key => ({ id: key, items: groups[key] }));
  })();

  $: if (activeTab === 'vault') {
      fetchConfig();
  }

  async function fetchItems(field?: string, value?: string) {
    loading = true;
    try {
      if (field !== undefined && value !== undefined) {
          currentSearchField = field;
          currentSearchValue = value;
      }

      let url = `http://localhost:8000/api/items?sort=${currentSort}&media_type=${currentMediaType}`;
      if (currentSearchField && currentSearchValue) {
          url += `&field=${currentSearchField}&value=${encodeURIComponent(currentSearchValue)}`;
      }

      const response = await fetch(url);
      items = await response.json();
      const statsRes = await fetch('http://localhost:8000/api/stats');
      stats = await statsRes.json();
      await fetchSecondaryStats();
    } catch (error) { uiLog('ERROR', 'Failed to fetch items', { error });
    } finally { loading = false; }
  }

  function clearSearch() {
      searchQuery = '';
      currentSearchField = '';
      currentSearchValue = '';
      fetchItems();
  }

  async function fetchSecondaryStats() {
    try {
        const qStatsRes = await fetch('http://localhost:8000/api/queue-stats');
        queueStats = await qStatsRes.json();
        const reviewRes = await fetch('http://localhost:8000/api/review');
        const reviewData = await reviewRes.json();
        reviewCount = reviewData.length;
    } catch (e) { }
  }

  function handleSearchKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      const text = searchQuery.trim();
      if (!text) { fetchItems(); return; }
      uiLog('INFO', `Searching for: ${text}`);
      if (text.startsWith('a:')) fetchItems('source_artist', text.slice(2).trim());
      else if (text.startsWith('@')) fetchItems('platform', text.slice(1).trim());
      else fetchItems('original_filename', text);
      searchQuery = '';
      activeTab = 'vault';
    }
  }

  function handleSelectItem(item: VaultItem, group: any) {
    selectedItem = item;
    selectedGroup = group;
    uiLog('DEBUG', `Selected item: ${item.hash.substring(0, 12)}`);
  }

  function handleUpdate(event: CustomEvent) {
    const { hash, artist, source_url, platform } = event.detail;
    uiLog('INFO', `Item updated: ${hash.substring(0, 12)}`, { artist, platform });
    items = items.map(i => (i.hash === hash ? { ...i, artist, source_url, platform } : i));
    if (selectedItem && selectedItem.hash === hash) {
      selectedItem = { ...selectedItem, artist, source_url, platform };
    }
  }

  function handleFocusMode(event: CustomEvent) {
      focusMode = event.detail.mode;
      focusStartTime = event.detail.startTime || 0;
      uiLog('INFO', `Switched to ${focusMode} view from time ${focusStartTime}`);
  }

  onMount(() => {
    uiLog('INFO', 'Svelte UI initialized and mounted');
    fetchConfig();
    fetchItems();
    const interval = setInterval(fetchSecondaryStats, 5000);
    return () => clearInterval(interval);
  });
</script>

<div class="root-container">
  <div class="app-container">
    <aside class="sidebar">
    <div class="nav-group">
      <button class:active={activeTab === 'vault'} on:click={() => activeTab = 'vault'}>Vault</button>
      <button class:active={activeTab === 'review'} on:click={() => activeTab = 'review'}>
        Review {#if reviewCount > 0}<span class="badge warn">{reviewCount}</span>{/if}
      </button>
      <button class:active={activeTab === 'ingest'} on:click={() => activeTab = 'ingest'}>
        Ingestion {#if (queueStats.normal + queueStats.force) > 0}<span class="badge">{(queueStats.normal + queueStats.force)}</span>{/if}
      </button>
      <button class:active={activeTab === 'logs'} on:click={() => activeTab = 'logs'}>App Logs</button>
      <button class:active={activeTab === 'settings'} on:click={() => activeTab = 'settings'}>Settings</button>
    </div>
  </aside>

  <main class="main-content">
    <header class="top-header">
      <div class="search-container">
        <div class="search-wrapper">
          <input 
            type="text" 
            placeholder="Search (use a: for artist, > for cmd)..." 
            bind:value={searchQuery}
            on:keydown={handleSearchKeydown}
          />
          {#if currentSearchValue || currentSearchField}
              <button class="clear-search" on:click={clearSearch} title="Clear Search">✖</button>
          {/if}
        </div>
      </div>
      <div class="header-actions" class:with-inspector={activeTab === 'vault'}>
        <select class="filter-select" bind:value={currentSort} on:change={() => fetchItems()}>
          <option value="newest">Newest First</option>
          <option value="oldest">Oldest First</option>
          <option value="artist">Artist (A-Z)</option>
          <option value="shuffle">Shuffle</option>
        </select>
        
        <select class="filter-select" bind:value={currentMediaType} on:change={() => fetchItems()}>
          <option value="all">All Media</option>
          <option value="image">Images Only</option>
          <option value="video">Videos Only</option>
        </select>

        <button class="primary" on:click={() => activeTab = 'ingest'}>Add Files</button>
      </div>
    </header>

    <div class="view-and-inspector">
      <div class="viewport">
        {#if activeTab === 'vault'}
          {#if loading}
            <div class="loading">Loading...</div>
          {:else}
            <div class="masonry-container">
              <div class="vault-layout {currentLayout}">
                {#each groupedItems as group (group.id)}
                  <VaultGroupTile 
                    {group} 
                    layout={currentLayout}
                    selectedHash={selectedItem?.hash}
                    on:select={(e) => handleSelectItem(e.detail, group)} 
                  />
                {/each}
              </div>
            </div>
          {/if}
        {:else if activeTab === 'review'}
          <ReviewView />
        {:else if activeTab === 'ingest'}
          <Ingestion />
        {:else if activeTab === 'settings'}
          <SettingsView />
        {:else}
          <LogsView />
        {/if}
      </div>

      {#if activeTab === 'vault'}
        <Inspector 
            item={selectedItem} 
            group={selectedGroup}
            on:close={() => { selectedItem = null; selectedGroup = null; }} 
            on:updated={handleUpdate} 
            on:focus={handleFocusMode}
            on:changeItem={(e) => selectedItem = e.detail}
            on:deleted={() => { selectedItem = null; selectedGroup = null; fetchItems(); }}
        />
      {/if}
    </div>
  </main>
  
  {#if focusMode !== 'normal' && selectedItem}
    <MediaFocus 
        item={selectedItem} 
        mode={focusMode} 
        startTime={focusStartTime}
        on:close={() => focusMode = 'normal'} 
    />
  {/if}
  </div>

  <footer class="bottom-status">
      <span class="status-left">Total Items: {stats.total_items} | DB: WAL | LIZ Tauri</span>
      <span class="status-right">Showing {groupedItems.length} groups of {stats.total_items} items</span>
  </footer>
</div>

<style>
  .root-container { display: flex; flex-direction: column; height: 100vh; width: 100vw; background: var(--bg-main); overflow: hidden; }
  .app-container { display: flex; flex-grow: 1; overflow: hidden; }
  .sidebar { width: 120px; background: var(--bg-main); border-right: 1px solid var(--border-dim); display: flex; flex-direction: column; padding: 15px 10px; flex-shrink: 0; }
  .nav-group { display: flex; flex-direction: column; gap: 10px; }
  .nav-group button { width: 100%; padding: 10px 5px; font-size: 13px; border-radius: 6px; background: transparent; border: 1px solid rgba(255, 255, 255, 0.15); color: var(--text-main); text-align: center; }
  .nav-group button.active { background: var(--accent-primary); color: white; border-color: var(--accent-primary); }
  .nav-group button:not(.active):hover { border-color: rgba(255, 255, 255, 0.3); background: var(--bg-panel); }
  .main-content { flex-grow: 1; display: flex; flex-direction: column; overflow: hidden; }
  .top-header { height: var(--header-height); display: flex; align-items: center; padding: 0 15px; gap: 15px; border-bottom: 1px solid var(--border-dim); flex-shrink: 0; z-index: 100; }
  .search-container { flex-grow: 1; }
  .search-wrapper { position: relative; width: 100%; display: flex; align-items: center; }
  .search-wrapper input { width: 100%; max-width: 100%; padding-right: 35px; }
  .clear-search { position: absolute; right: 8px; background: transparent; border: none; color: var(--text-muted); font-size: 14px; cursor: pointer; padding: 4px; }
  .clear-search:hover { color: var(--accent-danger); background: transparent; border: none; }
  .header-actions { display: flex; align-items: center; gap: 10px; }
  .header-actions.with-inspector { width: calc(400px - 15px); min-width: calc(400px - 15px); justify-content: flex-start; padding-left: 15px; border-left: 1px solid var(--border-dim); }
  .filter-select { background: var(--bg-input); border: 1px solid var(--border-dim); color: var(--text-main); padding: 5px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; height: 32px; }
  .status-text { color: var(--text-muted); font-size: 12px; white-space: nowrap; }
  .view-and-inspector { flex-grow: 1; display: flex; overflow: hidden; }
  .viewport { flex-grow: 1; display: flex; flex-direction: column; overflow: hidden; }
  .masonry-container { flex-grow: 1; overflow-y: auto; padding: 15px; }
  .vault-layout.masonry { column-count: 5; column-gap: 10px; }
  .vault-layout.grid { 
      display: grid; 
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); 
      gap: 15px; 
      align-items: stretch;
  }
  .tile-wrapper { margin-bottom: 10px; break-inside: avoid; border-radius: 8px; border: 2px solid transparent; }
  .bottom-status { height: 25px; background: #010409; border-top: 1px solid var(--border-dim); padding: 0; display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: var(--text-muted); flex-shrink: 0; z-index: 200; width: 100%; box-sizing: border-box; }
  .status-left { padding-left: 15px; }
  .status-right { padding-right: 15px; }
  .badge { background: var(--accent-primary); color: white; font-size: 10px; padding: 1px 5px; border-radius: 10px; margin-left: 3px; }
  .badge.warn { background: var(--accent-warning); }
  @media (max-width: 1400px) { .vault-layout.masonry { column-count: 4; } }
  @media (max-width: 1100px) { .vault-layout.masonry { column-count: 3; } }
  @media (max-width: 800px) { .vault-layout.masonry { column-count: 2; } }
</style>
