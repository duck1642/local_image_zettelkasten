<script lang="ts">
  import { onMount } from 'svelte';
  import { apiFetch } from './api';
  import { log as uiLog } from './logger';

  type FacetKind = 'wd_tag' | 'artist' | 'platform' | 'topic';
  type FacetItem = { value: string; count: number };

  const kinds: { label: string; value: FacetKind }[] = [
    { label: 'WD Tags', value: 'wd_tag' },
    { label: 'Artists', value: 'artist' },
    { label: 'Platforms', value: 'platform' },
    { label: 'Topics', value: 'topic' }
  ];

  let activeKind: FacetKind = 'wd_tag';
  let searchText = '';
  let items: FacetItem[] = [];
  let loading = false;
  let error = '';
  let debounceTimer: number | null = null;

  async function loadFacets() {
    loading = true;
    error = '';
    try {
      const params = new URLSearchParams({
        kind: activeKind,
        q: searchText.trim(),
        limit: '200'
      });
      const response = await apiFetch(`/api/facets?${params.toString()}`);
      if (!response.ok) throw new Error(`Facet request failed: ${response.status}`);
      const data = await response.json();
      items = Array.isArray(data.items) ? data.items : [];
    } catch (err) {
      error = 'Failed to load stats';
      uiLog('ERROR', 'Failed to load facet stats', { error: err });
    } finally {
      loading = false;
    }
  }

  function setKind(kind: FacetKind) {
    activeKind = kind;
    loadFacets();
  }

  function handleSearchInput() {
    if (debounceTimer !== null) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(loadFacets, 200);
  }

  function handleGlobalRefresh(event: Event) {
    const detail = (event as CustomEvent).detail || {};
    if (detail.tab !== 'stats') return;
    uiLog('INFO', 'Stats view refresh requested', { kind: activeKind });
    loadFacets();
  }

  onMount(() => {
    window.addEventListener('liz:refresh', handleGlobalRefresh);
    loadFacets();
    return () => {
      window.removeEventListener('liz:refresh', handleGlobalRefresh);
      if (debounceTimer !== null) clearTimeout(debounceTimer);
    };
  });
</script>

<div class="stats-container">
  <div class="stats-header">
    <h3>Vault Stats</h3>
    <span class="muted">{items.length} values</span>
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

  .stats-list {
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    background: var(--bg-panel);
    overflow-y: auto;
    min-height: 0;
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
</style>
