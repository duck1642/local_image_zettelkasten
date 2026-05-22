<script lang="ts">
  import { onMount } from 'svelte';
  import { apiFetch, apiUrl } from './api';
  import { log as uiLog } from './logger';
  import { refreshReviewCount } from './statsStore';
  import { runtimeSessionKey } from './runtimeStore';

  interface ReviewItem {
    filename: string;
    display_name?: string;
    url: string;
    mime_type?: string;
    extension?: string;
    metadata: any;
    state?: string;
    section?: 'pending' | 'cleanup';
    last_action?: string;
    last_cleanup_error?: string;
    best_match: {
      hash: string;
      url: string;
      artist: string;
      mime_type?: string;
      extension?: string;
    } | null;
  }

  type MediaInfo = {
    url?: string;
    filename?: string;
    mime_type?: string;
    extension?: string;
  } | null | undefined;

  let items: ReviewItem[] = [];
  let selectedFilename = '';
  let loading = true;
  let acting = false;
  let mediaMounted = true;
  let currentRuntimeSessionKey = '';

  const VIDEO_EXTENSIONS = new Set(['.mp4', '.webm', '.ogv', '.mov', '.m4v', '.avi', '.mkv']);

  $: pendingItems = items.filter((item) => (item.section || 'pending') === 'pending');
  $: cleanupItems = items.filter((item) => item.section === 'cleanup');
  $: current = items.find((item) => item.filename === selectedFilename) || pendingItems[0] || cleanupItems[0];
  $: currentSectionItems = current?.section === 'cleanup' ? cleanupItems : pendingItems;
  $: currentSectionIndex = current ? currentSectionItems.findIndex((item) => item.filename === current.filename) : -1;
  $: if ($runtimeSessionKey) {
    if (currentRuntimeSessionKey && currentRuntimeSessionKey !== $runtimeSessionKey) {
      resetForRuntimeSwitch();
    }
    currentRuntimeSessionKey = $runtimeSessionKey;
  }

  function extFromUrl(url: string) {
    const clean = (url || '').split('?')[0].split('#')[0];
    const dot = clean.lastIndexOf('.');
    if (dot < 0) return '';
    return clean.slice(dot).toLowerCase();
  }

  function isVideoMedia(item: MediaInfo) {
    if (!item) return false;
    const mime = String(item.mime_type || '').toLowerCase();
    if (mime.startsWith('video/')) return true;
    const ext = String(item.extension || '').toLowerCase() || extFromUrl(item.url || '');
    return VIDEO_EXTENSIONS.has(ext);
  }

  function mediaUrl(item: MediaInfo) {
    if (!item) return '';
    if (item.filename) return apiUrl(`/review-assets/${encodeURIComponent(item.filename)}`);
    return apiUrl(item.url || '');
  }

  function displayName(item: ReviewItem | null | undefined) {
    return item?.display_name || item?.metadata?.original_name || item?.filename || '';
  }

  async function readErrorDetail(response: Response) {
    try {
      const data = await response.json();
      if (typeof data?.detail === 'string' && data.detail.trim()) return data.detail;
      if (typeof data?.message === 'string' && data.message.trim()) return data.message;
    } catch {
      // ignore parse errors and fall back to HTTP status text
    }
    return '';
  }

  function ensureSelection(nextItems: ReviewItem[]) {
    if (selectedFilename && nextItems.some((item) => item.filename === selectedFilename)) return;
    selectedFilename = nextItems.find((item) => (item.section || 'pending') === 'pending')?.filename
      || nextItems.find((item) => item.section === 'cleanup')?.filename
      || '';
  }

  async function loadReview() {
    loading = true;
    try {
      const res = await apiFetch('/api/review');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      items = Array.isArray(data) ? data : [];
      ensureSelection(items);
      mediaMounted = true;
      await refreshReviewCount();
    } catch (e) {
      uiLog('ERROR', 'Failed to load review queue', { error: String(e) });
      alert('Failed to load review queue. Check App Logs for details.');
    } finally {
      loading = false;
    }
  }

  function resetForRuntimeSwitch() {
    items = [];
    selectedFilename = '';
    acting = false;
    mediaMounted = false;
    loadReview();
  }

  async function handleAction(action: 'keep' | 'delete' | 'variant' | 'replace') {
    if (!current || acting || current.section === 'cleanup') return;
    if (action === 'replace') {
      const target = String(current.metadata?.best_match || current.best_match?.hash || '').trim();
      const message = target
        ? `Replace target ${target.slice(0, 10)}... with ${displayName(current)}?`
        : `Replace target is missing for ${displayName(current)}. Continue anyway?`;
      if (!confirm(message)) return;
    }

    acting = true;
    if (action !== 'keep') await unmountMediaForFileAction();
    try {
      const filename = encodeURIComponent(current.filename);
      const res = await apiFetch(`/api/review/${filename}/action?action=${action}`, { method: 'POST' });
      if (!res.ok) {
        const detail = await readErrorDetail(res);
        throw new Error(detail ? `HTTP ${res.status}: ${detail}` : `HTTP ${res.status}`);
      }
      const payload = await res.json().catch(() => ({}));
      if (payload?.status === 'warning') {
        uiLog('WARNING', 'Review action warning', { action, filename: current.filename, display_name: displayName(current), message: payload?.message || '' });
        alert(payload?.message || 'Action returned warning.');
      } else {
        uiLog('INFO', 'Review action succeeded', { action, filename: current.filename, display_name: displayName(current), message: payload?.message || '' });
      }
      await loadReview();
    } catch (e) {
      mediaMounted = true;
      uiLog('ERROR', 'Review action failed', { action, error: String(e) });
      alert(`Review action "${action}" failed. Check App Logs for details.`);
    } finally {
      acting = false;
    }
  }

  async function retryCleanup() {
    if (acting) return;
    acting = true;
    await unmountMediaForFileAction();
    try {
      const res = await apiFetch('/api/review/cleanup', { method: 'POST' });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(payload?.detail || `HTTP ${res.status}`);
      uiLog('INFO', 'Review cleanup retried', {
        cleaned: payload?.cleaned ?? 0,
        failed: payload?.failed ?? 0,
        cleaned_orphans: payload?.cleaned_orphans ?? 0,
        failed_orphans: payload?.failed_orphans ?? 0
      });
      await loadReview();
    } catch (e) {
      mediaMounted = true;
      uiLog('ERROR', 'Review cleanup retry failed', { error: String(e) });
      alert('Review cleanup retry failed. Check App Logs for details.');
    } finally {
      acting = false;
    }
  }

  function nextAnimationFrame() {
    return new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  }

  async function unmountMediaForFileAction() {
    mediaMounted = false;
    await nextAnimationFrame();
  }

  function selectItem(item: ReviewItem) {
    selectedFilename = item.filename;
  }

  function selectRelative(delta: number) {
    if (!currentSectionItems.length || currentSectionIndex < 0) return;
    const nextIndex = Math.max(0, Math.min(currentSectionItems.length - 1, currentSectionIndex + delta));
    selectedFilename = currentSectionItems[nextIndex].filename;
  }

  function handleGlobalRefresh(event: Event) {
    const detail = (event as CustomEvent).detail || {};
    if (detail.tab !== 'review') return;
    uiLog('INFO', 'Review view refresh requested');
    loadReview();
  }

  onMount(() => {
    window.addEventListener('lmz:refresh', handleGlobalRefresh);
    loadReview();
    return () => window.removeEventListener('lmz:refresh', handleGlobalRefresh);
  });
