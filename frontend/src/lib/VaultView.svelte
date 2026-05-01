<script lang="ts">
  import { createEventDispatcher, onMount, tick } from 'svelte';
  import type { SearchFilters, VaultGroup, VaultItem } from './types';
  import { apiFetch } from './api';
  import { config, loadConfig, saveCurrentConfig, setVaultLayoutMode, setVaultTileMinWidthLocal } from './configStore';
  import { log as uiLog } from './logger';
  import type { VaultLayoutMode } from './layout';
  import { DEFAULT_TILE_MIN_WIDTH, normalizeLayoutMode, normalizeTileMinWidth } from './layout';
  import { buildItemQueryParams, emptyFilters } from './search';
  import { updateSelection } from './selection';
  import GridRenderer from './renderers/grid/GridRenderer.svelte';
  import MasonryRenderer from './renderers/masonry/MasonryRenderer.svelte';
  import Inspector from './Inspector.svelte';
  import MediaFocus from './MediaFocus.svelte';
  import SearchBar from './SearchBar.svelte';

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
  let currentLayoutMode: VaultLayoutMode = 'masonry';
  let currentSort = 'newest';
  let currentMediaType = 'all';
  let activeFilters: SearchFilters = emptyFilters();
  let nextCursor: string | null = null;
  let hasMore = false;
  let sentinelEl: HTMLElement | null = null;
  let observer: IntersectionObserver | null = null;
  let observedSentinel: HTMLElement | null = null;
  let observedLayout = '';
  let loadMoreCheckTimer: number | null = null;
  let layoutHostEl: HTMLElement | null = null;
  let observedLayoutHost: HTMLElement | null = null;
  let resizeObserver: ResizeObserver | null = null;
  let vaultWidth = 0;
  let tileMinWidth = DEFAULT_TILE_MIN_WIDTH;
  let tileSizeSaveTimer: number | null = null;
  let groupIndexes: Record<string, number> = {};
  let visualHashOrder: string[] = [];

  $: groupedItems = groupVaultItems(items);
  $: emitStatus(stats.total_items, groupedItems.length, hasMore, currentLayoutMode);
  $: jsVisualHashOrder = visualHashOrder.length ? visualHashOrder : groupedItems.flatMap((group) => group.items.map((item) => item.hash));
  $: attachInfiniteScroll(sentinelEl, currentLayoutMode);
  $: observeLayoutHost(layoutHostEl);
  $: if ($config) {
    const nextMode = normalizeLayoutMode($config);
    const nextWidth = normalizeTileMinWidth($config?.ui?.vault_tile_min_width);
    if (currentLayoutMode !== nextMode) {
      currentLayoutMode = nextMode;
      visualHashOrder = [];
      scheduleLoadMoreCheck();
    }
    if (tileMinWidth !== nextWidth) {
      tileMinWidth = nextWidth;
      scheduleLoadMoreCheck();
    }
  }

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

  function emitStatus(totalItems: number, groups: number, moreAvailable: boolean, layoutMode: VaultLayoutMode) {
    dispatch('status', { totalItems, groups, hasMore: moreAvailable, layoutMode });
  }

  async function fetchConfig() {
    try {
      const loaded = await loadConfig();
      currentLayoutMode = normalizeLayoutMode(loaded);
      tileMinWidth = normalizeTileMinWidth(loaded?.ui?.vault_tile_min_width);
    } catch (error) {
      uiLog('ERROR', 'Failed to fetch config', { error });
    }
  }

  async function saveLayoutMode(mode: VaultLayoutMode) {
    currentLayoutMode = mode;
    visualHashOrder = [];
    scheduleLoadMoreCheck();
    try {
      await setVaultLayoutMode(mode);
    } catch (error) {
      uiLog('ERROR', 'Failed to save layout mode command', { error });
    }
  }

  function saveTileSizeDebounced() {
    if (tileSizeSaveTimer !== null) window.clearTimeout(tileSizeSaveTimer);
    tileSizeSaveTimer = window.setTimeout(async () => {
      tileSizeSaveTimer = null;
      try {
        await saveCurrentConfig();
      } catch (error) {
        uiLog('ERROR', 'Failed to save vault zoom', { error });
      }
    }, 500);
  }

  function zoomTileSize(delta: number) {
    const next = normalizeTileMinWidth(tileMinWidth + delta);
    if (next === tileMinWidth) return;
    tileMinWidth = next;
    setVaultTileMinWidthLocal(next);
    scheduleLoadMoreCheck();
    saveTileSizeDebounced();
  }

  function zoomIn() {
    zoomTileSize(20);
  }

  function zoomOut() {
    zoomTileSize(-20);
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
      scheduleLoadMoreCheck();
    }
  }

  function loadMore() {
    if (hasMore && nextCursor && !isSearching && !isLoadingMore) fetchItems(true);
  }

  function sentinelIsNearViewport() {
    if (!sentinelEl) return false;
    const rect = sentinelEl.getBoundingClientRect();
    return rect.top <= window.innerHeight + 400 && rect.bottom >= -400;
  }

  function scheduleLoadMoreCheck() {
    if (loadMoreCheckTimer !== null) window.clearTimeout(loadMoreCheckTimer);
    loadMoreCheckTimer = window.setTimeout(() => {
      loadMoreCheckTimer = null;
      maybeLoadMore();
    }, 50);
  }

  async function maybeLoadMore() {
    await tick();
    if (hasMore && nextCursor && !isSearching && !isLoadingMore && sentinelIsNearViewport()) {
      loadMore();
    }
  }

  function handleFiltersChanged(event: CustomEvent) {
    activeFilters = event.detail.filters;
    visualHashOrder = [];
    fetchItems();
  }

  function handleCommand(event: CustomEvent) {
    const command = event.detail.command;
    if (command === 'masonry' || command === 'grid') {
      saveLayoutMode(command);
    } else if (command === 'zoom-in') {
      zoomIn();
    } else if (command === 'zoom-out') {
      zoomOut();
    }
  }

  function loadedHashOrder() {
    return jsVisualHashOrder.length ? jsVisualHashOrder : items.map((item) => item.hash);
  }

  function findGroupForItem(target: VaultItem | null) {
    if (!target) return null;
    return groupedItems.find((group) => group.items.some((item) => item.hash === target.hash)) || null;
  }

  function handleSelectItem(item: VaultItem, group: VaultGroup, event?: MouseEvent) {
    const next = updateSelection(selectedHashes, loadedHashOrder(), item.hash, lastSelectedHash, event);
    selectedHashes = next.selectedHashes;
    lastSelectedHash = next.lastSelectedHash;
    if (selectedHashes.has(item.hash)) {
      selectedItem = item;
      selectedGroup = group;
    } else if (selectedHashes.size > 0) {
      selectedItem = items.find((candidate) => selectedHashes.has(candidate.hash)) || null;
      selectedGroup = findGroupForItem(selectedItem);
    } else {
      selectedItem = null;
      selectedGroup = null;
    }
    uiLog('DEBUG', `Selected item: ${item.hash.substring(0, 12)}`);
  }

  function handleGroupIndexChange(groupId: string, index: number) {
    groupIndexes = { ...groupIndexes, [groupId]: index };
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
      const response = await apiFetch('/api/items/bulk_delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hashes })
      });
      if (!response.ok) throw new Error(await responseErrorText(response, `HTTP ${response.status}`));
      const result = await response.json();
      if (result.failed_cleanup_count > 0) {
        uiLog('WARNING', 'Bulk delete completed with cleanup failures', result);
        alert(`Deleted ${result.deleted_count} item(s), but ${result.failed_cleanup_count} cleanup operation(s) failed. Check App Logs.`);
      } else {
        uiLog('INFO', 'Bulk delete completed', result);
      }
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

  async function responseErrorText(response: Response, fallback: string) {
    try {
      const data = await response.json();
      return data?.detail || data?.message || fallback;
    } catch {
      return fallback;
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
    const target = event.target as HTMLElement | null;
    const editing = target?.closest('input, textarea, select, [contenteditable="true"]');
    if (!editing && (event.code === 'NumpadAdd' || event.key === '+')) {
      event.preventDefault();
      zoomIn();
      return;
    }
    if (!editing && (event.code === 'NumpadSubtract' || event.key === '-')) {
      event.preventDefault();
      zoomOut();
      return;
    }
  }

  async function refreshFromTop() {
    uiLog('INFO', 'Vault refresh from top requested', { layout: currentLayoutMode });
    if (layoutHostEl) layoutHostEl.scrollTop = 0;
    clearSelection();
    focusMode = 'normal';
    nextCursor = null;
    hasMore = false;
    items = [];
    visualHashOrder = [];
    await fetchItems(false);
    await tick();
    if (layoutHostEl) layoutHostEl.scrollTop = 0;
  }

  function handleGlobalRefresh(event: Event) {
    const detail = (event as CustomEvent).detail || {};
    if (detail.tab !== 'vault') return;
    refreshFromTop();
  }

  function handleVaultWheel(event: WheelEvent) {
    if (!event.ctrlKey) return;
    event.preventDefault();
    if (event.deltaY < 0) zoomIn();
    else if (event.deltaY > 0) zoomOut();
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
    scheduleLoadMoreCheck();
  }

  function observeLayoutHost(node: HTMLElement | null) {
    if (!node) {
      resizeObserver?.disconnect();
      resizeObserver = null;
      observedLayoutHost = null;
      vaultWidth = 0;
      return;
    }
    if (observedLayoutHost === node) return;
    resizeObserver?.disconnect();
    observedLayoutHost = node;
    vaultWidth = Math.floor(node.clientWidth);
    resizeObserver = new ResizeObserver(([entry]) => {
      vaultWidth = Math.floor(entry.contentRect.width);
      scheduleLoadMoreCheck();
    });
    resizeObserver.observe(node);
  }

  onMount(() => {
    window.addEventListener('liz:refresh', handleGlobalRefresh);
    fetchConfig();
    fetchItems();
    return () => {
      window.removeEventListener('liz:refresh', handleGlobalRefresh);
      observer?.disconnect();
      resizeObserver?.disconnect();
      if (tileSizeSaveTimer !== null) window.clearTimeout(tileSizeSaveTimer);
      if (loadMoreCheckTimer !== null) window.clearTimeout(loadMoreCheckTimer);
    };
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
  </div>
</header>

<div class="view-and-inspector">
  <div class="viewport" on:wheel={handleVaultWheel}>
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
    {:else if currentLayoutMode === 'masonry'}
      <MasonryRenderer
        groups={groupedItems}
        viewportWidth={vaultWidth}
        {tileMinWidth}
        selectedHash={selectedItem?.hash}
        {selectedHashes}
        activeIndexes={groupIndexes}
        bind:sentinelEl
        bind:hostEl={layoutHostEl}
        {isLoadingMore}
        onSelectItem={handleSelectItem}
        onIndexChange={handleGroupIndexChange}
        onVisualOrderChange={(hashes) => visualHashOrder = hashes}
      />
    {:else}
      <GridRenderer
        groups={groupedItems}
        viewportWidth={vaultWidth}
        {tileMinWidth}
        selectedHash={selectedItem?.hash}
        {selectedHashes}
        activeIndexes={groupIndexes}
        bind:sentinelEl
        bind:hostEl={layoutHostEl}
        {isLoadingMore}
        onSelectItem={handleSelectItem}
        onIndexChange={handleGroupIndexChange}
        onVisualOrderChange={(hashes) => visualHashOrder = hashes}
      />
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
  .header-actions.with-inspector { width: calc(400px - 15px); min-width: calc(400px - 15px); justify-content: flex-start; padding-left: 15px; border-left: 1px solid var(--border-dim); align-self: stretch; }
  .filter-select { background: var(--bg-input); border: 1px solid var(--border-dim); color: var(--text-main); padding: 5px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; height: 32px; }
  .view-and-inspector { flex-grow: 1; display: flex; overflow: hidden; min-width: 0; }
  .viewport { flex-grow: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; position: relative; }
  .bulk-action-bar { position: absolute; left: 50%; bottom: 18px; transform: translateX(-50%); z-index: 60; display: flex; align-items: center; gap: 10px; padding: 9px 12px; border: 1px solid var(--border-dim); border-radius: 8px; background: rgba(13, 17, 23, 0.96); box-shadow: 0 10px 30px rgba(0,0,0,0.35); }
  .selection-count { color: var(--text-bright); font-weight: 600; white-space: nowrap; }
  .initial-loading { flex-grow: 1; }
</style>
