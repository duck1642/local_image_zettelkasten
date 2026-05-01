<script lang="ts">
  import VaultGroupTile from '../../VaultGroupTile.svelte';
  import { onDestroy } from 'svelte';
  import type { VaultGroup, VaultItem } from '../../types';
  import { log as uiLog } from '../../logger';
  import {
    computeGridExpLayout,
    visibleGridExpPositions,
    visualOrderFromGridExpPositions,
    GRID_EXP_OVERSCAN
  } from './gridExpLayout';

  export let groups: VaultGroup[] = [];
  export let viewportWidth = 0;
  export let tileMinWidth = 190;
  export let selectedHash: string | undefined = '';
  export let selectedHashes: Set<string> = new Set();
  export let activeIndexes: Record<string, number> = {};
  export let sentinelEl: HTMLElement | null = null;
  export let hostEl: HTMLElement | null = null;
  export let isLoadingMore = false;
  export let onSelectItem: (item: VaultItem, group: VaultGroup, event?: MouseEvent) => void = () => {};
  export let onIndexChange: (groupId: string, index: number) => void = () => {};
  export let onVisualOrderChange: (hashes: string[]) => void = () => {};

  let scrollTop = 0;
  let viewportHeight = 0;
  let scrollFrame: number | null = null;
  let lastSummaryLog = 0;
  let lastSummaryKey = '';
  let lastVisualOrderKey = '';

  $: layout = computeGridExpLayout(groups, viewportWidth, tileMinWidth);
  $: visiblePositions = visibleGridExpPositions(
    layout.positions,
    scrollTop,
    viewportHeight,
    layout.rowHeight,
    layout.columnCount,
    GRID_EXP_OVERSCAN
  );
  $: emitVisualOrder();
  $: if (hostEl) {
    scrollTop = hostEl.scrollTop;
    viewportHeight = hostEl.clientHeight;
  }
  $: logSummary();

  function handleScroll(event: Event) {
    const target = event.currentTarget as HTMLElement;
    if (scrollFrame !== null) return;
    scrollFrame = window.requestAnimationFrame(() => {
      scrollTop = target.scrollTop;
      viewportHeight = target.clientHeight;
      scrollFrame = null;
    });
  }

  function emitVisualOrder() {
    const hashes = visualOrderFromGridExpPositions(layout.positions);
    const key = hashes.join('|');
    if (key === lastVisualOrderKey) return;
    lastVisualOrderKey = key;
    onVisualOrderChange(hashes);
  }

  function logSummary() {
    const now = Date.now();
    const key = [
      groups.length,
      visiblePositions.length,
      layout.columnCount,
      Math.round(layout.totalHeight),
      Math.floor(scrollTop / 500),
      Math.round(viewportHeight),
      Math.round(layout.columnWidth)
    ].join(':');
    if (key === lastSummaryKey || now - lastSummaryLog < 500) return;
    lastSummaryKey = key;
    lastSummaryLog = now;
    uiLog('INFO', 'Grid experiment layout summary', {
      total_groups: groups.length,
      mounted_tiles: visiblePositions.length,
      unmounted_tiles: Math.max(0, groups.length - visiblePositions.length),
      columns: layout.columnCount,
      scroll_top: Math.round(scrollTop),
      viewport_height: Math.round(viewportHeight),
      tile_width: Math.round(layout.columnWidth),
      row_height: Math.round(layout.rowHeight),
      total_height: Math.round(layout.totalHeight)
    });
  }

  onDestroy(() => {
    if (scrollFrame !== null) window.cancelAnimationFrame(scrollFrame);
  });
</script>

<div class="grid-exp-scroll" bind:this={hostEl} on:scroll={handleScroll}>
  <div class="grid-exp-surface" style={`height: ${layout.totalHeight}px;`}>
    {#each visiblePositions as position (position.group.id)}
      <div
        class="grid-exp-item"
        style={`width: ${position.width}px; height: ${position.height}px; transform: translate3d(${position.left}px, ${position.top}px, 0);`}
      >
        <VaultGroupTile
          group={position.group}
          layout="grid"
          eagerImages={true}
          activeIndex={activeIndexes[position.group.id] || 0}
          {selectedHash}
          {selectedHashes}
          on:select={(event) => onSelectItem(event.detail.item, position.group, event.detail.event)}
          on:indexChange={(event) => onIndexChange(event.detail.groupId, event.detail.index)}
        />
      </div>
    {/each}
  </div>
  <div bind:this={sentinelEl} class="scroll-sentinel"></div>
  {#if isLoadingMore}
    <div class="loading-more">Loading more...</div>
  {/if}
</div>

<style>
  .grid-exp-scroll {
    flex-grow: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 15px;
    position: relative;
    min-width: 0;
    box-sizing: border-box;
  }

  .grid-exp-surface {
    position: relative;
    min-height: 1px;
  }

  .grid-exp-item {
    position: absolute;
    top: 0;
    left: 0;
  }

  .grid-exp-item :global(.tile-group) {
    margin-bottom: 0;
    height: 100%;
    content-visibility: visible;
  }

  .scroll-sentinel {
    height: 1px;
  }

  .loading-more {
    text-align: center;
    padding: 15px;
    color: var(--text-muted);
    font-size: 12px;
  }
</style>
