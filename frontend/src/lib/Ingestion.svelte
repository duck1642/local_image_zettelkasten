<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { log as uiLog } from './logger';

  let currentQueue: 'normal' | 'force' | 'failed' = 'normal';
  let queueContent = '';
  let counts = { normal: 0, force: 0, failed: 0 };
  let saving = false;
  let running = false;
  let isDirty = false;
  let parseTimer: any = null;

  // Monitor Logs
  let monitorLogs: any[] = [];
  let logSource: EventSource | null = null;
  let monitorContainer: HTMLElement;

  function connectMonitor() {
    if (logSource) logSource.close();
    // Read from the structured ingestion log
    logSource = new EventSource(`http://localhost:8000/api/logs?filename=ingestion.jsonl`);
    logSource.onmessage = (e) => {
        try {
            const entry = JSON.parse(e.data);
            monitorLogs = [...monitorLogs, entry].slice(-150);
            setTimeout(() => { if (monitorContainer) monitorContainer.scrollTop = monitorContainer.scrollHeight; }, 30);
        } catch { }
    };
  }

  async function loadQueue(name: string) {
    try {
      const res = await fetch(`http://localhost:8000/api/queue/${name}`);
      const data = await res.json();
      queueContent = data.content;
      isDirty = false;
    } catch (e) { console.error(e); }
  }

  async function fetchStats() {
    if (isDirty) return; // don't overwrite live counts while editing
    try {
      const res = await fetch('http://localhost:8000/api/queue-stats');
      counts = await res.json();
    } catch (e) { console.error(e); }
  }

  function handleTabChange(name: 'normal' | 'force' | 'failed') {
    if (isDirty) { 
        if (!confirm('You have unsaved changes. Discard them?')) return; 
    }
    currentQueue = name;
    loadQueue(name);
  }

  async function saveQueue() {
    saving = true;
    try {
      await fetch(`http://localhost:8000/api/queue/${currentQueue}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: queueContent })
      });
      isDirty = false;
      await fetchStats();
      uiLog('INFO', `Queue ${currentQueue} saved`);
    } finally { saving = false; }
  }

  async function startIngestion() {
    if (currentQueue === 'failed') {
        alert("Failed queue cannot be started directly. Use Retry Failed.");
        return;
    }
    if (isDirty) await saveQueue();
    running = true;
    uiLog('INFO', `Starting ingestion for queue: ${currentQueue}`);
    try {
      await fetch(`http://localhost:8000/api/ingest/${currentQueue}`, { method: 'POST' });
    } finally { 
        setTimeout(() => running = false, 5000); 
    }
  }

  function onEditorInput() {
    isDirty = true;
    clearTimeout(parseTimer);
    parseTimer = setTimeout(async () => {
        try {
            const res = await fetch(`http://localhost:8000/api/queue/${currentQueue}/parse`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: queueContent })
            });
            const data = await res.json();
            counts = { ...counts, [currentQueue]: data.count };
        } catch {}
    }, 400);
  }

  async function openExternal() {
      if (isDirty) {
          if (confirm("Save changes before opening?")) {
              await saveQueue();
          } else {
              return;
          }
      }
      try {
          await fetch(`http://localhost:8000/api/queue/${currentQueue}/open`, { method: 'POST' });
      } catch (e) { console.error(e); }
  }

  async function retryFailed() {
      if (isDirty) {
          if (!confirm("Discard unsaved changes before retrying?")) return;
      }
      if (counts.failed === 0) {
          alert("No failed URLs found.");
          return;
      }
      const target = prompt(`Retry ${counts.failed} failed URLs?\n\nType 'normal' or 'force' to choose destination:`, "normal");
      if (target === 'normal' || target === 'force') {
          try {
              const res = await fetch(`http://localhost:8000/api/queue/actions/retry-failed`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ target })
              });
              const data = await res.json();
              alert(`Moved ${data.moved} URLs to ${target}.`);
              counts = data.counts;
              if (currentQueue === target || currentQueue === 'failed') {
                  loadQueue(currentQueue);
              }
          } catch(e) { console.error(e); }
      }
  }

  async function clearFailed() {
      if (isDirty) {
          if (!confirm("Discard unsaved changes before clearing?")) return;
      }
      if (counts.failed === 0) {
          alert("No failed URLs found.");
          return;
      }
      if (confirm("Clear failed_links.md?")) {
          try {
              const res = await fetch(`http://localhost:8000/api/queue/actions/clear-failed`, { method: 'POST' });
              const data = await res.json();
              counts = data.counts;
              if (currentQueue === 'failed') loadQueue('failed');
          } catch(e) { console.error(e); }
      }
  }

  $: readyCount = (counts.normal || 0) + (counts.force || 0);

  onMount(() => {
    loadQueue('normal');
    fetchStats();
    connectMonitor();
    const interval = setInterval(fetchStats, 5000);
    return () => {
        clearInterval(interval);
        logSource?.close();
    };
  });
