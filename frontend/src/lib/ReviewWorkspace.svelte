<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { IconChevronLeft, IconChevronRight, IconInfoCircle, IconMaximizeDiagonal } from './icons';
  import {
    extFromUrl,
    formatBytes,
    formatDuration,
    reviewComparisonData,
    type ReviewItem
  } from './reviewUtils';

  export let current: ReviewItem;
  export let mediaMounted = true;
  export let isVideoMedia: (item: any) => boolean;
  export let mediaUrl: (item: any) => string;
  export let displayName: (item: any) => string;
  export let activeMatchIndex = 0;

  const dispatch = createEventDispatcher();

  function prevMatch() {
    dispatch('changeMatch', { index: activeMatchIndex - 1 });
  }

  function nextMatch() {
    dispatch('changeMatch', { index: activeMatchIndex + 1 });
  }

  $: comparison = reviewComparisonData(current, activeMatchIndex);
  $: resolvedMatches = comparison.resolvedMatches;
  $: activeMatch = comparison.activeMatch;
  $: stagedWidth = comparison.stagedWidth;
  $: stagedHeight = comparison.stagedHeight;
  $: stagedSize = comparison.stagedSize;
  $: stagedCodec = comparison.stagedCodec;
  $: stagedDuration = comparison.stagedDuration;
  $: stagedFrames = comparison.stagedFrames;
  $: stagedWdTags = comparison.stagedWdTags;
  $: vaultWidth = comparison.vaultWidth;
  $: vaultHeight = comparison.vaultHeight;
  $: vaultSize = comparison.vaultSize;
  $: vaultCodec = comparison.vaultCodec;
  $: vaultDuration = comparison.vaultDuration;
  $: vaultFrames = comparison.vaultFrames;
  $: vaultWdTags = comparison.vaultWdTags;
  $: resClassStaged = comparison.resClassStaged;
  $: resClassVault = comparison.resClassVault;
  $: sizeClassStaged = comparison.sizeClassStaged;
  $: sizeClassVault = comparison.sizeClassVault;
  $: validationWarning = current.validation_warning || current.metadata?.validation_warning || '';
</script>

