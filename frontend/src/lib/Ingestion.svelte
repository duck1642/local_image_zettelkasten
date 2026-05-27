<script lang="ts">
  import { createEventDispatcher, onMount, tick } from 'svelte';
  import { open as openDialog } from '@tauri-apps/plugin-dialog';
  import { log as uiLog } from './logger';
  import { apiFetch, apiUrl } from './api';
  import { queueStats, refreshQueueStats, setQueueStats } from './statsStore';
  import { runtimeSessionKey } from './runtimeStore';
  import { IconInfoCircle } from './icons';

  type IngestMode = 'online' | 'local';
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
  const LOG_RECONNECT_BASE_MS = 800;
  const LOG_RECONNECT_MAX_MS = 8000;
  const DEFAULT_EDITOR_HEIGHT = 280;
  const MIN_EDITOR_HEIGHT = 120;
  const MIN_MONITOR_HEIGHT = 120;

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
  let artistOptions: ArtistOption[] = [];
  let platformOptions: PlatformOption[] = [];
  let platformSelectOptions: string[] = ['Local'];
  let artistOptionsTimer: number | null = null;
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
  let currentRuntimeSessionKey = '';

  $: counts = $queueStats;
  $: readyCount = (counts.normal || 0) + (counts.force || 0);
  $: queueLineNumbers = Array.from({ length: Math.max(1, queueContent.split('\n').length) }, (_, index) => index + 1);
  $: queueGutterWidth = Math.max(24, Math.min(58, 14 + String(queueLineNumbers.length).length * 8));
  $: warningLines = new Set(queuePreview.warnings.map((warning) => warning.line));
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
    if (parseTimer !== null) {
      clearTimeout(parseTimer);
      parseTimer = null;
    }
    if (artistOptionsTimer !== null) {
      clearTimeout(artistOptionsTimer);
      artistOptionsTimer = null;
    }
    if (directiveSuggestionTimer !== null) {
      clearTimeout(directiveSuggestionTimer);
      directiveSuggestionTimer = null;
    }
    stopLocalStatusPolling();
    queueContent = '';
    isDirty = false;
    running = false;
    queuePreview = { count: 0, groups: [], warnings: [] };
    directiveSuggestionsOpen = false;
    directiveSuggestions = [];
    directiveSuggestionKind = null;
    localPaths = [];
    localStatus = emptyLocalStatus();
    monitorLogs = [];
    monitorLogIdCounter = 0;
    artistOptions = [];
    platformOptions = [];
    localDefaults = { artist: '', platform: 'Local', source_url: '' };
    loadQueue(currentQueue);
    fetchStats();
    refreshLocalStatus();
    loadArtistOptions('');
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

  function scheduleArtistOptions(q = localDefaults.artist) {
    if (artistOptionsTimer !== null) clearTimeout(artistOptionsTimer);
    artistOptionsTimer = window.setTimeout(() => {
      artistOptionsTimer = null;
      loadArtistOptions(q);
    }, 180);
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
    if (group.artist_status === 'new') return `${group.artist} · new artist`;
    if (group.artist_status === 'alias') return `${group.artist} -> ${group.artist_label || group.artist}`;
    return group.artist_label || group.artist;
  }

  function platformPreviewLabel(group: QueueParseGroup) {
    if (group.platform_status === 'inferred' || !group.platform) return 'infer platform';
    if (group.platform_status === 'new') return `${group.platform} · new platform`;
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
    window.addEventListener('resize', clampCurrentEditorHeight);
    loadQueue('normal');
    fetchStats();
    connectMonitor();
    refreshLocalStatus();
    loadArtistOptions('');
    loadPlatformOptions();
    tick().then(clampCurrentEditorHeight);
    return () => {
      window.removeEventListener('lmz:refresh', handleGlobalRefresh);
      window.removeEventListener('resize', clampCurrentEditorHeight);
      logSource?.close();
      stopSplitterDrag();
      if (logReconnectTimer !== null) clearTimeout(logReconnectTimer);
      if (parseTimer !== null) clearTimeout(parseTimer);
      if (artistOptionsTimer !== null) clearTimeout(artistOptionsTimer);
      if (directiveSuggestionTimer !== null) clearTimeout(directiveSuggestionTimer);
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
    <div class="online-panel" bind:this={onlinePanel}>
    <div class="toolbar" bind:this={toolbarElement}>
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
        <div
          class="queue-editor-shell"
          style={`--queue-gutter-width: ${queueGutterWidth}px; ${editorHeightPx ? `--queue-editor-height: ${editorHeightPx}px;` : ''}`}
        >
          <div class="line-gutter" bind:this={queueGutter} aria-hidden="true">
            {#each queueLineNumbers as line}
              <button
                type="button"
                class:warning={warningLines.has(line)}
                tabindex="-1"
                on:mousedown|preventDefault
                on:click={() => goToQueueLine(line)}
              >
                {line}
              </button>
            {/each}
          </div>
          <textarea
            bind:this={queueEditor}
            bind:value={queueContent}
            on:input={onEditorInput}
            on:click={refreshDirectiveSuggestions}
            on:keydown={handleEditorKeydown}
            on:scroll={syncQueueGutterScroll}
            on:blur={() => window.setTimeout(clearDirectiveSuggestions, 120)}
            placeholder="Edit queue markdown here..."
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
          <div bind:this={directiveSuggestionsListEl} class="directive-suggestions" style={`top: ${directiveSuggestionTop}px; left: ${directiveSuggestionLeft}px;`}>
            {#each directiveSuggestions as suggestion, index}
              <button
                type="button"
                class:active={index === activeDirectiveSuggestionIndex}
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
      <div class="queue-preview" bind:this={previewElement}>
        <div class="preview-summary">
          <span>{queuePreview.count} URLs</span>
          {#if queuePreview.groups.length > 0}
            <span>{queuePreview.groups.length} groups</span>
          {/if}
          {#if queuePreview.warnings.length > 0}
            <span class="warning-count">{queuePreview.warnings.length} warnings</span>
          {/if}
        </div>
        {#if queuePreview.groups.length > 0}
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
        <label>
          Artist
          <input class="local-artist-input" list="local-artist-options" bind:value={localDefaults.artist} on:input={() => scheduleArtistOptions()} placeholder="Optional default artist" />
        </label>
        <datalist id="local-artist-options">
          {#each artistOptions as artist}
            <option value={artist.name}>{artist.item_count} items</option>
          {/each}
        </datalist>
        <label>
          Platform
          <select bind:value={localDefaults.platform}>
            {#each platformSelectOptions as platform}
              <option value={platform}>{platform}</option>
            {/each}
          </select>
        </label>
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
    min-height: 0;
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

  .online-panel {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
    gap: 10px;
    overflow: hidden;
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

  .help-menu {
    position: relative;
    display: inline-flex;
  }

  .icon-help-btn {
    width: 30px;
    height: 30px;
    padding: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .icon-help-btn.active {
    color: var(--accent-primary);
    border-color: rgba(88, 166, 255, 0.35);
    background: rgba(88, 166, 255, 0.12);
  }

  .editor-area {
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
    gap: 8px;
  }

  .queue-editor-shell {
    display: grid;
    grid-template-columns: var(--queue-gutter-width, 24px) 1fr;
    height: var(--queue-editor-height, 35vh);
    min-height: 100px;
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    overflow: hidden;
    position: relative;
  }

  .line-gutter {
    overflow: hidden;
    padding: 15px 0;
    border-right: 1px solid var(--border-dim);
    background: rgba(1, 4, 9, 0.22);
    color: var(--text-muted);
    font-family: 'Consolas', monospace;
    font-size: 13px;
    line-height: normal;
    user-select: none;
  }

  .line-gutter button {
    width: 100%;
    height: 16px;
    display: block;
    padding: 0 6px 0 0;
    border: 0;
    border-radius: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    line-height: 16px;
    text-align: right;
  }

  .line-gutter button.warning {
    color: var(--accent-warning);
    background: rgba(255, 171, 0, 0.12);
  }

  textarea {
    height: 100%;
    min-height: 0;
    max-height: none;
    width: 100%;
    border: 0;
    border-radius: 0;
    font-family: 'Consolas', monospace;
    font-size: 13px;
    line-height: 16px;
    resize: none;
    padding: 15px;
    color: var(--text-main);
  }

  textarea:focus {
    outline: none;
  }

  .editor-splitter {
    height: 8px;
    width: 100%;
    padding: 0;
    border: 0;
    border-radius: 0;
    background: transparent;
    cursor: row-resize;
    position: absolute;
    left: 0;
    right: 0;
    bottom: -4px;
    z-index: 15;
  }

  .editor-splitter::before {
    content: '';
    position: absolute;
    left: 6px;
    right: 6px;
    top: 3px;
    height: 1px;
    background: transparent;
  }

  .editor-splitter:hover::before,
  .editor-splitter.dragging::before {
    height: 2px;
    top: 3px;
    background: var(--accent-primary);
    box-shadow: 0 0 8px rgba(47, 129, 247, 0.45);
  }

  .queue-editor-wrap {
    position: relative;
    display: flex;
    flex-direction: column;
  }

  .directive-suggestions {
    position: absolute;
    z-index: 20;
    width: 300px;
    max-width: calc(100% - 10px);
    max-height: min(520px, calc(100vh - 110px));
    overflow-y: auto;
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.5);
    padding: 5px 0;
  }

  .directive-suggestions button {
    width: 100%;
    display: flex;
    justify-content: space-between;
    gap: 12px;
    border: 0;
    border-radius: 0;
    background: transparent;
    color: var(--text-main);
    padding: 8px 15px;
    text-align: left;
    font-size: 13px;
    cursor: pointer;
  }

  .directive-suggestions button span:last-child {
    color: var(--text-muted);
    flex-shrink: 0;
  }

  .directive-suggestions button:hover,
  .directive-suggestions button.active {
    background: var(--accent-primary);
    color: white;
  }

  .directive-suggestions button:hover span:last-child,
  .directive-suggestions button.active span:last-child {
    color: rgba(255, 255, 255, 0.78);
  }

  .queue-preview {
    background: #010409;
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    font-size: 12px;
    color: var(--text-muted);
  }

  .preview-summary,
  .preview-groups,
  .preview-group {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .preview-summary {
    color: var(--text-main);
    font-weight: 600;
  }

  .preview-group {
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    padding: 4px 7px;
    background: var(--bg-panel);
  }

  .preview-artist {
    color: var(--text-main);
    font-weight: 600;
  }

  .preview-group .new {
    color: var(--accent-warning);
  }

  .preview-group .unknown {
    color: var(--text-muted);
    font-style: italic;
  }

  .warning-count,
  .preview-warnings {
    color: var(--accent-warning);
  }

  .preview-warnings {
    display: grid;
    gap: 3px;
    font-size: 11px;
  }

  .preview-warnings button {
    display: grid;
    gap: 2px;
    justify-items: start;
    border: 0;
    background: transparent;
    color: var(--accent-warning);
    padding: 0;
    font: inherit;
    text-align: left;
  }

  .preview-warnings button:hover {
    text-decoration: underline;
  }

  .preview-warnings code {
    color: var(--text-muted);
    font-family: 'Consolas', monospace;
    text-decoration: none;
  }

  .queue-help-popover {
    position: absolute;
    top: calc(100% + 3px);
    left: 50%;
    transform: translateX(-50%);
    z-index: 25;
    display: grid;
    gap: 6px;
    width: 240px;
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.5);
    padding: 10px 12px;
    color: var(--text-muted);
    font-size: 12px;
  }

  .queue-help-popover code,
  .queue-help-popover kbd {
    color: var(--text-main);
    font-family: 'Consolas', monospace;
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
  }

  .local-defaults {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(180px, 260px);
    gap: 10px;
  }

  .local-defaults label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 11px;
    color: var(--text-muted);
  }

  .local-defaults input,
  .local-defaults select {
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    color: var(--text-main);
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 12px;
  }

  .local-defaults select {
    height: 28px;
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
