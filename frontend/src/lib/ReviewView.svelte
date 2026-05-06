<script lang="ts">
  import { onMount } from 'svelte';
  import { apiFetch, apiUrl } from './api';
  import { log as uiLog } from './logger';
  import { refreshReviewCount } from './statsStore';

  interface ReviewItem {
    filename: string;
    url: string;
    mime_type?: string;
    extension?: string;
    metadata: any;
    state?: string;
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
    mime_type?: string;
    extension?: string;
  } | null | undefined;

  let items: ReviewItem[] = [];
  let currentIndex = 0;
  let loading = true;
  let acting = false;

  const VIDEO_EXTENSIONS = new Set(['.mp4', '.webm', '.ogv', '.mov', '.m4v', '.avi', '.mkv']);

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

  async function loadReview() {
    loading = true;
    try {
      const res = await apiFetch('/api/review');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      items = Array.isArray(data) ? data : [];
      if (currentIndex >= items.length) currentIndex = Math.max(0, items.length - 1);
      await refreshReviewCount();
    } catch (e) {
      uiLog('ERROR', 'Failed to load review queue', { error: String(e) });
      alert('Failed to load review queue. Check App Logs for details.');
    } finally {
      loading = false;
    }
  }

  async function handleAction(action: 'keep' | 'delete' | 'variant' | 'replace') {
    const current = items[currentIndex];
    if (!current || acting) return;
    if (action === 'replace') {
      const target = String(current.metadata?.best_match || current.best_match?.hash || '').trim();
      const message = target
        ? `Replace target ${target.slice(0, 10)}... with ${current.filename}?`
        : `Replace target is missing for ${current.filename}. Continue anyway?`;
      if (!confirm(message)) return;
    }

    acting = true;
    try {
      const res = await apiFetch(`/api/review/${current.filename}/action?action=${action}`, { method: 'POST' });
      if (!res.ok) {
        const detail = await readErrorDetail(res);
        throw new Error(detail ? `HTTP ${res.status}: ${detail}` : `HTTP ${res.status}`);
      }
      const payload = await res.json().catch(() => ({}));
      if (payload?.status === 'warning') {
        uiLog('WARNING', 'Review action warning', { action, filename: current.filename, message: payload?.message || '' });
        alert(payload?.message || 'Action returned warning.');
        await refreshReviewCount();
        return;
      }

      uiLog('INFO', 'Review action succeeded', { action, filename: current.filename, message: payload?.message || '' });
      items = items.filter((_, i) => i !== currentIndex);
      if (currentIndex >= items.length && items.length > 0) currentIndex = items.length - 1;
      await refreshReviewCount();
    } catch (e) {
      uiLog('ERROR', 'Review action failed', { action, error: String(e) });
      alert(`Review action "${action}" failed. Check App Logs for details.`);
    } finally {
      acting = false;
    }
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

  $: current = items[currentIndex];
</script>

<div class="review-root">
  {#if loading}
    <div class="centered">Loading...</div>
  {:else if items.length === 0}
    <div class="centered">Review folder is empty.</div>
  {:else}
    <aside class="queue-list">
      <div class="queue-title">Pending Review ({items.length})</div>
      <div class="queue-scroll">
        {#each items as item, index}
          <button class="queue-item {index === currentIndex ? 'active' : ''}" on:click={() => currentIndex = index}>
            <span class="queue-name">{item.filename}</span>
            <span class="queue-state">{item.state || 'pending'}</span>
          </button>
        {/each}
      </div>
    </aside>

    <section class="review-main">
      <div class="comparison-header">
        <div class="column-title">NEW ITEM</div>
        <div class="column-title">BEST MATCH IN VAULT</div>
      </div>

      <div class="panes">
        <div class="pane">
          {#if isVideoMedia(current)}
            <!-- svelte-ignore a11y_media_has_caption -->
            <video src={apiUrl(current.url)} controls preload="metadata"></video>
          {:else}
            <img src={apiUrl(current.url)} alt="New" />
          {/if}
        </div>
        <div class="pane">
          {#if current.best_match}
            {#if isVideoMedia(current.best_match)}
              <!-- svelte-ignore a11y_media_has_caption -->
              <video src={apiUrl(current.best_match.url)} controls preload="metadata"></video>
            {:else}
              <img src={apiUrl(current.best_match.url)} alt="Match" />
            {/if}
          {:else}
            <div class="no-match">No best-match preview available.</div>
          {/if}
        </div>
      </div>

      <div class="meta-bar">
        <span>File: {current.filename}</span>
        <span>Target: {current.best_match?.hash || current.metadata?.best_match || 'missing'}</span>
      </div>

      <div class="action-bar">
        <button class="action-big keep-btn" on:click={() => handleAction('keep')} disabled={acting}>Keep for Later</button>
        <button class="action-big variant-btn" on:click={() => handleAction('variant')} disabled={acting}>Save Variant</button>
        <button class="action-big replace-btn" on:click={() => handleAction('replace')} disabled={acting}>Replace</button>
        <button class="action-big delete-btn" on:click={() => handleAction('delete')} disabled={acting}>Delete</button>
      </div>

      <div class="nav-bar">
        <button on:click={() => currentIndex--} disabled={currentIndex === 0}>Previous</button>
        <div class="counter">Item {currentIndex + 1} of {items.length}</div>
        <button on:click={() => currentIndex++} disabled={currentIndex === items.length - 1}>Next</button>
      </div>
    </section>
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

  .replace-btn {
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

  .centered {
    flex-grow: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
  }
</style>
