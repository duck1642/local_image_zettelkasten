<script lang="ts">
  import { onMount } from 'svelte';
  import Ingestion from './lib/Ingestion.svelte';
  import LogsView from './lib/LogsView.svelte';
  import ReviewView from './lib/ReviewView.svelte';
  import SettingsView from './lib/SettingsView.svelte';
  import StatsView from './lib/StatsView.svelte';
  import VaultView from './lib/VaultView.svelte';
  import { log as uiLog } from './lib/logger';
  import { ramStats, startRamTracker } from './lib/ramStore';
  import { queueStats, reviewCount, reviewStats, startSharedStatsPolling } from './lib/statsStore';
  import { apiFetch } from './lib/api';

  type AppTab = 'vault' | 'logs' | 'ingest' | 'review' | 'stats' | 'settings';

  let activeTab: AppTab = 'vault';
  let vaultStatus = { totalItems: 0, groups: 0, hasMore: false, layoutMode: 'masonry' };
  let forceClosing = false;
  let closeFlowRunning = false;

  function handleVaultStatus(event: CustomEvent) {
    vaultStatus = event.detail;
  }

  function handleGlobalKeydown(event: KeyboardEvent) {
    if (event.key !== 'F5') return;
    event.preventDefault();
    if (event.ctrlKey) {
      uiLog('INFO', 'Ctrl+F5 pressed: reloading full app');
      window.location.reload();
      return;
    }
    uiLog('INFO', 'F5 pressed: refreshing active view', { tab: activeTab });
    window.dispatchEvent(new CustomEvent('lmz:refresh', { detail: { tab: activeTab } }));
  }

  function ramStatusText(stats: any) {
    if (stats.error) return 'RAM: unavailable';
    if (stats.backendMb === null) return 'RAM: loading';
    if (stats.frontendMb !== null && stats.totalMb !== null) {
      return `RAM: backend ${stats.backendMb} MB | frontend ${stats.frontendMb} MB | total ${stats.totalMb} MB`;
    }
    return `RAM: backend ${stats.backendMb} MB`;
  }

  onMount(() => {
    uiLog('INFO', 'Svelte UI initialized and mounted');
    const stopStats = startSharedStatsPolling();
    const stopRam = startRamTracker();
    let unlistenClose: (() => void) | null = null;

    (async () => {
      try {
        const { getCurrentWindow } = await import('@tauri-apps/api/window');
        const appWindow = getCurrentWindow();
        unlistenClose = await appWindow.onCloseRequested(async (event) => {
          if (forceClosing) return;
          event.preventDefault();
          if (closeFlowRunning) return;

          async function closeNow() {
            forceClosing = true;
            await appWindow.destroy();
          }

          async function fetchRuntimeStatus() {
            const controller = new AbortController();
            const timeout = window.setTimeout(() => controller.abort(), 2500);
            try {
              const statusRes = await apiFetch('/api/ingest/runtime-status', { signal: controller.signal });
              if (!statusRes.ok) return null;
              return await statusRes.json();
            } finally {
              window.clearTimeout(timeout);
            }
          }

          try {
            const status = await fetchRuntimeStatus();
            if (!status?.any_running) {
              await closeNow();
              return;
            }

            const shouldStop = confirm('Ingestion is running.\n\nStop after current item and exit?');
            if (!shouldStop) return;

            closeFlowRunning = true;
            await apiFetch('/api/ingest/stop-after-current', { method: 'POST' });

            const startedAt = Date.now();
            while (Date.now() - startedAt < 10 * 60 * 1000) {
              await new Promise((resolve) => setTimeout(resolve, 900));
              const pollRes = await apiFetch('/api/ingest/runtime-status');
              if (!pollRes.ok) continue;
              const poll = await pollRes.json();
              if (!poll?.any_running) {
                await closeNow();
                return;
              }
            }
            closeFlowRunning = false;
            alert('Timed out waiting for ingestion to stop. Try again in a few moments.');
          } catch (error) {
            closeFlowRunning = false;
            uiLog('WARNING', 'Close guard failed open', { error: String(error) });
            await closeNow();
          }
        });
      } catch {
        // non-tauri context
      }
    })();

    return () => {
      stopStats();
      stopRam();
      if (unlistenClose) unlistenClose();
    };
  });
</script>

<svelte:window on:keydown={handleGlobalKeydown} />

<div class="root-container">
  <div class="app-container">
    <aside class="sidebar">
      <div class="nav-group">
        <button class:active={activeTab === 'vault'} on:click={() => activeTab = 'vault'}>Vault</button>
        <button class:active={activeTab === 'ingest'} on:click={() => activeTab = 'ingest'}>
          Ingestion {#if ($queueStats.normal + $queueStats.force) > 0}<span class="badge">{$queueStats.normal + $queueStats.force}</span>{/if}
        </button>
        <button class:active={activeTab === 'review'} on:click={() => activeTab = 'review'}>
          Review {#if $reviewCount > 0}<span class="badge warn">{$reviewCount}</span>{/if}
        </button>
        <button class:active={activeTab === 'stats'} on:click={() => activeTab = 'stats'}>Stats</button>
        <button class:active={activeTab === 'settings'} on:click={() => activeTab = 'settings'}>Settings</button>
        <button class:active={activeTab === 'logs'} on:click={() => activeTab = 'logs'}>App Logs</button>
      </div>
    </aside>

    <main class="main-content">
      <!-- VaultView stays mounted across tab switches to preserve scroll position, selection, and loaded items.
           Its IntersectionObserver/ResizeObserver are idle when display:none, so the cost is negligible.
           Other tabs use {#if} since they can re-fetch on demand. -->
      <div class:hidden={activeTab !== 'vault'} class="tab-panel">
        <VaultView on:status={handleVaultStatus} />
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
      <span class="status-left">Total Items: {vaultStatus.totalItems} | View: {vaultStatus.layoutMode} | LMZ Tauri</span>
      <span class="status-right">
        {#if $ramStats.enabled}<span class="ram-status">{ramStatusText($ramStats)}</span>{/if}
        <span>Showing {vaultStatus.groups} groups{vaultStatus.hasMore ? ' (more available)' : ''}</span>
      </span>
    {:else if activeTab === 'ingest'}
      <span class="status-left">Ingestion | Normal: {$queueStats.normal} | Force: {$queueStats.force} | Failed: {$queueStats.failed}</span>
      <span class="status-right">{#if $ramStats.enabled}<span class="ram-status">{ramStatusText($ramStats)}</span>{/if}<span>LMZ Tauri</span></span>
    {:else if activeTab === 'review'}
      <span class="status-left">Review | Pending: {$reviewStats.pending} | Cleanup: {$reviewStats.cleanup}</span>
      <span class="status-right">{#if $ramStats.enabled}<span class="ram-status">{ramStatusText($ramStats)}</span>{/if}<span>LMZ Tauri</span></span>
    {:else}
      <span class="status-left">{activeTab === 'logs' ? 'App Logs' : activeTab === 'stats' ? 'Stats' : 'Settings'}</span>
      <span class="status-right">{#if $ramStats.enabled}<span class="ram-status">{ramStatusText($ramStats)}</span>{/if}<span>LMZ Tauri</span></span>
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
  .status-right { padding-right: 15px; display: flex; align-items: center; gap: 14px; }
  .ram-status { color: var(--text-muted); white-space: nowrap; }
  .badge { background: var(--accent-primary); color: white; font-size: 10px; padding: 1px 5px; border-radius: 10px; margin-left: 3px; }
  .badge.warn { background: var(--accent-warning); }
</style>
