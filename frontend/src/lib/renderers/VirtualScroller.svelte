<script lang="ts">
  import { onDestroy } from 'svelte';

  export let totalHeight = 0;
  export let sentinelEl: HTMLElement | null = null;
  export let hostEl: HTMLElement | null = null;
  export let isLoadingMore = false;

  export let scrollTop = 0;
  export let viewportHeight = 0;

  let scrollFrame: number | null = null;

  $: if (hostEl) {
    scrollTop = hostEl.scrollTop;
    viewportHeight = hostEl.clientHeight;
  }

  function handleScroll(event: Event) {
    const target = event.currentTarget as HTMLElement;
    const nextScrollTop = target.scrollTop;
    const nextViewportHeight = target.clientHeight;
    if (scrollFrame !== null) return;
    scrollFrame = window.requestAnimationFrame(() => {
      scrollTop = nextScrollTop;
      viewportHeight = nextViewportHeight;
      scrollFrame = null;
    });
  }

  onDestroy(() => {
    if (scrollFrame !== null) window.cancelAnimationFrame(scrollFrame);
  });
</script>

<div class="virtual-scroller" bind:this={hostEl} on:scroll={handleScroll}>
  <div class="virtual-surface" style={`height: ${totalHeight}px;`}>
    <slot {scrollTop} {viewportHeight}></slot>
  </div>
  <div bind:this={sentinelEl} class="scroll-sentinel"></div>
  {#if isLoadingMore}
    <div class="loading-more">Loading more...</div>
  {/if}
</div>

<style>
  .virtual-scroller {
    flex-grow: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 15px;
    position: relative;
    min-width: 0;
    box-sizing: border-box;
  }

  .virtual-surface {
    position: relative;
    min-height: 1px;
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