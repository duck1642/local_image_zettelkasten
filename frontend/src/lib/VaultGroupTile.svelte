<script lang="ts">
  import type { VaultItem } from './types';
  import { createEventDispatcher } from 'svelte';
  
  export let group: { id: string, items: VaultItem[] };
  export let selectedHash: string | undefined = '';
  
  const dispatch = createEventDispatcher();
  let index = 0;

  $: current = group.items[index];
  $: assetUrl = `http://localhost:8000${current.url}`;
  $: isSelected = group.items.some(i => i.hash === selectedHash);

  function next(e: MouseEvent) {
    e.stopPropagation();
    index = (index + 1) % group.items.length;
  }

  function prev(e: MouseEvent) {
    e.stopPropagation();
    index = (index - 1 + group.items.length) % group.items.length;
  }

  function select() {
    dispatch('select', current);
  }
</script>

<div class="tile-group" class:selected={isSelected} on:click={select}>
    <div class="media-stack">
        {#if current.mime_type.startsWith('image/')}
            <img src={assetUrl} alt="Vault Item" loading="lazy" />
        {:else}
            <video src={assetUrl} muted loop on:mouseenter={e => e.target.play()} on:mouseleave={e => {e.target.pause(); e.target.currentTime = 0}}></video>
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
        <span class="hash">{current.hash.substring(0, 12)}</span>
        <span class="artist">{current.artist || 'Unknown'}</span>
    </div>
</div>

<style>
  .tile-group {
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 12px;
    break-inside: avoid;
    cursor: pointer;
    border: 2px solid transparent;
    transition: all 0.1s;
  }

  .tile-group:hover { border-color: var(--border-hover); }
  .tile-group.selected { border-color: var(--accent-primary); background: rgba(31, 111, 235, 0.05); }

  .media-stack { position: relative; width: 100%; background: #000; min-height: 100px; }

  img, video { width: 100%; display: block; height: auto; }

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

  .info {
    padding: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
  }

  .hash { color: var(--text-muted); font-family: monospace; }
  .artist { color: var(--accent-purple); font-weight: bold; }
</style>
