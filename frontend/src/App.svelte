<script lang="ts">
  import { onMount } from 'svelte';
  import Ingestion from './lib/Ingestion.svelte';
  import LogsView from './lib/LogsView.svelte';
  import ReviewView from './lib/ReviewView.svelte';
  import SettingsView from './lib/SettingsView.svelte';
  import StatsView from './lib/StatsView.svelte';
  import VaultView from './lib/VaultView.svelte';
  import { apiFetch } from './lib/api';
  import { log as uiLog } from './lib/logger';

  type AppTab = 'vault' | 'logs' | 'ingest' | 'review' | 'stats' | 'settings';

  let activeTab: AppTab = 'vault';
  let queueStats = { normal: 0, force: 0, failed: 0 };
  let reviewCount = 0;
  let vaultStatus = { totalItems: 0, groups: 0, hasMore: false };

  async function fetchSecondaryStats() {
    try {
      const qStatsRes = await apiFetch('/api/queue-stats');
      queueStats = await qStatsRes.json();
      const reviewRes = await apiFetch('/api/review');
      const reviewData = await reviewRes.json();
      reviewCount = reviewData.length;
    } catch (error) {
      uiLog('ERROR', 'Failed to fetch sidebar stats', { error });
    }
  }

  function handleVaultStatus(event: CustomEvent) {
    vaultStatus = event.detail;
  }

  function navigate(event: CustomEvent<AppTab>) {
    activeTab = event.detail;
  }

  onMount(() => {
    uiLog('INFO', 'Svelte UI initialized and mounted');
    fetchSecondaryStats();
    const interval = setInterval(fetchSecondaryStats, 5000);
    return () => clearInterval(interval);
  });
</script>

<div class="root-container">
  <div class="app-container">
    <aside class="sidebar">
      <div class="nav-group">
        <button class:active={activeTab === 'vault'} on:click={() => activeTab = 'vault'}>Vault</button>
        <button class:active={activeTab === 'ingest'} on:click={() => activeTab = 'ingest'}>
          Ingestion {#if (queueStats.normal + queueStats.force) > 0}<span class="badge">{queueStats.normal + queueStats.force}</span>{/if}
        </button>
        <button class:active={activeTab === 'review'} on:click={() => activeTab = 'review'}>
          Review {#if reviewCount > 0}<span class="badge warn">{reviewCount}</span>{/if}
        </button>
        <button class:active={activeTab === 'stats'} on:click={() => activeTab = 'stats'}>Stats</button>
        <button class:active={activeTab === 'settings'} on:click={() => activeTab = 'settings'}>Settings</button>
        <button class:active={activeTab === 'logs'} on:click={() => activeTab = 'logs'}>App Logs</button>
      </div>
    </aside>

    <main class="main-content">
      <div class:hidden={activeTab !== 'vault'} class="tab-panel">
        <VaultView on:status={handleVaultStatus} on:navigate={navigate} />
      </div>
      {#if activeTab === 'review'}
        <div class="view-shell"><ReviewView /></div>
      {:else if activeTab === 'ingest'}
        <div class="view-shell"><Ingestion /></div>
      {:else if activeTab === 'stats'}
        <div class="view-shell"><StatsView /></div>
      {:else if activeTab === 'settings'}
        <div class="view-shell"><SettingsView /></div>
      {:else if activeTab === 'logs'}
        <div class="view-shell"><LogsView /></div>
      {/if}
    </main>
  </div>

  <footer class="bottom-status">
    {#if activeTab === 'vault'}
      <span class="status-left">Total Items: {vaultStatus.totalItems} | DB: WAL | LIZ Tauri</span>
      <span class="status-right">Showing {vaultStatus.groups} groups{vaultStatus.hasMore ? ' (more available)' : ''}</span>
    {:else if activeTab === 'ingest'}
      <span class="status-left">Ingestion | Normal: {queueStats.normal} | Force: {queueStats.force} | Failed: {queueStats.failed}</span>
      <span class="status-right">LIZ Tauri</span>
    {:else if activeTab === 'review'}
      <span class="status-left">Review | Pending: {reviewCount}</span>
      <span class="status-right">LIZ Tauri</span>
    {:else}
      <span class="status-left">{activeTab === 'logs' ? 'App Logs' : activeTab === 'stats' ? 'Stats' : 'Settings'}</span>
      <span class="status-right">LIZ Tauri</span>
    {/if}
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
  .tab-panel { flex-grow: 1; display: flex; flex-direction: column; overflow: hidden; }
  .tab-panel.hidden { display: none; }
  .view-shell { flex-grow: 1; display: flex; flex-direction: column; overflow: hidden; }
  .bottom-status { height: 25px; background: #010409; border-top: 1px solid var(--border-dim); padding: 0; display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: var(--text-muted); flex-shrink: 0; z-index: 200; width: 100%; box-sizing: border-box; }
  .status-left { padding-left: 15px; }
  .status-right { padding-right: 15px; }
  .badge { background: var(--accent-primary); color: white; font-size: 10px; padding: 1px 5px; border-radius: 10px; margin-left: 3px; }
  .badge.warn { background: var(--accent-warning); }
</style>
