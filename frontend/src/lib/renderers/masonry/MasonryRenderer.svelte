<script lang="ts">
  import VirtualScroller from '../VirtualScroller.svelte';
  import VaultGroupTile from '../../VaultGroupTile.svelte';
  import { onDestroy } from 'svelte';
  import type { VaultGroup, VaultItem } from '../../types';
  import { log as uiLog } from '../../logger';
  import {
    MASONRY_DRIFT_THRESHOLD,
    MASONRY_OVERSCAN,
    createMasonryLayoutEngine,
    visibleMasonryPositions,
    visualOrderFromMasonryPositions,
    type MasonryPosition
  } from './masonryLayout';
  import type { MeasurementStore } from './measurementStore';

  const computeLayout = createMasonryLayoutEngine();

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

  $: layout = computeLayout(groups, viewportWidth, tileMinWidth, activeIndexes, measurements);
  $: visiblePositions = visibleMasonryPositions(layout.positions, scrollTop, viewportHeight, MASONRY_OVERSCAN);
  $: emitVisualOrder(layout.positions);
  $: if (import.meta.env.DEV) logSummary(groups, visiblePositions, layout, scrollTop, viewportHeight, recomputeCount, measurements);

  function emitVisualOrder(positions: typeof layout.positions) {
    const key = `${positions.length}:${positions[0]?.group.id ?? ''}:${positions[positions.length - 1]?.group.id ?? ''}:${layout.columnCount}`;
    if (key === lastVisualOrderKey) return;
    lastVisualOrderKey = key;
    onVisualOrderChange(visualOrderFromMasonryPositions(positions));
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

  function logSummary(
    groupsArg: VaultGroup[],
    visible: typeof visiblePositions,
    layoutArg: typeof layout,
    scroll: number,
    height: number,
    recomputes: number,
    store: MeasurementStore
  ) {
    const now = Date.now();
    const key = [
      groupsArg.length,
      visible.length,
      layoutArg.columnCount,
      Math.round(layoutArg.totalHeight),
      Math.floor(scroll / 500),
      Math.round(height),
      Math.round(layoutArg.columnWidth),
      recomputes
    ].join(':');
    if (key === lastSummaryKey || now - lastSummaryLog < 500) return;
    lastSummaryKey = key;
    lastSummaryLog = now;
    uiLog('DEBUG', 'Masonry renderer layout summary', {
      total_groups: groupsArg.length,
      mounted_tiles: visible.length,
      unmounted_tiles: Math.max(0, groupsArg.length - visible.length),
      columns: layoutArg.columnCount,
      scroll_top: Math.round(scroll),
      viewport_height: Math.round(height),
      tile_width: Math.round(layoutArg.columnWidth),
      total_height: Math.round(layoutArg.totalHeight),
      recompute_count: recomputes,
      measured_count: Object.keys(store).length
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
        data-testid="masonry-renderer-item"
        style={`width: ${position.width}px; transform: translate3d(${position.left}px, ${position.top}px, 0);`}
        use:measureTile={position}
      >
        <VaultGroupTile
          group={position.group}
          layout="masonry"
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
  .measured-item {
    position: absolute;
    top: 0;
    left: 0;
  }

  .measured-item :global(.tile-group) {
    margin-bottom: 0;
  }
</style>
