<script lang="ts">
  import { onMount } from 'svelte';
  import { apiFetch, apiUrl } from './api';
  import { log as uiLog } from './logger';
  import { refreshReviewCount } from './statsStore';
  import { runtimeSessionKey } from './runtimeStore';
  import {
    IconCheckCircle,
    IconChevronLeft,
    IconChevronRight,
    IconClose,
    IconMaximizeDiagonal
  } from './icons';

  import ReviewInboxList from './ReviewInboxList.svelte';
  import ReviewWorkspace from './ReviewWorkspace.svelte';
  import ReviewActionBar from './ReviewActionBar.svelte';
  import { getMockSandboxItems, simulateSandboxAction } from './ReviewSandbox';

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
  let isSandbox = false;
  let activeMatchIndex = 0;
  let fullscreenOpen = false;

  $: if (selectedFilename) {
    activeMatchIndex = 0;
    fullscreenOpen = false;
  }

  $: resolvedMatches = current?.matches && current.matches.length > 0
    ? current.matches
    : (current?.best_match ? [current.best_match] : []);

  $: activeMatch = resolvedMatches[activeMatchIndex] || null;

  function changeMatchIndex(delta: number) {
    if (!resolvedMatches.length) return;
    activeMatchIndex = Math.max(0, Math.min(resolvedMatches.length - 1, activeMatchIndex + delta));
  }

  function handleKeydown(event: KeyboardEvent) {
    if (!fullscreenOpen) return;
    const key = event.key.toLowerCase();
    if (key === 'escape') {
      fullscreenOpen = false;
    } else if (key === 'a' || event.key === 'ArrowLeft') {
      changeMatchIndex(-1);
    } else if (key === 'd' || event.key === 'ArrowRight') {
      changeMatchIndex(1);
    }
  }

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
    if (item.url && item.url.startsWith('data:')) return item.url;
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

  async function handleAction(event: CustomEvent) {
    const action = event.detail.action;
    if (!current || acting) return;

    const resolvedMatches = current.matches && current.matches.length > 0
      ? current.matches
      : (current.best_match ? [current.best_match] : []);
    const activeMatch = resolvedMatches[activeMatchIndex] || null;
    const targetHash = activeMatch?.hash || '';

    if (isSandbox) {
      acting = true;
      await unmountMediaForFileAction();
      const result = await simulateSandboxAction(action, current.filename, items, targetHash);
      items = result.nextItems;
      isSandbox = result.isSandbox;
      acting = false;
      ensureSelection(items);
      return;
    }

    if (current.section === 'cleanup') return;
    if (action === 'replace') {
      if (!targetHash) {
        alert('No visual match selected to replace.');
        return;
      }
      const message = `Replace target copy ${targetHash.slice(0, 12)}... with ${displayName(current)}?`;
      if (!confirm(message)) return;
    }

    acting = true;
    if (action !== 'keep') await unmountMediaForFileAction();
    try {
      const filename = encodeURIComponent(current.filename);
      const url = action === 'replace'
        ? `/api/review/${filename}/action?action=${action}&target_hash=${encodeURIComponent(targetHash)}`
        : `/api/review/${filename}/action?action=${action}`;
      const res = await apiFetch(url, { method: 'POST' });
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

    if (isSandbox && current) {
      acting = true;
      await unmountMediaForFileAction();
      const result = await simulateSandboxAction('retryCleanup', current.filename, items);
      items = result.nextItems;
      isSandbox = result.isSandbox;
      acting = false;
      ensureSelection(items);
      return;
    }

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

  function startSandbox() {
    isSandbox = true;
    items = getMockSandboxItems();
    selectedFilename = items[0].filename;
  }

  function nextAnimationFrame() {
    return new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  }

  async function unmountMediaForFileAction() {
    mediaMounted = false;
    await nextAnimationFrame();
  }

  function handleSelectItem(event: CustomEvent) {
    selectedFilename = event.detail.item.filename;
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
    window.addEventListener('keydown', handleKeydown);
    loadReview();
    return () => {
      window.removeEventListener('lmz:refresh', handleGlobalRefresh);
      window.removeEventListener('keydown', handleKeydown);
    };
  });
</script>

<div class="review-root">
  {#if loading}
    <div class="centered-state">
      <div class="spinner"></div>
      <span>Loading review queue...</span>
    </div>
  {:else if items.length === 0}
    <div class="centered-state empty-state">
      <IconCheckCircle size={48} strokeWidth={1.5} />
      <span>Review folder is completely empty.</span>
      <p class="sub-muted">Everything is perfectly ingested and categorized!</p>
      <button class="sandbox-trigger-btn" on:click={startSandbox}>
        Try Review Sandbox
      </button>
    </div>
  {:else}
    <!-- Queue Sidebar List -->
    <ReviewInboxList
      {items}
      {pendingItems}
      {cleanupItems}
      {current}
      {isVideoMedia}
      {displayName}
      currentIndex={currentSectionIndex}
      totalCount={currentSectionItems.length}
      on:select={handleSelectItem}
      on:prev={() => selectRelative(-1)}
      on:next={() => selectRelative(1)}
    />

    <!-- Main Comparison Section -->
    {#if current}
      <section class="review-main">
        <div class="workspace-container">
          <!-- Render Comparison Panes and Metadata card -->
          <ReviewWorkspace
            {current}
            {mediaMounted}
            {isVideoMedia}
            {mediaUrl}
            {displayName}
            {activeMatchIndex}
            on:changeMatch={(e) => activeMatchIndex = e.detail.index}
            on:toggleFullscreen={() => fullscreenOpen = true}
          />
        </div>

        <!-- Renders Bottom Action Bar -->
        <ReviewActionBar
          section={current.section || 'pending'}
          {acting}
          on:action={handleAction}
          on:retryCleanup={retryCleanup}
        />
      </section>
    {/if}
  {/if}

  {#if fullscreenOpen && current}
    <!-- Symmetrical Fullscreen Comparison Overlay -->
    <div class="comparison-overlay">
      <div class="overlay-header">
        <div class="overlay-header-left">
          <span class="overlay-title">Symmetrical Duplicate Comparison</span>
          <span class="overlay-subtitle">{current.filename}</span>
        </div>
        <div class="overlay-header-right">
          {#if resolvedMatches.length > 1}
            <div class="match-nav inverse">
              <button class="match-nav-btn" on:click={() => changeMatchIndex(-1)} disabled={activeMatchIndex <= 0} title="Previous Match (A or ArrowLeft)">
                <IconChevronLeft size={10} />
              </button>
              <span class="match-counter">Match {activeMatchIndex + 1} of {resolvedMatches.length}</span>
              <button class="match-nav-btn" on:click={() => changeMatchIndex(1)} disabled={activeMatchIndex >= resolvedMatches.length - 1} title="Next Match (D or ArrowRight)">
                <IconChevronRight size={10} />
              </button>
            </div>
          {/if}
          <button class="close-overlay-btn" on:click={() => fullscreenOpen = false} title="Close Comparison (Esc)">
            <IconClose size={16} />
          </button>
        </div>
      </div>

      <div class="overlay-workspace">
        <!-- Left side (Incoming Staged) -->
        <div class="overlay-pane">
          <div class="pane-badge purple">Incoming Staged File</div>
          <div class="pane-media">
            {#if isVideoMedia(current)}
              <!-- svelte-ignore a11y-media-has-caption -->
              <video src={mediaUrl(current)} controls preload="metadata"></video>
            {:else}
              <img src={mediaUrl(current)} alt="New staged item" />
            {/if}
          </div>
          <div class="pane-meta">
            <div class="meta-row"><span class="meta-label">Original Filename:</span> <span class="meta-val truncate" title={displayName(current)}>{displayName(current)}</span></div>
            <div class="meta-row"><span class="meta-label">Format:</span> <span class="meta-val uppercase">{current.extension || extFromUrl(current.url) || 'unknown'}</span></div>
            <div class="meta-row"><span class="meta-label">Artist:</span> <span class="meta-val">{current.metadata?.artist || 'None detected'}</span></div>
          </div>
        </div>

        <!-- Right side (Vault Duplicate) -->
        <div class="overlay-pane">
          <div class="pane-badge blue">Vault Duplicate Copy</div>
          <div class="pane-media">
            {#if activeMatch}
              {#if isVideoMedia(activeMatch)}
                <!-- svelte-ignore a11y-media-has-caption -->
                <video src={mediaUrl(activeMatch)} controls preload="metadata"></video>
              {:else}
                <img src={mediaUrl(activeMatch)} alt="Match copy" />
              {/if}
            {:else}
              <div class="no-match-fullscreen">No matching duplicate copy.</div>
            {/if}
          </div>
          <div class="pane-meta">
            {#if activeMatch}
              <div class="meta-row"><span class="meta-label">Hash ID:</span> <span class="meta-val truncate-hash" title={activeMatch.hash}>{activeMatch.hash}</span></div>
              <div class="meta-row"><span class="meta-label">Format:</span> <span class="meta-val uppercase">{activeMatch.extension || 'unknown'}</span></div>
              <div class="meta-row"><span class="meta-label">Artist:</span> <span class="meta-val">{activeMatch.artist || 'Unassigned'}</span></div>
            {/if}
          </div>
        </div>
      </div>
      
      <div class="overlay-footer-hud">
        <span class="hud-item">[A] / [D] or Arrow keys to cycle duplicates</span>
        <span class="hud-item">[Esc] to close symmetrical view</span>
      </div>
    </div>
  {/if}
</div>

<style>
  .review-root {
    flex-grow: 1;
    display: flex;
    gap: 16px;
    padding: 16px;
    background: var(--bg-main);
    overflow: hidden;
    height: calc(100vh - var(--header-height));
  }

  /* Main Comparison Body */
  .review-main {
    flex-grow: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-width: 0;
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 6px;
  }

  .workspace-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 16px;
    min-height: 0;
    overflow-y: auto;
  }

  /* Nav arrow footer removed - consolidated in ReviewInboxList footer */

  /* Centered Loader states */
  .centered-state {
    flex-grow: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    color: var(--text-muted);
    font-size: 13px;
  }

  .empty-state :global(svg) {
    color: var(--text-muted);
    background: rgba(255, 255, 255, 0.03);
    padding: 16px;
    border-radius: 50%;
    border: 1px solid var(--border-dim);
    margin-bottom: 8px;
  }

  .empty-state span {
    font-size: 15px;
    font-weight: bold;
    color: var(--text-bright);
  }

  .sub-muted {
    font-size: 11px;
    color: var(--text-muted);
    margin: 0;
  }

  .sandbox-trigger-btn {
    margin-top: 16px;
    padding: 8px 20px;
    background: transparent;
    border: 2px solid var(--accent-primary);
    color: var(--accent-primary);
    font-weight: 700;
    font-size: 12px;
    border-radius: 6px;
    cursor: pointer;
  }

  .sandbox-trigger-btn:hover {
    background: var(--accent-primary);
    color: white;
  }

  /* Loading Spinner */
  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid rgba(88, 166, 255, 0.1);
    border-top-color: var(--accent-primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* Fullscreen Symmetrical Comparison Overlay */
  .comparison-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: #090c10;
    z-index: 10000;
    display: flex;
    flex-direction: column;
    padding: 24px;
    box-sizing: border-box;
  }

  .overlay-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 48px;
    border-bottom: 1px solid var(--border-dim);
    padding-bottom: 16px;
    margin-bottom: 24px;
  }

  .overlay-header-left {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .overlay-title {
    font-size: 14px;
    font-weight: 700;
    color: var(--text-bright);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .overlay-subtitle {
    font-size: 11px;
    color: var(--text-muted);
    font-family: monospace;
  }

  .overlay-header-right {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .match-nav.inverse {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
  }

  .close-overlay-btn {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 1px solid transparent;
    color: var(--text-muted);
    border-radius: 4px;
    cursor: pointer;
    padding: 0;
  }

  .close-overlay-btn:hover {
    background: rgba(248, 81, 73, 0.15);
    border-color: rgba(248, 81, 73, 0.25);
    color: var(--accent-danger);
  }

  .overlay-workspace {
    flex: 1;
    display: flex;
    gap: 24px;
    min-height: 0;
  }

  .overlay-pane {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    gap: 14px;
  }

  .pane-badge {
    align-self: flex-start;
    font-size: 10px;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 4px;
    text-transform: uppercase;
  }

  .pane-badge.purple {
    color: var(--accent-purple);
    background: rgba(163, 113, 247, 0.12);
    border: 1px solid rgba(163, 113, 247, 0.25);
  }

  .pane-badge.blue {
    color: var(--accent-primary);
    background: rgba(88, 166, 255, 0.1);
    border: 1px solid rgba(88, 166, 255, 0.2);
  }

  .pane-media {
    flex: 1;
    background: #000000;
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    position: relative;
  }

  .pane-media img,
  .pane-media video {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }

  .pane-meta {
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .truncate-hash {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-family: monospace;
    max-width: 400px;
    color: var(--text-main);
  }

  .no-match-fullscreen {
    color: var(--text-muted);
    font-style: italic;
    font-size: 13px;
  }

  .overlay-footer-hud {
    display: flex;
    justify-content: center;
    gap: 32px;
    margin-top: 24px;
    font-size: 11px;
    color: var(--text-muted);
    font-weight: 600;
    border-top: 1px solid var(--border-dim);
    padding-top: 16px;
  }

  .hud-item {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.05);
    padding: 4px 12px;
    border-radius: 4px;
  }
</style>
