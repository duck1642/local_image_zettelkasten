<script lang="ts">
  import { onMount, tick, onDestroy } from 'svelte';
  import { log as uiLog } from './logger';
  import { apiFetch, apiUrl } from './api';
  import { queueStats, refreshQueueStats, setQueueStats } from './statsStore';
  import { runtimeSessionKey } from './runtimeStore';
  import {
    IconInfoCircle,
    IconRefresh,
    IconExternalLink
  } from './icons';

  type QueueName = 'normal' | 'force' | 'failed';
  type ArtistOption = { id: number; name: string; kind: string; item_count: number; link_count: number; alias_count: number };
  type PlatformOption = { id: number; key_norm: string; display_name: string; kind: string; item_count: number; alias_count: number };
  type QueueParseWarning = { line: number; code: string; message: string; text?: string };
  type QueueParseGroup = {
    index: number;
    artist: string;
    artist_label?: string;
    artist_status?: 'unknown' | 'existing' | 'alias' | 'new';
    platform: string;
    platform_label?: string;
    platform_status?: 'inferred' | 'existing' | 'alias' | 'new';
    url_count: number;
    warnings: number;
  };
  type QueueParsePreview = { count: number; groups: QueueParseGroup[]; warnings: QueueParseWarning[] };
  type QueueDirectiveKind = 'artist' | 'platform';
  type QueueDirectiveSuggestion = { value: string; detail?: string };

  let currentQueue: QueueName = 'normal';
  let queueContent = '';
  let counts = { normal: 0, force: 0, failed: 0 };
  let saving = false;
  let running = false;
  let isDirty = false;
  let queueEditor: HTMLTextAreaElement;
  let queueGutter: HTMLDivElement;
  let onlinePanel: HTMLDivElement;
  let toolbarElement: HTMLDivElement;
  let editorAreaElement: HTMLDivElement;
  let previewElement: HTMLDivElement;
  let footerElement: HTMLDivElement;
  let editorHeightPx = 0;
  let splitterDragging = false;
  let splitterStartY = 0;
  let splitterStartHeight = 0;
  let parseTimer: number | null = null;
  let parseRequestId = 0;
  let queuePreview: QueueParsePreview = { count: 0, groups: [], warnings: [] };
  let showQueueHelp = false;
  let directiveSuggestionTimer: number | null = null;
  let directiveSuggestionsOpen = false;
  let directiveSuggestionKind: QueueDirectiveKind | null = null;
  let directiveSuggestionQuery = '';
  let directiveSuggestions: QueueDirectiveSuggestion[] = [];
  let activeDirectiveSuggestionIndex = 0;
  let directiveSuggestionTop = 34;
  let directiveSuggestionLeft = 18;
  let directiveMeasureCanvas: HTMLCanvasElement | null = null;
  let directiveMeasureContext: CanvasRenderingContext2D | null = null;
  let directiveSuggestionsListEl: HTMLDivElement;
  let monitorLogIdCounter = 0;

  let monitorLogs: any[] = [];
  let logSource: EventSource | null = null;
  let logReconnectTimer: number | null = null;
  let logReconnectAttempts = 0;
  let monitorContainer: HTMLElement;
  let platformOptions: PlatformOption[] = [];

  const LOG_RECONNECT_BASE_MS = 800;
  const LOG_RECONNECT_MAX_MS = 8000;
  const DEFAULT_EDITOR_HEIGHT = 280;
  const MIN_EDITOR_HEIGHT = 120;
  const MIN_MONITOR_HEIGHT = 120;

  let currentRuntimeSessionKey = '';

  $: counts = $queueStats;
  $: readyCount = (counts.normal || 0) + (counts.force || 0);
  $: queueLineNumbers = Array.from({ length: Math.max(1, queueContent.split('\n').length) }, (_, index) => index + 1);
  $: queueGutterWidth = Math.max(24, Math.min(58, 14 + String(queueLineNumbers.length).length * 8));
  $: warningLines = new Set(queuePreview.warnings.map((warning) => warning.line));

  $: if ($runtimeSessionKey) {
    if (currentRuntimeSessionKey && currentRuntimeSessionKey !== $runtimeSessionKey) {
      resetForRuntimeSwitch();
    }
    currentRuntimeSessionKey = $runtimeSessionKey;
  }

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

  function resetForRuntimeSwitch() {
    if (parseTimer !== null) {
      clearTimeout(parseTimer);
      parseTimer = null;
    }
    if (directiveSuggestionTimer !== null) {
      clearTimeout(directiveSuggestionTimer);
      directiveSuggestionTimer = null;
    }
    queueContent = '';
    isDirty = false;
    running = false;
    queuePreview = { count: 0, groups: [], warnings: [] };
    directiveSuggestionsOpen = false;
    directiveSuggestions = [];
    directiveSuggestionKind = null;
    monitorLogs = [];
    monitorLogIdCounter = 0;
    platformOptions = [];
    loadQueue(currentQueue);
    fetchStats();
    loadPlatformOptions();
    connectMonitor();
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
      await parseQueueContent();
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
      await parseQueueContent();
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
    if (queuePreview.warnings.length > 0) {
      const lines = queuePreview.warnings
        .slice(0, 5)
        .map((warning) => `Line ${warning.line}: ${warning.message}`)
        .join('\n');
      const extra = queuePreview.warnings.length > 5 ? `\n${queuePreview.warnings.length - 5} more warnings...` : '';
      if (!confirm(`Queue has ${queuePreview.warnings.length} warning${queuePreview.warnings.length === 1 ? '' : 's'}.\n\n${lines}${extra}\n\nContinue ingestion?`)) {
        return;
      }
    }
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
    refreshDirectiveSuggestions();
    if (parseTimer !== null) clearTimeout(parseTimer);
    parseTimer = window.setTimeout(() => {
      parseTimer = null;
      parseQueueContent();
    }, 400);
  }

  function syncQueueGutterScroll() {
    if (queueGutter && queueEditor) {
      queueGutter.scrollTop = queueEditor.scrollTop;
    }
    const active = currentDirectiveLine();
    if (active && directiveSuggestionsOpen) updateDirectiveSuggestionPosition(active);
  }

  function currentEditorHeight() {
    return editorHeightPx || queueEditor?.closest('.queue-editor-shell')?.getBoundingClientRect().height || DEFAULT_EDITOR_HEIGHT;
  }

  function onlinePanelGap() {
    if (!onlinePanel) return 10;
    const style = window.getComputedStyle(onlinePanel);
    return parseFloat(style.rowGap || style.gap || '0') || 0;
  }

  function editorAreaGap() {
    if (!editorAreaElement) return 8;
    const style = window.getComputedStyle(editorAreaElement);
    return parseFloat(style.rowGap || style.gap || '0') || 0;
  }

  function maxEditorHeight() {
    if (!onlinePanel) return DEFAULT_EDITOR_HEIGHT;
    const gap = onlinePanelGap();
    const panelHeight = onlinePanel.clientHeight;
    const toolbarHeight = toolbarElement?.getBoundingClientRect().height || 0;
    const previewHeight = previewElement?.getBoundingClientRect().height || 0;
    const footerHeight = footerElement?.getBoundingClientRect().height || 0;
    const nonEditorHeight = toolbarHeight + previewHeight + footerHeight + MIN_MONITOR_HEIGHT + (gap * 3) + editorAreaGap();
    return Math.max(MIN_EDITOR_HEIGHT, panelHeight - nonEditorHeight);
  }

  function clampEditorHeight(value: number) {
    return Math.max(MIN_EDITOR_HEIGHT, Math.min(maxEditorHeight(), Math.round(value)));
  }

  function clampCurrentEditorHeight() {
    const current = currentEditorHeight();
    const clamped = clampEditorHeight(current);
    if (editorHeightPx || clamped < current) {
      editorHeightPx = clamped;
    }
  }

  function handleSplitterMove(event: PointerEvent) {
    if (!splitterDragging) return;
    editorHeightPx = clampEditorHeight(splitterStartHeight + event.clientY - splitterStartY);
    syncQueueGutterScroll();
  }

  function stopSplitterDrag() {
    splitterDragging = false;
    window.removeEventListener('pointermove', handleSplitterMove);
    window.removeEventListener('pointerup', stopSplitterDrag);
  }

  function startSplitterDrag(event: PointerEvent) {
    if (event.button !== 0) return;
    event.preventDefault();
    splitterDragging = true;
    splitterStartY = event.clientY;
    splitterStartHeight = currentEditorHeight();
    window.addEventListener('pointermove', handleSplitterMove);
    window.addEventListener('pointerup', stopSplitterDrag);
  }

  function resetEditorHeight() {
    editorHeightPx = clampEditorHeight(DEFAULT_EDITOR_HEIGHT);
    syncQueueGutterScroll();
  }

  async function parseQueueContent() {
    if (currentQueue === 'failed') {
      queuePreview = { count: 0, groups: [], warnings: [] };
      return;
    }
    const requestId = ++parseRequestId;
    try {
      const res = await apiFetch(`/api/queue/${currentQueue}/parse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: queueContent })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (requestId !== parseRequestId) return;
      queuePreview = {
        count: Number(data.count || 0),
        groups: Array.isArray(data.groups) ? data.groups : [],
        warnings: Array.isArray(data.warnings) ? data.warnings : []
      };
      setQueueStats({ ...counts, [currentQueue]: queuePreview.count });
      await tick();
      clampCurrentEditorHeight();
    } catch (e) {
      uiLog('ERROR', 'Failed to parse queue content', { queue: currentQueue, error: String(e) });
    }
  }

  function currentDirectiveLine() {
    if (!queueEditor) return null;
    const cursor = queueEditor.selectionStart ?? queueContent.length;
    const lineStart = queueContent.lastIndexOf('\n', Math.max(0, cursor - 1)) + 1;
    const lineEndRaw = queueContent.indexOf('\n', cursor);
    const lineEnd = lineEndRaw === -1 ? queueContent.length : lineEndRaw;
    const line = queueContent.slice(lineStart, lineEnd);
    const match = line.match(/^(\s*)@(artist|platform):\s*(.*)$/i);
    if (!match) return null;
    return {
      kind: match[2].toLowerCase() as QueueDirectiveKind,
      query: String(match[3] || '').trimStart(),
      lineStart,
      lineEnd,
      line,
      valueColumn: line.length - String(match[3] || '').length + (String(match[3] || '').length - String(match[3] || '').trimStart().length),
      indent: match[1] || ''
    };
  }

  function measureEditorText(text: string) {
    if (!queueEditor) return 0;
    const style = window.getComputedStyle(queueEditor);
    if (!directiveMeasureCanvas) {
      directiveMeasureCanvas = document.createElement('canvas');
      directiveMeasureContext = directiveMeasureCanvas.getContext('2d');
    }
    if (!directiveMeasureContext) return 0;
    directiveMeasureContext.font = `${style.fontStyle} ${style.fontVariant} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    return directiveMeasureContext.measureText(text).width;
  }

  function updateDirectiveSuggestionPosition(active: { lineStart: number; line: string; valueColumn: number }) {
    if (!queueEditor) return;
    const before = queueContent.slice(0, active.lineStart);
    const lineNumber = before ? before.split('\n').length - 1 : 0;
    const style = window.getComputedStyle(queueEditor);
    const lineHeight = parseFloat(style.lineHeight || '0') || 18;
    const paddingTop = parseFloat(style.paddingTop || '0') || 0;
    const paddingLeft = parseFloat(style.paddingLeft || '0') || 0;
    const valuePrefix = active.line.slice(0, active.valueColumn);
    const rawLeft = queueEditor.offsetLeft + paddingLeft + measureEditorText(valuePrefix) - queueEditor.scrollLeft;
    const maxLeft = Math.max(0, queueEditor.offsetLeft + queueEditor.clientWidth - 310);
    directiveSuggestionTop = Math.max(34, paddingTop + ((lineNumber + 1) * lineHeight) - queueEditor.scrollTop + 4);
    directiveSuggestionLeft = Math.max(8, Math.min(rawLeft, maxLeft));
  }

  function clearDirectiveSuggestions() {
    if (directiveSuggestionTimer !== null) {
      clearTimeout(directiveSuggestionTimer);
      directiveSuggestionTimer = null;
    }
    directiveSuggestionsOpen = false;
    directiveSuggestions = [];
    directiveSuggestionKind = null;
    directiveSuggestionQuery = '';
    activeDirectiveSuggestionIndex = 0;
  }

  function platformDirectiveSuggestions(query: string): QueueDirectiveSuggestion[] {
    const needle = query.trim().toLocaleLowerCase();
    return platformOptions
      .filter((platform) => {
        const value = platform.display_name || '';
        return value && (!needle || value.toLocaleLowerCase().includes(needle));
      })
      .slice(0, 8)
      .map((platform) => ({
        value: platform.display_name,
        detail: `${platform.item_count || 0} items`
      }));
  }

  function refreshDirectiveSuggestions() {
    const active = currentDirectiveLine();
    if (!active) {
      clearDirectiveSuggestions();
      return;
    }
    directiveSuggestionKind = active.kind;
    directiveSuggestionQuery = active.query;
    activeDirectiveSuggestionIndex = 0;
    updateDirectiveSuggestionPosition(active);

    if (directiveSuggestionTimer !== null) clearTimeout(directiveSuggestionTimer);

    if (active.kind === 'platform') {
      directiveSuggestions = platformDirectiveSuggestions(active.query);
      directiveSuggestionsOpen = directiveSuggestions.length > 0;
      return;
    }

    directiveSuggestionTimer = window.setTimeout(async () => {
      directiveSuggestionTimer = null;
      const request = currentDirectiveLine();
      if (!request || request.kind !== 'artist') return;
      try {
        const params = new URLSearchParams({ q: request.query.trim(), limit: '8' });
        const res = await apiFetch(`/api/artists?${params.toString()}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const latest = currentDirectiveLine();
        if (!latest || latest.kind !== 'artist' || latest.query !== request.query) return;
        directiveSuggestions = Array.isArray(data.items)
          ? data.items.map((artist: ArtistOption) => ({
              value: artist.name,
              detail: `${artist.item_count || 0} items`
            }))
          : [];
        directiveSuggestionsOpen = directiveSuggestions.length > 0;
      } catch (error) {
        uiLog('ERROR', 'Failed to load queue directive suggestions', { error: String(error) });
        clearDirectiveSuggestions();
      }
    }, 150);
  }

  async function scrollActiveDirectiveSuggestionIntoView() {
    await tick();
    const active = directiveSuggestionsListEl?.querySelector('button.active');
    active?.scrollIntoView({ block: 'nearest' });
  }

  async function goToQueueLine(line: number) {
    const targetLine = Math.max(1, Number(line) || 1);
    const lines = queueContent.split('\n');
    const offset = lines.slice(0, targetLine - 1).reduce((sum, value) => sum + value.length + 1, 0);
    await tick();
    queueEditor?.focus();
    queueEditor?.setSelectionRange(offset, offset);
  }

  function artistPreviewLabel(group: QueueParseGroup) {
    if (group.artist_status === 'unknown' || !group.artist) return 'unknown artist';
    if (group.artist_status === 'new') return `${group.artist} - new artist`;
    if (group.artist_status === 'alias') return `${group.artist} -> ${group.artist_label || group.artist}`;
    return group.artist_label || group.artist;
  }

  function platformPreviewLabel(group: QueueParseGroup) {
    if (group.platform_status === 'inferred' || !group.platform) return 'infer platform';
    if (group.platform_status === 'new') return `${group.platform} - new platform`;
    if (group.platform_status === 'alias') return `${group.platform} -> ${group.platform_label || group.platform}`;
    return group.platform_label || group.platform;
  }

  async function applyDirectiveSuggestion(value: string) {
    const active = currentDirectiveLine();
    if (!active) return;
    const before = queueContent.slice(0, active.lineStart);
    const after = queueContent.slice(active.lineEnd);
    const nextLine = `${active.indent}@${active.kind}: ${value}`;
    queueContent = `${before}${nextLine}${after}`;
    isDirty = true;
    clearDirectiveSuggestions();
    parseQueueContent();
    await tick();
    const position = before.length + nextLine.length;
    queueEditor?.focus();
    queueEditor?.setSelectionRange(position, position);
  }

  function handleEditorKeydown(event: KeyboardEvent) {
    if (!directiveSuggestionsOpen || directiveSuggestions.length === 0) {
      if (event.key === 'Escape') clearDirectiveSuggestions();
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      event.stopPropagation();
      activeDirectiveSuggestionIndex = (activeDirectiveSuggestionIndex + 1) % directiveSuggestions.length;
      scrollActiveDirectiveSuggestionIntoView();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      event.stopPropagation();
      activeDirectiveSuggestionIndex = (activeDirectiveSuggestionIndex - 1 + directiveSuggestions.length) % directiveSuggestions.length;
      scrollActiveDirectiveSuggestionIntoView();
    } else if (event.key === 'Tab') {
      event.preventDefault();
      event.stopPropagation();
      applyDirectiveSuggestion(directiveSuggestions[activeDirectiveSuggestionIndex]?.value || '');
    } else if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      clearDirectiveSuggestions();
    }
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

  function handleGlobalRefresh(event: Event) {
    const detail = (event as CustomEvent).detail || {};
    if (detail.tab !== 'ingest') return;
    if (isDirty && !confirm('You have unsaved queue changes. Discard them and refresh?')) return;
    uiLog('INFO', 'Ingestion online view refresh requested');
    loadQueue(currentQueue);
    fetchStats();
    connectMonitor();
  }

  onMount(() => {
    loadQueue(currentQueue);
    fetchStats();
    loadPlatformOptions();
    connectMonitor();
    window.addEventListener('lmz:refresh', handleGlobalRefresh);
  });

  onDestroy(() => {
    if (parseTimer !== null) clearTimeout(parseTimer);
    if (directiveSuggestionTimer !== null) clearTimeout(directiveSuggestionTimer);
    if (logReconnectTimer !== null) clearTimeout(logReconnectTimer);
    if (logSource) logSource.close();
    window.removeEventListener('lmz:refresh', handleGlobalRefresh);
  });
</script>

<div class="online-panel" bind:this={onlinePanel}>
  <div class="toolbar" bind:this={toolbarElement}>
    <div class="queue-tabs">
      <button class:active={currentQueue === 'normal'} on:click={() => handleTabChange('normal')} disabled={running}>
        Normal <span class="tab-count">{counts.normal || 0}</span>
      </button>
      <button class:active={currentQueue === 'force'} on:click={() => handleTabChange('force')} disabled={running}>
        Force <span class="tab-count">{counts.force || 0}</span>
      </button>
      <button class:active={currentQueue === 'failed'} on:click={() => handleTabChange('failed')} disabled={running}>
        Failed <span class="tab-count">{counts.failed || 0}</span>
      </button>
      <span class="status-label online-bold">READY: {readyCount}</span>
      <span class="save-state-dot" class:dirty={isDirty} title={isDirty ? 'Unsaved changes' : 'All changes saved'}></span>
    </div>

    <div class="action-group">
      <button type="button" class="icon-btn-chip" on:click={() => handleTabChange(currentQueue)} disabled={running} title="Reload active queue">
        <IconRefresh size={14} />
      </button>
      <button type="button" class="icon-btn-chip" on:click={openExternal} disabled={running} title="Open queue in external editor">
        <IconExternalLink size={14} />
      </button>
      <div class="help-menu">
        <button class="icon-help-btn" class:active={showQueueHelp} title="Queue syntax help" aria-label="Queue syntax help" on:click={() => showQueueHelp = !showQueueHelp}>
          <IconInfoCircle size={14} />
        </button>
        {#if showQueueHelp}
          <div class="queue-help-popover">
            <div><code>@artist: name</code></div>
            <div><code>@platform: name</code></div>
            <div><code>---</code> separates groups</div>
            <div><code># comment</code> for full-line comments</div>
            <div><kbd>Tab</kbd> accepts suggestions</div>
          </div>
        {/if}
      </div>
      <button class="primary" on:click={startIngestion} disabled={running || currentQueue === 'failed'}>
        {running ? 'Worker Active...' : 'Start Ingestion'}
      </button>
    </div>
  </div>

  <div class="editor-area" bind:this={editorAreaElement}>
    <div class="queue-editor-wrap">
      <div class="queue-editor-shell" style="--queue-editor-height: {editorHeightPx ? `${editorHeightPx}px` : '35vh'}; --queue-gutter-width: {queueGutterWidth}px;">
        <div class="line-gutter" bind:this={queueGutter}>
          {#each queueLineNumbers as num}
            <button type="button" class:warning={warningLines.has(num)} on:click={() => goToQueueLine(num)}>{num}</button>
          {/each}
        </div>
        <textarea
          bind:this={queueEditor}
          bind:value={queueContent}
          on:input={onEditorInput}
          on:click={refreshDirectiveSuggestions}
          on:focus={refreshDirectiveSuggestions}
          on:scroll={syncQueueGutterScroll}
          on:keydown={handleEditorKeydown}
          on:blur={() => window.setTimeout(clearDirectiveSuggestions, 120)}
          disabled={running}
          placeholder="Enter links to ingest..."
          spellcheck="false"
        ></textarea>
        <button
          type="button"
          class="editor-splitter"
          class:dragging={splitterDragging}
          title="Drag to resize editor. Double-click to reset."
          aria-label="Resize queue editor"
          on:pointerdown={startSplitterDrag}
          on:dblclick={resetEditorHeight}
        ></button>
      </div>

      {#if directiveSuggestionsOpen && directiveSuggestions.length > 0}
        <div bind:this={directiveSuggestionsListEl} class="directive-suggestions" style="top: {directiveSuggestionTop}px; left: {directiveSuggestionLeft}px;">
          {#each directiveSuggestions as suggestion, i}
            <button
              type="button"
              class:active={i === activeDirectiveSuggestionIndex}
              on:mousedown|preventDefault
              on:click={() => applyDirectiveSuggestion(suggestion.value)}
            >
              <span>{suggestion.value}</span>
              {#if suggestion.detail}
                <span>{suggestion.detail}</span>
              {/if}
            </button>
          {/each}
        </div>
      {/if}
    </div>

    {#if queuePreview.count > 0 || queuePreview.warnings.length > 0}
      <div class="queue-preview" bind:this={previewElement}>
        {#if queuePreview.count > 0}
          <div class="preview-summary">Preview: {queuePreview.count} item{queuePreview.count === 1 ? '' : 's'} in {queuePreview.groups.length} group{queuePreview.groups.length === 1 ? '' : 's'}</div>
          <div class="preview-groups">
            {#each queuePreview.groups as group}
              <div class="preview-group">
                <span class="preview-artist" class:new={group.artist_status === 'new'} class:unknown={group.artist_status === 'unknown'}>{artistPreviewLabel(group)}</span>
                <span class:new={group.platform_status === 'new'} class:unknown={group.platform_status === 'inferred'}>{platformPreviewLabel(group)}</span>
                <span>{group.url_count} URLs</span>
                {#if group.warnings > 0}
                  <span class="warning-count">{group.warnings} warnings</span>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
        {#if queuePreview.warnings.length > 0}
          <div class="preview-warnings">
            {#each queuePreview.warnings.slice(0, 4) as warning}
              <button type="button" on:click={() => goToQueueLine(warning.line)}>
                <span>Line {warning.line}: {warning.message}</span>
                {#if warning.text}
                  <code>{warning.text}</code>
                {/if}
              </button>
            {/each}
            {#if queuePreview.warnings.length > 4}
              <div>{queuePreview.warnings.length - 4} more warnings...</div>
            {/if}
          </div>
        {/if}
      </div>
    {/if}
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

  <div class="footer-btns" bind:this={footerElement}>
    <button class:primary={isDirty} on:click={saveQueue} disabled={!isDirty || saving || running}>Save Changes</button>
    <button on:click={retryFailed} disabled={running || counts.failed === 0}>Retry Failed</button>
    <button on:click={clearFailed} disabled={running || counts.failed === 0}>Clear Failed</button>
  </div>
</div>
