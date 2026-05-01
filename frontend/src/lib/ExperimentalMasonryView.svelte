<script lang="ts">
  import type { VaultGroup, VaultItem } from './types';
  import VaultGroupTile from './VaultGroupTile.svelte';
  import { log as uiLog } from './logger';
  import {
    EXPERIMENTAL_MASONRY_DRIFT_THRESHOLD,
    EXPERIMENTAL_MASONRY_OVERSCAN,
    buildExperimentalMasonryColumns,
    rowIsVisible,
    type ExperimentalMasonryRow
  } from './experimentalMasonry';

  export let columns: VaultGroup[][] = [];
  export let columnWidth = 0;
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
  const loggedDrifts = new Set<string>();
  let lastSummaryLog = 0;
  let lastBucket = '';
  let lastVisibleCount = -1;
  let lastSpacerCount = -1;
  let lastColumnCount = -1;
  let lastGroupCount = -1;
  let lastColumnWidth = -1;

  $: experimentalColumns = buildExperimentalMasonryColumns(columns, columnWidth, activeIndexes);
  $: if (hostEl) {
    scrollTop = hostEl.scrollTop;
    viewportHeight = hostEl.clientHeight;
  }
  $: visibilityStats = summarizeVisibility();
  $: logVisibilitySummary(visibilityStats);

  function handleScroll(event: Event) {
    const target = event.currentTarget as HTMLElement;
    scrollTop = target.scrollTop;
    viewportHeight = target.clientHeight;
  }

  function measureRow(node: HTMLElement, row: ExperimentalMasonryRow) {
    let frame = window.requestAnimationFrame(() => {
      const actual = node.getBoundingClientRect().height;
      const diff = Math.abs(actual - row.estimatedHeight);
      const key = `${row.group.id}:${Math.round(columnWidth)}`;
      if (diff > EXPERIMENTAL_MASONRY_DRIFT_THRESHOLD && !loggedDrifts.has(key)) {
        loggedDrifts.add(key);
        uiLog('WARNING', 'Experimental masonry height drift', {
          group_id: row.group.id,
          hash: row.group.items[0]?.hash,
          column_width: Math.round(columnWidth),
          estimated_height: Math.round(row.estimatedHeight),
          actual_height: Math.round(actual),
          difference: Math.round(diff)
        });
      }
    });
    return {
      destroy() {
        window.cancelAnimationFrame(frame);
      }
    };
  }

  function summarizeVisibility() {
    let total = 0;
    let visible = 0;
    let spacer = 0;
    let estimatedTotalHeight = 0;
    const columnHeights: number[] = [];
    for (const column of experimentalColumns) {
      let columnHeight = 0;
      for (const row of column.rows) {
        total += 1;
        columnHeight = Math.max(columnHeight, row.bottom);
        if (rowIsVisible(row, scrollTop, viewportHeight, EXPERIMENTAL_MASONRY_OVERSCAN)) visible += 1;
        else spacer += 1;
      }
      columnHeights.push(Math.round(columnHeight));
      estimatedTotalHeight = Math.max(estimatedTotalHeight, columnHeight);
    }
    return {
      total,
      visible,
      spacer,
      columns: experimentalColumns.length,
      scrollTop: Math.round(scrollTop),
      viewportHeight: Math.round(viewportHeight),
      columnWidth: Math.round(columnWidth),
      estimatedTotalHeight: Math.round(estimatedTotalHeight),
      columnHeights
    };
  }

  function logVisibilitySummary(stats: ReturnType<typeof summarizeVisibility>) {
    const now = Date.now();
    const bucket = `${Math.floor(stats.scrollTop / 500)}:${stats.viewportHeight}`;
    const changed =
      bucket !== lastBucket ||
      stats.visible !== lastVisibleCount ||
      stats.spacer !== lastSpacerCount ||
      stats.columns !== lastColumnCount ||
      stats.total !== lastGroupCount ||
      stats.columnWidth !== lastColumnWidth;

    if (!changed || now - lastSummaryLog < 350) return;

    lastSummaryLog = now;
    lastBucket = bucket;
    lastVisibleCount = stats.visible;
    lastSpacerCount = stats.spacer;
    lastColumnCount = stats.columns;
    lastGroupCount = stats.total;
    lastColumnWidth = stats.columnWidth;

    uiLog('INFO', 'Experimental masonry visibility summary', {
      total_groups: stats.total,
      mounted_tiles: stats.visible,
      spacer_rows: stats.spacer,
      columns: stats.columns,
      scroll_top: stats.scrollTop,
      viewport_height: stats.viewportHeight,
      column_width: stats.columnWidth,
      overscan: EXPERIMENTAL_MASONRY_OVERSCAN,
      estimated_total_height: stats.estimatedTotalHeight,
      column_heights: stats.columnHeights
    });
  }
</script>

<div class="js-layout-scroll experimental-masonry-scroll" bind:this={hostEl} on:scroll={handleScroll}>
  <div class="vault-layout masonry experimental-masonry" style={`--tile-width: ${columnWidth}px;`}>
    {#each experimentalColumns as column}
      <div class="js-column">
        {#each column.rows as row (row.group.id)}
          {#if rowIsVisible(row, scrollTop, viewportHeight, EXPERIMENTAL_MASONRY_OVERSCAN)}
            <div use:measureRow={row}>
              <VaultGroupTile
                group={row.group}
                layout="masonry"
                activeIndex={activeIndexes[row.group.id] || 0}
                {selectedHash}
                {selectedHashes}
                on:select={(event) => onSelectItem(event.detail.item, row.group, event.detail.event)}
                on:indexChange={(event) => onIndexChange(event.detail.groupId, event.detail.index)}
              />
            </div>
          {:else}
            <div class="experimental-spacer" style={`height: ${row.estimatedHeight}px;`}></div>
          {/if}
        {/each}
      </div>
    {/each}
  </div>
  <div bind:this={sentinelEl} class="scroll-sentinel"></div>
  {#if isLoadingMore}
    <div class="loading-more">Loading more...</div>
  {/if}
</div>

<style>
  .js-layout-scroll { flex-grow: 1; overflow: auto; padding: 15px; }
  .vault-layout { display: flex; align-items: flex-start; gap: 12px; }
  .js-column { flex: 0 0 var(--tile-width); width: var(--tile-width); min-width: var(--tile-width); }
  .experimental-spacer { margin-bottom: 12px; }
  .scroll-sentinel { height: 1px; }
  .loading-more { text-align: center; padding: 15px; color: var(--text-muted); font-size: 12px; }
</style>
