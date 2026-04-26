<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { log as uiLog } from './logger';

  interface LogEntry {
    timestamp: string;
    level: string;
    module: string;
    message: string;
    raw?: string;
    isRaw?: boolean;
  }

  let logs: LogEntry[] = [];
  let currentFile = 'system.log';
  let currentMode: 'Normal' | 'Full' = 'Normal';
  let showDebug = true;
  let eventSource: EventSource | null = null;
  let logContainer: HTMLElement;

  const logFiles = [
    { label: 'system.log (Backend)', value: 'system.log' },
    { label: 'terminal.log (Python Stdout)', value: 'terminal.log' },
    { label: 'svelte.log (Frontend)', value: 'svelte.log' },
    { label: 'tauri.log (Shell)', value: 'tauri.log' },
    { label: 'ingestion.log (Worker)', value: 'ingestion.log' },
    { label: 'pyui.log (Legacy)', value: 'pyui.log' }
  ];

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
    if (eventSource) eventSource.close();
    logs = [];
    
    eventSource = new EventSource(`http://localhost:8000/api/logs?filename=${currentFile}`);
    eventSource.onmessage = (e) => {
      try {
        const raw = e.data;
        const entry = JSON.parse(raw);
        entry.raw = raw;

        logs = [...logs, entry].slice(-400);
        setTimeout(() => { if (logContainer) logContainer.scrollTop = logContainer.scrollHeight; }, 30);
      } catch {
          // Try to parse Tauri log format: [2026-04-25][09:40:06][tauri_plugin_shell::process][DEBUG] Message
          const tauriMatch = e.data.match(/^\[(.*?)\]\[(.*?)\]\[(.*?)\]\[(.*?)\] (.*)$/);
          
          if (tauriMatch) {
              const entry = {
                  timestamp: `${tauriMatch[1]} ${tauriMatch[2]}`,
                  level: tauriMatch[4],
                  module: tauriMatch[3],
                  message: tauriMatch[5],
                  raw: e.data,
                  isRaw: false
              };
              logs = [...logs, entry].slice(-400);
          } else {
              // Raw terminal line with ANSI or unknown text
              const entry = {
                  timestamp: '',
                  level: '',
                  module: '',
                  message: ansiToHtml(e.data),
                  raw: e.data,
                  isRaw: true
              };
              logs = [...logs, entry].slice(-400);
          }
          setTimeout(() => { if (logContainer) logContainer.scrollTop = logContainer.scrollHeight; }, 30);
      }
    };
  }

  async function openExternal() {
    try {
      await fetch(`http://localhost:8000/api/logs/open?filename=${currentFile}`, { method: 'POST' });
    } catch (e) { console.error(e); }
  }

  function handleFileChange() {
    uiLog('DEBUG', `Switched log view to ${currentFile}`);
    connectToLogs();
  }

  onMount(connectToLogs);
  onDestroy(() => eventSource?.close());
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

        <label class="check-label">
            <input type="checkbox" bind:checked={showDebug} /> 
            Show Debug
        </label>

        <div class="spacer"></div>

        <button on:click={connectToLogs}>Reload</button>
        <button on:click={openExternal}>Open Externally</button>
    </div>

    <div class="log-output" bind:this={logContainer}>
        {#each logs as log}
            {#if showDebug || log.level !== 'DEBUG'}
                {#if currentMode === 'Normal'}
                    <div class="line">
                        {#if log.isRaw}
                            <span class="message raw-terminal">{@html log.message}</span>
                        {:else}
                            <span class="timestamp">{log.timestamp}</span>
                            <span class="level {log.level.toLowerCase()}">{log.level}</span>
                            <span class="module">[{log.module}]</span>
                            <span class="message">{log.message}</span>
                        {/if}
                    </div>
                {:else}
                    <div class="line raw">
                        {log.raw}
                    </div>
                {/if}
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
        gap: 12px;
        align-items: center;
        margin-bottom: 12px;
        background: var(--bg-panel);
        padding: 8px 15px;
        border-radius: 8px;
        border: 1px solid var(--border-dim);
    }

    .spacer { flex-grow: 1; }

    select {
        background: var(--bg-input);
        border: 1px solid var(--border-dim);
        color: var(--text-main);
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 13px;
    }

    .check-label {
        font-size: 13px;
        display: flex;
        align-items: center;
        gap: 6px;
        color: var(--text-main);
        cursor: pointer;
    }

    .log-output {
        flex-grow: 1;
        background: #010409;
        border: 1px solid var(--border-dim);
        border-radius: 8px;
        padding: 15px;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 12px;
        overflow-y: auto;
        overflow-x: auto;
    }

    .line { 
        margin-bottom: 4px; 
        line-height: 1.4; 
        white-space: pre; 
        width: max-content;
        padding-right: 15px;
    }
    .line.raw { 
        color: #8b949e; 
        font-size: 11px; 
        margin-bottom: 8px; 
        border-bottom: 1px solid #161b22; 
        padding-bottom: 4px; 
        font-family: 'Consolas', monospace;
        white-space: pre;
        width: max-content;
        padding-right: 15px;
    }
    
    .timestamp { color: #58a6ff; margin-right: 12px; }
    .level { font-weight: bold; margin-right: 12px; min-width: 60px; display: inline-block; }
    .module { color: var(--accent-purple); margin-right: 12px; }
    
    .level.info { color: #c9d1d9; }
    .level.warning { color: var(--accent-warning); }
    .level.error { color: var(--accent-danger); }
    .level.debug { color: #484f58; }
    
    .message { color: #c9d1d9; }

    button {
        background: var(--bg-input);
        padding: 4px 15px;
        font-size: 12px;
        font-weight: 600;
    }
</style>
