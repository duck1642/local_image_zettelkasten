<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';

  export let itemCount: number = 0;
  export let itemPositions: { top: number; height: number }[] = [];
  export let containerHeight: number = 0;
  export let bufferCount: number = 5;

  const dispatch = createEventDispatcher();

  let scrollEl: HTMLElement;
  let scrollTop = 0;
  let viewportHeight = 600;

  function findStartIndex(top: number): number {
    let lo = 0, hi = itemPositions.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (itemPositions[mid].top + itemPositions[mid].height < top) lo = mid + 1;
      else hi = mid - 1;
    }
    return Math.max(0, lo);
  }

  function findEndIndex(bottom: number): number {
    let lo = 0, hi = itemPositions.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (itemPositions[mid].top > bottom) hi = mid - 1;
      else lo = mid + 1;
    }
    return Math.min(itemPositions.length - 1, hi);
  }

  $: visibleStart = itemPositions.length > 0 ? findStartIndex(scrollTop) : 0;
  $: visibleEnd = itemPositions.length > 0 ? findEndIndex(scrollTop + viewportHeight) : 0;
  $: renderStart = Math.max(0, visibleStart - bufferCount);
  $: renderEnd = Math.min(itemCount - 1, visibleEnd + bufferCount);

  function onScroll() {
    if (!scrollEl) return;
    scrollTop = scrollEl.scrollTop;
    if (scrollTop + viewportHeight > containerHeight - 600) {
      dispatch('loadMore');
    }
  }

  onMount(() => {
    if (scrollEl) {
      viewportHeight = scrollEl.clientHeight;
      const ro = new ResizeObserver(() => {
        if (scrollEl) viewportHeight = scrollEl.clientHeight;
      });
      ro.observe(scrollEl);
      return () => ro.disconnect();
    }
  });
</script>

<div class="virtual-scroller" bind:this={scrollEl} on:scroll={onScroll}>
  <div class="virtual-content" style="position: relative; height: {containerHeight}px;">
    {#each Array(renderEnd - renderStart + 1) as _, idx}
      {@const i = renderStart + idx}
      {@const pos = itemPositions[i]}
      {#if pos}
        <div class="virtual-item" style="position: absolute; top: {pos.top}px; left: 0; right: 0; height: {pos.height}px;">
          <slot {i} />
        </div>
      {/if}
    {/each}
  </div>
</div>

<style>
  .virtual-scroller {
    flex-grow: 1;
    overflow-y: auto;
    padding: 15px;
  }
  .virtual-content { width: 100%; }
  .virtual-item { box-sizing: border-box; }
</style>
