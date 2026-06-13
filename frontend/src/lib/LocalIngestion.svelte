<script lang="ts">
  import { onMount, tick, onDestroy } from 'svelte';
  import { open as openDialog } from '@tauri-apps/plugin-dialog';
  import { log as uiLog } from './logger';
  import { apiFetch } from './api';
  import { runtimeSessionKey } from './runtimeStore';
  import {
    IconRefresh,
    IconTrash,
    IconPlus,
    IconFolder,
    IconClose
  } from './icons';

  type ArtistOption = { id: number; name: string; kind: string; item_count: number; link_count: number; alias_count: number };
  type PlatformOption = { id: number; key_norm: string; display_name: string; kind: string; item_count: number; alias_count: number };
  type DropRequest = {
    id: string;
    session_id: string;
    accepted_paths: string[];
    skipped: Array<{ path: string; reason: string }>;
    summary: { received: number; accepted: number; skipped: number };
    source_tab: string;
  };
  type LocalStatus = {
    running: boolean;
    phase: string;
    run_id: string | null;
    scanned: number;
    staged: number;
    queued: number;
    processed: number;
    summary: { ingested: number; review: number; failed: number; duplicate: number };
    results: Array<{ path: string; source_path?: string; staged_path?: string; name: string; status: string; message: string }>;
    failed_paths: string[];
    last_defaults?: { artist?: string; platform?: string; source_url?: string };
    last_skip_similarity?: boolean;
    started_at: string | null;
    finished_at: string | null;
    stop_requested?: boolean;
  };

  export let dropRequest: DropRequest | null = null;

  let localPaths: string[] = [];
  let localDefaults = { artist: '', platform: 'Local', source_url: '' };
  let artistOptions: ArtistOption[] = [];
  let platformOptions: PlatformOption[] = [];
  let platformSelectOptions: string[] = ['Local'];
  let artistOptionsTimer: number | null = null;

  let showArtistSuggestions = false;
  let activeArtistSuggestionIndex = 0;
  let artistSuggestionsListEl: HTMLDivElement;

  let localPanelWidth = 380;
  let localSeparatorDragging = false;
  let localSeparatorStartX = 0;
  let localSeparatorStartWidth = 0;
  const MIN_LOCAL_PANEL_WIDTH = 280;
  const MAX_LOCAL_PANEL_WIDTH = 600;

  let localStatus: LocalStatus = emptyLocalStatus();
  let localStatusTimer: number | null = null;
  let currentRuntimeSessionKey = '';
  let lastDropRequestId = '';

  $: {
    const values = new Set<string>(['Local']);
    for (const platform of platformOptions) {
      if (platform.display_name) values.add(platform.display_name);
    }
    if (localDefaults.platform) values.add(localDefaults.platform);
    platformSelectOptions = [...values];
  }

  $: if ($runtimeSessionKey) {
    if (currentRuntimeSessionKey && currentRuntimeSessionKey !== $runtimeSessionKey) {
      resetForRuntimeSwitch();
    }
    currentRuntimeSessionKey = $runtimeSessionKey;
  }

  $: if (dropRequest && dropRequest.id !== lastDropRequestId) {
    lastDropRequestId = dropRequest.id;
    const added = addLocalPaths(dropRequest.accepted_paths || []);
    uiLog('INFO', 'Drop staged for local ingestion', {
      session_id: dropRequest.session_id,
      source_tab: dropRequest.source_tab,
      accepted: dropRequest.summary?.accepted ?? dropRequest.accepted_paths.length,
      skipped: dropRequest.summary?.skipped ?? (dropRequest.skipped || []).length,
      staged_new: added
    });
    dropRequest = null;
  }

  let wasRunning = false;
  $: if (localStatus) {
    if (wasRunning && !localStatus.running) {
      cleanSuccessfulPaths();
    }
    wasRunning = localStatus.running;
  }

  function cleanSuccessfulPaths() {
    const results = localStatus.results || [];
    if (results.length === 0) return;

    localPaths = localPaths.filter(stagedPath => {
      const itemsUnderPath = results.filter(r => {
        if (!r.source_path) return false;
        return r.source_path === stagedPath || 
               r.source_path.startsWith(stagedPath + '\\') || 
               r.source_path.startsWith(stagedPath + '/');
      });

      if (itemsUnderPath.length === 0) return true;

      const hasFailure = itemsUnderPath.some(r => r.status === 'failed');
      return hasFailure;
    });
  }

  function emptyLocalStatus(): LocalStatus {
    return {
      running: false,
      phase: 'idle',
      run_id: null,
      scanned: 0,
      staged: 0,
      queued: 0,
      processed: 0,
      summary: { ingested: 0, review: 0, failed: 0, duplicate: 0 },
      results: [],
      failed_paths: [],
      started_at: null,
      finished_at: null
    };
  }

  function resetForRuntimeSwitch() {
    if (artistOptionsTimer !== null) {
      clearTimeout(artistOptionsTimer);
      artistOptionsTimer = null;
    }
    stopLocalStatusPolling();
    localPaths = [];
    localStatus = emptyLocalStatus();
    artistOptions = [];
    platformOptions = [];
    localDefaults = { artist: '', platform: 'Local', source_url: '' };
    refreshLocalStatus();
    loadArtistOptions('');
    loadPlatformOptions();
  }

  async function loadArtistOptions(q = localDefaults.artist) {
    try {
      const params = new URLSearchParams({ q: String(q || '').trim(), limit: '50' });
      const res = await apiFetch(`/api/artists?${params.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      artistOptions = Array.isArray(data.items) ? data.items : [];
    } catch (e) {
      uiLog('ERROR', 'Failed to load artist options', { error: String(e) });
    }
  }

  async function loadPlatformOptions() {
    try {
      const res = await apiFetch('/api/platforms?limit=200');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      platformOptions = Array.isArray(data.items) ? data.items : [];
    } catch (e) {
      uiLog('ERROR', 'Failed to load platform options', { error: String(e) });
    }
  }

  function scheduleArtistOptions(q = localDefaults.artist) {
    if (artistOptionsTimer !== null) clearTimeout(artistOptionsTimer);
    artistOptionsTimer = window.setTimeout(() => {
      artistOptionsTimer = null;
      loadArtistOptions(q);
    }, 180);
  }

  function handleArtistInput() {
    showArtistSuggestions = true;
    activeArtistSuggestionIndex = 0;
    scheduleArtistOptions(localDefaults.artist);
  }

  function handleArtistFocus() {
    showArtistSuggestions = true;
    activeArtistSuggestionIndex = 0;
    loadArtistOptions(localDefaults.artist);
  }

  function selectArtistSuggestion(name: string) {
    localDefaults.artist = name;
    showArtistSuggestions = false;
  }

  function handleArtistKeydown(event: KeyboardEvent) {
    if (showArtistSuggestions && artistOptions.length > 0) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        activeArtistSuggestionIndex = (activeArtistSuggestionIndex + 1) % artistOptions.length;
        scrollArtistSuggestionIntoView();
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        activeArtistSuggestionIndex = (activeArtistSuggestionIndex - 1 + artistOptions.length) % artistOptions.length;
        scrollArtistSuggestionIntoView();
      } else if (event.key === 'Enter' || event.key === 'Tab') {
        event.preventDefault();
        selectArtistSuggestion(artistOptions[activeArtistSuggestionIndex].name);
      } else if (event.key === 'Escape') {
        event.preventDefault();
        showArtistSuggestions = false;
      }
    }
  }

  async function scrollArtistSuggestionIntoView() {
    await tick();
    const active = artistSuggestionsListEl?.querySelector('button.active');
    active?.scrollIntoView({ block: 'nearest' });
  }

  function handleWindowClick(event: PointerEvent) {
    const target = event.target as HTMLElement;
    if (!target) return;
    if (showArtistSuggestions && !target.closest('.local-artist-wrap')) {
      showArtistSuggestions = false;
    }
  }

  function handleLocalSeparatorMove(event: PointerEvent) {
    if (!localSeparatorDragging) return;
    const deltaX = event.clientX - localSeparatorStartX;
    localPanelWidth = Math.max(MIN_LOCAL_PANEL_WIDTH, Math.min(MAX_LOCAL_PANEL_WIDTH, localSeparatorStartWidth + deltaX));
  }

  function stopLocalSeparatorDrag() {
    localSeparatorDragging = false;
    window.removeEventListener('pointermove', handleLocalSeparatorMove);
    window.removeEventListener('pointerup', stopLocalSeparatorDrag);
  }

  function startLocalSeparatorDrag(event: PointerEvent) {
    if (event.button !== 0) return;
    event.preventDefault();
    localSeparatorDragging = true;
    localSeparatorStartX = event.clientX;
    localSeparatorStartWidth = localPanelWidth;
    window.addEventListener('pointermove', handleLocalSeparatorMove);
    window.addEventListener('pointerup', stopLocalSeparatorDrag);
  }

  function resetLocalPanelWidth() {
    localPanelWidth = 380;
  }

  function addLocalPaths(paths: string[]) {
    const existing = new Set(localPaths);
    const next = [...localPaths];
    let added = 0;
    for (const path of paths) {
      const value = String(path || '').trim();
      if (!value || existing.has(value)) continue;
      existing.add(value);
      next.push(value);
      added += 1;
    }
    if (added > 0) localPaths = next;
    return added;
  }

  async function pickLocalFiles() {
    try {
      const selection = await openDialog({ directory: false, multiple: true });
      if (!selection) return;
      const paths = Array.isArray(selection) ? selection : [selection];
      addLocalPaths(paths);
    } catch (e) {
      uiLog('ERROR', 'Failed to open file picker', { error: String(e) });
      alert('Failed to open file picker.');
    }
  }

  async function pickLocalFolders() {
    try {
      const selection = await openDialog({ directory: true, multiple: true });
      if (!selection) return;
      const paths = Array.isArray(selection) ? selection : [selection];
      addLocalPaths(paths);
    } catch (e) {
      uiLog('ERROR', 'Failed to open folder picker', { error: String(e) });
      alert('Failed to open folder picker.');
    }
  }

  function removeLocalPath(index: number) {
    localPaths = localPaths.filter((_, i) => i !== index);
  }

  function clearLocalPaths() {
    localPaths = [];
  }

  async function refreshLocalStatus() {
    try {
      const res = await apiFetch('/api/local-ingest/status');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      localStatus = await res.json();
      if (localStatus.running) {
        startLocalStatusPolling();
      } else {
        stopLocalStatusPolling();
      }
    } catch (e) {
      uiLog('ERROR', 'Failed to refresh local ingest status', { error: String(e) });
    }
  }

  function startLocalStatusPolling() {
    if (localStatusTimer !== null) return;
    localStatusTimer = window.setInterval(() => {
      refreshLocalStatus();
    }, 1200);
  }

  function stopLocalStatusPolling() {
    if (localStatusTimer !== null) {
      clearInterval(localStatusTimer);
      localStatusTimer = null;
    }
  }

  async function startLocalIngestion() {
    if (localPaths.length === 0) {
      alert('Add files or folders first.');
      return;
    }
    try {
      const res = await apiFetch('/api/local-ingest/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paths: localPaths,
          defaults: localDefaults,
          skip_similarity: false
        })
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(payload?.detail || `HTTP ${res.status}`);
      }
      uiLog('INFO', 'Started local ingestion', { run_id: payload?.run_id || '', phase: payload?.phase || 'scanning' });
      await refreshLocalStatus();
      startLocalStatusPolling();
    } catch (e) {
      uiLog('ERROR', 'Failed to start local ingestion', { error: String(e) });
      alert(`Failed to start local ingestion: ${String(e)}`);
    }
  }

  async function retryLocalFailed() {
    try {
      const res = await apiFetch('/api/local-ingest/retry-failed', { method: 'POST' });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(payload?.detail || `HTTP ${res.status}`);
      if ((payload?.queued || 0) > 0) {
        startLocalStatusPolling();
      }
      uiLog('INFO', 'Retried local failed items', { queued: payload?.queued || 0, run_id: payload?.run_id || '', phase: payload?.phase || 'scanning' });
      await refreshLocalStatus();
    } catch (e) {
      uiLog('ERROR', 'Failed to retry local failed items', { error: String(e) });
      alert(`Failed to retry local failed items: ${String(e)}`);
    }
  }

  function handleGlobalRefresh(event: Event) {
    const detail = (event as CustomEvent).detail || {};
    if (detail.tab !== 'ingest') return;
    uiLog('INFO', 'Ingestion local view refresh requested');
    refreshLocalStatus();
  }

  onMount(() => {
    refreshLocalStatus();
    loadArtistOptions('');
    loadPlatformOptions();
    window.addEventListener('lmz:refresh', handleGlobalRefresh);
  });

  onDestroy(() => {
    if (artistOptionsTimer !== null) clearTimeout(artistOptionsTimer);
    stopLocalStatusPolling();
    window.removeEventListener('pointermove', handleLocalSeparatorMove);
    window.removeEventListener('pointerup', stopLocalSeparatorDrag);
    window.removeEventListener('lmz:refresh', handleGlobalRefresh);
  });
</script>

<svelte:window on:pointerdown={handleWindowClick} />

<div class="local-mode" data-drop-zone="ingest-local">
  <div class="local-config-panel" style={`width: ${localPanelWidth}px;`}>
    <div class="local-defaults">
      <div class="local-default-item local-artist-wrap">
        <label class="field-label" for="local-artist-input">Artist</label>
        <div class="custom-dropdown-wrap">
          <input
            id="local-artist-input"
            class="local-artist-input"
            type="text"
            bind:value={localDefaults.artist}
            on:input={handleArtistInput}
            on:keydown={handleArtistKeydown}
            on:focus={handleArtistFocus}
            placeholder="Optional default artist"
          />
          {#if showArtistSuggestions && artistOptions.length > 0}
            <div bind:this={artistSuggestionsListEl} class="custom-dropdown-popover artist-suggestions sleek-scrollbar">
              {#each artistOptions as artist, i}
                <button
                  type="button"
                  class:active={i === activeArtistSuggestionIndex}
                  on:click={() => selectArtistSuggestion(artist.name)}
                >
                  <span class="option-name">{artist.name}</span>
                  <span class="option-detail">{artist.item_count} items</span>
                </button>
              {/each}
            </div>
          {/if}
        </div>
      </div>

      <div class="local-default-item local-platform-wrap">
        <label class="field-label" for="local-platform-select">Platform</label>
        <select id="local-platform-select" class="local-platform-select" bind:value={localDefaults.platform}>
          {#each platformSelectOptions as platform}
            <option value={platform}>{platform}</option>
          {/each}
        </select>
      </div>
    </div>


    <div class="local-toolbar">
      <button type="button" class="icon-btn-chip-text" on:click={pickLocalFiles} disabled={localStatus.running}>
        <IconPlus size={12} />
        <span>Files</span>
      </button>
      <button type="button" class="icon-btn-chip-text" on:click={pickLocalFolders} disabled={localStatus.running}>
        <IconFolder size={12} />
        <span>Folder</span>
      </button>
      <button type="button" class="icon-btn-chip-text" on:click={clearLocalPaths} disabled={localStatus.running || localPaths.length === 0}>
        <IconTrash size={12} />
        <span>Clear</span>
      </button>
    </div>

    <div class="local-list sleek-scrollbar">
      {#each localPaths as path, index}
        <div class="local-item">
          <span class="local-path" title={path}>{path}</span>
          <button type="button" class="remove-path-btn" on:click={() => removeLocalPath(index)} disabled={localStatus.running} title="Remove path">
            <IconClose size={12} />
          </button>
        </div>
      {/each}
      {#if localPaths.length === 0}
        <div class="empty-monitor">Drop paths here to stage</div>
      {/if}
    </div>

    <button type="button" class="primary start-local-btn" on:click={startLocalIngestion} disabled={localStatus.running || localPaths.length === 0}>
      Start Local Ingestion
    </button>
  </div>

  <button
    type="button"
    class="local-separator-handle"
    class:active={localSeparatorDragging}
    title="Drag to resize panels. Double-click to reset."
    aria-label="Resize local staging panel"
    on:pointerdown={startLocalSeparatorDrag}
    on:dblclick={resetLocalPanelWidth}
  ></button>

  <div class="local-monitor-panel">
    <div class="local-status">
      <div class="monitor-header">Local Run Status</div>
      <div class="local-status-terminal">
        <div class="terminal-row pipeline-metrics">
          <span class="metric">PHASE: <strong class="uppercase text-bright">{localStatus.phase}</strong></span>
          <span class="divider">-</span>
          <span class="metric">SCANNED: <strong>{localStatus.scanned}</strong></span>
          <span class="divider">-</span>
          <span class="metric">STAGED: <strong>{localStatus.staged}</strong></span>
          <span class="divider">-</span>
          <span class="metric">QUEUED: <strong>{localStatus.queued}</strong></span>
          <span class="divider">-</span>
          <span class="metric">PROCESSED: <strong>{localStatus.processed}</strong></span>
        </div>
        <div class="terminal-row outcomes">
          <span class="outcome-pill ingested">
            <strong>{localStatus.summary.ingested}</strong> INGESTED
          </span>
          <span class="outcome-pill review">
            <strong>{localStatus.summary.review}</strong> REVIEW
          </span>
          <span class="outcome-pill duplicate">
            <strong>{localStatus.summary.duplicate}</strong> DUP
          </span>
          <span class="outcome-pill failed">
            <strong>{localStatus.summary.failed}</strong> FAILED
          </span>
        </div>
      </div>
      <div class="footer-btns">
        <button type="button" class="icon-btn-chip-text" on:click={refreshLocalStatus}>
          <IconRefresh size={12} />
          <span>Refresh</span>
        </button>
        <button type="button" class="icon-btn-chip-text" on:click={retryLocalFailed} disabled={localStatus.running || localStatus.failed_paths.length === 0}>
          <IconRefresh size={12} />
          <span>Retry Session</span>
        </button>
      </div>
      <div class="local-results sleek-scrollbar">
        {#each localStatus.results.slice(-120).reverse() as result}
          <div class="result-line">
            <span class="result-status {result.status}">[{result.status}]</span>
            <span class="result-name">{result.name}</span>
            <span class="result-message">- {result.message}</span>
          </div>
        {/each}
        {#if localStatus.results.length === 0}
          <div class="empty-monitor">Console idle</div>
        {/if}
      </div>
    </div>
  </div>
</div>
