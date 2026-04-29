<script lang="ts">
  import { onMount, tick } from 'svelte';
  import type { VaultItem } from './lib/types';
  import Inspector from './lib/Inspector.svelte';
  import LogsView from './lib/LogsView.svelte';
  import Ingestion from './lib/Ingestion.svelte';
  import ReviewView from './lib/ReviewView.svelte';
  import SettingsView from './lib/SettingsView.svelte';
  import StatsView from './lib/StatsView.svelte';
  import VaultGroupTile from './lib/VaultGroupTile.svelte';
  import MediaFocus from './lib/MediaFocus.svelte';
  import { log as uiLog } from './lib/logger';
  import { apiFetch } from './lib/api';

  let items: VaultItem[] = [];
  let stats = { total_items: 0 };
  let queueStats = { normal: 0, force: 0, failed: 0 };
  let reviewCount = 0;
  let isSearching = true;
  let isLoadingMore = false;
  let selectedItem: VaultItem | null = null;
  let selectedGroup: { id: string, items: VaultItem[] } | null = null;
  let activeTab: 'vault' | 'logs' | 'ingest' | 'review' | 'stats' | 'settings' = 'vault';
  let searchQuery = '';
  let showSuggestions = false;
  let activeSuggestionIndex = 0;
  let suggestions: FacetSuggestion[] = [];
  let suggestionLeft = 0;
  let searchInputEl: HTMLInputElement;
  const availableCommands = ['>grid', '>masonry'];
  
  let focusMode: 'normal' | 'wide' | 'fullscreen' = 'normal';
  let focusStartTime = 0;
  let currentLayout: 'masonry' | 'grid' = 'masonry';
  let configCache: any = null;

  let currentSort = 'newest';
  let currentMediaType = 'all';
  type SuggestionKind = 'none' | 'command' | 'artist' | 'platform' | 'topic' | 'wd_tag';
  type FacetSuggestion = { value: string; count?: number };
  type SearchFilters = { artists: string[]; platforms: string[]; topics: string[]; wd_tags: string[]; text_terms: string[]; command?: string };
  type ActiveSegment = { kind: SuggestionKind; prefix: string; value: string; segmentStart: number; segmentEnd: number; valueStart: number };
  let activeFilters: SearchFilters = emptyFilters();
  let searchDebounceTimer: number | null = null;

  let nextCursor: string | null = null;
  let hasMore = false;
  let sentinelEl: HTMLElement | null = null;
  let observer: IntersectionObserver | null = null;
  let observedSentinel: HTMLElement | null = null;
  let observedLayout = '';

  async function fetchConfig() {
    try {
      const res = await apiFetch('/api/config');
      configCache = await res.json();
      if (configCache?.ui?.vault_layout) {
          currentLayout = configCache.ui.vault_layout;
      }
    } catch(e) {}
  }

  $: groupedItems = (() => {
    const groups: { [key: string]: VaultItem[] } = {};
    const orderedKeys: string[] = [];
    items.forEach(item => {
      const key = item.source_url && item.source_url.trim() !== '' ? item.source_url : `single-${item.hash}`;
      if (!groups[key]) { groups[key] = []; orderedKeys.push(key); }
      groups[key].push(item);
    });
    return orderedKeys.map(key => ({ id: key, items: groups[key] }));
  })();

  function emptyFilters(): SearchFilters {
    return { artists: [], platforms: [], topics: [], wd_tags: [], text_terms: [] };
  }

  function hasActiveFilters(filters: SearchFilters) {
    return Boolean(filters.command || filters.artists.length || filters.platforms.length || filters.topics.length || filters.wd_tags.length || filters.text_terms.length);
  }

  function parseSearchQuery(query: string): SearchFilters {
    const filters = emptyFilters();
    const segments = query.split(';').map(segment => segment.trim()).filter(Boolean);

    for (const segment of segments) {
      if (segment.startsWith('a:')) {
        const value = segment.slice(2).trim();
        if (value) filters.artists.push(value);
      } else if (segment.startsWith('@')) {
        const value = segment.slice(1).trim();
        if (value) filters.platforms.push(value);
      } else if (segment.startsWith('#')) {
        const value = segment.slice(1).trim();
        if (value) filters.topics.push(value);
      } else if (segment.startsWith('*')) {
        const value = segment.slice(1).trim();
        if (value) filters.wd_tags.push(value);
      } else if (segment.startsWith('>')) {
        const value = segment.slice(1).trim();
        if (value) filters.command = value;
      } else {
        filters.text_terms.push(...segment.split(/\s+/).map(term => term.trim()).filter(Boolean));
      }
    }

    return filters;
  }

  async function fetchItems(append = false) {
    if (!append) { nextCursor = null; isSearching = true; }
    else { isLoadingMore = true; }
    try {
      const params = new URLSearchParams({
        sort: currentSort,
        media_type: currentMediaType,
        limit: '50'
      });
      if (append && nextCursor) params.set('cursor', nextCursor);
      activeFilters.artists.forEach(value => params.append('artist', value));
      activeFilters.platforms.forEach(value => params.append('platform', value));
      activeFilters.topics.forEach(value => params.append('topic', value));
      activeFilters.wd_tags.forEach(value => params.append('wd_tag', value));
      activeFilters.text_terms.forEach(value => params.append('text', value));

      const response = await apiFetch(`/api/items?${params.toString()}`);
      const data = await response.json();
      const newItems: VaultItem[] = Array.isArray(data.items) ? data.items : [];
      items = append ? [...items, ...newItems] : newItems;
      nextCursor = data.next_cursor || null;
      hasMore = data.has_more || false;

      const statsRes = await apiFetch('/api/stats');
      stats = await statsRes.json();
      await fetchSecondaryStats();
    } catch (error) { uiLog('ERROR', 'Failed to fetch items', { error });
    } finally { 
      if (!append) { isSearching = false; }
      else { isLoadingMore = false; }
    }
  }

  function loadMore() {
    if (hasMore && !isSearching && !isLoadingMore) fetchItems(true);
  }

  function applySearch(immediate: boolean = false) {
    if (searchDebounceTimer !== null) {
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = null;
    }
    const text = searchQuery.trim();
    if (!text) {
      activeFilters = emptyFilters();
      fetchItems();
      return;
    }
    activeFilters = parseSearchQuery(text);

    // Handle commands ONLY when the user hits Enter (immediate = true)
    if ('command' in activeFilters) {
        if (immediate) {
            const cmd = (activeFilters.command || '').toLowerCase();
            if (cmd === 'grid' || cmd === 'masonry') {
                currentLayout = cmd;
                if (configCache) {
                    if (!configCache.ui) configCache.ui = {};
                    configCache.ui.vault_layout = currentLayout;
                    apiFetch('/api/config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(configCache)
                    }).catch(e => console.error('Failed to save command-triggered layout change:', e));
                }
            }
            searchQuery = '';
            activeFilters = emptyFilters();
            fetchItems();
        }
        // If they are just typing a command, do NOT trigger the live search debounce
        return;
    }

    if (immediate) {
      fetchItems();
    } else {
      searchDebounceTimer = setTimeout(() => fetchItems(), 300);
    }
  }

  function clearSearch() {
    searchQuery = '';
    activeFilters = emptyFilters();
    showSuggestions = false;
    suggestions = [];
    if (searchDebounceTimer !== null) {
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = null;
    }
    fetchItems();
  }

  function getActiveSegment(): ActiveSegment {
    const cursor = searchInputEl?.selectionStart ?? searchQuery.length;
    const segmentStart = searchQuery.lastIndexOf(';', Math.max(0, cursor - 1)) + 1;
    const nextSeparator = searchQuery.indexOf(';', cursor);
    const segmentEnd = nextSeparator === -1 ? searchQuery.length : nextSeparator;
    const rawSegment = searchQuery.slice(segmentStart, segmentEnd);
    const leadingLength = rawSegment.length - rawSegment.trimStart().length;
    const contentStart = segmentStart + leadingLength;
    const content = searchQuery.slice(contentStart, segmentEnd);

    if (content.startsWith('a:')) return { kind: 'artist', prefix: 'a:', value: searchQuery.slice(contentStart + 2, cursor).trimStart(), segmentStart: contentStart, segmentEnd, valueStart: contentStart + 2 };
    if (content.startsWith('@')) return { kind: 'platform', prefix: '@', value: searchQuery.slice(contentStart + 1, cursor).trimStart(), segmentStart: contentStart, segmentEnd, valueStart: contentStart + 1 };
    if (content.startsWith('#')) return { kind: 'topic', prefix: '#', value: searchQuery.slice(contentStart + 1, cursor).trimStart(), segmentStart: contentStart, segmentEnd, valueStart: contentStart + 1 };
    if (content.startsWith('*')) return { kind: 'wd_tag', prefix: '*', value: searchQuery.slice(contentStart + 1, cursor).trimStart(), segmentStart: contentStart, segmentEnd, valueStart: contentStart + 1 };
    if (content.startsWith('>')) return { kind: 'command', prefix: '>', value: searchQuery.slice(contentStart + 1, cursor).trimStart(), segmentStart: contentStart, segmentEnd, valueStart: contentStart + 1 };
    return { kind: 'none', prefix: '', value: '', segmentStart: contentStart, segmentEnd, valueStart: contentStart };
  }

  function measureInputText(text: string) {
    if (!searchInputEl) return 0;
    const style = window.getComputedStyle(searchInputEl);
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    if (!context) return 0;
    context.font = `${style.fontStyle} ${style.fontVariant} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    return context.measureText(text).width;
  }

  function updateSuggestionPosition(active: ActiveSegment) {
    if (!searchInputEl) return;
    const style = window.getComputedStyle(searchInputEl);
    const paddingLeft = parseFloat(style.paddingLeft || '0');
    const before = searchQuery.slice(0, active.segmentStart);
    const left = paddingLeft + measureInputText(before) - searchInputEl.scrollLeft;
    const maxLeft = Math.max(0, searchInputEl.clientWidth - 320);
    suggestionLeft = Math.max(0, Math.min(left, maxLeft));
  }

  async function refreshSuggestions() {
    await tick();
    const active = getActiveSegment();
    updateSuggestionPosition(active);

    if (active.kind === 'none') {
      showSuggestions = false;
      suggestions = [];
      return;
    }

    if (active.kind === 'command') {
      const query = active.value.toLowerCase();
      suggestions = availableCommands
        .filter(cmd => cmd.toLowerCase().startsWith(`>${query}`) || cmd.toLowerCase().slice(1).startsWith(query))
        .map(value => ({ value }));
      showSuggestions = suggestions.length > 0;
      activeSuggestionIndex = 0;
      return;
    }

    const requestKind = active.kind;
    const requestValue = active.value;
    try {
      const params = new URLSearchParams({ kind: requestKind, q: requestValue });
      const response = await apiFetch(`/api/search/suggestions?${params.toString()}`);
      const data = await response.json();
      const latest = getActiveSegment();
      if (latest.kind !== requestKind || latest.value !== requestValue) return;
      if (Array.isArray(data.items)) {
        suggestions = data.items
          .filter((item: any) => item && item.value)
          .map((item: any) => ({ value: String(item.value), count: Number(item.count || 0) }));
      } else {
        suggestions = Array.isArray(data.suggestions) ? data.suggestions.map((value: string) => ({ value })) : [];
      }
      showSuggestions = suggestions.length > 0;
      activeSuggestionIndex = 0;
      updateSuggestionPosition(latest);
    } catch (error) {
      uiLog('ERROR', 'Failed to fetch search suggestions', { error });
      showSuggestions = false;
      suggestions = [];
    }
  }

  function handleSearchInput() {
    refreshSuggestions();
    applySearch(false);
  }

  async function selectSuggestion(value: string) {
    const active = getActiveSegment();
    if (active.kind === 'command') {
      searchQuery = value;
      showSuggestions = false;
      suggestions = [];
      applySearch(true);
      activeTab = 'vault';
      return;
    }
    if (active.kind === 'none') return;

    const before = searchQuery.slice(0, active.segmentStart);
    const after = searchQuery.slice(active.segmentEnd).replace(/^;\s*/, '').replace(/^\s*/, '');
    const nextSegment = `${active.prefix}${value}; `;
    searchQuery = `${before}${nextSegment}${after}`;
    showSuggestions = false;
    suggestions = [];
    activeFilters = parseSearchQuery(searchQuery);
    applySearch(false);
    await tick();
    const position = before.length + nextSegment.length;
    searchInputEl?.setSelectionRange(position, position);
    searchInputEl?.focus();
  }

  function handleSearchKeydown(event: KeyboardEvent) {
    if (showSuggestions && suggestions.length > 0) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        activeSuggestionIndex = (activeSuggestionIndex + 1) % suggestions.length;
        return;
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        activeSuggestionIndex = (activeSuggestionIndex - 1 + suggestions.length) % suggestions.length;
        return;
      } else if (event.key === 'Enter' || event.key === 'Tab') {
        event.preventDefault();
        selectSuggestion(suggestions[activeSuggestionIndex].value);
        return;
      } else if (event.key === 'Escape') {
        showSuggestions = false;
        return;
      }
    }

    if (event.key === 'Enter') {
      event.preventDefault();
      showSuggestions = false;
      applySearch(true);
      activeTab = 'vault';
    }
  }

  async function fetchSecondaryStats() {
    try {
        const qStatsRes = await apiFetch('/api/queue-stats');
        queueStats = await qStatsRes.json();
        const reviewRes = await apiFetch('/api/review');
        const reviewData = await reviewRes.json();
        reviewCount = reviewData.length;
    } catch (e) { }
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

  function handleGlobalKeydown(e: KeyboardEvent) {
      if (e.key === 'F5') {
          if (e.ctrlKey) {
              uiLog('INFO', 'Ctrl+F5 pressed: Reloading full app');
              window.location.reload();
          } else {
              e.preventDefault();
              uiLog('INFO', 'F5 pressed: Refreshing database/items');
              fetchItems();
          }
      }
  }

  function attachInfiniteScroll(node: HTMLElement | null, layout: string, tab: string) {
    if (!node || tab !== 'vault') {
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

  $: attachInfiniteScroll(sentinelEl, currentLayout, activeTab);

  onMount(() => {
    uiLog('INFO', 'Svelte UI initialized and mounted');
    fetchConfig();
    fetchItems();
    const interval = setInterval(fetchSecondaryStats, 5000);

    return () => { clearInterval(interval); observer?.disconnect(); };
  });
</script>

<svelte:window on:keydown={handleGlobalKeydown} />

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
      <button class:active={activeTab === 'stats'} on:click={() => activeTab = 'stats'}>Stats</button>
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
            placeholder="a: artist; # topic; * wd-tag; @ platform; > cmd"
            bind:this={searchInputEl}
            bind:value={searchQuery}
            on:input={handleSearchInput}
            on:keydown={handleSearchKeydown}
            on:click={refreshSuggestions}
          />
          {#if searchQuery.trim() || hasActiveFilters(activeFilters)}
              <button class="clear-search" on:click={clearSearch} title="Clear Search">✖</button>
          {/if}
          {#if showSuggestions && suggestions.length > 0}
            <ul class="suggestions-dropdown" style={`left: ${suggestionLeft}px;`}>
              {#each suggestions as suggestion, i}
                <li>
                  <button type="button" class:active={i === activeSuggestionIndex} on:click={() => selectSuggestion(suggestion.value)}>
                    <span class="suggestion-value">{suggestion.value}</span>
                    {#if suggestion.count}
                      <span class="suggestion-count">{suggestion.count}</span>
                    {/if}
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      </div>
      <div class="header-actions" class:with-inspector={activeTab === 'vault'}>
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

        <button class="primary" on:click={() => activeTab = 'ingest'}>Add Files</button>
      </div>
    </header>

    <div class="view-and-inspector">
      <div class="viewport">
        {#if activeTab === 'vault'}
          {#if isSearching && items.length === 0}
            <!-- Silently loading initial items -->
          {:else if currentLayout === 'masonry'}
            <div class="masonry-scroll">
              <div class="vault-layout masonry">
                {#each groupedItems as group (group.id)}
                  <VaultGroupTile 
                    {group} 
                    layout="masonry"
                    selectedHash={selectedItem?.hash}
                    on:select={(e) => handleSelectItem(e.detail, group)} 
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
                    on:select={(e) => handleSelectItem(e.detail, group)} 
                  />
                {/each}
              </div>
              <div bind:this={sentinelEl} class="scroll-sentinel"></div>
              {#if isLoadingMore}
                <div class="loading-more">Loading more...</div>
              {/if}
            </div>
          {/if}
        {:else if activeTab === 'review'}
          <ReviewView />
        {:else if activeTab === 'ingest'}
          <Ingestion />
        {:else if activeTab === 'stats'}
          <StatsView />
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
        on:switchMode={(e) => { focusMode = e.detail; }}
    />
  {/if}
  </div>

  <footer class="bottom-status">
      <span class="status-left">Total Items: {stats.total_items} | DB: WAL | LIZ Tauri</span>
      <span class="status-right">Showing {groupedItems.length} groups{hasMore ? ' (more available)' : ''}</span>
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
  .suggestions-dropdown { position: absolute; top: 100%; width: 300px; max-width: calc(100% - 10px); background: var(--bg-panel); border: 1px solid var(--border-dim); border-radius: 6px; margin-top: 5px; padding: 5px 0; list-style: none; z-index: 1000; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
  .suggestions-dropdown li { padding: 0; }
  .suggestions-dropdown button { width: 100%; padding: 8px 15px; border: 0; border-radius: 0; background: transparent; color: var(--text-main); text-align: left; font-size: 13px; cursor: pointer; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .suggestions-dropdown button:hover, .suggestions-dropdown button.active { background: var(--accent-primary); color: white; }
  .suggestion-value { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .suggestion-count { color: var(--text-muted); font-variant-numeric: tabular-nums; }
  .suggestions-dropdown button:hover .suggestion-count, .suggestions-dropdown button.active .suggestion-count { color: rgba(255,255,255,0.8); }
  .clear-search { position: absolute; right: 8px; background: transparent; border: none; color: var(--text-muted); font-size: 14px; cursor: pointer; padding: 4px; }
  .clear-search:hover { color: var(--accent-danger); background: transparent; border: none; }
  .header-actions { display: flex; align-items: center; gap: 10px; }
  .header-actions.with-inspector { width: calc(400px - 15px); min-width: calc(400px - 15px); justify-content: flex-start; padding-left: 15px; border-left: 1px solid var(--border-dim); }
  .filter-select { background: var(--bg-input); border: 1px solid var(--border-dim); color: var(--text-main); padding: 5px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; height: 32px; }
  .view-and-inspector { flex-grow: 1; display: flex; overflow: hidden; }
  .viewport { flex-grow: 1; display: flex; flex-direction: column; overflow: hidden; }
  .grid-scroll { flex-grow: 1; overflow-y: auto; padding: 15px; }
  .masonry-scroll { flex-grow: 1; overflow-y: auto; padding: 15px; }
  .vault-layout.masonry {
      column-count: 5;
      column-gap: 12px;
  }
  .vault-layout.grid { 
      display: grid; 
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); 
      gap: 15px; 
      align-items: stretch;
  }
  .scroll-sentinel { height: 1px; }
  .loading-more { text-align: center; padding: 15px; color: var(--text-muted); font-size: 12px; }
  .bottom-status { height: 25px; background: #010409; border-top: 1px solid var(--border-dim); padding: 0; display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: var(--text-muted); flex-shrink: 0; z-index: 200; width: 100%; box-sizing: border-box; }
  .status-left { padding-left: 15px; }
  .status-right { padding-right: 15px; }
  .badge { background: var(--accent-primary); color: white; font-size: 10px; padding: 1px 5px; border-radius: 10px; margin-left: 3px; }
  .badge.warn { background: var(--accent-warning); }
</style>
