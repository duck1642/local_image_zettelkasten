<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import ConfirmationModal from './ConfirmationModal.svelte';
  import { log as uiLog } from './logger';
  import { apiFetch, apiUrl } from './api';
  import { runtimeSessionKey } from './runtimeStore';

  interface LogEntry {
    id?: number;
    timestamp: string;
    level: string;
    module: string;
    message: string;
    raw?: string;
    isRaw?: boolean;
    extras?: Record<string, any>;
    platform?: string;
  }

  type LogSource = 'startup' | 'vault' | 'console';

  let logs: LogEntry[] = [];
  let logIdCounter = 0;
  let currentFile = 'system.jsonl';
  let logSource: LogSource = 'startup';
  let sourceTouched = false;
  let currentMode: 'Normal' | 'Full' = 'Normal';
  let logLocationLabel = 'Startup logs';
  let logLocationMode: LogSource = 'startup';
  let vaultLogsAvailable = false;
  let eventSource: EventSource | null = null;
  let reconnectTimer: number | null = null;
  let reconnectAttempts = 0;
  let streamStatus: 'live' | 'reconnecting' | 'offline' = 'offline';
  let connectionToken = 0;
  let clearConfirmOpen = false;
  let clearBusy = false;
  let logContainer: HTMLElement;
  let searchText = '';
  let currentRuntimeSessionKey = '';
  const RECONNECT_BASE_MS = 800;
  const RECONNECT_MAX_MS = 8000;
  $: if ($runtimeSessionKey) {
    if (currentRuntimeSessionKey && currentRuntimeSessionKey !== $runtimeSessionKey) {
      reconnectForRuntimeSwitch();
    }
    currentRuntimeSessionKey = $runtimeSessionKey;
  }

  // Level filter: all on except DEBUG by default
  let levelFilters: Record<string, boolean> = {
    INFO: true,
    WARNING: true,
    ERROR: true,
    CRITICAL: true,
    OTHER: true,
    DEBUG: false
  };

  const startupLogFiles = [
    { title: 'Backend', value: 'system.jsonl' },
    { title: 'Frontend', value: 'svelte.jsonl' },
    { title: 'Auth', value: 'auth.jsonl' },
  ];

  const vaultLogFiles = [
    { title: 'Backend', value: 'system.jsonl' },
    { title: 'Frontend', value: 'svelte.jsonl' },
    { title: 'Local ingest', value: 'ingest_local.jsonl' },
    { title: 'Online ingest', value: 'ingest_online.jsonl' },
    { title: 'Review', value: 'review.jsonl' },
    { title: 'Auth', value: 'auth.jsonl' },
    { title: 'Audit', value: 'ingestion_audit.jsonl' },
  ];

  const consoleFile = { title: 'Console output', value: 'console.log' };

  $: activeLogFiles = logSource === 'startup' ? startupLogFiles : logSource === 'vault' ? vaultLogFiles : [consoleFile];
  $: effectiveFile = logSource === 'console' ? 'console.log' : currentFile;
  $: logScopeLabel = logSource === 'console' ? 'Console' : logSource === 'vault' ? logLocationLabel : 'Startup logs';
  $: clearTargetLabel = logSource === 'console' ? 'console output' : logSource === 'vault' ? 'vault logs' : 'startup logs';
  $: streamStatusLabel = streamStatus === 'live' ? 'Live' : streamStatus === 'reconnecting' ? 'Reconnecting' : 'Offline';

  // Fields to exclude from inline extras (already shown in columns)
  const HIDDEN_EXTRA_KEYS = new Set(['timestamp', 'level', 'module', 'message', 'platform']);

  function extractExtras(entry: any): Record<string, any> {
    const extras: Record<string, any> = {};
    for (const [key, value] of Object.entries(entry)) {
      if (!HIDDEN_EXTRA_KEYS.has(key) && key !== 'raw' && key !== 'isRaw' && key !== 'extras') {
        extras[key] = value;
      }
    }
    return extras;
  }

  function normalizeLevel(level: unknown) {
    const rawLevel = String(level || '').trim().toUpperCase();
    if (!rawLevel) return { level: 'OTHER', originalLevel: '' };
    if (Object.prototype.hasOwnProperty.call(levelFilters, rawLevel)) {
      return { level: rawLevel, originalLevel: rawLevel };
    }
    return { level: 'OTHER', originalLevel: rawLevel };
  }

  // Get module name from the current file to suppress redundant display
  function currentFileModule(): string {
    return effectiveFile.replace('.jsonl', '').replace('.log', '');
  }

  function shouldShowModule(mod: string): boolean {
    if (!mod || mod === 'root' || mod === 'logger') return false;
    if (mod === currentFileModule()) return false;
    return true;
  }

  function platformLabel(platform: string) {
    const value = (platform || '').trim();
    if (!value) return '';
    if (value === 'generic' || value === 'other') return 'OTHER URL';
    return value.toUpperCase();
  }

  function ansiToHtml(text: string) {
    const ansiColors: Record<string, string> = {
        '30': '#8b949e', '31': '#ff7b72', '32': '#3fb950', '33': '#d29922', '34': '#58a6ff', '35': '#d2a8ff', '36': '#56d4dd', '37': '#f0f6fc',
        '90': '#8b949e', '91': '#ff7b72', '92': '#3fb950', '93': '#d29922', '94': '#58a6ff', '95': '#d2a8ff', '96': '#56d4dd', '97': '#f0f6fc'
    };
    
    let html = text.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    html = html.replace(/\x1b\[([0-9;]*)m/g, (match, p1) => {
        if (p1 === '0' || p1 === '') return '</span>';
        const codes = p1.split(';');
        let style = '';
        for (const code of codes) {
            if (ansiColors[code]) style += `color: ${ansiColors[code]};`;
            if (code === '1') style += `font-weight: bold;`;
        }
        return style ? `<span style="${style}">` : '<span>';
    });
    return html;
  }

  function nextReconnectDelayMs() {
    const exponential = Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * Math.pow(2, reconnectAttempts));
    const jitter = Math.floor(Math.random() * 300);
    reconnectAttempts += 1;
    return Math.min(RECONNECT_MAX_MS, exponential + jitter);
  }

  function scheduleReconnect() {
    if (reconnectTimer !== null) return;
    streamStatus = 'reconnecting';
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      connectToLogs();
    }, nextReconnectDelayMs());
  }

  function filesForSource(source: LogSource) {
    if (source === 'startup') return startupLogFiles;
    if (source === 'vault') return vaultLogFiles;
    return [consoleFile];
  }

  async function connectToLogs() {
    const token = ++connectionToken;
    if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    streamStatus = 'reconnecting';
    logs = [];
    await loadLogLocation();
    if (token !== connectionToken) return;

    const nextSource = new EventSource(apiUrl(`/api/logs?filename=${effectiveFile}&source=${logSource}`));
    eventSource = nextSource;
    nextSource.onopen = () => {
      if (token !== connectionToken) return;
      reconnectAttempts = 0;
      streamStatus = 'live';
    };
    nextSource.onmessage = (e) => {
      if (token !== connectionToken) return;
      reconnectAttempts = 0;
      streamStatus = 'live';
      try {
        const raw = e.data;
        const parsed = JSON.parse(raw);
        const normalized = normalizeLevel(parsed.level);
        const extras = extractExtras(parsed);
        if (normalized.level === 'OTHER' && normalized.originalLevel) {
          extras.original_level = normalized.originalLevel;
        }
        const entry: LogEntry = {
          timestamp: parsed.timestamp || '',
          level: normalized.level,
          module: parsed.module || '',
          message: parsed.message || '',
          platform: parsed.platform || '',
          raw,
          isRaw: false,
          extras
        };

        appendLog(entry);
      } catch {
          // Raw terminal line with ANSI or unknown text
          const entry: LogEntry = {
              timestamp: '',
              level: '',
              module: '',
              message: ansiToHtml(e.data),
              raw: e.data,
              isRaw: true
          };
          appendLog(entry);
      }
    };
    nextSource.onerror = () => {
        if (token !== connectionToken) return;
        nextSource.close();
        if (eventSource === nextSource) eventSource = null;
        scheduleReconnect();
    };
  }

  async function loadLogLocation() {
    try {
      const sourceParam = sourceTouched ? logSource : 'active';
      const response = await apiFetch(`/api/logs/location?source=${sourceParam}`);
      if (!response.ok) {
        if (logSource === 'vault') logSource = 'startup';
        return;
      }
      const payload = await response.json();
      vaultLogsAvailable = Boolean(payload.vault_available);
      if (!sourceTouched) {
        logSource = payload.active_mode === 'vault' ? 'vault' : 'startup';
      }
      logLocationMode = payload.mode === 'console' ? 'console' : payload.mode === 'vault' ? 'vault' : 'startup';
      logLocationLabel = payload.label || (payload.mode === 'console' ? 'Console' : payload.mode === 'vault' ? 'Vault logs' : 'Startup logs');
    } catch {
      vaultLogsAvailable = false;
      logSource = 'startup';
      logLocationMode = 'startup';
      logLocationLabel = 'Startup logs';
    }
  }

  function reconnectForRuntimeSwitch() {
    connectionToken += 1;
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    eventSource?.close();
    eventSource = null;
    logs = [];
    logIdCounter = 0;
    reconnectAttempts = 0;
    streamStatus = 'offline';
    sourceTouched = false;
    connectToLogs();
  }

  function isNearBottom(node: HTMLElement) {
    return node.scrollHeight - node.scrollTop - node.clientHeight < 48;
  }

  function appendLog(entry: LogEntry) {
    entry.id = logIdCounter++;
    const shouldScroll = !logContainer || isNearBottom(logContainer);
    logs.push(entry);
    if (logs.length > 400) logs.splice(0, logs.length - 400);
    logs = logs;
    if (shouldScroll) {
      tick().then(() => {
        if (logContainer) logContainer.scrollTop = logContainer.scrollHeight;
      });
    }
  }

  async function openExternal() {
    try {
      const response = await apiFetch(`/api/logs/open?filename=${effectiveFile}&source=${logSource}`, { method: 'POST' });
      if (!response.ok) throw new Error(await response.text());
    } catch (e) {
      console.error(e);
      alert('Failed to open log file.');
    }
  }

  function requestClearLogs() {
    clearConfirmOpen = true;
  }

  async function confirmClearLogs() {
    if (clearBusy) return;
    clearBusy = true;
    try {
        const response = await apiFetch(`/api/logs/clear?source=${logSource}`, { method: 'POST' });
        if (!response.ok) throw new Error(await response.text());
        logs = [];
        clearConfirmOpen = false;
        uiLog('INFO', 'Logs cleared by user.', { source: logSource });
        connectToLogs();
    } catch (e) {
        console.error(e);
        alert("Failed to clear logs.");
    } finally {
        clearBusy = false;
    }
  }

  function handleFileChange() {
    uiLog('DEBUG', `Switched log view to ${effectiveFile}`);
    streamStatus = 'offline';
    connectToLogs();
  }

  function handleSourceChange() {
    sourceTouched = true;
    const nextFiles = filesForSource(logSource);
    const allowedFiles = nextFiles.map((file) => file.value);
    if (!allowedFiles.includes(currentFile)) {
      currentFile = nextFiles[0]?.value || 'system.jsonl';
    }
    streamStatus = 'offline';
    connectToLogs();
  }

  function handleGlobalRefresh(event: Event) {
    const detail = (event as CustomEvent).detail || {};
    if (detail.tab !== 'logs') return;
    uiLog('INFO', 'Logs view refresh requested', { file: effectiveFile, source: logSource });
    connectToLogs();
  }

  function toggleLevel(level: string) {
    levelFilters[level] = !levelFilters[level];
    levelFilters = levelFilters; // trigger reactivity
  }

  function formatExtraValue(value: any): string {
    let str = typeof value === 'string' ? value : JSON.stringify(value);
    // Truncate long values (paths, urls) for readability
    if (str.length > 80) str = str.substring(0, 77) + '...';
    return str;
  }

  // Filtered logs based on level and search
  $: filteredLogs = logs.filter(log => {
    // Raw lines always pass level filter
    if (!log.isRaw) {
      const level = log.level?.toUpperCase() || 'OTHER';
      if (!levelFilters[level]) return false;
    }
    // Search filter
    if (searchText) {
      const q = searchText.toLowerCase();
      const extras = log.extras
        ? Object.entries(log.extras).map(([key, value]) => `${key} ${formatExtraValue(value)}`).join(' ')
        : '';
      const haystack = [
        log.timestamp,
        log.level,
        log.module,
        log.platform,
        log.message,
        extras,
        log.raw || ''
      ].join(' ').toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });

  onMount(() => {
    window.addEventListener('lmz:refresh', handleGlobalRefresh);
    connectToLogs();
  });
  onDestroy(() => {
    window.removeEventListener('lmz:refresh', handleGlobalRefresh);
    connectionToken += 1;
    eventSource?.close();
    if (reconnectTimer !== null) clearTimeout(reconnectTimer);
  });
</script>

<div class="logs-container">
    <div class="logs-toolbar">
      <div class="toolbar-row primary-row">
        <label class="toolbar-field source-field">
          <span>Source</span>
          <select bind:value={logSource} on:change={handleSourceChange}>
            <option value="startup">Startup logs</option>
            {#if vaultLogsAvailable || logSource === 'vault'}
                <option value="vault">Vault logs</option>
            {/if}
            <option value="console">Console</option>
          </select>
        </label>

        <label class="toolbar-field file-field">
          <span>File</span>
          <select bind:value={currentFile} on:change={handleFileChange} disabled={logSource === 'console'}>
            {#each activeLogFiles as file}
                <option value={file.value}>{file.title}</option>
            {/each}
          </select>
        </label>

        <label class="toolbar-field view-field">
          <span>View</span>
          <select bind:value={currentMode}>
            <option value="Normal">Normal View</option>
            <option value="Full">Full (Raw JSON)</option>
          </select>
        </label>

        <span class="stream-status {streamStatus}">{streamStatusLabel}</span>
        <span class="log-location" title={logScopeLabel}>{logScopeLabel}</span>

        <div class="toolbar-actions">
          <button type="button" on:click={connectToLogs}>Reload</button>
          <button type="button" on:click={openExternal}>Open</button>
          <button type="button" class="danger-ghost" on:click={requestClearLogs}>Clear</button>
        </div>
      </div>

      <div class="toolbar-row secondary-row">
        <div class="level-filters">
            {#each Object.entries(levelFilters) as [level, active]}
                <button
                    type="button"
                    class="level-pill {level.toLowerCase()}"
                    class:active={active}
                    on:click={() => toggleLevel(level)}
                >{level}</button>
            {/each}
        </div>

        <input
            class="search-box"
            type="text"
            placeholder="Filter loaded logs..."
            bind:value={searchText}
        />

        <span class="log-hint">Showing streamed/tail rows only.</span>
      </div>
    </div>

    <div class="log-output sleek-scrollbar" bind:this={logContainer}>
        {#each filteredLogs as log (log.id)}
            {#if currentMode === 'Normal'}
                <div class="line">
                    {#if log.isRaw}
                        <span class="message raw-terminal">{@html log.message}</span>
                    {:else}
                        <span class="timestamp">{log.timestamp}</span>
                        <span class="level {log.level.toLowerCase()}">{log.level}</span>
                        <span class="platform-tag {log.platform ? log.platform.toLowerCase() : ''}">{log.platform ? `[${platformLabel(log.platform)}]` : ''}</span>
                        {#if shouldShowModule(log.module)}
                            <span class="module">[{log.module}]</span>
                        {/if}
                        <span class="message">{log.message?.trim()}</span>
                        {#if log.extras && Object.keys(log.extras).length > 0}
                            <span class="extras">
                                {#each Object.entries(log.extras) as [key, value]}
                                    <span class="extra-pair"><span class="extra-key">{key}</span>=<span class="extra-val">{formatExtraValue(value)}</span></span>
                                {/each}
                            </span>
                        {/if}
                    {/if}
                </div>
            {:else}
                <div class="line raw">
                    {log.raw}
                </div>
            {/if}
        {/each}
    </div>
</div>

<ConfirmationModal
  open={clearConfirmOpen}
  title={`Clear ${clearTargetLabel}?`}
  confirmLabel={clearBusy ? 'Clearing...' : 'Clear logs'}
  danger={true}
  busy={clearBusy}
  on:cancel={() => (clearConfirmOpen = false)}
  on:confirm={confirmClearLogs}
>
  <p>This will clear the current {clearTargetLabel} files. This cannot be undone.</p>
</ConfirmationModal>

<style>
    .logs-container {
        flex-grow: 1;
        background: var(--bg-main);
        display: flex;
        flex-direction: column;
        padding: 10px 15px;
        overflow: hidden;
    }

    .logs-toolbar {
        display: grid;
        gap: 8px;
        margin-bottom: 10px;
        background: var(--bg-panel);
        padding: 8px 10px;
        border-radius: 8px;
        border: 1px solid var(--border-dim);
    }

    .toolbar-row {
        display: flex;
        align-items: center;
        gap: 8px;
        min-width: 0;
    }

    .primary-row {
        flex-wrap: nowrap;
    }

    .secondary-row {
        flex-wrap: wrap;
    }

    .toolbar-field {
        display: flex;
        align-items: center;
        gap: 6px;
        min-width: 0;
    }

    .toolbar-field span {
        color: var(--text-muted);
        font-size: 11px;
        font-weight: 600;
        white-space: nowrap;
    }

    .source-field select { width: 128px; }
    .file-field select { width: 148px; }
    .view-field select { width: 148px; }

    select {
        background: var(--bg-input);
        border: 1px solid var(--border-dim);
        color: var(--text-main);
        height: 28px;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 12px;
    }

    .stream-status {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 88px;
        height: 24px;
        padding: 0 10px;
        border: 1px solid var(--border-dim);
        border-radius: 999px;
        color: var(--text-muted);
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0;
        text-transform: uppercase;
    }

    .stream-status.live {
        border-color: rgba(63, 185, 80, 0.45);
        color: #3fb950;
        background: rgba(63, 185, 80, 0.08);
    }

    .stream-status.reconnecting {
        border-color: rgba(210, 153, 34, 0.45);
        color: var(--accent-warning);
        background: rgba(210, 153, 34, 0.08);
    }

    .stream-status.offline {
        border-color: rgba(139, 148, 158, 0.28);
        color: #8b949e;
        background: rgba(139, 148, 158, 0.06);
    }

    .log-location {
        flex: 1;
        min-width: 120px;
        overflow: hidden;
        color: var(--text-muted);
        font-size: 12px;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .toolbar-actions {
        display: flex;
        gap: 6px;
        margin-left: auto;
    }

    .search-box {
        background: var(--bg-input);
        border: 1px solid var(--border-dim);
        color: var(--text-main);
        height: 28px;
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 12px;
        width: min(320px, 28vw);
        min-width: 180px;
        outline: none;
    }
    .search-box::placeholder { color: #484f58; }
    .search-box:focus { border-color: #58a6ff; }

    .level-filters {
        display: flex;
        gap: 4px;
        flex-wrap: wrap;
    }

    .level-pill {
        padding: 2px 10px;
        font-size: 11px;
        font-weight: 600;
        border-radius: 12px;
        border: 1px solid var(--border-dim);
        background: transparent;
        cursor: pointer;
        opacity: 0.35;
        color: #c9d1d9;
    }
    .level-pill.active { opacity: 1; }
    .level-pill.info.active { background: rgba(201, 209, 217, 0.12); color: #c9d1d9; }
    .level-pill.warning.active { background: rgba(210, 153, 34, 0.15); color: var(--accent-warning); }
    .level-pill.error.active { background: rgba(218, 54, 51, 0.15); color: var(--accent-danger); }
    .level-pill.critical.active { background: rgba(248, 81, 73, 0.18); color: #ff7b72; }
    .level-pill.other.active { background: rgba(139, 148, 158, 0.16); color: #8b949e; }
    .level-pill.debug.active { background: rgba(72, 79, 88, 0.2); color: #8b949e; }

    .log-hint {
        color: var(--text-muted);
        font-size: 11px;
        white-space: nowrap;
    }

    .log-output {
        flex-grow: 1;
        background: #010409;
        border: 1px solid var(--border-dim);
        border-radius: 8px;
        padding: 12px;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 12px;
        overflow-y: auto;
        overflow-x: auto;
    }
    .log-output::-webkit-scrollbar-corner {
        background: transparent;
    }

    .line { 
        margin-bottom: 2px; 
        line-height: 1.45; 
        white-space: pre; 
        width: max-content;
        padding-right: 15px;
    }
    .line.raw { 
        color: #8b949e; 
        font-size: 11px; 
        margin-bottom: 6px; 
        border-bottom: 1px solid #161b22; 
        padding-bottom: 3px; 
        font-family: 'Consolas', monospace;
        white-space: pre;
        width: max-content;
        padding-right: 15px;
    }
    
    .timestamp { color: #58a6ff; margin-right: 8px; min-width: 152px; display: inline-block; }
    .level { font-weight: bold; margin-right: 8px; min-width: 56px; display: inline-block; }
    .module { color: var(--accent-purple); margin-right: 6px; }
    
    .level.info { color: #c9d1d9; }
    .level.warning { color: var(--accent-warning); }
    .level.error { color: var(--accent-danger); }
    .level.critical { color: #ff7b72; }
    .level.other { color: #8b949e; }
    .level.debug { color: #484f58; }
    
    .message { color: #c9d1d9; }
    
    .platform-tag { font-weight: bold; margin-right: 6px; min-width: 96px; display: inline-block; }
    .platform-tag.youtube { color: #ff4a4a; }
    .platform-tag.pixiv { color: #0096fa; }
    .platform-tag.x { color: #1da1f2; }
    .platform-tag.instagram { color: #e1306c; }
    .platform-tag.pinterest { color: #e60023; }

    .extras {
        margin-left: 6px;
        color: #484f58;
        font-size: 11px;
    }
    .extra-pair {
        margin-left: 6px;
    }
    .extra-key {
        color: #6e7681;
    }
    .extra-val {
        color: #8b949e;
    }

    button {
        background: var(--bg-input);
        border: 1px solid var(--border-dim);
        color: var(--text-main);
        border-radius: 6px;
        padding: 4px 12px;
        font-size: 11px;
        font-weight: 600;
        cursor: pointer;
    }

    button:hover {
        border-color: var(--border-hover);
        color: var(--text-bright);
    }

    .danger-ghost {
        color: #ff7b72;
        border-color: rgba(248, 81, 73, 0.35);
        background: rgba(248, 81, 73, 0.06);
    }

    .danger-ghost:hover {
        border-color: rgba(248, 81, 73, 0.65);
        background: rgba(248, 81, 73, 0.12);
    }

    @media (max-width: 980px) {
        .primary-row {
            flex-wrap: wrap;
        }

        .log-location {
            flex-basis: 100%;
            order: 10;
        }

        .toolbar-actions {
            margin-left: 0;
        }

        .search-box {
            width: 100%;
            max-width: 360px;
        }
    }
</style>
