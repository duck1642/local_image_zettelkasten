<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import type { SearchFilters, VaultGroup, VaultItem } from './types';
  import { apiFetch } from './api';
  import { log as uiLog } from './logger';
  import { buildItemQueryParams, emptyFilters } from './search';
  import { updateSelection } from './selection';
  import Inspector from './Inspector.svelte';
  import MediaFocus from './MediaFocus.svelte';
  import SearchBar from './SearchBar.svelte';
  import VaultGroupTile from './VaultGroupTile.svelte';

  const dispatch = createEventDispatcher();

  let items: VaultItem[] = [];
  let stats = { total_items: 0 };
  let isSearching = true;
  let isLoadingMore = false;
  let selectedItem: VaultItem | null = null;
  let selectedGroup: VaultGroup | null = null;
  let selectedHashes = new Set<string>();
  let lastSelectedHash: string | null = null;
  let bulkDeleting = false;
  let focusMode: 'normal' | 'wide' | 'fullscreen' = 'normal';
  let focusStartTime = 0;
  let currentLayout: 'masonry' | 'grid' = 'masonry';
  let configCache: any = null;
  let currentSort = 'newest';
  let currentMediaType = 'all';
  let activeFilters: SearchFilters = emptyFilters();
  let nextCursor: string | null = null;
  let hasMore = false;
  let sentinelEl: HTMLElement | null = null;
  let observer: IntersectionObserver | null = null;
  let observedSentinel: HTMLElement | null = null;
  let observedLayout = '';

  $: groupedItems = groupVaultItems(items);
  $: emitStatus();
  $: attachInfiniteScroll(sentinelEl, currentLayout);

  function groupVaultItems(rows: VaultItem[]): VaultGroup[] {
    const groups: { [key: string]: VaultItem[] } = {};
    const orderedKeys: string[] = [];
    rows.forEach((item) => {
      const key = item.source_url && item.source_url.trim() !== '' ? item.source_url : `single-${item.hash}`;
      if (!groups[key]) {
        groups[key] = [];
        orderedKeys.push(key);
      }
      groups[key].push(item);
    });
    return orderedKeys.map((key) => ({ id: key, items: groups[key] }));
  }

  function emitStatus() {
    dispatch('status', { totalItems: stats.total_items, groups: groupedItems.length, hasMore });
  }

  async function fetchConfig() {
    try {
      const res = await apiFetch('/api/config');
      configCache = await res.json();
      if (configCache?.ui?.vault_layout) currentLayout = configCache.ui.vault_layout;
    } catch (error) {
      uiLog('ERROR', 'Failed to fetch config', { error });
    }
  }

  async function saveLayout(layout: 'masonry' | 'grid') {
    currentLayout = layout;
    if (!configCache) return;
    if (!configCache.ui) configCache.ui = {};
    configCache.ui.vault_layout = currentLayout;
    try {
      await apiFetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(configCache)
      });
    } catch (error) {
      uiLog('ERROR', 'Failed to save layout command', { error });
    }
  }

  async function fetchItems(append = false) {
    if (!append) {
      nextCursor = null;
      isSearching = true;
    } else {
      isLoadingMore = true;
    }
    try {
      const params = buildItemQueryParams(activeFilters, currentSort, currentMediaType, '50', append ? nextCursor : null);
      const response = await apiFetch(`/api/items?${params.toString()}`);
      const data = await response.json();
      const newItems: VaultItem[] = Array.isArray(data.items) ? data.items : [];
      items = append ? [...items, ...newItems] : newItems;
      nextCursor = data.next_cursor || null;
      hasMore = data.has_more || false;

      const statsRes = await apiFetch('/api/stats');
      stats = await statsRes.json();
    } catch (error) {
      uiLog('ERROR', 'Failed to fetch items', { error });
    } finally {
      if (!append) isSearching = false;
      else isLoadingMore = false;
    }
  }

  function loadMore() {
    if (hasMore && !isSearching && !isLoadingMore) fetchItems(true);
  }

  function handleFiltersChanged(event: CustomEvent) {
    activeFilters = event.detail.filters;
    fetchItems();
  }

  function handleCommand(event: CustomEvent) {
    const command = event.detail.command;
    if (command === 'grid' || command === 'masonry') saveLayout(command);
  }

  function loadedHashOrder() {
    return items.map((item) => item.hash);
  }

  function handleSelectItem(item: VaultItem, group: VaultGroup, event?: MouseEvent) {
    selectedItem = item;
    selectedGroup = group;
    const next = updateSelection(selectedHashes, loadedHashOrder(), item.hash, lastSelectedHash, event);
    selectedHashes = next.selectedHashes;
    lastSelectedHash = next.lastSelectedHash;
    uiLog('DEBUG', `Selected item: ${item.hash.substring(0, 12)}`);
  }

  function setSingleSelection(item: VaultItem) {
    selectedItem = item;
    selectedHashes = new Set([item.hash]);
    lastSelectedHash = item.hash;
  }

  function clearSelection() {
    selectedHashes = new Set();
    lastSelectedHash = null;
    selectedItem = null;
    selectedGroup = null;
  }

  async function deleteSelected() {
    const hashes = Array.from(selectedHashes);
    if (!hashes.length || bulkDeleting) return;
    const confirmed = confirm(`Delete ${hashes.length} selected item${hashes.length === 1 ? '' : 's'}? This removes DB rows, vault files, notes, and WD tag cache.`);
    if (!confirmed) return;
    bulkDeleting = true;
    try {
      for (const hash of hashes) {
        const response = await apiFetch(`/api/items/${hash}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(`Delete failed for ${hash}: ${response.status}`);
      }
      uiLog('INFO', 'Bulk delete completed', { count: hashes.length });
      clearSelection();
      await fetchItems();
    } catch (error) {
      uiLog('ERROR', 'Bulk delete failed', { error: String(error) });
      alert('Delete failed. Check App Logs for details.');
      await fetchItems();
    } finally {
      bulkDeleting = false;
    }
  }

  function handleUpdate(event: CustomEvent) {
    const { hash, artist, source_url, platform } = event.detail;
    uiLog('INFO', `Item updated: ${hash.substring(0, 12)}`, { artist, platform });
    items = items.map((item) => (item.hash === hash ? { ...item, artist, source_url, platform } : item));
    if (selectedItem && selectedItem.hash === hash) selectedItem = { ...selectedItem, artist, source_url, platform };
  }

  function handleFocusMode(event: CustomEvent) {
    focusMode = event.detail.mode;
    focusStartTime = event.detail.startTime || 0;
    uiLog('INFO', `Switched to ${focusMode} view from time ${focusStartTime}`);
  }

  function handleGlobalKeydown(event: KeyboardEvent) {
    if (event.key === 'F5') {
      if (event.ctrlKey) {
        uiLog('INFO', 'Ctrl+F5 pressed: Reloading full app');
        window.location.reload();
      } else {
        event.preventDefault();
        uiLog('INFO', 'F5 pressed: Refreshing database/items');
        fetchItems();
      }
    }
  }

  function attachInfiniteScroll(node: HTMLElement | null, layout: string) {
    if (!node) {
      observer?.disconnect();
      observer = null;
      observedSentinel = null;
      observedLayout = '';
      return;
    }
    if (observer && observedSentinel === node && observedLayout === layout) return;
    observer?.disconnect();
    observedSentinel = node;
    observedLayout = layout;
    observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && hasMore && !isSearching && !isLoadingMore) loadMore();
    }, { rootMargin: '400px' });
    observer.observe(node);
  }

  onMount(() => {
    fetchConfig();
    fetchItems();
    return () => observer?.disconnect();
  });
</script>

<svelte:window on:keydown={handleGlobalKeydown} />

<header class="top-header">
  <SearchBar on:filtersChanged={handleFiltersChanged} on:command={handleCommand} />
  <div class="header-actions with-inspector">
    <select class="filter-select" bind:value={currentSort} on:change={() => fetchItems()}>
      <option value="newest">Newest First</option>
      <option value="oldest">Oldest First</option>
      <option value="artist">Artist (A-Z)</option>
    </select>

    <select class="filter-select" bind:value={currentMediaType} on:change={() => fetchItems()}>
      <option value="all">All Media</option>
      <option value="image">Images Only</option>
      <option value="video">Videos Only</option>
    </select>

    <button class="primary" on:click={() => dispatch('navigate', 'ingest')}>Add Files</button>
  </div>
</header>

<div class="view-and-inspector">
  <div class="viewport">
    {#if selectedHashes.size > 1}
      <div class="bulk-action-bar">
        <span class="selection-count">{selectedHashes.size} selected</span>
        <button on:click={clearSelection}>Clear Selection</button>
        <button class="danger" on:click={deleteSelected} disabled={bulkDeleting}>
          {bulkDeleting ? 'Deleting...' : 'Delete Selected'}
        </button>
      </div>
    {/if}
    {#if isSearching && items.length === 0}
      <div class="initial-loading"></div>
    {:else if currentLayout === 'masonry'}
      <div class="masonry-scroll">
        <div class="vault-layout masonry">
          {#each groupedItems as group (group.id)}
            <VaultGroupTile
              {group}
              layout="masonry"
              selectedHash={selectedItem?.hash}
              {selectedHashes}
              on:select={(event) => handleSelectItem(event.detail.item, group, event.detail.event)}
            />
          {/each}
        </div>
        <div bind:this={sentinelEl} class="scroll-sentinel"></div>
        {#if isLoadingMore}
          <div class="loading-more">Loading more...</div>
        {/if}
      </div>
    {:else}
      <div class="grid-scroll">
        <div class="vault-layout grid">
          {#each groupedItems as group (group.id)}
            <VaultGroupTile
              {group}
              layout="grid"
              selectedHash={selectedItem?.hash}
              {selectedHashes}
              on:select={(event) => handleSelectItem(event.detail.item, group, event.detail.event)}
            />
          {/each}
        </div>
        <div bind:this={sentinelEl} class="scroll-sentinel"></div>
        {#if isLoadingMore}
          <div class="loading-more">Loading more...</div>
        {/if}
      </div>
    {/if}
  </div>

  <Inspector
    item={selectedItem}
    group={selectedGroup}
    on:close={clearSelection}
    on:updated={handleUpdate}
    on:focus={handleFocusMode}
    on:changeItem={(event) => setSingleSelection(event.detail)}
    on:deleted={() => { clearSelection(); fetchItems(); }}
  />
</div>

{#if focusMode !== 'normal' && selectedItem}
  <MediaFocus
    item={selectedItem}
    mode={focusMode}
    startTime={focusStartTime}
    on:close={() => focusMode = 'normal'}
    on:switchMode={(event) => { focusMode = event.detail; }}
  />
{/if}

<style>
  .top-header { height: var(--header-height); display: flex; align-items: center; padding: 0 15px; gap: 15px; border-bottom: 1px solid var(--border-dim); flex-shrink: 0; z-index: 100; }
  .header-actions { display: flex; align-items: center; gap: 10px; }
  .header-actions.with-inspector { width: calc(400px - 15px); min-width: calc(400px - 15px); justify-content: flex-start; padding-left: 15px; border-left: 1px solid var(--border-dim); }
  .filter-select { background: var(--bg-input); border: 1px solid var(--border-dim); color: var(--text-main); padding: 5px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; height: 32px; }
  .view-and-inspector { flex-grow: 1; display: flex; overflow: hidden; }
  .viewport { flex-grow: 1; display: flex; flex-direction: column; overflow: hidden; position: relative; }
  .bulk-action-bar { position: absolute; left: 50%; bottom: 18px; transform: translateX(-50%); z-index: 60; display: flex; align-items: center; gap: 10px; padding: 9px 12px; border: 1px solid var(--border-dim); border-radius: 8px; background: rgba(13, 17, 23, 0.96); box-shadow: 0 10px 30px rgba(0,0,0,0.35); }
  .selection-count { color: var(--text-bright); font-weight: 600; white-space: nowrap; }
  .grid-scroll { flex-grow: 1; overflow-y: auto; padding: 15px; }
  .masonry-scroll { flex-grow: 1; overflow-y: auto; padding: 15px; }
  .vault-layout.masonry { column-count: 5; column-gap: 12px; }
  .vault-layout.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; align-items: stretch; }
  .scroll-sentinel { height: 1px; }
  .initial-loading { flex-grow: 1; }
  .loading-more { text-align: center; padding: 15px; color: var(--text-muted); font-size: 12px; }
</style>
