<script lang="ts">
  import { createEventDispatcher, onDestroy, tick } from 'svelte';
  import type { ActiveSegment, FacetSuggestion, SearchFilters } from './types';
  import { emptyFilters, getActiveSegment as findActiveSegment, hasActiveFilters, parseSearchQuery } from './search';
  import { apiFetch } from './api';
  import { log as uiLog } from './logger';
  import { runtimeSessionKey } from './runtimeStore';
  import { IconClose } from './icons';

  const dispatch = createEventDispatcher();
  export let externalQuery: { id: string; query: string } | null = null;
  const availableCommands = [
    '/masonry',
    '/grid',
    '/zoom-in',
    '/zoom-out',
    '/toggle-inspector',
    '/ram-track',
    '/scan-auth',
    '/cleanup-review',
    '/sort-newest',
    '/sort-oldest',
    '/sort-artist',
    '/media-all',
    '/media-image',
    '/media-video'
  ];

  let searchQuery = '';
  let activeFilters: SearchFilters = emptyFilters();
  let showSuggestions = false;
  let activeSuggestionIndex = 0;
  let suggestions: FacetSuggestion[] = [];
  let suggestionLeft = 0;
  let searchInputEl: HTMLInputElement;
  let suggestionsListEl: HTMLUListElement;
  let searchDebounceTimer: number | null = null;
  let refreshDebounceTimer: number | null = null;
  let measureCanvas: HTMLCanvasElement | null = null;
  let measureContext: CanvasRenderingContext2D | null = null;
  let appliedExternalQueryId = '';
  let currentRuntimeSessionKey = '';

  $: if (externalQuery && externalQuery.id !== appliedExternalQueryId) {
    applyExternalQuery(externalQuery.id, externalQuery.query);
  }
  $: if ($runtimeSessionKey) {
    if (currentRuntimeSessionKey && currentRuntimeSessionKey !== $runtimeSessionKey) {
      clearSearch();
    }
    currentRuntimeSessionKey = $runtimeSessionKey;
  }

  function emitFilters(immediate = false) {
    dispatch('filtersChanged', { filters: activeFilters, immediate });
  }

  function getActiveSegment(): ActiveSegment {
    const cursor = searchInputEl?.selectionStart ?? searchQuery.length;
    return findActiveSegment(searchQuery, cursor);
  }

  function measureInputText(text: string) {
    if (!searchInputEl) return 0;
    const style = window.getComputedStyle(searchInputEl);
    if (!measureCanvas) {
      measureCanvas = document.createElement('canvas');
      measureContext = measureCanvas.getContext('2d');
    }
    if (!measureContext) return 0;
    measureContext.font = `${style.fontStyle} ${style.fontVariant} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    return measureContext.measureText(text).width;
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

  async function scrollActiveSuggestionIntoView() {
    await tick();
    const active = suggestionsListEl?.querySelector('button.active');
    active?.scrollIntoView({ block: 'nearest' });
  }

  async function refreshSuggestions() {
    await tick();
    const active = getActiveSegment();
    updateSuggestionPosition(active);

    if (active.kind === 'none') {
      clearRefreshDebounce();
      showSuggestions = false;
      suggestions = [];
      return;
    }

    if (active.kind === 'command') {
      clearRefreshDebounce();
      const query = active.value.toLowerCase();
      suggestions = availableCommands
        .filter((cmd) => cmd.slice(1).toLowerCase().startsWith(query))
        .map((value) => ({ value }));
      showSuggestions = suggestions.length > 0;
      activeSuggestionIndex = 0;
      return;
    }

    clearRefreshDebounce();
    refreshDebounceTimer = window.setTimeout(async () => {
      refreshDebounceTimer = null;
      const requestKind = active.kind;
      const requestValue = active.value;
      try {
        const params = new URLSearchParams({ kind: requestKind, q: requestValue, limit: '100' });
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
    }, 150);
  }

  function clearDebounce() {
    if (searchDebounceTimer !== null) {
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = null;
    }
  }

  function clearRefreshDebounce() {
    if (refreshDebounceTimer !== null) {
      clearTimeout(refreshDebounceTimer);
      refreshDebounceTimer = null;
    }
  }

  function applySearch(immediate = false) {
    clearDebounce();
    const text = searchQuery.trim();
    if (!text) {
      activeFilters = emptyFilters();
      emitFilters(true);
      return;
    }

    activeFilters = parseSearchQuery(text);
    if (activeFilters.command) {
      if (immediate) {
        dispatch('command', { command: activeFilters.command.toLowerCase() });
        searchQuery = '';
        activeFilters = emptyFilters();
        emitFilters(true);
      }
      return;
    }

    if (immediate) {
      emitFilters(true);
    } else {
      searchDebounceTimer = setTimeout(() => emitFilters(false), 300);
    }
  }

  function clearSearch() {
    searchQuery = '';
    activeFilters = emptyFilters();
    showSuggestions = false;
    suggestions = [];
    clearDebounce();
    clearRefreshDebounce();
    emitFilters(true);
  }

  async function applyExternalQuery(id: string, query: string) {
    appliedExternalQueryId = id;
    searchQuery = String(query || '').trim();
    showSuggestions = false;
    suggestions = [];
    clearDebounce();
    clearRefreshDebounce();
    activeFilters = parseSearchQuery(searchQuery);
    emitFilters(true);
    await tick();
    searchInputEl?.focus();
    searchInputEl?.setSelectionRange(searchQuery.length, searchQuery.length);
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
      clearRefreshDebounce();
      applySearch(true);
      return;
    }
    if (active.kind === 'none') return;

    const before = searchQuery.slice(0, active.segmentStart);
    const after = searchQuery.slice(active.segmentEnd).replace(/^;\s*/, '').replace(/^\s*/, '');
    const nextSegment = `${active.prefix}${value}; `;
    searchQuery = `${before}${nextSegment}${after}`;
    showSuggestions = false;
    suggestions = [];
    clearRefreshDebounce();
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
        scrollActiveSuggestionIntoView();
        return;
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        activeSuggestionIndex = (activeSuggestionIndex - 1 + suggestions.length) % suggestions.length;
        scrollActiveSuggestionIntoView();
        return;
      } else if (event.key === 'Enter' || event.key === 'Tab') {
        event.preventDefault();
        selectSuggestion(suggestions[activeSuggestionIndex].value);
        return;
      } else if (event.key === 'Escape') {
        showSuggestions = false;
        clearRefreshDebounce();
        return;
      }
    }

    if (event.key === 'Enter') {
      event.preventDefault();
      showSuggestions = false;
      clearRefreshDebounce();
      applySearch(true);
    }
  }

  onDestroy(() => {
    if (searchDebounceTimer !== null) clearTimeout(searchDebounceTimer);
    clearRefreshDebounce();
  });
</script>

<div class="search-container">
  <div class="search-wrapper">
    <input
      type="text"
      data-testid="vault-search-input"
      placeholder="/cmd; a:artist; p:platform; t:topic; #wd-tag"
      bind:this={searchInputEl}
      bind:value={searchQuery}
      on:input={handleSearchInput}
      on:keydown={handleSearchKeydown}
      on:click={refreshSuggestions}
    />
    {#if searchQuery.trim() || hasActiveFilters(activeFilters)}
      <button class="clear-search" on:click={clearSearch} title="Clear Search">
        <IconClose size={11} />
      </button>
    {/if}
    {#if showSuggestions && suggestions.length > 0}
      <ul bind:this={suggestionsListEl} class="suggestions-dropdown" style={`left: ${suggestionLeft}px;`}>
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

<style>
  .search-container { flex-grow: 1; }
  .search-wrapper { position: relative; width: 100%; display: flex; align-items: center; }
  .search-wrapper input { width: 100%; max-width: 100%; padding-right: 35px; }
  .suggestions-dropdown { position: absolute; top: 100%; width: 300px; max-width: calc(100% - 10px); max-height: min(520px, calc(100vh - 110px)); overflow-y: auto; background: var(--bg-panel); border: 1px solid var(--border-dim); border-radius: 6px; margin-top: 5px; padding: 5px 0; list-style: none; z-index: 1000; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
  .suggestions-dropdown li { padding: 0; }
  .suggestions-dropdown button { width: 100%; padding: 8px 15px; border: 0; border-radius: 0; background: transparent; color: var(--text-main); text-align: left; font-size: 13px; cursor: pointer; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .suggestions-dropdown button:hover, .suggestions-dropdown button.active { background: var(--accent-primary); color: white; }
  .suggestion-value { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .suggestion-count { color: var(--text-muted); font-variant-numeric: tabular-nums; }
  .suggestions-dropdown button:hover .suggestion-count, .suggestions-dropdown button.active .suggestion-count { color: rgba(255,255,255,0.8); }
  .clear-search { position: absolute; right: 8px; background: transparent; border: none; color: var(--text-muted); cursor: pointer; padding: 4px; display: inline-flex; align-items: center; justify-content: center; }
  .clear-search:hover { color: var(--accent-danger); background: transparent; border: none; }
</style>
