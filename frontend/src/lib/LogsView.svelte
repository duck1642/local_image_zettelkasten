<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { log as uiLog } from './logger';
  import { apiFetch, apiUrl } from './api';

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

  let logs: LogEntry[] = [];
  let logIdCounter = 0;
  let currentFile = 'system.jsonl';
  let currentMode: 'Normal' | 'Full' = 'Normal';
  let eventSource: EventSource | null = null;
  let reconnectTimer: number | null = null;
  let logContainer: HTMLElement;
  let searchText = '';

  // Level filter: all on except DEBUG by default
  let levelFilters: Record<string, boolean> = {
    INFO: true,
    WARNING: true,
    ERROR: true,
    DEBUG: false
  };

  const logFiles = [
    { label: 'system.jsonl (Backend)', value: 'system.jsonl' },
    { label: 'terminal.log (Python Stdout)', value: 'terminal.log' },
    { label: 'svelte.jsonl (Frontend)', value: 'svelte.jsonl' },
    { label: 'ingestion.jsonl (Worker)', value: 'ingestion.jsonl' },
    { label: 'review.jsonl (Review)', value: 'review.jsonl' },
    { label: 'auth.jsonl (Auth)', value: 'auth.jsonl' },
    { label: 'activity.jsonl (Audit)', value: 'activity.jsonl' },
  ];

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

  // Get module name from the current file to suppress redundant display
  function currentFileModule(): string {
    return currentFile.replace('.jsonl', '').replace('.log', '');
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

  function connectToLogs() {
    if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    if (eventSource) eventSource.close();
    logs = [];

    eventSource = new EventSource(apiUrl(`/api/logs?filename=${currentFile}`));
    eventSource.onmessage = (e) => {
      try {
        const raw = e.data;
        const parsed = JSON.parse(raw);
        const entry: LogEntry = {
          timestamp: parsed.timestamp || '',
          level: parsed.level || '',
          module: parsed.module || '',
          message: parsed.message || '',
          platform: parsed.platform || '',
          raw,
          isRaw: false,
          extras: extractExtras(parsed)
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
    eventSource.onerror = () => {
        eventSource?.close();
        reconnectTimer = window.setTimeout(() => {
            reconnectTimer = null;
            connectToLogs();
        }, 2000);
    };
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
      await apiFetch(`/api/logs/open?filename=${currentFile}`, { method: 'POST' });
    } catch (e) { console.error(e); }
  }

  async function clearLogs() {
    if (!confirm("Are you sure you want to clear all log files? This cannot be undone.")) return;
    try {
        await apiFetch(`/api/logs/clear`, { method: 'POST' });
        logs = [];
        uiLog('INFO', 'All logs cleared by user.');
        connectToLogs();
    } catch (e) {
        console.error(e);
        alert("Failed to clear logs.");
    }
  }

  function handleFileChange() {
    uiLog('DEBUG', `Switched log view to ${currentFile}`);
    connectToLogs();
  }

  function handleGlobalRefresh(event: Event) {
    const detail = (event as CustomEvent).detail || {};
    if (detail.tab !== 'logs') return;
    uiLog('INFO', 'Logs view refresh requested', { file: currentFile });
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
    if (!log.isRaw && log.level && !levelFilters[log.level.toUpperCase()]) return false;
    // Search filter
    if (searchText) {
      const q = searchText.toLowerCase();
      const haystack = (log.message + ' ' + (log.raw || '')).toLowerCase();
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
    eventSource?.close();
    if (reconnectTimer !== null) clearTimeout(reconnectTimer);
  });
</script>

<div class="logs-container">
    <div class="toolbar">
        <select bind:value={currentFile} on:change={handleFileChange}>
            {#each logFiles as file}
                <option value={file.value}>{file.label}</option>
            {/each}
        </select>

        <select bind:value={currentMode}>
            <option value="Normal">Normal View</option>
            <option value="Full">Full (Raw JSON)</option>
        </select>

        <div class="level-filters">
            {#each Object.entries(levelFilters) as [level, active]}
                <button
                    class="level-pill {level.toLowerCase()}"
                    class:active={active}
                    on:click={() => toggleLevel(level)}
                >{level}</button>
            {/each}
        </div>

        <input
            class="search-box"
            type="text"
            placeholder="Search logs..."
            bind:value={searchText}
        />

        <div class="spacer"></div>

        <button on:click={connectToLogs}>Reload</button>
        <button on:click={clearLogs}>Clear Logs</button>
        <button on:click={openExternal}>Open Externally</button>
    </div>

    <div class="log-output" bind:this={logContainer}>
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

<style>
    .logs-container {
        flex-grow: 1;
        background: var(--bg-main);
        display: flex;
        flex-direction: column;
        padding: 10px 15px;
        overflow: hidden;
    }

    .toolbar {
        display: flex;
        gap: 8px;
        align-items: center;
        margin-bottom: 10px;
        background: var(--bg-panel);
        padding: 6px 12px;
        border-radius: 8px;
        border: 1px solid var(--border-dim);
        flex-wrap: wrap;
    }

    .spacer { flex-grow: 1; }

    select {
        background: var(--bg-input);
        border: 1px solid var(--border-dim);
        color: var(--text-main);
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 12px;
    }

    .search-box {
        background: var(--bg-input);
        border: 1px solid var(--border-dim);
        color: var(--text-main);
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 12px;
        width: 160px;
        outline: none;
    }
    .search-box::placeholder { color: #484f58; }
    .search-box:focus { border-color: #58a6ff; }

    .level-filters {
        display: flex;
        gap: 4px;
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
        transition: opacity 0.15s, background 0.15s;
        color: #c9d1d9;
    }
    .level-pill.active { opacity: 1; }
    .level-pill.info.active { background: rgba(201, 209, 217, 0.12); color: #c9d1d9; }
    .level-pill.warning.active { background: rgba(210, 153, 34, 0.15); color: var(--accent-warning); }
    .level-pill.error.active { background: rgba(218, 54, 51, 0.15); color: var(--accent-danger); }
    .level-pill.debug.active { background: rgba(72, 79, 88, 0.2); color: #8b949e; }

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
        padding: 4px 12px;
        font-size: 11px;
        font-weight: 600;
    }
</style>
