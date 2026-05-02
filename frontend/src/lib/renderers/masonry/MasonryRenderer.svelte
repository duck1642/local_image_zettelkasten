<script lang="ts">
  import VirtualScroller from '../VirtualScroller.svelte';
  import VaultGroupTile from '../../VaultGroupTile.svelte';
  import { onDestroy } from 'svelte';
  import type { VaultGroup, VaultItem } from '../../types';
  import { log as uiLog } from '../../logger';
  import {
    MASONRY_DRIFT_THRESHOLD,
    MASONRY_OVERSCAN,
    computeMasonryLayout,
    visibleMasonryPositions,
    visualOrderFromMasonryPositions,
    type MasonryPosition
  } from './masonryLayout';
  import type { MeasurementStore } from './measurementStore';

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
  let pendingMeasurements: Record<string, { width: number; height: number; position: MasonryPosition }> = {};
  let measurementFrame: number | null = null;
  let recomputeCount = 0;
  let lastSummaryLog = 0;
  let lastSummaryKey = '';
  let lastVisualOrderKey = '';
  let measureObserver: ResizeObserver | null = null;
  const measuredNodes = new Map<HTMLElement, MasonryPosition>();
  const loggedDrifts = new Set<string>();

  $: layout = computeMasonryLayout(groups, viewportWidth, tileMinWidth, activeIndexes, measurements);
  $: visiblePositions = visibleMasonryPositions(layout.positions, scrollTop, viewportHeight, MASONRY_OVERSCAN);
  $: emitVisualOrder();
  $: logSummary();

  function emitVisualOrder() {
    const hashes = visualOrderFromMasonryPositions(layout.positions);
    const key = hashes.join('|');
    if (key === lastVisualOrderKey) return;
    lastVisualOrderKey = key;
    onVisualOrderChange(hashes);
  }

  function measureTile(node: HTMLElement, position: MasonryPosition) {
    if (!measureObserver) {
      measureObserver = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const target = entry.target as HTMLElement;
          const currentPosition = measuredNodes.get(target);
          if (currentPosition) queueMeasurement(target, currentPosition);
        }
      });
    }
    measuredNodes.set(node, position);
    measureObserver.observe(node);
    queueMeasurement(node, position);
    return {
      update(nextPosition: MasonryPosition) {
        measuredNodes.set(node, nextPosition);
        queueMeasurement(node, nextPosition);
      },
      destroy() {
        measureObserver?.unobserve(node);
        measuredNodes.delete(node);
      }
    };
  }

  function queueMeasurement(node: HTMLElement, position: MasonryPosition) {
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
    const next: MeasurementStore = { ...measurements };
    let changed = false;
    for (const [groupId, measurement] of Object.entries(pending)) {
      const diff = Math.abs(measurement.height - measurement.position.height);
      const key = `${groupId}:${Math.round(measurement.width)}:${Math.round(measurement.height)}`;
      if (!measurement.position.estimated && diff > MASONRY_DRIFT_THRESHOLD && !loggedDrifts.has(key)) {
        loggedDrifts.add(key);
        uiLog('WARNING', 'Masonry renderer height drift', {
          group_id: groupId,
          hash: measurement.position.group.items[0]?.hash,
          estimated_height: Math.round(measurement.position.height),
          measured_height: Math.round(measurement.height),
          difference: Math.round(diff),
          tile_width: Math.round(measurement.width)
        });
      }
      const updated = {
        width: measurement.width,
        height: measurement.height,
        ratio: measurement.height / measurement.width
      };
      const current = next[groupId];
      if (
        !current ||
        Math.abs(current.width - updated.width) >= 1 ||
        Math.abs(current.height - updated.height) >= 1 ||
        Math.abs(current.ratio - updated.ratio) >= 0.002
      ) {
        next[groupId] = updated;
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
    uiLog('INFO', 'Masonry renderer layout summary', {
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
    if (measurementFrame !== null) window.cancelAnimationFrame(measurementFrame);
    measureObserver?.disconnect();
    measuredNodes.clear();
  });
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
        class="measured-item"
        style={`width: ${position.width}px; transform: translate3d(${position.left}px, ${position.top}px, 0);`}
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
</VirtualScroller>

<style>
  .measured-item {
    position: absolute;
    top: 0;
    left: 0;
  }

  .measured-item :global(.tile-group) {
    margin-bottom: 0;
    content-visibility: visible;
  }
</style>