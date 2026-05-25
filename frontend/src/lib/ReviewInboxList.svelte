<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { IconAlertTriangle, IconImage, IconVideo } from './icons';

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
    best_match: any;
  }

  export let items: ReviewItem[] = [];
  export let pendingItems: ReviewItem[] = [];
  export let cleanupItems: ReviewItem[] = [];
  export let current: ReviewItem | null = null;
  export let isVideoMedia: (item: any) => boolean;
  export let displayName: (item: any) => string;

  const dispatch = createEventDispatcher();

  function selectItem(item: ReviewItem) {
    dispatch('select', { item });
  }
</script>

<aside class="queue-list">
  <div class="queue-header">
    <span class="queue-title">Review Inbox</span>
    <span class="total-badge">{items.length} items</span>
  </div>

  <div class="queue-scroll">
    <div class="queue-section-header">
      <span class="section-indicator blue-dot"></span>
      <span class="section-title">Pending Decisions ({pendingItems.length})</span>
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
      <span class="section-title">Cleanup Queue ({cleanupItems.length})</span>
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

<style>
  .queue-list {
    width: 290px;
    min-width: 260px;
    max-width: 320px;
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .queue-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    border-bottom: 1px solid var(--border-dim);
    background: rgba(0, 0, 0, 0.2);
  }

  .queue-title {
    font-size: 12px;
    color: var(--text-bright);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .total-badge {
    font-size: 10px;
    font-weight: 700;
    color: var(--text-muted);
    background: rgba(255, 255, 255, 0.05);
    padding: 2px 8px;
    border-radius: 4px;
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

  .queue-scroll::-webkit-scrollbar {
    width: 6px;
  }
  .queue-scroll::-webkit-scrollbar-track {
    background: transparent;
  }
  .queue-scroll::-webkit-scrollbar-thumb {
    background: #30363d;
    border-radius: 3px;
  }
  .queue-scroll::-webkit-scrollbar-thumb:hover {
    background: #484f58;
  }

  .queue-section-header {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 8px 0 2px 2px;
  }

  .cleanup-header {
    margin-top: 14px;
  }

  .section-indicator {
    width: 6px;
    height: 6px;
    border-radius: 50%;
  }

  .section-indicator.blue-dot {
    background: var(--accent-primary);
  }

  .section-indicator.orange-dot {
    background: var(--accent-warning);
  }

  .section-title {
    font-size: 10px;
    color: var(--text-muted);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .queue-empty {
    padding: 12px;
    font-size: 11px;
    color: var(--text-muted);
    font-style: italic;
    background: rgba(255, 255, 255, 0.01);
    border: 1px dashed var(--border-dim);
    border-radius: 4px;
    text-align: center;
  }

  .queue-item {
    width: 100%;
    text-align: left;
    background: rgba(255, 255, 255, 0.01);
    border: 1px solid var(--border-dim);
    border-left: 3px solid transparent;
    border-radius: 4px;
    padding: 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    cursor: pointer;
  }

  .queue-item:hover {
    background: var(--bg-hover);
    border-color: rgba(255, 255, 255, 0.12);
  }

  .queue-item.active {
    border-color: var(--border-dim) !important;
    border-left: 3px solid var(--accent-primary) !important;
    background: rgba(31, 111, 235, 0.08) !important;
  }

  .queue-item.cleanup.active {
    border-color: var(--border-dim) !important;
    border-left: 3px solid var(--accent-warning) !important;
    background: rgba(240, 139, 44, 0.08) !important;
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
    width: 18px;
    height: 18px;
    background: rgba(255, 255, 255, 0.04);
    border-radius: 3px;
    color: var(--text-muted);
    flex-shrink: 0;
  }

  .queue-item:hover .media-icon-indicator {
    color: var(--text-bright);
    background: rgba(255, 255, 255, 0.08);
  }

  .queue-item.active .media-icon-indicator {
    color: var(--accent-primary);
    background: rgba(31, 111, 235, 0.15);
  }

  .queue-item.cleanup.active .media-icon-indicator.warn {
    color: var(--accent-warning);
    background: rgba(240, 139, 44, 0.15);
  }

  .media-icon-indicator.warn {
    color: var(--accent-warning);
    background: rgba(240, 139, 44, 0.06);
  }

  .queue-name {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-main);
  }

  .queue-item.active .queue-name {
    color: var(--text-bright);
  }

  .queue-state {
    font-size: 10px;
    color: var(--text-muted);
    padding-left: 26px;
  }
</style>
