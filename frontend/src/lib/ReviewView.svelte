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
      await refreshReviewCount();
    } catch (e) {
      uiLog('ERROR', 'Failed to load review queue', { error: String(e) });
      alert('Failed to load review queue. Check App Logs for details.');
    } finally { loading = false; }
  }

  async function handleAction(action: 'keep' | 'delete' | 'variant') {
    if (!items[currentIndex] || acting) return;
    acting = true;
    try {
      const filename = items[currentIndex].filename;
      const res = await apiFetch(`/api/review/${filename}/action?action=${action}`, { method: 'POST' });
      if (!res.ok) {
        const detail = await readErrorDetail(res);
        throw new Error(detail ? `HTTP ${res.status}: ${detail}` : `HTTP ${res.status}`);
      }
      const payload = await res.json().catch(() => ({}));
      uiLog('INFO', 'Review action succeeded', { action, filename, message: payload?.message || '' });
      items = items.filter((_, i) => i !== currentIndex);
      if (currentIndex >= items.length && items.length > 0) currentIndex = items.length - 1;
      await refreshReviewCount();
    } catch (e) {
      uiLog('ERROR', 'Review action failed', { action, error: String(e) });
      alert(`Review action "${action}" failed. Check App Logs for details.`);
    } finally { acting = false; }
  }

  function handleGlobalRefresh(event: Event) {
    const detail = (event as CustomEvent).detail || {};
    if (detail.tab !== 'review') return;
    uiLog('INFO', 'Review view refresh requested');
    currentIndex = 0;
    loadReview();
  }

  onMount(() => {
    window.addEventListener('lmz:refresh', handleGlobalRefresh);
    loadReview();
    return () => window.removeEventListener('lmz:refresh', handleGlobalRefresh);
  });
  $: current = items[currentIndex];
</script>

<div class="review-container">
  {#if loading}
    <div class="centered">Loading...</div>
  {:else if items.length === 0}
    <div class="centered">Review folder is empty.</div>
  {:else}
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
                <div class="no-match">No duplicates found.</div>
            {/if}
        </div>
    </div>

    <div class="action-bar">
        <button class="keep-btn action-big" on:click={() => handleAction('keep')}>Keep</button>
        <button class="delete-btn action-big" on:click={() => handleAction('delete')}>Delete</button>
        <button class="action-big" on:click={() => handleAction('variant')}>Save as Variant</button>
    </div>

    <div class="nav-bar">
        <button on:click={() => currentIndex--} disabled={currentIndex === 0}>Previous</button>
        <div class="counter">Item {currentIndex + 1} of {items.length}</div>
        <button on:click={() => currentIndex++} disabled={currentIndex === items.length - 1}>Next</button>
    </div>
  {/if}
</div>

<style>
  .review-container {
    flex-grow: 1;
    display: flex;
    flex-direction: column;
    padding: 20px;
    background: var(--bg-main);
    overflow: hidden;
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

  .panes { flex: 1; display: flex; gap: 20px; min-height: 0; }
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

  .pane img, .pane video { max-width: 100%; max-height: 100%; object-fit: contain; }

  .action-bar {
    display: flex;
    gap: 10px;
    margin: 20px 0;
  }

  .action-big { flex: 1; padding: 12px; font-weight: bold; font-size: 14px; }
  .keep-btn { background: var(--accent-success); color: white; border: none; }
  .delete-btn { background: var(--accent-danger); color: white; border: none; }

  .nav-bar {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .nav-bar button { flex: 1; background: var(--bg-panel); }
  .counter { flex: 1; text-align: center; color: var(--text-muted); font-size: 12px; }

  .centered { flex-grow: 1; display: flex; align-items: center; justify-content: center; color: var(--text-muted); }
</style>
