<script lang="ts">
  import { createEventDispatcher, onMount, tick } from 'svelte';
  import { open as openDialog } from '@tauri-apps/plugin-dialog';
  import { log as uiLog } from './logger';
  import { apiFetch, apiUrl } from './api';
  import { queueStats, refreshQueueStats, setQueueStats } from './statsStore';

  type IngestMode = 'online' | 'local';
  type QueueName = 'normal' | 'force' | 'failed';
  type DropRequest = {
    id: string;
    session_id: string;
    accepted_paths: string[];
    skipped: Array<{ path: string; reason: string }>;
    summary: { received: number; accepted: number; skipped: number };
    source_tab: string;
  };

  export let dropRequest: DropRequest | null = null;
  const dispatch = createEventDispatcher<{ modechange: { mode: IngestMode } }>();

  let ingestMode: IngestMode = 'online';
  let lastModeEmitted: IngestMode | null = null;
  let lastDropRequestId = '';

  let currentQueue: QueueName = 'normal';
  let queueContent = '';
  let counts = { normal: 0, force: 0, failed: 0 };
  let saving = false;
  let running = false;
  let isDirty = false;
  let parseTimer: number | null = null;
  let monitorLogIdCounter = 0;

  let monitorLogs: any[] = [];
  let logSource: EventSource | null = null;
  let logReconnectTimer: number | null = null;
  let logReconnectAttempts = 0;
  let monitorContainer: HTMLElement;
  const LOG_RECONNECT_BASE_MS = 800;
  const LOG_RECONNECT_MAX_MS = 8000;

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

  let localPaths: string[] = [];
  let localDefaults = { artist: '', platform: 'Local', source_url: '' };
  let localStatus: LocalStatus = {
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
  let localStatusTimer: number | null = null;

  $: counts = $queueStats;
  $: readyCount = (counts.normal || 0) + (counts.force || 0);

  function nextLogReconnectDelayMs() {
    const exponential = Math.min(LOG_RECONNECT_MAX_MS, LOG_RECONNECT_BASE_MS * Math.pow(2, logReconnectAttempts));
    const jitter = Math.floor(Math.random() * 300);
    logReconnectAttempts += 1;
    return Math.min(LOG_RECONNECT_MAX_MS, exponential + jitter);
  }

  function scheduleMonitorReconnect() {
    if (logReconnectTimer !== null) return;
    logReconnectTimer = window.setTimeout(() => {
      logReconnectTimer = null;
      connectMonitor();
    }, nextLogReconnectDelayMs());
  }

  function connectMonitor() {
    if (logReconnectTimer !== null) {
      clearTimeout(logReconnectTimer);
      logReconnectTimer = null;
    }
    if (logSource) logSource.close();
    logSource = new EventSource(apiUrl('/api/logs?filename=ingest_online.jsonl'));
    logSource.onmessage = (e) => {
      logReconnectAttempts = 0;
      try {
        const entry = JSON.parse(e.data);
        appendMonitorLog(entry);
        if (entry.message && entry.message.includes('Ingestion cycle complete')) {
          running = false;
          fetchStats();
          if (!isDirty) loadQueue(currentQueue);
        }
      } catch {
        // ignore parse errors
      }
    };
    logSource.onerror = () => {
      logSource?.close();
      scheduleMonitorReconnect();
    };
  }

  function isNearBottom(node: HTMLElement) {
    return node.scrollHeight - node.scrollTop - node.clientHeight < 48;
  }

  function appendMonitorLog(entry: any) {
    entry.id = monitorLogIdCounter++;
    const shouldScroll = !monitorContainer || isNearBottom(monitorContainer);
    monitorLogs.push(entry);
    if (monitorLogs.length > 150) monitorLogs.splice(0, monitorLogs.length - 150);
    monitorLogs = monitorLogs;
    if (shouldScroll) {
      tick().then(() => {
        if (monitorContainer) monitorContainer.scrollTop = monitorContainer.scrollHeight;
      });
    }
  }

  async function loadQueue(name: QueueName) {
    try {
      const res = await apiFetch(`/api/queue/${name}`);
      const data = await res.json();
      queueContent = data.content;
      isDirty = false;
    } catch (e) {
      uiLog('ERROR', 'Failed to load queue', { queue: name, error: String(e) });
    }
  }

  async function fetchStats() {
    if (isDirty) return;
    try {
      await refreshQueueStats();
    } catch (e) {
      uiLog('ERROR', 'Failed to refresh queue stats', { error: String(e) });
    }
  }

  function handleTabChange(name: QueueName) {
    if (isDirty) {
      if (!confirm('You have unsaved changes. Discard them?')) return;
    }
    currentQueue = name;
    loadQueue(name);
  }

  async function saveQueue() {
    saving = true;
    try {
      await apiFetch(`/api/queue/${currentQueue}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: queueContent })
      });
      isDirty = false;
      await refreshQueueStats();
      uiLog('INFO', `Queue ${currentQueue} saved`);
    } finally {
      saving = false;
    }
  }

  async function startIngestion() {
    if (currentQueue === 'failed') {
      alert('Failed queue cannot be started directly. Use Retry Failed.');
      return;
    }
    if (isDirty) await saveQueue();
    running = true;
    uiLog('INFO', `Starting ingestion for queue: ${currentQueue}`);
    try {
      const res = await apiFetch(`/api/ingest/${currentQueue}`, { method: 'POST' });
      if (!res.ok) {
        running = false;
        throw new Error(`HTTP ${res.status}`);
      }
    } catch (e) {
      running = false;
      uiLog('ERROR', 'Failed to start ingestion', { error: String(e) });
      alert('Failed to start ingestion. Check App Logs for details.');
    }
  }

  function onEditorInput() {
    isDirty = true;
    if (parseTimer !== null) clearTimeout(parseTimer);
    parseTimer = window.setTimeout(() => {
      parseTimer = null;
      const count = queueContent.split('\n').filter((l) => l.trim().startsWith('http')).length;
      setQueueStats({ ...counts, [currentQueue]: count });
    }, 400);
  }

  async function openExternal() {
    if (isDirty) {
      if (confirm('Save changes before opening?')) {
        await saveQueue();
      } else {
        return;
      }
    }
    try {
      await apiFetch(`/api/queue/${currentQueue}/open`, { method: 'POST' });
    } catch (e) {
      uiLog('ERROR', 'Failed to open queue file', { error: String(e) });
    }
  }

  async function retryFailed() {
    if (isDirty) {
      if (!confirm('Discard unsaved changes before retrying?')) return;
    }
    if (counts.failed === 0) {
      alert('No failed URLs found.');
      return;
    }
    const target = prompt(`Retry ${counts.failed} failed URLs?\n\nType 'normal' or 'force' to choose destination:`, 'normal');
    if (target === 'normal' || target === 'force') {
      try {
        const res = await apiFetch(`/api/queue/actions/retry-failed`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target })
        });
        const data = await res.json();
        alert(`Moved ${data.moved} URLs to ${target}.`);
        setQueueStats(data.counts);
        if (currentQueue === target || currentQueue === 'failed') loadQueue(currentQueue);
      } catch (e) {
        uiLog('ERROR', 'Failed to retry failed queue', { error: String(e) });
      }
    }
  }

  async function clearFailed() {
    if (isDirty) {
      if (!confirm('Discard unsaved changes before clearing?')) return;
    }
    if (counts.failed === 0) {
      alert('No failed URLs found.');
      return;
    }
    if (confirm('Clear failed_links.md?')) {
      try {
        const res = await apiFetch('/api/queue/actions/clear-failed', { method: 'POST' });
        const data = await res.json();
        setQueueStats(data.counts);
        if (currentQueue === 'failed') loadQueue('failed');
      } catch (e) {
        uiLog('ERROR', 'Failed to clear failed queue', { error: String(e) });
      }
    }
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
      const values = Array.isArray(selection) ? selection : [selection];
      addLocalPaths(values.map((value) => String(value)));
    } catch (e) {
      uiLog('ERROR', 'Failed to open file picker', { error: String(e) });
      alert('Failed to open file picker.');
    }
  }

  async function pickLocalFolders() {
    try {
      const selection = await openDialog({ directory: true, multiple: true });
      if (!selection) return;
      const values = Array.isArray(selection) ? selection : [selection];
      addLocalPaths(values.map((value) => String(value)));
    } catch (e) {
      uiLog('ERROR', 'Failed to open folder picker', { error: String(e) });
      alert('Failed to open folder picker.');
    }
  }

  function removeLocalPath(index: number) {
    localPaths = localPaths.filter((_, i) => i !== index);
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
    if (ingestMode === 'online' && isDirty && !confirm('You have unsaved queue changes. Discard them and refresh?')) return;
    uiLog('INFO', 'Ingestion view refresh requested', { mode: ingestMode });
    if (ingestMode === 'online') {
      loadQueue(currentQueue);
      fetchStats();
      connectMonitor();
      return;
    }
    refreshLocalStatus();
  }

  $: if (ingestMode !== lastModeEmitted) {
    lastModeEmitted = ingestMode;
    dispatch('modechange', { mode: ingestMode });
  }

  $: if (dropRequest && dropRequest.id !== lastDropRequestId) {
    lastDropRequestId = dropRequest.id;
    ingestMode = 'local';
    const added = addLocalPaths(dropRequest.accepted_paths || []);
    uiLog('INFO', 'Drop staged for local ingestion', {
      session_id: dropRequest.session_id,
      source_tab: dropRequest.source_tab,
      accepted: dropRequest.summary?.accepted ?? dropRequest.accepted_paths.length,
      skipped: dropRequest.summary?.skipped ?? (dropRequest.skipped || []).length,
      added,
      staged_total: localPaths.length,
    });
  }

  onMount(() => {
    window.addEventListener('lmz:refresh', handleGlobalRefresh);
    loadQueue('normal');
    fetchStats();
    connectMonitor();
    refreshLocalStatus();
    return () => {
      window.removeEventListener('lmz:refresh', handleGlobalRefresh);
      logSource?.close();
      if (logReconnectTimer !== null) clearTimeout(logReconnectTimer);
      if (parseTimer !== null) clearTimeout(parseTimer);
      stopLocalStatusPolling();
    };
  });
</script>

<div class="ingestion-container">
  <div class="mode-switch">
    <button class:active={ingestMode === 'online'} on:click={() => ingestMode = 'online'}>Online</button>
    <button class:active={ingestMode === 'local'} on:click={() => ingestMode = 'local'}>Local</button>
  </div>

  {#if ingestMode === 'online'}
    <div class="toolbar">
      <div class="queue-tabs">
        <button class:active={currentQueue === 'normal'} on:click={() => handleTabChange('normal')} disabled={running}>
          Normal {counts.normal || 0}
        </button>
        <button class:active={currentQueue === 'force'} on:click={() => handleTabChange('force')} disabled={running}>
          Force {counts.force || 0}
        </button>
        <button class:active={currentQueue === 'failed'} on:click={() => handleTabChange('failed')} disabled={running}>
          Failed {counts.failed || 0}
        </button>
        <span class="status-label online-bold">Ready: {readyCount}</span>
        <span class="status-label saved">{isDirty ? '* Unsaved' : 'Saved'}</span>
      </div>

      <div class="action-group">
        <button on:click={() => handleTabChange(currentQueue)} disabled={running}>Reload</button>
        <button on:click={openExternal} disabled={running}>Open</button>
        <button class="primary" on:click={startIngestion} disabled={running || currentQueue === 'failed'}>
          {running ? 'Worker Active...' : 'Start Ingestion'}
        </button>
      </div>
    </div>

    <div class="editor-area">
      <textarea bind:value={queueContent} on:input={onEditorInput} placeholder="Edit queue markdown here..."></textarea>
    </div>

    <div class="monitor-area">
      <div class="monitor-header">Ingestion Monitor</div>
      <div class="monitor-logs" bind:this={monitorContainer}>
        {#each monitorLogs as log (log.id)}
          <div class="log-line">
            <span class="time">{log.timestamp?.split(' ')[1] || log.timestamp || ''}</span>
            <span class="level {(log.level || 'INFO').toLowerCase()}">{log.level || 'INFO'}</span>
            <span class="platform-tag {log.platform ? log.platform.toLowerCase() : ''}">{log.platform ? `[${log.platform.toUpperCase()}]` : ''}</span>
            <span class="msg">{log.message?.trim()}</span>
          </div>
        {/each}
        {#if monitorLogs.length === 0}
          <div class="empty-monitor">Waiting for ingestion activity...</div>
        {/if}
      </div>
    </div>

    <div class="footer-btns">
      <button class:primary={isDirty} on:click={saveQueue} disabled={!isDirty || saving || running}>Save Changes</button>
      <button on:click={retryFailed} disabled={running || counts.failed === 0}>Retry Failed</button>
      <button on:click={clearFailed} disabled={running || counts.failed === 0}>Clear Failed</button>
    </div>
  {:else}
    <div class="local-mode" data-drop-zone="ingest-local">
      <div class="local-toolbar">
        <div class="action-group">
          <button on:click={pickLocalFiles} disabled={localStatus.running}>Add Files</button>
          <button on:click={pickLocalFolders} disabled={localStatus.running}>Add Folder</button>
          <button on:click={() => localPaths = []} disabled={localStatus.running || localPaths.length === 0}>Clear List</button>
        </div>
        <div class="action-group">
          <button class="primary" on:click={startLocalIngestion} disabled={localStatus.running || localPaths.length === 0}>
            {localStatus.running ? 'Local Ingest Running...' : 'Start Local Ingestion'}
          </button>
        </div>
      </div>

      <div class="local-defaults">
        <label>Artist <input bind:value={localDefaults.artist} placeholder="Optional default artist" /></label>
        <label>Platform <input bind:value={localDefaults.platform} placeholder="Local" /></label>
        <label>Source URL <input bind:value={localDefaults.source_url} placeholder="Optional default source url" /></label>
      </div>

      <div class="local-staging">
        <div class="monitor-header">Staged Paths ({localPaths.length})</div>
        <div class="local-list">
          {#if localPaths.length === 0}
            <div class="empty-monitor">No files/folders selected yet.</div>
          {:else}
            {#each localPaths as path, index}
              <div class="local-item">
                <span class="local-path">{path}</span>
                <button on:click={() => removeLocalPath(index)} disabled={localStatus.running}>Remove</button>
              </div>
            {/each}
          {/if}
        </div>
      </div>

      <div class="local-status">
        <div class="monitor-header">Local Run Status</div>
        <div class="status-grid">
          <span>Phase: {localStatus.phase}</span>
          <span>Scanned: {localStatus.scanned}</span>
          <span>Staged: {localStatus.staged}</span>
          <span>Queued: {localStatus.queued}</span>
          <span>Processed: {localStatus.processed}</span>
          <span>Ingested: {localStatus.summary.ingested}</span>
          <span>Review: {localStatus.summary.review}</span>
          <span>Failed: {localStatus.summary.failed}</span>
          <span>Duplicate: {localStatus.summary.duplicate}</span>
        </div>
        <div class="footer-btns">
          <button on:click={refreshLocalStatus}>Refresh</button>
          <button on:click={retryLocalFailed} disabled={localStatus.running || localStatus.failed_paths.length === 0}>Retry Failed Session</button>
        </div>
        <div class="local-results">
          {#each localStatus.results.slice(-120).reverse() as result}
            <div class="result-line">
              <span class="result-status {result.status}">{result.status}</span>
              <span class="result-name">{result.name}</span>
              <span class="result-message">{result.message}</span>
            </div>
          {/each}
          {#if localStatus.results.length === 0}
            <div class="empty-monitor">No local ingestion run yet.</div>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .ingestion-container {
    flex-grow: 1;
    display: flex;
    flex-direction: column;
    padding: 10px 15px;
    background: var(--bg-main);
    gap: 10px;
    overflow: hidden;
  }

  .mode-switch {
    display: flex;
    gap: 8px;
  }

  .mode-switch button {
    background: var(--bg-panel);
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 700;
  }

  .mode-switch button.active {
    background: var(--accent-primary);
    border-color: var(--accent-primary);
    color: #ffffff;
  }

  .toolbar, .local-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-shrink: 0;
  }

  .local-mode {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
    gap: 10px;
  }

  .queue-tabs {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .queue-tabs button {
    background: var(--bg-panel);
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 600;
  }

  .queue-tabs button.active {
    background: var(--accent-primary);
    border-color: var(--accent-primary);
    color: white;
  }

  .status-label {
    font-size: 11px;
    color: var(--text-muted);
    margin-left: 10px;
  }

  .online-bold {
    color: var(--text-main);
    font-weight: 700;
  }

  .action-group {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .editor-area {
    display: flex;
    flex-direction: column;
    flex-shrink: 1;
  }

  textarea {
    height: 35vh;
    min-height: 100px;
    max-height: calc(100vh - 320px);
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    font-family: 'Consolas', monospace;
    font-size: 13px;
    resize: vertical;
    padding: 15px;
    color: var(--text-main);
  }

  .monitor-area, .local-staging, .local-status {
    flex: 1;
    background: #010409;
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-height: 120px;
    flex-shrink: 1;
  }

  .monitor-header {
    background: rgba(255, 255, 255, 0.02);
    padding: 5px 10px;
    font-size: 12px;
    color: var(--accent-primary);
    text-align: left;
    border-bottom: 1px solid var(--border-dim);
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-weight: 600;
    flex-shrink: 0;
  }

  .monitor-logs, .local-list, .local-results {
    flex-grow: 1;
    overflow-y: auto;
    overflow-x: auto;
    padding: 10px;
    font-family: 'Consolas', monospace;
    font-size: 12px;
  }

  .log-line {
    margin-bottom: 2px;
    white-space: pre;
    width: max-content;
    padding-right: 15px;
  }

  .time {
    color: #484f58;
    margin-right: 10px;
  }

  .level {
    font-weight: bold;
    margin-right: 10px;
    width: 50px;
    display: inline-block;
    flex-shrink: 0;
  }

  .level.info { color: #58a6ff; }
  .level.warning { color: var(--accent-warning); }
  .level.error { color: var(--accent-danger); }

  .platform-tag {
    font-weight: bold;
    margin-right: 5px;
    min-width: 96px;
    display: inline-block;
  }

  .msg { color: #8b949e; }

  .empty-monitor {
    color: #30363d;
    text-align: center;
    margin-top: 20px;
    font-style: italic;
  }

  .footer-btns {
    display: flex;
    gap: 10px;
    flex-shrink: 0;
    padding: 8px 10px;
    border-top: 1px solid var(--border-dim);
  }

  .local-defaults {
    display: grid;
    grid-template-columns: 1fr 1fr 1.5fr;
    gap: 10px;
  }

  .local-defaults label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 11px;
    color: var(--text-muted);
  }

  .local-defaults input {
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    color: var(--text-main);
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 12px;
  }

  .local-item {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 8px;
  }

  .local-path {
    color: var(--text-main);
    word-break: break-all;
    flex-grow: 1;
  }

  .status-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
    padding: 10px;
    font-size: 12px;
    color: var(--text-main);
    border-bottom: 1px solid var(--border-dim);
  }

  .result-line {
    display: grid;
    grid-template-columns: 92px 200px 1fr;
    gap: 8px;
    margin-bottom: 6px;
    align-items: start;
  }

  .result-status {
    font-weight: 700;
    text-transform: uppercase;
    font-size: 11px;
  }

  .result-status.ingested { color: var(--accent-success); }
  .result-status.review { color: var(--accent-warning); }
  .result-status.failed { color: var(--accent-danger); }
  .result-status.duplicate { color: #8b949e; }

  .result-name {
    color: var(--text-main);
    word-break: break-word;
  }

  .result-message {
    color: var(--text-muted);
    word-break: break-word;
  }
</style>
