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
    orderedKeys.forEach(key => { groups[key].sort((a, b) => a.date_added.localeCompare(b.date_added)); });
    return orderedKeys.map(key => ({ id: key, items: groups[key] }));
  })();

  $: if (activeTab === 'vault') {
      fetchConfig();
  }

  async function fetchItems(field?: string, value?: string) {
    loading = true;
    try {
      let url = 'http://localhost:8000/api/items';
      if (field && value) url += `?field=${field}&value=${encodeURIComponent(value)}`;
      const response = await fetch(url);
      items = await response.json();
      const statsRes = await fetch('http://localhost:8000/api/stats');
      stats = await statsRes.json();
      await fetchSecondaryStats();
    } catch (error) { uiLog('ERROR', 'Failed to fetch items', { error });
    } finally { loading = false; }
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
        <input 
          type="text" 
          placeholder="Search (use a: for artist, > for cmd)..." 
          bind:value={searchQuery}
          on:keydown={handleSearchKeydown}
        />
      </div>
      <div class="header-actions">
        <button class="primary" on:click={() => activeTab = 'ingest'}>Add Files</button>
        <button on:click={() => fetchItems()}>Refresh</button>
        <span class="status-text">Showing {groupedItems.length} groups of {stats.total_items} items</span>
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
        />
      {/if}
    </div>
    
    <footer class="bottom-status">
        Total Items: {stats.total_items} | DB: WAL | LIZ Tauri
    </footer>
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

<style>
  .app-container { display: flex; height: 100vh; width: 100vw; background: var(--bg-main); overflow: hidden; }
  .sidebar { width: 120px; background: var(--bg-main); border-right: 1px solid var(--border-dim); display: flex; flex-direction: column; padding: 15px 10px; flex-shrink: 0; }
  .nav-group { display: flex; flex-direction: column; gap: 10px; }
  .nav-group button { width: 100%; padding: 10px 5px; font-size: 13px; border-radius: 6px; background: transparent; border: 1px solid transparent; color: var(--text-main); text-align: center; }
  .nav-group button.active { background: var(--accent-primary); color: white; border-color: var(--accent-primary); }
  .nav-group button:not(.active):hover { border-color: var(--border-dim); background: var(--bg-panel); }
  .main-content { flex-grow: 1; display: flex; flex-direction: column; overflow: hidden; }
  .top-header { height: var(--header-height); display: flex; align-items: center; padding: 0 15px; gap: 15px; border-bottom: 1px solid var(--border-dim); flex-shrink: 0; z-index: 100; }
  .search-container { flex-grow: 1; }
  .search-container input { width: 100%; max-width: 800px; }
  .header-actions { display: flex; align-items: center; gap: 10px; }
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
  .bottom-status { height: 25px; background: #010409; border-top: 1px solid var(--border-dim); padding: 0 10px; display: flex; align-items: center; font-size: 11px; color: var(--text-muted); flex-shrink: 0; }
  .badge { background: var(--accent-primary); color: white; font-size: 10px; padding: 1px 5px; border-radius: 10px; margin-left: 3px; }
  .badge.warn { background: var(--accent-warning); }
  @media (max-width: 1400px) { .vault-layout.masonry { column-count: 4; } }
  @media (max-width: 1100px) { .vault-layout.masonry { column-count: 3; } }
  @media (max-width: 800px) { .vault-layout.masonry { column-count: 2; } }
</style>