</script>

<div class="ingestion-container">
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
      <span class="status-label" style="color: var(--text-main); font-weight: bold;">Ready: {readyCount}</span>
      <span class="status-label saved">{isDirty ? '● Unsaved' : 'Saved'}</span>
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
    <textarea 
        bind:value={queueContent} 
        on:input={onEditorInput}
        placeholder="Edit queue markdown here..."
    ></textarea>
  </div>

  <div class="monitor-area">
    <div class="monitor-header">Ingestion Monitor</div>
    <div class="monitor-logs" bind:this={monitorContainer}>
        {#each monitorLogs as log}
            <div class="log-line">
                <span class="time">{log.timestamp?.split(' ')[1] || log.timestamp || ''}</span>
                <span class="level {(log.level || 'INFO').toLowerCase()}">{log.level || 'INFO'}</span>
                {#if log.platform}
                    <span class="platform-tag {log.platform.toLowerCase()}">[{log.platform.toUpperCase()}]</span>
                {/if}
                <span class="msg">{log.message}</span>
            </div>
        {/each}
        {#if monitorLogs.length === 0}
            <div class="empty-monitor">Waiting for ingestion activity...</div>
        {/if}
    </div>
  </div>

  <div class="footer-btns">
      <button on:click={saveQueue} disabled={!isDirty || saving || running}>Save Changes</button>
      <button on:click={retryFailed} disabled={running || counts.failed === 0}>Retry Failed</button>
      <button on:click={clearFailed} disabled={running || counts.failed === 0}>Clear Failed</button>
  </div>
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

  .toolbar { display: flex; justify-content: space-between; align-items: center; }
  .queue-tabs { display: flex; gap: 8px; align-items: center; }
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

  .status-label { font-size: 11px; color: var(--text-muted); margin-left: 10px; }
  .action-group { display: flex; gap: 8px; align-items: center; }
  .check-label { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-main); margin-right: 10px; }

  .editor-area { flex: 2; display: flex; min-height: 200px; }
  textarea {
    flex-grow: 1;
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    font-family: 'Consolas', monospace;
    font-size: 13px;
    resize: none;
    padding: 15px;
    color: var(--text-main);
  }

  .monitor-area {
    flex: 1;
    background: #010409;
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-height: 150px;
  }

  .monitor-header {
    background: rgba(255,255,255,0.02);
    padding: 5px 10px;
    font-size: 12px;
    color: var(--accent-primary);
    text-align: left;
    border-bottom: 1px solid var(--border-dim);
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-weight: 600;
  }

  .monitor-logs { 
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
  .time { color: #484f58; margin-right: 10px; }
  .level { font-weight: bold; margin-right: 10px; width: 50px; display: inline-block; }
  .level.info { color: #58a6ff; }
  .level.warning { color: var(--accent-warning); }
  .level.error { color: var(--accent-danger); }
  
  .platform-tag { font-weight: bold; margin-right: 5px; }
  .platform-tag.youtube { color: #ff4a4a; }
  .platform-tag.pixiv { color: #0096fa; }
  .platform-tag.x { color: #1da1f2; }
  .platform-tag.instagram { color: #e1306c; }
  .platform-tag.pinterest { color: #e60023; }
  
  .msg { color: #8b949e; }

  .empty-monitor { color: #30363d; text-align: center; margin-top: 20px; font-style: italic; }

  .footer-btns { display: flex; gap: 10px; }
</style>
