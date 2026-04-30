<script lang="ts">
  import type { VaultItem } from './types';
  import { createEventDispatcher } from 'svelte';
  import { assetUrl } from './api';
  import { isImageMedia, isVideoMedia } from './media';
  
  export let group: { id: string, items: VaultItem[] };
  export let selectedHash: string | undefined = '';
  export let selectedHashes: Set<string> = new Set();
  export let layout: 'masonry' | 'grid' = 'masonry';
  export let activeIndex = 0;
  
  const dispatch = createEventDispatcher();

  $: index = Math.min(Math.max(activeIndex || 0, 0), Math.max(0, group.items.length - 1));
  $: current = group.items[index];
  $: thumbnailUrl = current ? assetUrl(current.thumbnail_url) : '';
  $: fullUrl = current ? assetUrl(current.url) : '';
  $: isSelected = current ? current.hash === selectedHash || selectedHashes.has(current.hash) : false;
  $: aspectStyle = (current?.width && current?.height)
    ? `aspect-ratio: ${current.width} / ${current.height}`
    : '';

  function next(e: MouseEvent) {
    e.stopPropagation();
    const nextIndex = (index + 1) % group.items.length;
    dispatch('indexChange', { groupId: group.id, index: nextIndex });
  }

  function prev(e: MouseEvent) {
    e.stopPropagation();
    const nextIndex = (index - 1 + group.items.length) % group.items.length;
    dispatch('indexChange', { groupId: group.id, index: nextIndex });
  }

  function select(event: MouseEvent) {
    if (current) dispatch('select', { item: current, event });
  }

  function playVideo(e: MouseEvent & { currentTarget: HTMLVideoElement }) {
    e.currentTarget.play().catch(() => {});
  }

  function pauseVideo(e: MouseEvent & { currentTarget: HTMLVideoElement }) {
    const v = e.currentTarget;
    v.pause();
    v.currentTime = 0;
  }
</script>

<div class="tile-group {layout}" class:selected={isSelected} on:click={select}>
    <div class="media-stack" style={layout !== 'grid' ? aspectStyle : ''}>
        {#if current && isImageMedia(current)}
            <img src={thumbnailUrl} alt="Vault Item" loading="lazy"
                 width={current.width || undefined} height={current.height || undefined} />
        {:else if current && isVideoMedia(current)}
            <video src={fullUrl} poster={thumbnailUrl} preload="none" muted loop
                   on:mouseenter={playVideo} on:mouseleave={pauseVideo}></video>
        {:else}
            <div class="unsupported-media">Unknown media</div>
        {/if}

        {#if group.items.length > 1}
            <div class="controls">
                <button class="nav-btn" on:click={prev}>&lt;</button>
                <div class="counter">{index + 1} / {group.items.length}</div>
                <button class="nav-btn" on:click={next}>&gt;</button>
            </div>
        {/if}
    </div>

    <div class="info">
        <span class="hash">{current ? current.hash.substring(0, 12) : ''}</span>
        <span class="artist">{current?.artist || 'Unknown'}</span>
    </div>
</div>

<style>
  .tile-group {
    background: var(--bg-panel);
    border: 2px solid transparent;
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 12px;
    break-inside: avoid;
    cursor: pointer;
    transition: border-color 0.1s, background 0.1s;
    display: flex;
    flex-direction: column;
    content-visibility: auto;
  }

  .tile-group.grid {
    margin-bottom: 0;
    height: 100%;
  }

  .tile-group:hover { border-color: var(--border-hover); }
  .tile-group.selected {
    border-color: #f0b429;
    background: rgba(240, 180, 41, 0.08);
    box-shadow: 0 0 0 2px rgba(240, 180, 41, 0.35);
  }

  .media-stack { position: relative; width: 100%; background: #000; min-height: 100px; display: flex; align-items: center; justify-content: center; }
  
  .tile-group.grid .media-stack {
    flex-grow: 1;
    aspect-ratio: 1 / 1;
  }

  img, video { width: 100%; display: block; height: auto; }
  
  .tile-group.grid img, .tile-group.grid video {
    height: 100%;
    width: 100%;
    object-fit: cover;
  }

  .controls {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    background: rgba(0,0,0,0.7);
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 2px;
    opacity: 0;
    transition: opacity 0.2s;
  }

  .tile-group:hover .controls { opacity: 1; }

  .nav-btn {
    background: #161b22;
    border: 1px solid #30363d;
    color: white;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: bold;
  }
  .nav-btn:hover { border-color: var(--accent-primary); }

  .counter { font-size: 10px; color: #8b949e; font-weight: bold; }
  .unsupported-media { min-height: 100px; display: flex; align-items: center; justify-content: center; color: var(--text-muted); font-size: 11px; }

  .info {
    padding: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
    flex-shrink: 0;
  }

  .hash { color: var(--text-muted); font-family: monospace; }
  .artist { color: var(--accent-purple); font-weight: bold; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 60%; text-align: right; }
</style>
