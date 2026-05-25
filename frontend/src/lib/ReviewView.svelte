<script lang="ts">
  import { onMount } from 'svelte';
  import { apiFetch, apiUrl } from './api';
  import { log as uiLog } from './logger';
  import { refreshReviewCount } from './statsStore';
  import { runtimeSessionKey } from './runtimeStore';
  import {
    IconAlertTriangle,
    IconCheckCircle,
    IconChevronLeft,
    IconChevronRight,
    IconCopy,
    IconEye,
    IconImage,
    IconInfoCircle,
    IconRefresh,
    IconReplace,
    IconTrash,
    IconVideo
  } from './icons';

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
    <div class="centered-state">
      <div class="spinner"></div>
      <span>Loading review queue...</span>
    </div>
  {:else if items.length === 0}
    <div class="centered-state empty-state">
      <IconCheckCircle size={48} strokeWidth={1.5} />
      <span>Review folder is completely empty.</span>
      <p class="sub-muted">Everything is perfectly ingested and categorized!</p>
    </div>
  {:else}
    <!-- Queue Sidebar List -->
    <aside class="queue-list">
      <div class="queue-header">
        <span class="queue-title">Review Inbox</span>
        <span class="total-badge">{items.length} items</span>
      </div>

      <div class="queue-scroll">
        <div class="queue-section-header">
          <span class="section-indicator blue-dot"></span>
          <span class="section-title">Pending ({pendingItems.length})</span>
        </div>
        {#if pendingItems.length === 0}
          <div class="queue-empty">No pending decisions.</div>
        {:else}
          {#each pendingItems as item}
            <button class="queue-item" class:active={item.filename === current?.filename} on:click={() => selectItem(item)}>
              <div class="queue-item-row">
                <span class="media-icon-indicator" title={isVideoMedia(item) ? "Video File" : "Image File"}>
                  {#if isVideoMedia(item)}
                    <IconVideo size={12} />
                  {:else}
                    <IconImage size={12} />
                  {/if}
                </span>
                <span class="queue-name truncate">{displayName(item)}</span>
              </div>
              <span class="queue-state">{item.state || 'pending decision'}</span>
            </button>
          {/each}
        {/if}

        <div class="queue-section-header cleanup-header">
          <span class="section-indicator orange-dot"></span>
          <span class="section-title">Cleanup ({cleanupItems.length})</span>
        </div>
        {#if cleanupItems.length === 0}
          <div class="queue-empty">No cleanup problems.</div>
        {:else}
          {#each cleanupItems as item}
            <button class="queue-item cleanup" class:active={item.filename === current?.filename} on:click={() => selectItem(item)}>
              <div class="queue-item-row">
                <span class="media-icon-indicator warn">
                  <IconAlertTriangle size={12} />
                </span>
                <span class="queue-name truncate">{displayName(item)}</span>
              </div>
              <span class="queue-state truncate">{item.last_cleanup_error || item.state || 'pending_cleanup'}</span>
            </button>
          {/each}
        {/if}
      </div>
    </aside>

    <!-- Main Comparison Section -->
    {#if current}
      <section class="review-main">
        {#if current.section === 'cleanup'}
          <!-- Header titles -->
          <div class="comparison-header">
            <div class="column-title">
              <span class="pill-badge warning">Review File (Active)</span>
            </div>
            <div class="column-title">
              <span class="pill-badge neutral">Cleanup Error Details</span>
            </div>
          </div>

          <!-- Comparison panes -->
          <div class="panes">
            <div class="pane">
              {#if mediaMounted}
                {#if isVideoMedia(current)}
                  <!-- svelte-ignore a11y-media-has-caption -->
                  <video src={mediaUrl(current)} controls preload="metadata"></video>
                {:else}
                  <img src={mediaUrl(current)} alt="Review cleanup item" />
                {/if}
              {/if}
            </div>
            <div class="pane detail-pane">
              <div class="cleanup-detail">
                <div class="detail-label">Current State</div>
                <div class="detail-val">{current.state || 'pending_cleanup'}</div>
                <div class="detail-label">Last Action Attempt</div>
                <div class="detail-val">{current.last_action || current.metadata?.last_action || 'unknown'}</div>
                <div class="detail-label">Error Output</div>
                <div class="error-text-box">
                  {current.last_cleanup_error || current.metadata?.last_cleanup_error || 'Cleanup failed.'}
                </div>
              </div>
            </div>
          </div>

          <!-- File info metadata card -->
          <div class="meta-card">
            <div class="meta-grid">
              <div class="meta-item"><span class="meta-label">Original File:</span> <span class="meta-val" title={displayName(current)}>{displayName(current)}</span></div>
              <div class="meta-item"><span class="meta-label">Target ID:</span> <span class="meta-val" title={current.metadata?.target_hash || current.metadata?.best_match || 'missing'}>{current.metadata?.target_hash || current.metadata?.best_match || 'missing'}</span></div>
            </div>
          </div>

          <!-- Big Action Button Area -->
          <div class="action-bar">
            <button class="action-big retry-btn" on:click={retryCleanup} disabled={acting}>
              <IconRefresh size={14} />
              <span>Retry Cleanup & Delete Staged File</span>
            </button>
          </div>
        {:else}
          <!-- Header titles -->
          <div class="comparison-header">
            <div class="column-title">
              <span class="pill-badge primary">Incoming Item (Inbox)</span>
            </div>
            <div class="column-title">
              <span class="pill-badge info">Best Similarity Match in Vault</span>
            </div>
          </div>

          <!-- Comparison panes -->
          <div class="panes">
            <div class="pane">
              {#if mediaMounted}
                {#if isVideoMedia(current)}
                  <!-- svelte-ignore a11y-media-has-caption -->
                  <video src={mediaUrl(current)} controls preload="metadata"></video>
                {:else}
                  <img src={mediaUrl(current)} alt="New" />
                {/if}
              {/if}
            </div>
            <div class="pane">
              {#if mediaMounted && current.best_match}
                {#if isVideoMedia(current.best_match)}
                  <!-- svelte-ignore a11y-media-has-caption -->
                  <video src={mediaUrl(current.best_match)} controls preload="metadata"></video>
                {:else}
                  <img src={mediaUrl(current.best_match)} alt="Match" />
                {/if}
              {:else if mediaMounted}
                <div class="no-match">
                  <IconInfoCircle size={36} strokeWidth={1.5} />
                  <span>No best-match duplicates detected in vault.</span>
                  <p class="sub-muted">This file appears to be entirely unique.</p>
                </div>
              {/if}
            </div>
          </div>

          <!-- File info metadata card -->
          <div class="meta-card">
            <div class="meta-grid">
              <div class="meta-item"><span class="meta-label">Original File:</span> <span class="meta-val" title={displayName(current)}>{displayName(current)}</span></div>
              <div class="meta-item"><span class="meta-label">Match Target:</span> <span class="meta-val" title={current.best_match?.hash || current.metadata?.best_match || 'missing'}>{current.best_match?.hash || current.metadata?.best_match || 'none'}</span></div>
            </div>
          </div>

          <!-- Big Action Button Area -->
          <div class="action-bar">
            <!-- Keep: Leaves file in review staging -->
            <button class="action-big keep-btn" on:click={() => handleAction('keep')} disabled={acting}>
              <IconEye size={14} />
              <span>Keep Staged</span>
            </button>
            <!-- Save Variant: Ingests new variant cleanly without replacing matching vault item -->
            <button class="action-big variant-btn" on:click={() => handleAction('variant')} disabled={acting}>
              <IconCopy size={14} />
              <span>Save as Variant</span>
            </button>
            <!-- Replace: Replaces the duplicate matching file in Vault, preserving manual YAML tags -->
            <button class="action-big replace-btn" on:click={() => handleAction('replace')} disabled={acting}>
              <IconReplace size={14} />
              <span>Replace Vault Copy</span>
            </button>
            <!-- Delete: Deletes the staged file from Review immediately -->
            <button class="action-big delete-btn" on:click={() => handleAction('delete')} disabled={acting}>
              <IconTrash size={14} />
              <span>Delete Staged</span>
            </button>
          </div>
        {/if}

        <!-- Queue Nav Bar -->
        <div class="nav-bar">
          <button class="nav-arrow-btn" on:click={() => selectRelative(-1)} disabled={currentSectionIndex <= 0}>
            <IconChevronLeft size={14} />
            <span>Previous</span>
          </button>
          <div class="counter">
            Item <span class="focus-number">{currentSectionIndex + 1}</span> of <span class="total-number">{currentSectionItems.length}</span>
          </div>
          <button class="nav-arrow-btn" on:click={() => selectRelative(1)} disabled={currentSectionIndex >= currentSectionItems.length - 1}>
            <span>Next</span>
            <IconChevronRight size={14} />
          </button>
        </div>
      </section>
    {/if}
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

  /* Premium Sidebar List */
  .queue-list {
    width: 290px;
    min-width: 260px;
    max-width: 320px;
    background: rgba(22, 27, 34, 0.92);
    border: 1px solid var(--border-dim);
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  }

  .queue-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    border-bottom: 1px solid var(--border-dim);
    background: rgba(0, 0, 0, 0.15);
  }

  .queue-title {
    font-size: 13px;
    color: var(--text-bright);
    font-weight: 700;
  }

  .total-badge {
    font-size: 10px;
    font-weight: bold;
    color: var(--text-muted);
    background: rgba(255, 255, 255, 0.06);
    padding: 2px 8px;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.08);
  }

  .queue-scroll {
    overflow-y: auto;
    overflow-x: hidden;
    flex-grow: 1;
    padding: 10px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  /* Custom scrollbar for sidebar */
  .queue-scroll::-webkit-scrollbar {
    width: 6px;
  }
  .queue-scroll::-webkit-scrollbar-track {
    background: transparent;
  }
  .queue-scroll::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.1);
    border-radius: 3px;
  }
  .queue-scroll::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.25);
  }

  .queue-section-header {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 8px 0 2px 2px;
  }

  .section-indicator {
    width: 6px;
    height: 6px;
    border-radius: 50%;
  }

  .section-indicator.blue-dot {
    background: var(--accent-primary);
    box-shadow: 0 0 6px var(--accent-primary);
  }

  .section-indicator.orange-dot {
    background: var(--accent-warning);
    box-shadow: 0 0 6px var(--accent-warning);
  }

  .section-title {
    font-size: 10px;
    color: var(--text-muted);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .queue-empty {
    padding: 10px;
    font-size: 11px;
    color: var(--text-muted);
    font-style: italic;
    background: rgba(255, 255, 255, 0.02);
    border: 1px dashed var(--border-dim);
    border-radius: 6px;
    text-align: center;
  }

  /* Queue card item */
  .queue-item {
    width: 100%;
    text-align: left;
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    padding: 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    cursor: pointer;
  }

  .queue-item:hover {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(255, 255, 255, 0.15);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  }

  .queue-item.cleanup {
    border-color: rgba(240, 139, 44, 0.2);
    background: rgba(240, 139, 44, 0.01);
  }

  .queue-item.cleanup:hover {
    border-color: rgba(240, 139, 44, 0.4);
    background: rgba(240, 139, 44, 0.04);
  }

  .queue-item.active {
    border-color: var(--accent-primary) !important;
    background: rgba(31, 111, 235, 0.1) !important;
    box-shadow: 0 4px 16px rgba(31, 111, 235, 0.15);
  }

  .queue-item-row {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  .media-icon-indicator {
    display: inline-grid;
    place-items: center;
    width: 20px;
    height: 20px;
    background: rgba(255, 255, 255, 0.06);
    border-radius: 4px;
    color: var(--text-muted);
    flex-shrink: 0;
  }

  .queue-item:hover .media-icon-indicator {
    color: var(--accent-primary);
    background: rgba(88, 166, 255, 0.15);
  }

  .media-icon-indicator.warn {
    color: var(--accent-warning);
    background: rgba(240, 139, 44, 0.1);
  }

  .queue-name {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-main);
  }

  .queue-item.active .queue-name {
    color: var(--text-bright);
  }

  .queue-state {
    font-size: 10px;
    color: var(--text-muted);
    padding-left: 28px;
  }

  /* Main Comparison Body */
  .review-main {
    flex-grow: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-width: 0;
  }

  .comparison-header {
    display: flex;
    gap: 16px;
    margin-bottom: 12px;
  }

  .column-title {
    flex: 1;
    display: flex;
    align-items: center;
  }

  .pill-badge {
    font-size: 11px;
    font-weight: bold;
    padding: 4px 12px;
    border-radius: 999px;
    border: 1px solid transparent;
  }

  .pill-badge.primary {
    color: var(--accent-purple);
    background: rgba(163, 113, 247, 0.12);
    border-color: rgba(163, 113, 247, 0.25);
  }

  .pill-badge.info {
    color: var(--accent-primary);
    background: rgba(88, 166, 255, 0.1);
    border-color: rgba(88, 166, 255, 0.2);
  }

  .pill-badge.warning {
    color: var(--accent-warning);
    background: rgba(240, 139, 44, 0.1);
    border-color: rgba(240, 139, 44, 0.2);
  }

  .pill-badge.neutral {
    color: var(--text-muted);
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(255, 255, 255, 0.08);
  }

  .panes {
    flex: 1;
    display: flex;
    gap: 16px;
    min-height: 0;
  }

  .pane {
    flex: 1;
    background: rgba(15, 17, 23, 0.25);
    border: 1px solid var(--border-dim);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    min-width: 0;
    position: relative;
    box-shadow: inset 0 2px 10px rgba(0,0,0,0.5);
  }

  .pane:hover {
    border-color: rgba(255, 255, 255, 0.1);
  }

  .detail-pane {
    align-items: stretch;
    justify-content: flex-start;
    padding: 20px;
    background: rgba(22, 27, 34, 0.35);
  }

  .cleanup-detail {
    display: grid;
    grid-template-columns: 140px minmax(0, 1fr);
    gap: 14px 10px;
    width: 100%;
    color: var(--text-main);
    font-size: 12px;
    align-content: start;
  }

  .detail-label {
    color: var(--text-muted);
    font-weight: bold;
    text-transform: uppercase;
    font-size: 10px;
    letter-spacing: 0.5px;
    align-self: center;
  }

  .detail-val {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.06);
    padding: 4px 10px;
    border-radius: 6px;
    font-family: monospace;
    font-size: 11px;
    color: var(--text-bright);
  }

  .error-text-box {
    background: rgba(240, 139, 44, 0.08);
    border: 1px solid rgba(240, 139, 44, 0.25);
    padding: 10px 14px;
    border-radius: 6px;
    font-family: monospace;
    font-size: 11px;
    color: var(--accent-warning);
    word-break: break-all;
    overflow-y: auto;
    max-height: 240px;
  }

  .pane img, .pane video {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    border-radius: 4px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
  }

  /* Unique duplicate placeholder */
  .no-match {
    flex-direction: column;
    gap: 12px;
    text-align: center;
    padding: 30px;
  }

  .no-match :global(svg) {
    color: var(--accent-success);
    background: rgba(46, 160, 67, 0.15);
    padding: 8px;
    border-radius: 50%;
  }

  .no-match span {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-bright);
  }

  .sub-muted {
    font-size: 11px;
    color: var(--text-muted);
    margin: 0;
  }

  /* File Info Metadata Card */
  .meta-card {
    background: rgba(0, 0, 0, 0.2);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    padding: 10px 16px;
    margin-top: 12px;
  }

  .meta-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }

  .meta-item {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    font-size: 11px;
  }

  .meta-label {
    color: var(--text-muted);
    font-weight: bold;
    flex-shrink: 0;
  }

  .meta-val {
    color: var(--text-main);
    font-family: monospace;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }

  /* Action Buttons panel */
  .action-bar {
    display: flex;
    gap: 12px;
    margin: 12px 0;
  }

  .action-big {
    flex: 1;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    font-weight: 700;
    font-size: 12px;
    border-radius: 8px;
    cursor: pointer;
  }

  .action-big:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(0,0,0,0.3);
  }

  .action-big:active:not(:disabled) {
    transform: translateY(0);
  }

  .action-big:disabled {
    cursor: not-allowed;
    opacity: 0.45;
  }

  .keep-btn {
    background: rgba(139, 148, 158, 0.15);
    color: var(--text-bright);
    border: 1px solid rgba(139, 148, 158, 0.3);
  }
  .keep-btn:hover:not(:disabled) {
    background: rgba(139, 148, 158, 0.25);
    border-color: rgba(255, 255, 255, 0.3);
  }

  .variant-btn {
    background: rgba(46, 160, 67, 0.15);
    color: var(--accent-success);
    border: 1px solid rgba(46, 160, 67, 0.3);
  }
  .variant-btn:hover:not(:disabled) {
    background: var(--accent-success);
    color: white;
    border-color: var(--accent-success);
  }

  .replace-btn {
    background: rgba(240, 139, 44, 0.15);
    color: var(--accent-warning);
    border: 1px solid rgba(240, 139, 44, 0.3);
  }
  .replace-btn:hover:not(:disabled) {
    background: var(--accent-warning);
    color: #111111;
    border-color: var(--accent-warning);
  }

  .retry-btn {
    background: rgba(240, 139, 44, 0.15);
    color: var(--accent-warning);
    border: 1px solid rgba(240, 139, 44, 0.3);
    width: 100%;
  }
  .retry-btn:hover:not(:disabled) {
    background: var(--accent-warning);
    color: #111111;
    border-color: var(--accent-warning);
  }

  .delete-btn {
    background: rgba(248, 81, 73, 0.15);
    color: var(--accent-danger);
    border: 1px solid rgba(248, 81, 73, 0.3);
  }
  .delete-btn:hover:not(:disabled) {
    background: var(--accent-danger);
    color: white;
    border-color: var(--accent-danger);
  }

  /* Nav arrow footer */
  .nav-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    background: rgba(0, 0, 0, 0.15);
    padding: 8px 16px;
    border-radius: 8px;
    border: 1px solid var(--border-dim);
  }

  .nav-arrow-btn {
    flex: 1;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.08);
    color: var(--text-main);
    border-radius: 6px;
    cursor: pointer;
    font-size: 11px;
    font-weight: 600;
  }

  .nav-arrow-btn:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.1);
    color: var(--text-bright);
    border-color: rgba(255, 255, 255, 0.2);
  }

  .nav-arrow-btn:disabled {
    cursor: not-allowed;
    opacity: 0.35;
  }

  .counter {
    flex: 1.5;
    text-align: center;
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 500;
  }

  .focus-number {
    color: var(--text-bright);
    font-weight: 700;
  }

  .total-number {
    font-weight: bold;
  }

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
</style>
