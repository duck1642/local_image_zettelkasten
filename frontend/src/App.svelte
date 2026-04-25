<script lang="ts">
  import { onMount } from 'svelte';
  import type { VaultItem } from './lib/types';
  import ItemTile from './lib/ItemTile.svelte';
  import Inspector from './lib/Inspector.svelte';
  import LogsView from './lib/LogsView.svelte';

  let items: VaultItem[] = [];
  let stats = { total_items: 0 };
  let loading = true;
  let selectedItem: VaultItem | null = null;
  let activeTab: 'vault' | 'logs' = 'vault';

  async function fetchItems() {
    try {
      const response = await fetch('http://localhost:8000/api/items');
      items = await response.json();
      
      const statsRes = await fetch('http://localhost:8000/api/stats');
      stats = await statsRes.json();
    } catch (error) {
      console.error('Failed to fetch items:', error);
    } finally {
      loading = false;
    }
  }

  function handleSelectItem(item: VaultItem) {
    selectedItem = item;
  }

  function handleUpdate(event: CustomEvent) {
    const { hash, artist, source_url, platform } = event.detail;
    items = items.map(i => {
      if (i.hash === hash) {
        return { ...i, artist, source_url, platform };
      }
      return i;
    });
    if (selectedItem && selectedItem.hash === hash) {
      selectedItem = { ...selectedItem, artist, source_url, platform };
    }
  }

  onMount(() => {
    fetchItems();
  });
</script>

<main>
  <header>
    <div class="logo">LIZ <span>Management Center</span></div>
    
    <nav class="tabs">
      <button class:active={activeTab === 'vault'} on:click={() => activeTab = 'vault'}>Vault</button>
      <button class:active={activeTab === 'logs'} on:click={() => activeTab = 'logs'}>Logs</button>
    </nav>

    <div class="stats">
      {stats.total_items} items
      <button class="refresh-btn" title="Refresh Data" on:click={fetchItems}>🔄</button>
    </div>
    
    <div class="search-bar">
      <input type="text" placeholder="Search (a:artist, @platform, #tag)..." />
    </div>
  </header>

  <div class="main-layout">
    <div class="view-container">
      {#if activeTab === 'vault'}
        {#if loading}
          <div class="loading">Loading your vault...</div>
        {:else}
          <div class="content">
            <div class="masonry">
              {#each items as item (item.hash)}
                <div 
                  class="tile-wrapper" 
                  class:selected={selectedItem?.hash === item.hash}
                  on:click={() => handleSelectItem(item)}
                >
                  <ItemTile {item} />
                </div>
              {/each}
            </div>
          </div>
        {/if}
      {:else}
        <LogsView />
      {/if}
    </div>

    {#if activeTab === 'vault'}
      <Inspector 
          item={selectedItem} 
          on:close={() => selectedItem = null}
          on:updated={handleUpdate}
      />
    {/if}
  </div>
</main>

<style>
  main {
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: var(--bg-main);
  }

  header {
    height: 60px;
    background: var(--bg-panel);
    border-bottom: 1px solid var(--border-dim);
    display: flex;
    align-items: center;
    padding: 0 20px;
    gap: 30px;
    z-index: 10;
  }

  .logo {
    font-weight: bold;
    font-size: 18px;
    color: var(--text-bright);
    flex-shrink: 0;
  }

  .logo span {
    font-weight: normal;
    color: var(--text-muted);
    font-size: 14px;
    margin-left: 5px;
  }

  .tabs {
    display: flex;
    gap: 5px;
  }

  .tabs button {
    background: transparent;
    border: none;
    color: var(--text-muted);
    padding: 8px 16px;
    font-weight: 600;
  }

  .tabs button.active {
    color: var(--accent-primary);
    border-bottom: 2px solid var(--accent-primary);
    border-radius: 0;
  }

  .stats {
    color: var(--text-muted);
    font-size: 12px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .refresh-btn {
    background: transparent;
    border: 1px solid var(--border-dim);
    padding: 4px 8px;
    font-size: 12px;
    border-radius: 4px;
    color: var(--text-muted);
  }

  .refresh-btn:hover {
    border-color: var(--accent-primary);
    color: var(--text-bright);
  }

  .search-bar {
    flex-grow: 1;
  }

  .search-bar input {
    width: 100%;
    max-width: 400px;
  }

  .main-layout {
    flex-grow: 1;
    display: flex;
    overflow: hidden;
  }

  .view-container {
    flex-grow: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .loading {
    flex-grow: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
  }

  .content {
    flex-grow: 1;
    overflow-y: auto;
    padding: 20px;
  }

  .masonry {
    column-count: 5;
    column-gap: 15px;
  }

  .tile-wrapper {
    cursor: pointer;
    border-radius: 10px;
    transition: all 0.2s;
    border: 2px solid transparent;
    margin-bottom: 15px;
    break-inside: avoid;
  }

  .tile-wrapper:hover {
    transform: translateY(-2px);
  }

  .tile-wrapper.selected {
    border-color: var(--accent-primary);
    background: rgba(31, 111, 235, 0.1);
  }

  @media (max-width: 1600px) { .masonry { column-count: 4; } }
  @media (max-width: 1200px) { .masonry { column-count: 3; } }
  @media (max-width: 800px) { .masonry { column-count: 2; } }
  @media (max-width: 500px) { .masonry { column-count: 1; } }
</style>
