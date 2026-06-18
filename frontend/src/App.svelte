<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import Ingestion from './lib/Ingestion.svelte';
  import Launcher from './lib/Launcher.svelte';
  import LogsView from './lib/LogsView.svelte';
  import ReviewView from './lib/ReviewView.svelte';
  import SettingsView from './lib/SettingsView.svelte';
  import StatsView from './lib/StatsView.svelte';
  import VaultView from './lib/VaultView.svelte';
  import Toaster from './lib/Toaster.svelte';
  import NotificationHistory from './lib/NotificationHistory.svelte';
  import { log as uiLog } from './lib/logger';
  import { ramStats, startRamTracker } from './lib/ramStore';
  import { queueStats, reviewCount, reviewStats, startSharedStatsPolling } from './lib/statsStore';
  import { apiFetch } from './lib/api';
  import { privacyBlur } from './lib/privacyStore';
  import { applyMainWindowLayout } from './lib/windowLayout';
  import {
    IconFolder,
    IconDownload,
    IconEye,
    IconChart,
    IconSettings,
    IconFileText
  } from './lib/icons';

  type AppTab = 'vault' | 'logs' | 'ingest' | 'review' | 'stats' | 'settings';
  type IngestMode = 'online' | 'local';

  let workspaceLoaded = false;
  let activeWorkspaceId = '';
  let activeVaultId = '';
  let stopStats: (() => void) | null = null;
  let stopRam: (() => void) | null = null;

  $: if (workspaceLoaded) {
    if (!stopStats) {
      stopStats = startSharedStatsPolling();
    }
    if (!stopRam) {
      stopRam = startRamTracker();
    }
  }

  function handleWorkspaceLoaded(event: CustomEvent<{ workspace_id: string; vault_id: string | null }>) {
    activeWorkspaceId = event.detail.workspace_id;
    activeVaultId = event.detail.vault_id || '';
    workspaceLoaded = true;
    uiLog('INFO', `Workspace loaded: ${activeWorkspaceId}, vault: ${activeVaultId}`);
    void applyMainWindowLayout();
  }

  type DropPoint = { x: number; y: number };
  type DropRequest = {
    id: string;
    session_id: string;
    accepted_paths: string[];
    skipped: Array<{ path: string; reason: string }>;
    summary: { received: number; accepted: number; skipped: number };
    source_tab: string;
  };
  type VaultFilterRequest = {
    id: string;
    query: string;
  };

  let activeTab: AppTab = 'vault';
  let vaultStatus = { totalItems: 0, groups: 0, hasMore: false, layoutMode: 'masonry' };
  let forceClosing = false;
  let closeFlowRunning = false;
  let ingestModeState: IngestMode = 'online';
  let dragOverlayVisible = false;
  let dragOverlayText = 'Drop files/folders to stage in Local Ingestion';
  let pendingDropRequest: DropRequest | null = null;
  let pendingVaultFilterRequest: VaultFilterRequest | null = null;
  let dragScaleFactor = 1;

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

  function handleIngestModeChange(event: CustomEvent<{ mode: IngestMode }>) {
    ingestModeState = event.detail?.mode === 'local' ? 'local' : 'online';
  }

  function cssDropPoint(point: DropPoint | null): DropPoint | null {
    if (!point) return null;
    const scale = Number.isFinite(dragScaleFactor) && dragScaleFactor > 0 ? dragScaleFactor : 1;
    return { x: point.x / scale, y: point.y / scale };
  }

  function isEditableElementAt(point: DropPoint | null): boolean {
    if (!point) return false;
    const cssPoint = cssDropPoint(point);
    if (!cssPoint) return false;
    const target = document.elementFromPoint(cssPoint.x, cssPoint.y) as HTMLElement | null;
    if (!target) return false;
    if (target.closest('input, textarea, [contenteditable="true"], [contenteditable=""]')) return true;
    return false;
  }

  function isDropTargetAllowed(point: DropPoint | null): boolean {
    if (!point || isEditableElementAt(point)) return false;
    const cssPoint = cssDropPoint(point);
    if (!cssPoint) return false;
    const target = document.elementFromPoint(cssPoint.x, cssPoint.y) as HTMLElement | null;
    if (!target) return false;
    if (activeTab === 'vault') return Boolean(target.closest('[data-drop-zone="vault"]'));
    if (activeTab !== 'ingest') return false;
    if (ingestModeState !== 'local') return false;
    return Boolean(target.closest('[data-drop-zone="ingest-local"]'));
  }

  function hideDropOverlay() {
    dragOverlayVisible = false;
  }

  function buildDropSessionId() {
    return `${Date.now()}_${Math.random().toString(16).slice(2, 10)}`;
  }

  async function processDroppedPaths(paths: string[]) {
    const cleanPaths = (paths || []).map((value) => String(value || '').trim()).filter(Boolean);
    if (cleanPaths.length === 0) return;

    const sourceTab = activeTab;
    const sessionId = buildDropSessionId();
    try {
      const response = await apiFetch('/api/local-ingest/drop-intake', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, source_tab: sourceTab, paths: cleanPaths }),
      });
      const payload = await response.json().catch(() => ({}));
      if (response.status === 409) {
        const message = String(payload?.detail || 'Ingestion is already running. Drop blocked.');
        uiLog('WARNING', 'Drop blocked while ingestion is running', { source_tab: sourceTab, dropped_count: cleanPaths.length });
        alert(message);
        return;
      }
      if (!response.ok) {
        throw new Error(String(payload?.detail || `HTTP ${response.status}`));
      }

      const acceptedPaths = Array.isArray(payload?.accepted_paths)
        ? payload.accepted_paths.map((value: unknown) => String(value || '')).filter(Boolean)
        : [];
      const skipped = Array.isArray(payload?.skipped) ? payload.skipped : [];
      const summary = payload?.summary || {
        received: cleanPaths.length,
        accepted: acceptedPaths.length,
        skipped: skipped.length,
      };
      if (acceptedPaths.length === 0) {
        uiLog('INFO', 'Drop ignored: no supported files/folders', {
          session_id: String(payload?.session_id || sessionId),
          source_tab: sourceTab,
          received: summary.received,
          skipped: summary.skipped,
        });
        alert('No supported files/folders found in drop.');
        return;
      }

      pendingDropRequest = {
        id: `${String(payload?.session_id || sessionId)}:${Date.now()}`,
        session_id: String(payload?.session_id || sessionId),
        accepted_paths: acceptedPaths,
        skipped,
        summary: {
          received: Number(summary.received || cleanPaths.length),
          accepted: Number(summary.accepted || acceptedPaths.length),
          skipped: Number(summary.skipped || skipped.length),
        },
        source_tab: String(payload?.source_tab || sourceTab),
      };
      activeTab = 'ingest';
    } catch (error) {
      uiLog('ERROR', 'Drop intake failed', { error: String(error), source_tab: sourceTab, dropped_count: cleanPaths.length });
      alert(`Drop intake failed: ${String(error)}`);
    }
  }

  function ramStatusText(stats: any) {
    if (stats.error) return 'RAM: unavailable';
    if (stats.backendMb === null) return 'RAM: loading';
    if (stats.runtimeMb !== null) {
      const roles = stats.roles || {};
      const parts = [`RAM: runtime ${stats.runtimeMb} MB`, `backend ${stats.backendMb} MB`];
      if (Number(roles.webview_mb) > 0) parts.push(`webview ${roles.webview_mb} MB`);
      if (Number(roles.dev_tool_mb) > 0) parts.push(`dev ${roles.dev_tool_mb} MB`);
      if (Number(roles.subprocess_mb) > 0) parts.push(`subprocess ${roles.subprocess_mb} MB`);
      if (stats.frontendMb !== null) parts.push(`JS heap ${stats.frontendMb} MB`);
      return parts.join(' | ');
    }
    if (stats.frontendMb !== null && stats.totalMb !== null) {
      return `RAM: backend ${stats.backendMb} MB | frontend ${stats.frontendMb} MB | total ${stats.totalMb} MB`;
    }
    return `RAM: backend ${stats.backendMb} MB`;
  }

  function handleTestDropRequest(event: Event) {
    const detail = (event as CustomEvent).detail || {};
    const accepted = Array.isArray(detail.accepted_paths) ? detail.accepted_paths.map((value: unknown) => String(value || '')).filter(Boolean) : [];
    if (accepted.length === 0) return;
    const skipped = Array.isArray(detail.skipped) ? detail.skipped : [];
    pendingDropRequest = {
      id: String(detail.id || `test:${Date.now()}`),
      session_id: String(detail.session_id || 'test-session'),
      accepted_paths: accepted,
      skipped,
      summary: {
        received: Number(detail.summary?.received || accepted.length + skipped.length),
        accepted: Number(detail.summary?.accepted || accepted.length),
        skipped: Number(detail.summary?.skipped || skipped.length),
      },
      source_tab: String(detail.source_tab || activeTab),
    };
    activeTab = 'ingest';
  }

  function searchSegment(prefix: string, value: string) {
    const clean = String(value || '').trim().replace(/;/g, ' ');
    return clean ? `${prefix}${clean};` : '';
  }

  function handleStatsFilterVault(event: CustomEvent<{ topics?: string[]; wd_tags?: string[] }>) {
    const topics = Array.isArray(event.detail?.topics) ? event.detail.topics : [];
    const wdTags = Array.isArray(event.detail?.wd_tags) ? event.detail.wd_tags : [];
    const query = [
      ...topics.map((value) => searchSegment('t:', value)),
      ...wdTags.map((value) => searchSegment('#', value))
    ].filter(Boolean).join(' ');
    if (!query) return;
    pendingVaultFilterRequest = { id: `${Date.now()}_${Math.random().toString(16).slice(2, 8)}`, query };
    activeTab = 'vault';
    uiLog('INFO', 'Stats filters applied to vault', { topics: topics.length, wd_tags: wdTags.length });
  }

  onMount(() => {
    uiLog('INFO', 'Svelte UI initialized and mounted');
    let unlistenClose: (() => void) | null = null;
    let unlistenDrop: (() => void) | null = null;
    let unlistenScale: (() => void) | null = null;

    // Check if running inside Playwright / test mode
    const params = new URLSearchParams(window.location.search);
    if (params.has('lmz_test_page_size')) {
      workspaceLoaded = true;
      activeWorkspaceId = 'default';
      activeVaultId = 'default';
      uiLog('INFO', 'Test mode detected: bypassing workspace launcher');
    }

    (async () => {
      try {
        const { getCurrentWindow } = await import('@tauri-apps/api/window');
        const appWindow = getCurrentWindow();
        dragScaleFactor = await appWindow.scaleFactor().catch(() => 1);
        try {
          unlistenScale = await appWindow.onScaleChanged(({ payload }) => {
            dragScaleFactor = payload?.scaleFactor || 1;
          });
        } catch {
          // Older/nonstandard runtimes can still use the initial scale factor.
        }
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

        try {
          unlistenDrop = await appWindow.onDragDropEvent((event: any) => {
            const payload = event?.payload || {};
            if (payload.type === 'over') {
              dragOverlayVisible = isDropTargetAllowed(payload.position ?? null);
              return;
            }
            if (payload.type === 'drop') {
              hideDropOverlay();
              if (!isDropTargetAllowed(payload.position ?? null)) return;
              const droppedPaths = Array.isArray(payload.paths) ? payload.paths : [];
              void processDroppedPaths(droppedPaths);
              return;
            }
            hideDropOverlay();
          });
        } catch (error) {
          uiLog('WARNING', 'Native drag-drop listener unavailable', { error: String(error) });
        }
      } catch {
        // non-tauri context
      }
    })();
    window.addEventListener('lmz:test-drop-request', handleTestDropRequest);

    return () => {
      window.removeEventListener('lmz:test-drop-request', handleTestDropRequest);
      if (unlistenClose) unlistenClose();
      if (unlistenDrop) unlistenDrop();
      if (unlistenScale) unlistenScale();
    };
  });

  onDestroy(() => {
    if (stopStats) stopStats();
    if (stopRam) stopRam();
  });