</script>

<div class="review-root">
  {#if loading}
    <div class="centered">Loading...</div>
  {:else if items.length === 0}
    <div class="centered">Review folder is empty.</div>
  {:else}
    <aside class="queue-list">
      <div class="queue-title">Review Queue</div>
      <div class="queue-scroll">
        <div class="queue-section-title">Pending ({pendingItems.length})</div>
        {#if pendingItems.length === 0}
          <div class="queue-empty">No pending decisions.</div>
        {:else}
          {#each pendingItems as item}
            <button class="queue-item {item.filename === current?.filename ? 'active' : ''}" on:click={() => selectItem(item)}>
              <span class="queue-name">{displayName(item)}</span>
              <span class="queue-state">{item.state || 'pending'}</span>
            </button>
          {/each}
        {/if}

        <div class="queue-section-title cleanup-title">Cleanup ({cleanupItems.length})</div>
        {#if cleanupItems.length === 0}
          <div class="queue-empty">No cleanup problems.</div>
        {:else}
          {#each cleanupItems as item}
            <button class="queue-item cleanup {item.filename === current?.filename ? 'active' : ''}" on:click={() => selectItem(item)}>
              <span class="queue-name">{displayName(item)}</span>
              <span class="queue-state">{item.last_cleanup_error || item.state || 'pending_cleanup'}</span>
            </button>
          {/each}
        {/if}
      </div>
    </aside>

    {#if current}
      <section class="review-main">
        {#if current.section === 'cleanup'}
          <div class="comparison-header">
            <div class="column-title">REVIEW FILE</div>
            <div class="column-title">CLEANUP PROBLEM</div>
          </div>

          <div class="panes">
            <div class="pane">
              {#if mediaMounted}
                {#if isVideoMedia(current)}
                  <!-- svelte-ignore a11y_media_has_caption -->
                  <video src={mediaUrl(current)} controls preload="metadata"></video>
                {:else}
                  <img src={mediaUrl(current)} alt="Review cleanup item" />
                {/if}
              {/if}
            </div>
            <div class="pane detail-pane">
              <div class="cleanup-detail">
                <div class="detail-label">State</div>
                <div>{current.state || 'pending_cleanup'}</div>
                <div class="detail-label">Last action</div>
                <div>{current.last_action || current.metadata?.last_action || 'unknown'}</div>
                <div class="detail-label">Last error</div>
                <div class="error-text">{current.last_cleanup_error || current.metadata?.last_cleanup_error || 'Cleanup failed.'}</div>
              </div>
            </div>
          </div>

          <div class="meta-bar">
            <span>File: {displayName(current)}</span>
            <span>Target: {current.metadata?.target_hash || current.metadata?.best_match || 'missing'}</span>
          </div>

          <div class="action-bar">
            <button class="action-big retry-btn" on:click={retryCleanup} disabled={acting}>Retry Cleanup</button>
          </div>
        {:else}
          <div class="comparison-header">
            <div class="column-title">NEW ITEM</div>
            <div class="column-title">BEST MATCH IN VAULT</div>
          </div>

          <div class="panes">
            <div class="pane">
              {#if mediaMounted}
                {#if isVideoMedia(current)}
                  <!-- svelte-ignore a11y_media_has_caption -->
                  <video src={mediaUrl(current)} controls preload="metadata"></video>
                {:else}
                  <img src={mediaUrl(current)} alt="New" />
                {/if}
              {/if}
            </div>
            <div class="pane">
              {#if mediaMounted && current.best_match}
                {#if isVideoMedia(current.best_match)}
                  <!-- svelte-ignore a11y_media_has_caption -->
                  <video src={mediaUrl(current.best_match)} controls preload="metadata"></video>
                {:else}
                  <img src={mediaUrl(current.best_match)} alt="Match" />
                {/if}
              {:else if mediaMounted}
                <div class="no-match">No best-match preview available.</div>
              {/if}
            </div>
          </div>

          <div class="meta-bar">
            <span>File: {displayName(current)}</span>
            <span>Target: {current.best_match?.hash || current.metadata?.best_match || 'missing'}</span>
          </div>

          <div class="action-bar">
            <button class="action-big keep-btn" on:click={() => handleAction('keep')} disabled={acting}>Keep Visible</button>
            <button class="action-big variant-btn" on:click={() => handleAction('variant')} disabled={acting}>Save Variant</button>
            <button class="action-big replace-btn" on:click={() => handleAction('replace')} disabled={acting}>Replace</button>
            <button class="action-big delete-btn" on:click={() => handleAction('delete')} disabled={acting}>Delete</button>
          </div>
        {/if}

        <div class="nav-bar">
          <button on:click={() => selectRelative(-1)} disabled={currentSectionIndex <= 0}>Previous</button>
          <div class="counter">Item {currentSectionIndex + 1} of {currentSectionItems.length}</div>
          <button on:click={() => selectRelative(1)} disabled={currentSectionIndex >= currentSectionItems.length - 1}>Next</button>
        </div>
      </section>
    {/if}
  {/if}
</div>

<style>
  .review-root {
    flex-grow: 1;
    display: flex;
    gap: 12px;
    padding: 14px;
    background: var(--bg-main);
    overflow: hidden;
  }

  .queue-list {
    width: 280px;
    min-width: 240px;
    max-width: 320px;
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .queue-title {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border-dim);
    font-size: 12px;
    color: var(--text-muted);
    font-weight: 700;
  }

  .queue-scroll {
    overflow: auto;
    flex-grow: 1;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .queue-section-title {
    margin-top: 4px;
    padding: 4px 2px;
    font-size: 11px;
    color: var(--text-muted);
    font-weight: 700;
    text-transform: uppercase;
  }

  .cleanup-title {
    margin-top: 12px;
    color: var(--accent-warning);
  }

  .queue-empty {
    padding: 7px 8px;
    font-size: 11px;
    color: var(--text-muted);
  }

  .queue-item {
    width: 100%;
    text-align: left;
    background: transparent;
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .queue-item.cleanup {
    border-color: rgba(210, 153, 34, 0.45);
  }

  .queue-item.active {
    border-color: var(--accent-primary);
    background: rgba(31, 111, 235, 0.14);
  }

  .queue-name {
    font-size: 12px;
    color: var(--text-main);
    word-break: break-word;
  }

  .queue-state {
    font-size: 11px;
    color: var(--text-muted);
    word-break: break-word;
  }

  .review-main {
    flex-grow: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-width: 0;
  }

  .comparison-header {
    display: flex;
    margin-bottom: 10px;
  }

  .column-title {
    flex: 1;
    font-size: 11px;
    color: var(--text-muted);
    font-weight: bold;
    text-align: left;
  }

  .panes {
    flex: 1;
    display: flex;
    gap: 20px;
    min-height: 0;
  }

  .pane {
    flex: 1;
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    min-width: 0;
  }

  .detail-pane {
    align-items: stretch;
    justify-content: flex-start;
    padding: 14px;
  }

  .cleanup-detail {
    display: grid;
    grid-template-columns: 110px minmax(0, 1fr);
    gap: 10px;
    width: 100%;
    color: var(--text-main);
    font-size: 12px;
    align-content: start;
  }

  .detail-label {
    color: var(--text-muted);
    font-weight: 700;
  }

  .error-text {
    color: var(--accent-warning);
    word-break: break-word;
  }

  .pane img, .pane video {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }

  .meta-bar {
    margin-top: 10px;
    display: flex;
    justify-content: space-between;
    gap: 12px;
    color: var(--text-muted);
    font-size: 11px;
    white-space: nowrap;
    overflow: hidden;
  }

  .meta-bar span {
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .action-bar {
    display: flex;
    gap: 10px;
    margin: 12px 0;
  }

  .action-big {
    flex: 1;
    padding: 10px;
    font-weight: 700;
    font-size: 13px;
  }

  .keep-btn {
    background: #8b949e;
    color: #0d1117;
    border: none;
  }

  .variant-btn {
    background: var(--accent-success);
    color: #ffffff;
    border: none;
  }

  .replace-btn, .retry-btn {
    background: var(--accent-warning);
    color: #111111;
    border: none;
  }

  .delete-btn {
    background: var(--accent-danger);
    color: #ffffff;
    border: none;
  }

  .nav-bar {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .nav-bar button {
    flex: 1;
    background: var(--bg-panel);
  }

  .counter {
    flex: 1;
    text-align: center;
    color: var(--text-muted);
    font-size: 12px;
  }

  .centered, .no-match {
    flex-grow: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
  }
</style>
