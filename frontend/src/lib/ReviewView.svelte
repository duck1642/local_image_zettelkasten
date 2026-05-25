<script lang="ts">
  import { onMount } from 'svelte';
  import { apiFetch, apiUrl } from './api';
  import { log as uiLog } from './logger';
  import { refreshReviewCount } from './statsStore';
  import { runtimeSessionKey } from './runtimeStore';
  import {
    IconCheckCircle,
    IconChevronLeft,
    IconChevronRight
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

    if (isSandbox) {
      acting = true;
      await unmountMediaForFileAction();
      const result = await simulateSandboxAction(action, current.filename, items);
      items = result.nextItems;
      isSandbox = result.isSandbox;
      acting = false;
      ensureSelection(items);
      return;
    }

    if (current.section === 'cleanup') return;
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
      on:select={handleSelectItem}
    />

    <!-- Main Comparison Section -->
    {#if current}
      <section class="review-main">
        <!-- Render Comparison Panes and Metadata card -->
        <ReviewWorkspace
          {current}
          {mediaMounted}
          {isVideoMedia}
          {mediaUrl}
          {displayName}
        />

        <!-- Renders Bottom Action Bar -->
        <ReviewActionBar
          section={current.section || 'pending'}
          {acting}
          on:action={handleAction}
          on:retryCleanup={retryCleanup}
        />

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

  /* Main Comparison Body */
  .review-main {
    flex-grow: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-width: 0;
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
</style>