</script>

<svelte:window on:keydown={handleGlobalKeydown} />

{#if !workspaceLoaded}
  <Launcher on:loaded={handleWorkspaceLoaded} />
{:else}
  <Toaster />
  <div class="root-container" class:privacy-blur={$privacyBlur}>
    {#if dragOverlayVisible}
      <div class="drop-overlay">
        <div class="drop-overlay-text">{dragOverlayText}</div>
      </div>
    {/if}
    <div class="app-container">
      <aside class="sidebar">
        <div class="nav-group">
          <button class:active={activeTab === 'vault'} on:click={() => activeTab = 'vault'}>
            <IconFolder size={14} />
            <span>Vault</span>
          </button>
          <button class:active={activeTab === 'ingest'} on:click={() => activeTab = 'ingest'}>
            <IconDownload size={14} />
            <span>Ingestion</span>
            {#if ($queueStats.normal + $queueStats.force) > 0}
              <span class="badge">{$queueStats.normal + $queueStats.force}</span>
            {/if}
          </button>
          <button class:active={activeTab === 'review'} on:click={() => activeTab = 'review'}>
            <IconEye size={14} />
            <span>Review</span>
            {#if $reviewCount > 0}
              <span class="badge warn">{$reviewCount}</span>
            {/if}
          </button>
          <button class:active={activeTab === 'stats'} on:click={() => activeTab = 'stats'}>
            <IconChart size={14} />
            <span>Stats</span>
          </button>
          <button class:active={activeTab === 'settings'} on:click={() => activeTab = 'settings'}>
            <IconSettings size={14} />
            <span>Settings</span>
          </button>
          <button class:active={activeTab === 'logs'} on:click={() => activeTab = 'logs'}>
            <IconFileText size={14} />
            <span>App Logs</span>
          </button>
        </div>
      </aside>

      <main class="main-content">
        <!-- VaultView stays mounted across tab switches to preserve scroll position, selection, and loaded items.
             Its IntersectionObserver/ResizeObserver are idle when display:none, so the cost is negligible.
             Other tabs use {#if} since they can re-fetch on demand. -->
        <div class:hidden={activeTab !== 'vault'} class="tab-panel" data-drop-zone="vault">
          <VaultView active={activeTab === 'vault'} filterRequest={pendingVaultFilterRequest} on:status={handleVaultStatus} />
        </div>
        {#if activeTab === 'review'}
          <div class="view-shell"><ReviewView /></div>
        {:else if activeTab === 'ingest'}
          <div class="view-shell">
            <Ingestion dropRequest={pendingDropRequest} on:modechange={handleIngestModeChange} />
          </div>
        {:else if activeTab === 'stats'}
          <div class="view-shell"><StatsView on:filterVault={handleStatsFilterVault} /></div>
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
      {:else if activeTab === 'ingest'}
        <span class="status-left">Ingestion | Normal: {$queueStats.normal} | Force: {$queueStats.force} | Failed: {$queueStats.failed}</span>
      {:else if activeTab === 'review'}
        <span class="status-left">Review | Pending: {$reviewStats.pending} | Cleanup: {$reviewStats.cleanup}</span>
      {:else}
        <span class="status-left">{activeTab === 'logs' ? 'App Logs' : activeTab === 'stats' ? 'Stats' : 'Settings'}</span>
      {/if}
      <span class="status-right">
        {#if $ramStats.enabled}<span class="ram-status">{ramStatusText($ramStats)}</span>{/if}
        {#if activeTab === 'vault'}
          <span>Showing {vaultStatus.groups} groups{vaultStatus.hasMore ? ' (more available)' : ''}</span>
        {:else}
          <span>LMZ Tauri</span>
        {/if}
        <NotificationHistory />
      </span>
    </footer>
  </div>
{/if}

<style>
  .root-container { display: flex; flex-direction: column; height: 100vh; width: 100vw; background: var(--bg-main); overflow: hidden; }
  .drop-overlay { position: fixed; inset: 0; z-index: 1200; background: rgba(1, 4, 9, 0.62); display: flex; align-items: center; justify-content: center; pointer-events: none; }
  .drop-overlay-text { color: #e6edf3; font-size: 20px; font-weight: 700; letter-spacing: 0; text-align: center; padding: 16px 22px; border: 1px solid rgba(255, 255, 255, 0.25); border-radius: 10px; background: rgba(0, 0, 0, 0.25); }
  .app-container { display: flex; flex-grow: 1; overflow: hidden; }
  .sidebar { width: 135px; background: var(--bg-main); border-right: 1px solid var(--border-dim); display: flex; flex-direction: column; padding: 15px 6px; flex-shrink: 0; }
  .nav-group { display: flex; flex-direction: column; gap: 10px; }
  .nav-group button { width: 100%; padding: 9px 8px; font-size: 13px; border-radius: 6px; background: transparent; border: 1px solid rgba(255, 255, 255, 0.15); color: var(--text-main); display: flex; align-items: center; gap: 8px; cursor: pointer; box-sizing: border-box; position: relative; }
  .nav-group button.active { background: var(--accent-primary); color: white; border-color: var(--accent-primary); }
  .nav-group button:not(.active):hover { border-color: rgba(255, 255, 255, 0.3); background: var(--bg-panel); }
  .main-content { flex-grow: 1; display: flex; flex-direction: column; overflow: hidden; }
  .tab-panel { flex-grow: 1; display: flex; flex-direction: column; overflow: hidden; }
  .tab-panel.hidden { display: none; }
  .view-shell { flex-grow: 1; display: flex; flex-direction: column; overflow: hidden; }
  .bottom-status { height: 25px; background: #010409; border-top: 1px solid var(--border-dim); padding: 0; display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: var(--text-muted); flex-shrink: 0; z-index: 200; width: 100%; box-sizing: border-box; }
  .status-left { padding-left: 15px; }
  .status-right { padding-right: 0; display: flex; align-items: center; gap: 14px; }
  .ram-status { color: var(--text-muted); white-space: nowrap; }
  .badge { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: var(--accent-primary); color: white; font-size: 10px; padding: 1px 5px; border-radius: 10px; }
  .badge.warn { background: var(--accent-warning); }
</style>
