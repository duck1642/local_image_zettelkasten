<script lang="ts">
  import VirtualScroller from '../VirtualScroller.svelte';
  import VaultGroupTile from '../../VaultGroupTile.svelte';
  import type { VaultGroup, VaultItem } from '../../types';
  import { log as uiLog } from '../../logger';
  import {
    computeGridLayout,
    visibleGridPositions,
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

  let scrollTop = 0;
  let viewportHeight = 0;
  let lastSummaryLog = 0;
  let lastSummaryKey = '';

  $: layout = computeGridLayout(groups, viewportWidth, tileMinWidth);
  $: visiblePositions = visibleGridPositions(
    layout.positions,
    scrollTop,
    viewportHeight,
    layout.rowHeight,
    layout.columnCount,
    GRID_OVERSCAN
  );
  $: if (import.meta.env.DEV) logSummary(groups, visiblePositions, layout, scrollTop, viewportHeight);

  function logSummary(
    groupsArg: VaultGroup[],
    visible: typeof visiblePositions,
    layoutArg: typeof layout,
    scroll: number,
    height: number
  ) {
    const now = Date.now();
    const key = [
      groupsArg.length,
      visible.length,
      layoutArg.columnCount,
      Math.round(layoutArg.totalHeight),
      Math.floor(scroll / 500),
      Math.round(height),
      Math.round(layoutArg.columnWidth)
    ].join(':');
    if (key === lastSummaryKey || now - lastSummaryLog < 500) return;
    lastSummaryKey = key;
    lastSummaryLog = now;
    uiLog('DEBUG', 'Grid renderer layout summary', {
      total_groups: groupsArg.length,
      mounted_tiles: visible.length,
      unmounted_tiles: Math.max(0, groupsArg.length - visible.length),
      columns: layoutArg.columnCount,
      scroll_top: Math.round(scroll),
      viewport_height: Math.round(height),
      tile_width: Math.round(layoutArg.columnWidth),
      row_height: Math.round(layoutArg.rowHeight),
      total_height: Math.round(layoutArg.totalHeight)
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
        data-testid="grid-renderer-item"
        style={`width: ${position.width}px; height: ${position.height}px; transform: translate3d(${position.left}px, ${position.top}px, 0);`}
      >
        <VaultGroupTile
          group={position.group}
          layout="grid"
          eagerImages={false}
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
  }
</style>
