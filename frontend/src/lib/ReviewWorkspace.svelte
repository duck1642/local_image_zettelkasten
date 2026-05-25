<script lang="ts">
  import { IconInfoCircle } from './icons';

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

  export let current: ReviewItem;
  export let mediaMounted = true;
  export let isVideoMedia: (item: any) => boolean;
  export let mediaUrl: (item: any) => string;
  export let displayName: (item: any) => string;

  function extFromUrl(url: string) {
    const clean = (url || '').split('?')[0].split('#')[0];
    const dot = clean.lastIndexOf('.');
    if (dot < 0) return '';
    return clean.slice(dot).toLowerCase();
  }
</script>

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

  <!-- Cleanup info metadata card -->
  <div class="meta-card">
    <div class="meta-table">
      <div class="meta-table-header cleanup-header-bar">
        <div class="meta-col-label">Metadata Property</div>
        <div class="meta-col-val text-warn">Active Staged File</div>
        <div class="meta-col-val text-muted">Cleanup Reference Hash</div>
      </div>
      
      <div class="meta-table-row">
        <div class="meta-col-label">Original Filename</div>
        <div class="meta-col-val truncate" title={displayName(current)}>{displayName(current)}</div>
        <div class="meta-col-val truncate" title={current.metadata?.target_hash || current.metadata?.best_match || 'missing'}>
          {current.metadata?.target_hash || current.metadata?.best_match || 'missing'}
        </div>
      </div>

      <div class="meta-table-row">
        <div class="meta-col-label">Format / Extension</div>
        <div class="meta-col-val uppercase">{current.extension || extFromUrl(current.url) || 'unknown'}</div>
        <div class="meta-col-val text-muted">-</div>
      </div>
    </div>
  </div>
{:else}
  <!-- Header titles -->
  <div class="comparison-header">
    <div class="column-title">
      <span class="pill-badge primary">Incoming Item (Staged)</span>
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
          <IconInfoCircle size={32} strokeWidth={1.5} />
          <span class="no-match-title">No best-match duplicates detected in vault.</span>
          <p class="sub-muted">This file appears to be entirely unique.</p>
        </div>
      {/if}
    </div>
  </div>

  <!-- Comparative side-by-side metadata table -->
  <div class="meta-card">
    <div class="meta-table">
      <div class="meta-table-header">
        <div class="meta-col-label">Metadata Property</div>
        <div class="meta-col-val text-primary">Incoming File (Staged)</div>
        <div class="meta-col-val text-info">Vault Duplicate (Current)</div>
      </div>
      
      <div class="meta-table-row">
        <div class="meta-col-label">Filename / Hash</div>
        <div class="meta-col-val truncate" title={displayName(current)}>{displayName(current)}</div>
        <div class="meta-col-val truncate" title={current.best_match?.hash || 'none'}>
          {current.best_match ? `${current.best_match.hash.slice(0, 16)}...${current.best_match.extension || ''}` : 'No matching copy'}
        </div>
      </div>

      <div class="meta-table-row">
        <div class="meta-col-label">Type / Extension</div>
        <div class="meta-col-val uppercase">{current.extension || extFromUrl(current.url) || 'unknown'}</div>
        <div class="meta-col-val uppercase">{current.best_match?.extension || 'none'}</div>
      </div>

      {#if current.best_match}
        <div class="meta-table-row">
          <div class="meta-col-label">Artist Attribution</div>
          <div class="meta-col-val">{current.metadata?.artist || 'None detected'}</div>
          <div class="meta-col-val">{current.best_match.artist || 'Unassigned'}</div>
        </div>
      {/if}

      {#if current.metadata?.validation_warning}
        <div class="meta-table-row warn-row">
          <div class="meta-col-label">Validation Alert</div>
          <div class="meta-col-val text-warn span-two" title={current.metadata.validation_warning}>
            {current.metadata.validation_warning}
          </div>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
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
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 4px;
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
    background: #090c10;
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    min-width: 0;
    position: relative;
  }

  .pane:hover {
    border-color: rgba(255, 255, 255, 0.15);
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
    border-radius: 4px;
    font-family: monospace;
    font-size: 11px;
    color: var(--text-bright);
  }

  .error-text-box {
    background: rgba(240, 139, 44, 0.08);
    border: 1px solid rgba(240, 139, 44, 0.25);
    padding: 10px 14px;
    border-radius: 4px;
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
    border-radius: 2px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
  }

  .no-match {
    display: flex;
    flex-direction: column;
    align-items: center;
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

  .no-match-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-bright);
  }

  .sub-muted {
    font-size: 11px;
    color: var(--text-muted);
    margin: 0;
  }

  /* Comparative Metadata Table Layout */
  .meta-card {
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    padding: 0;
    margin-top: 16px;
    overflow: hidden;
  }

  .meta-table {
    display: flex;
    flex-direction: column;
    width: 100%;
    font-size: 11px;
  }

  .meta-table-header {
    display: grid;
    grid-template-columns: 180px 1fr 1fr;
    background: rgba(0, 0, 0, 0.25);
    border-bottom: 1px solid var(--border-dim);
    padding: 8px 16px;
    font-weight: 700;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .cleanup-header-bar {
    grid-template-columns: 180px 1.5fr 0.5fr;
  }

  .meta-table-row {
    display: grid;
    grid-template-columns: 180px 1fr 1fr;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    padding: 8px 16px;
    align-items: center;
  }

  .meta-table-row:last-child {
    border-bottom: none;
  }

  .meta-col-label {
    font-weight: 600;
    color: var(--text-muted);
  }

  .meta-col-val {
    color: var(--text-main);
    font-family: monospace;
  }

  .meta-col-val.truncate {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding-right: 12px;
  }

  .text-primary {
    color: var(--accent-purple) !important;
  }

  .text-info {
    color: var(--accent-primary) !important;
  }

  .text-warn {
    color: var(--accent-warning) !important;
  }

  .span-two {
    grid-column: span 2;
  }

  .warn-row {
    background: rgba(240, 139, 44, 0.05);
    border-top: 1px dashed rgba(240, 139, 44, 0.2);
  }

  .uppercase {
    text-transform: uppercase;
  }
</style>