{#if current.section === 'cleanup'}
  <div class="workspace-grid">
    <!-- Left Column (Staged File) -->
    <div class="workspace-column">
      <div class="column-header">
        <span class="pill-badge warning">Review File (Active)</span>
      </div>
      
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

      <div class="meta-card">
        <div class="meta-card-title">Staged File Metadata</div>
        <div class="meta-row">
          <span class="meta-label">Original Filename:</span>
          <span class="meta-val truncate" title={displayName(current)}>{displayName(current)}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">Format / Ext:</span>
          <span class="meta-val uppercase">{current.extension || extFromUrl(current.url) || 'unknown'}</span>
        </div>
      </div>
    </div>

    <!-- Right Column (Error Details) -->
    <div class="workspace-column">
      <div class="column-header">
        <span class="pill-badge neutral">Cleanup Error Details</span>
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

      <div class="meta-card">
        <div class="meta-card-title">Cleanup Reference</div>
        <div class="meta-row">
          <span class="meta-label">Target Hash:</span>
          <span class="meta-val truncate" title={current.metadata?.target_hash || current.metadata?.best_match || 'missing'}>
            {current.metadata?.target_hash || current.metadata?.best_match || 'missing'}
          </span>
        </div>
      </div>
    </div>
  </div>
{:else}
  <div class="workspace-grid">
    <!-- Left Column (Incoming) -->
    <div class="workspace-column">
      <div class="column-header">
        <span class="pill-badge primary">Incoming Item (Staged)</span>
        <button class="fullscreen-toggle-btn" on:click={() => dispatch('toggleFullscreen')} title="Compare Symmetrically Fullscreen">
          <IconMaximizeDiagonal size={12} />
          <span>Compare Fullscreen</span>
        </button>
      </div>
      
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

      <div class="meta-card">
        <div class="meta-card-title">Staged File Metadata</div>
        <div class="meta-row">
          <span class="meta-label">Filename:</span>
          <span class="meta-val truncate" title={displayName(current)}>{displayName(current)}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">Format / Ext:</span>
          <span class="meta-val uppercase">{current.extension || extFromUrl(current.url) || 'unknown'}</span>
        </div>
        {#if stagedWidth > 0 && stagedHeight > 0}
          <div class="meta-row">
            <span class="meta-label">Dimensions:</span>
            <span class="meta-val {resClassStaged}">{stagedWidth} x {stagedHeight}</span>
          </div>
        {/if}
        {#if stagedSize > 0}
          <div class="meta-row">
            <span class="meta-label">File Size:</span>
            <span class="meta-val {sizeClassStaged}">{formatBytes(stagedSize)}</span>
          </div>
        {/if}
        {#if stagedFrames > 1}
          <div class="meta-row">
            <span class="meta-label">Frame Count:</span>
            <span class="meta-val">{stagedFrames} frames</span>
          </div>
        {/if}
        {#if isVideoMedia(current)}
          {#if stagedDuration > 0}
            <div class="meta-row">
              <span class="meta-label">Duration:</span>
              <span class="meta-val">{formatDuration(stagedDuration)}</span>
            </div>
          {/if}
          {#if stagedCodec}
            <div class="meta-row">
              <span class="meta-label">Video Codec:</span>
              <span class="meta-val uppercase">{stagedCodec}</span>
            </div>
          {/if}
          <div class="meta-row">
            <span class="meta-label">Audio Track:</span>
            <span class="meta-val">{current.metadata?.audio_present ? 'AAC Stereo' : 'Silent'}</span>
          </div>
        {/if}
        <div class="meta-row">
          <span class="meta-label">Artist:</span>
          <span class="meta-val">{current.metadata?.artist || 'None detected'}</span>
        </div>
        {#if validationWarning}
          <div class="meta-row alert-row">
            <span class="meta-label text-warn">Validation Alert:</span>
            <span class="meta-val text-warn truncate" title={validationWarning}>
              {validationWarning}
            </span>
          </div>
        {/if}
        {#if stagedWdTags && stagedWdTags.length > 0}
          <div class="wd-tags-container">
            <span class="wd-tags-label">WD Tags Suggested:</span>
            <div class="wd-chips">
              {#each stagedWdTags as tag}
                <span class="wd-chip">{tag}</span>
              {/each}
            </div>
          </div>
        {/if}
      </div>
    </div>

    <!-- Right Column (Vault Copy) -->
    <div class="workspace-column">
      <div class="column-header">
        <span class="pill-badge info">Best Similarity Match in Vault</span>
        {#if resolvedMatches.length > 1}
          <div class="match-nav">
            <button class="match-nav-btn" on:click={prevMatch} disabled={activeMatchIndex <= 0} title="Previous Similarity Match">
              <IconChevronLeft size={10} />
            </button>
            <span class="match-counter">Match {activeMatchIndex + 1} of {resolvedMatches.length}</span>
            <button class="match-nav-btn" on:click={nextMatch} disabled={activeMatchIndex >= resolvedMatches.length - 1} title="Next Similarity Match">
              <IconChevronRight size={10} />
            </button>
          </div>
        {/if}
      </div>

      <div class="pane">
        {#if mediaMounted && activeMatch}
          {#if isVideoMedia(activeMatch)}
            <!-- svelte-ignore a11y-media-has-caption -->
            <video src={mediaUrl(activeMatch)} controls preload="metadata"></video>
          {:else}
            <img src={mediaUrl(activeMatch)} alt="Match" />
          {/if}
        {:else if mediaMounted}
          <div class="no-match">
            <IconInfoCircle size={32} strokeWidth={1.5} />
            <span class="no-match-title">No best-match duplicates detected in vault.</span>
            <p class="sub-muted">This file appears to be entirely unique.</p>
          </div>
        {/if}
      </div>

      <div class="meta-card">
        <div class="meta-card-title">Vault Copy Metadata</div>
        {#if activeMatch}
          <div class="meta-row">
            <span class="meta-label">Hash ID:</span>
            <span class="meta-val truncate" title={activeMatch.hash}>{activeMatch.hash}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">Format / Ext:</span>
            <span class="meta-val uppercase">{activeMatch.extension || 'unknown'}</span>
          </div>
          {#if vaultWidth > 0 && vaultHeight > 0}
            <div class="meta-row">
              <span class="meta-label">Dimensions:</span>
              <span class="meta-val {resClassVault}">{vaultWidth} x {vaultHeight}</span>
            </div>
          {/if}
          {#if vaultSize > 0}
            <div class="meta-row">
              <span class="meta-label">File Size:</span>
              <span class="meta-val {sizeClassVault}">{formatBytes(vaultSize)}</span>
            </div>
          {/if}
          {#if vaultFrames > 1}
            <div class="meta-row">
              <span class="meta-label">Frame Count:</span>
              <span class="meta-val">{vaultFrames} frames</span>
            </div>
          {/if}
          {#if isVideoMedia(activeMatch)}
            {#if vaultDuration > 0}
              <div class="meta-row">
                <span class="meta-label">Duration:</span>
                <span class="meta-val">{formatDuration(vaultDuration)}</span>
              </div>
            {/if}
            {#if vaultCodec}
              <div class="meta-row">
                <span class="meta-label">Video Codec:</span>
                <span class="meta-val uppercase">{vaultCodec}</span>
              </div>
            {/if}
            <div class="meta-row">
              <span class="meta-label">Audio Track:</span>
              <span class="meta-val">{activeMatch.audio_present ? 'AAC Stereo' : 'Silent'}</span>
            </div>
          {/if}
          <div class="meta-row">
            <span class="meta-label">Artist:</span>
            <span class="meta-val">{activeMatch.artist || 'Unassigned'}</span>
          </div>
          {#if vaultWdTags && vaultWdTags.length > 0}
            <div class="wd-tags-container">
              <span class="wd-tags-label">WD Tags Index:</span>
              <div class="wd-chips">
                {#each vaultWdTags as tag}
                  <span class="wd-chip">{tag}</span>
                {/each}
              </div>
            </div>
          {/if}
        {:else}
          <div class="meta-row empty-meta">
            <span>No matching duplicate in vault.</span>
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .workspace-grid {
    flex: 1;
    display: flex;
    gap: 16px;
    min-height: 0;
  }

  .workspace-column {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    gap: 12px;
  }

  .column-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    height: 24px;
  }

  .match-nav {
    display: flex;
    align-items: center;
    gap: 8px;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.06);
    padding: 2px 8px;
    border-radius: 4px;
  }

  .match-nav-btn {
    width: 18px;
    height: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 0;
  }

  .match-nav-btn:hover:not(:disabled) {
    color: var(--text-bright);
  }

  .match-nav-btn:disabled {
    cursor: not-allowed;
    opacity: 0.3;
  }

  .match-counter {
    font-size: 10px;
    font-weight: 600;
    color: var(--text-muted);
  }

  .fullscreen-toggle-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    color: var(--text-muted);
    font-size: 10px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 4px;
    cursor: pointer;
  }

  .fullscreen-toggle-btn:hover {
    color: var(--text-bright);
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.15);
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

  /* Compact Metadata Cards */
  .meta-card {
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .meta-card-title {
    font-size: 10px;
    font-weight: 700;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    padding-bottom: 6px;
    margin-bottom: 2px;
  }

  .meta-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
    gap: 12px;
  }

  .meta-label {
    font-weight: 600;
    color: var(--text-muted);
    flex-shrink: 0;
  }

  .meta-val {
    color: var(--text-main);
    font-family: monospace;
    text-align: right;
  }

  .meta-val.truncate {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 240px;
  }

  .empty-meta {
    justify-content: center;
    color: var(--text-muted);
    font-style: italic;
    padding: 12px 0;
  }

  .alert-row {
    background: rgba(240, 139, 44, 0.05);
    border: 1px dashed rgba(240, 139, 44, 0.2);
    border-radius: 4px;
    padding: 4px 8px;
    margin-top: 2px;
  }

  .meta-val.better {
    color: var(--accent-success);
    background: rgba(46, 160, 67, 0.15);
    padding: 2px 6px;
    border-radius: 4px;
  }

  .meta-val.worse {
    color: var(--accent-danger);
    background: rgba(248, 81, 73, 0.15);
    padding: 2px 6px;
    border-radius: 4px;
  }

  .wd-tags-container {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: 8px;
    border-top: 1px dashed rgba(255, 255, 255, 0.04);
    padding-top: 8px;
  }

  .wd-tags-label {
    font-size: 9px;
    font-weight: 700;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    text-align: left;
  }

  .wd-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .wd-chip {
    font-size: 10px;
    padding: 2px 6px;
    background: rgba(255, 255, 255, 0.03);
    color: var(--text-main);
    border-radius: 4px;
    font-family: monospace;
  }

  .uppercase {
    text-transform: uppercase;
  }
</style>
