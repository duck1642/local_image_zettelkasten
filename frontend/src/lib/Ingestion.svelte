<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { log as uiLog } from './logger';

  let currentQueue: 'normal' | 'force' | 'failed' = 'normal';
  let queueContent = '';
  let counts = { normal: 0, force: 0, failed: 0 };
  let saving = false;
  let running = false;
  let isDirty = false;
  let showDebug = true;

  // Monitor Logs
  let monitorLogs: any[] = [];
  let logSource: EventSource | null = null;
  let monitorContainer: HTMLElement;

  function connectMonitor() {
    if (logSource) logSource.close();
    // We only want the last few lines for context in the monitor
    logSource = new EventSource(`http://localhost:8000/api/logs?filename=ingestion.log`);
    logSource.onmessage = (e) => {
        try {
            const entry = JSON.parse(e.data);
            if (!showDebug && entry.level === 'DEBUG') return;
            monitorLogs = [...monitorLogs, entry].slice(-100);
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
    try {
      const res = await fetch('http://localhost:8000/api/queue-stats');
      counts = await res.json();
    } catch (e) { console.error(e); }
  }

  function handleTabChange(name: 'normal' | 'force' | 'failed') {
    if (isDirty) { if (!confirm('Discard changes?')) return; }
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
      fetchStats();
      uiLog('INFO', `Queue ${currentQueue} saved`);
    } finally { saving = false; }
  }

  async function startIngestion() {
    if (isDirty) await saveQueue();
    running = true;
    uiLog('INFO', `Starting ingestion for queue: ${currentQueue}`);
    try {
      await fetch(`http://localhost:8000/api/ingest/${currentQueue}`, { method: 'POST' });
    } finally { 
        // Keep "Running" state for a bit to show activity
        setTimeout(() => running = false, 5000); 
    }
  }

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
      <button class:active={currentQueue === 'normal'} on:click={() => handleTabChange('normal')}>
        Normal {counts.normal}
      </button>
      <button class:active={currentQueue === 'force'} on:click={() => handleTabChange('force')}>
        Force {counts.force}
      </button>
      <button class:active={currentQueue === 'failed'} on:click={() => handleTabChange('failed')}>
        Failed {counts.failed}
      </button>
      <span class="status-label saved">{isDirty ? '● Unsaved' : 'Saved'}</span>
    </div>

    <div class="action-group">
      <label class="check-label">
        <input type="checkbox" bind:checked={showDebug} /> Show Debug
      </label>
      <button on:click={() => loadQueue(currentQueue)}>Reload</button>
      <button class="primary" on:click={startIngestion} disabled={running}>
        {running ? 'Worker Active...' : 'Start Ingestion'}
      </button>
    </div>
  </div>

  <div class="editor-area">
    <textarea 
        bind:value={queueContent} 
        on:input={() => isDirty = true}
        placeholder="Edit queue markdown here..."
    ></textarea>
  </div>

  <div class="monitor-area">
    <div class="monitor-header">--- Ingestion Monitor Active ---</div>
    <div class="monitor-logs" bind:this={monitorContainer}>
        {#each monitorLogs as log}
            <div class="log-line">
                <span class="time">{log.timestamp.split(' ')[1]}</span>
                <span class="level {log.level.toLowerCase()}">{log.level}</span>
                <span class="msg">{log.message}</span>
            </div>
        {/each}
        {#if monitorLogs.length === 0}
            <div class="empty-monitor">Waiting for ingestion activity...</div>
        {/if}
    </div>
  </div>

  <div class="footer-btns">
      <button on:click={saveQueue} disabled={!isDirty || saving}>Save Changes</button>
      <button>Retry Failed</button>
      <button>Clear Failed</button>
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
    padding: 5px;
    font-size: 10px;
    color: var(--accent-primary);
    text-align: center;
    border-bottom: 1px solid var(--border-dim);
    font-family: monospace;
    letter-spacing: 2px;
  }

  .monitor-logs { flex-grow: 1; overflow-y: auto; padding: 10px; font-family: 'Consolas', monospace; font-size: 12px; }
  .log-line { margin-bottom: 2px; }
  .time { color: #484f58; margin-right: 10px; }
  .level { font-weight: bold; margin-right: 10px; width: 50px; display: inline-block; }
  .level.info { color: #58a6ff; }
  .level.warning { color: var(--accent-warning); }
  .level.error { color: var(--accent-danger); }
  .msg { color: #8b949e; }

  .empty-monitor { color: #30363d; text-align: center; margin-top: 20px; font-style: italic; }

  .footer-btns { display: flex; gap: 10px; }
</style>
