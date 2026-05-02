<script lang="ts">
  import VirtualScroller from '../VirtualScroller.svelte';
  import VaultGroupTile from '../../VaultGroupTile.svelte';
  import { onDestroy } from 'svelte';
  import type { VaultGroup, VaultItem } from '../../types';
  import { log as uiLog } from '../../logger';
  import {
    computeGridLayout,
    visibleGridPositions,
    visualOrderFromGridPositions,
    GRID_OVERSCAN
  } from './gridLayout';

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
  let lastSummaryLog = 0;
  let lastSummaryKey = '';
  let lastVisualOrderKey = '';

  $: layout = computeGridLayout(groups, viewportWidth, tileMinWidth);
  $: visiblePositions = visibleGridPositions(
    layout.positions,
    scrollTop,
    viewportHeight,
    layout.rowHeight,
    layout.columnCount,
    GRID_OVERSCAN
  );
  $: emitVisualOrder();
  $: logSummary();

  function emitVisualOrder() {
    const hashes = visualOrderFromGridPositions(layout.positions);
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
    uiLog('INFO', 'Grid renderer layout summary', {
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

</script>

<VirtualScroller
  totalHeight={layout.totalHeight}
  bind:sentinelEl
  bind:hostEl
  {isLoadingMore}
  bind:scrollTop
  bind:viewportHeight
>
    {#each visiblePositions as position (position.group.id)}
      <div
        class="grid-renderer-item"
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
</VirtualScroller>

<style>
  .grid-renderer-item {
    position: absolute;
    top: 0;
    left: 0;
  }

  .grid-renderer-item :global(.tile-group) {
    margin-bottom: 0;
    height: 100%;
    content-visibility: visible;
  }
</style>