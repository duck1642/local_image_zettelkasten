<script lang="ts">
  import type { VaultItem } from './types';
  import { onMount } from 'svelte';

  export let items: { id: string; items: VaultItem[] }[] = [];
  export let columnCount: number = 5;
  export let columnGap: number = 10;

  let containerEl: HTMLElement;
  let containerWidth: number = 0;

  interface Position { top: number; left: number; width: number; height: number; }

  $: colWidth = columnCount > 0
    ? (containerWidth - columnGap * (columnCount - 1)) / columnCount
    : 0;

  $: layout = computeLayout(items, colWidth, columnCount, columnGap);

  $: containerHeight = layout.length > 0
    ? Math.max(...layout.map(p => p.top + p.height))
    : 0;

  function computeLayout(
    items: { id: string; items: VaultItem[] }[],
    colWidth: number,
    colCount: number,
    gap: number
  ): Position[] {
    if (colCount <= 0 || colWidth <= 0) return [];
    const colHeights = new Array(colCount).fill(0);
    return items.map(group => {
      const first = group.items[0];
      const aspectRatio = (first?.width && first?.height) ? first.width / first.height : 1;
      const tileHeight = colWidth / aspectRatio + 36;
      const shortest = colHeights.indexOf(Math.min(...colHeights));
      const pos: Position = {
        top: colHeights[shortest],
        left: shortest * (colWidth + gap),
        width: colWidth,
        height: tileHeight
      };
      colHeights[shortest] += tileHeight + gap;
      return pos;
    });
  }

  function measureWidth() {
    if (containerEl) containerWidth = containerEl.clientWidth;
  }

  onMount(() => {
    measureWidth();
    const ro = new ResizeObserver(measureWidth);
    ro.observe(containerEl);
    return () => ro.disconnect();
  });
</script>

<div class="masonry-container" bind:this={containerEl} style="position: relative; height: {containerHeight}px;">
  {#each items as group, i (group.id)}
    <div class="masonry-item" style="position: absolute; top: {layout[i]?.top || 0}px; left: {layout[i]?.left || 0}px; width: {layout[i]?.width || 0}px;">
      <slot {group} {i} />
    </div>
  {/each}
</div>

<style>
  .masonry-container { width: 100%; }
  .masonry-item { box-sizing: border-box; }
</style>
