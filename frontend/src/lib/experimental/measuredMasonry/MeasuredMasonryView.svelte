<script lang="ts">
  import VaultGroupTile from '../../VaultGroupTile.svelte';
  import { onDestroy } from 'svelte';
  import type { VaultGroup, VaultItem } from '../../types';
  import { log as uiLog } from '../../logger';
  import {
    MEASURED_MASONRY_DRIFT_THRESHOLD,
    MEASURED_MASONRY_OVERSCAN,
    computeMeasuredMasonryLayout,
    visibleMeasuredPositions,
    visualOrderFromMeasuredPositions,
    type MeasuredMasonryPosition
  } from './measuredMasonryLayout';
  import { withMeasurement, type MeasurementStore } from './measurementStore';

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
  let measurements: MeasurementStore = {};
  let pendingMeasurements: Record<string, { width: number; height: number; position: MeasuredMasonryPosition }> = {};
  let measurementFrame: number | null = null;
  let scrollFrame: number | null = null;
  let recomputeCount = 0;
  let lastSummaryLog = 0;
  let lastSummaryKey = '';
  let lastVisualOrderKey = '';
  const loggedDrifts = new Set<string>();

  $: layout = computeMeasuredMasonryLayout(groups, viewportWidth, tileMinWidth, activeIndexes, measurements);
  $: visiblePositions = visibleMeasuredPositions(layout.positions, scrollTop, viewportHeight, MEASURED_MASONRY_OVERSCAN);
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
    const hashes = visualOrderFromMeasuredPositions(layout.positions);
    const key = hashes.join('|');
    if (key === lastVisualOrderKey) return;
    lastVisualOrderKey = key;
    onVisualOrderChange(hashes);
  }

  function measureTile(node: HTMLElement, position: MeasuredMasonryPosition) {
    let cancelled = false;
    const observer = new ResizeObserver(() => {
      if (cancelled) return;
      queueMeasurement(node, position);
    });
    observer.observe(node);
    queueMeasurement(node, position);
    return {
      update(nextPosition: MeasuredMasonryPosition) {
        position = nextPosition;
        queueMeasurement(node, position);
      },
      destroy() {
        cancelled = true;
        observer.disconnect();
      }
    };
  }

  function queueMeasurement(node: HTMLElement, position: MeasuredMasonryPosition) {
    const width = node.getBoundingClientRect().width;
    const height = node.getBoundingClientRect().height;
    if (width <= 0 || height <= 10) return;
    pendingMeasurements[position.group.id] = { width, height, position };
    if (measurementFrame !== null) return;
    measurementFrame = window.requestAnimationFrame(flushMeasurements);
  }

  function flushMeasurements() {
    measurementFrame = null;
    const pending = pendingMeasurements;
    pendingMeasurements = {};
    let next = measurements;
    let changed = false;
    for (const [groupId, measurement] of Object.entries(pending)) {
      const diff = Math.abs(measurement.height - measurement.position.height);
      const key = `${groupId}:${Math.round(measurement.width)}:${Math.round(measurement.height)}`;
      if (diff > MEASURED_MASONRY_DRIFT_THRESHOLD && !loggedDrifts.has(key)) {
        loggedDrifts.add(key);
        uiLog('WARNING', 'Measured masonry height drift', {
          group_id: groupId,
          hash: measurement.position.group.items[0]?.hash,
          estimated_height: Math.round(measurement.position.height),
          measured_height: Math.round(measurement.height),
          difference: Math.round(diff),
          tile_width: Math.round(measurement.width)
        });
      }
      const updated = withMeasurement(next, groupId, measurement.width, measurement.height);
      if (updated !== next) {
        next = updated;
        changed = true;
      }
    }
    if (changed) {
      measurements = next;
      recomputeCount += 1;
    }
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
      Math.round(layout.columnWidth),
      recomputeCount
    ].join(':');
    if (key === lastSummaryKey || now - lastSummaryLog < 500) return;
    lastSummaryKey = key;
    lastSummaryLog = now;
    uiLog('INFO', 'Measured masonry layout summary', {
      total_groups: groups.length,
      mounted_tiles: visiblePositions.length,
      unmounted_tiles: Math.max(0, groups.length - visiblePositions.length),
      columns: layout.columnCount,
      scroll_top: Math.round(scrollTop),
      viewport_height: Math.round(viewportHeight),
      tile_width: Math.round(layout.columnWidth),
      total_height: Math.round(layout.totalHeight),
      recompute_count: recomputeCount,
      measured_count: Object.keys(measurements).length
    });
  }

  onDestroy(() => {
    if (scrollFrame !== null) window.cancelAnimationFrame(scrollFrame);
    if (measurementFrame !== null) window.cancelAnimationFrame(measurementFrame);
  });
</script>

<div class="measured-scroll" bind:this={hostEl} on:scroll={handleScroll}>
  <div class="measured-surface" style={`height: ${layout.totalHeight}px;`}>
    {#each visiblePositions as position (position.group.id)}
      <div
        class="measured-item"
        style={`width: ${position.width}px; transform: translate(${position.left}px, ${position.top}px);`}
        use:measureTile={position}
      >
        <VaultGroupTile
          group={position.group}
          layout="masonry"
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
  .measured-scroll {
    flex-grow: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 15px;
    position: relative;
    min-width: 0;
    box-sizing: border-box;
  }

  .measured-surface {
    position: relative;
    min-height: 1px;
  }

  .measured-item {
    position: absolute;
    top: 0;
    left: 0;
    will-change: transform;
  }

  .measured-item :global(.tile-group) {
    margin-bottom: 0;
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
