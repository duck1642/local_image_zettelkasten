<script lang="ts">
  import { onDestroy } from 'svelte';

  export let totalHeight = 0;
  export let sentinelEl: HTMLElement | null = null;
  export let hostEl: HTMLElement | null = null;
  export let isLoadingMore = false;

  export let scrollTop = 0;
  export let viewportHeight = 0;
  export let contentWidth = 0;

  let scrollFrame: number | null = null;
  let resizeObserver: ResizeObserver | null = null;
  let observedHost: HTMLElement | null = null;

  $: if (hostEl) {
    observeHost(hostEl);
  }

  function measureContentWidth(node: HTMLElement) {
    const style = window.getComputedStyle(node);
    const paddingLeft = parseFloat(style.paddingLeft || '0') || 0;
    const paddingRight = parseFloat(style.paddingRight || '0') || 0;
    return Math.max(0, node.clientWidth - paddingLeft - paddingRight);
  }

  function updateMetrics(node: HTMLElement) {
    scrollTop = node.scrollTop;
    viewportHeight = node.clientHeight;
    contentWidth = measureContentWidth(node);
  }

  function observeHost(node: HTMLElement) {
    if (observedHost === node) return;
    resizeObserver?.disconnect();
    observedHost = node;
    updateMetrics(node);
    resizeObserver = new ResizeObserver(() => updateMetrics(node));
    resizeObserver.observe(node);
  }

  function handleScroll(event: Event) {
    const target = event.currentTarget as HTMLElement;
    if (scrollFrame !== null) return;
    scrollFrame = window.requestAnimationFrame(() => {
      updateMetrics(target);
      scrollFrame = null;
    });
  }

  onDestroy(() => {
    if (scrollFrame !== null) window.cancelAnimationFrame(scrollFrame);
    resizeObserver?.disconnect();
  });
</script>

<div class="virtual-scroller" data-testid="virtual-scroller" bind:this={hostEl} on:scroll={handleScroll}>
  <div class="virtual-surface" data-testid="virtual-surface" style={`height: ${totalHeight}px;`}>
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
    padding: var(--vault-content-padding);
    scrollbar-gutter: stable;
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
