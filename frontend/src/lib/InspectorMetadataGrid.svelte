<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { VaultItem } from './types';
  import { IconCopy, IconExternalLink } from './icons';

  export let item: VaultItem;
  export let artist = '';
  export let platform = '';
  export let sourceUrl = '';

  const dispatch = createEventDispatcher<{
    artistChange: string;
    copyHash: void;
  }>();

  function updateArtist(event: Event) {
    dispatch('artistChange', (event.currentTarget as HTMLInputElement).value);
  }
</script>

<div class="metadata-grid">
  <label class="grid-label" for="inspector-artist">Artist</label>
  <div class="grid-value editable-value">
    <input
      id="inspector-artist"
      type="text"
      value={artist}
      on:input={updateArtist}
      placeholder="Unknown Artist"
      class="inline-input"
    />
  </div>
  <div class="grid-action"></div>

  <span class="grid-label">Platform</span>
  <div class="grid-value platform-row">
    <span class="platform-text">{platform || 'Unknown'}</span>
  </div>
  <div class="grid-action"></div>

  <label class="grid-label" for="inspector-source-url">Source URL</label>
  <div class="grid-value source-row">
    <input
      id="inspector-source-url"
      type="text"
      value={sourceUrl}
      placeholder="No Source URL"
      readonly
      class="inline-input read-only-input"
    />
  </div>
  <div class="grid-action">
    {#if sourceUrl}
      <a href={sourceUrl} target="_blank" rel="noopener noreferrer" class="link-icon-btn" title="Open Source URL: {sourceUrl}">
        <IconExternalLink size={12} />
      </a>
    {/if}
  </div>

  <span class="grid-label">Hash</span>
  <div class="grid-value hash-row">
    <span class="hash-text" title={item.hash}>{item.hash}</span>
  </div>
  <div class="grid-action">
    <button class="icon-btn-compact" on:click={() => dispatch('copyHash')} title="Copy Hash">
      <IconCopy size={11} />
    </button>
  </div>
</div>

<style>
  .metadata-grid {
    display: grid;
    grid-template-columns: 84px minmax(0, 1fr) 22px;
    row-gap: 6px;
    column-gap: 10px;
    align-items: center;
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    padding: 10px 12px;
  }

  .grid-label {
    font-size: 10px;
    color: var(--text-muted);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0;
    user-select: none;
  }

  .grid-value {
    display: flex;
    align-items: center;
    height: 24px;
    min-width: 0;
  }

  .grid-action {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    min-width: 22px;
    height: 24px;
  }

  input.inline-input {
    width: 100%;
    height: 24px;
    padding: 0;
    margin: 0;
    background: transparent !important;
    border: 0 !important;
    border-bottom: 1px solid transparent !important;
    border-radius: 0;
    color: var(--text-main);
    font-size: 12px;
    font-weight: 500;
    line-height: 24px;
    transition: none !important;
    box-shadow: none !important;
  }

  input.inline-input:hover {
    background: transparent !important;
    border-bottom-color: rgba(255, 255, 255, 0.14) !important;
  }

  input.inline-input:focus {
    background: transparent !important;
    border-bottom-color: var(--accent-purple) !important;
    outline: none !important;
  }

  input.inline-input.read-only-input {
    cursor: default;
    color: var(--text-muted);
  }

  input.inline-input.read-only-input:hover,
  input.inline-input.read-only-input:focus {
    background: transparent !important;
    border-bottom-color: transparent !important;
  }

  .platform-row {
    display: flex;
    align-items: center;
  }

  .platform-text {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-main);
    line-height: 24px;
  }

  .source-row {
    display: flex;
    align-items: center;
    width: 100%;
    min-width: 0;
  }

  .link-icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--accent-primary);
    opacity: 0.8;
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
  }

  .link-icon-btn:hover {
    opacity: 1;
    background: rgba(31, 111, 235, 0.1);
    color: var(--text-bright);
  }

  .hash-row {
    display: flex;
    align-items: center;
    width: 100%;
    min-width: 0;
  }

  .hash-text {
    font-family: monospace;
    font-size: 11px;
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex-grow: 1;
    line-height: 24px;
  }

  .icon-btn-compact {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    padding: 0;
    background: transparent;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    border-radius: 3px;
    flex-shrink: 0;
  }

  .icon-btn-compact:hover {
    background: rgba(255, 255, 255, 0.08);
    color: var(--text-bright);
  }
</style>
