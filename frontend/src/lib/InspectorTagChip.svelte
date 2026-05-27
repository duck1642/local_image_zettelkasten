<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { IconPencil, IconTrash } from './icons';

  export let label = '';
  export let count: number | null = null;
  export let kind: 'topic' | 'rating' | 'character' | 'visual' = 'visual';
  export let promoted = false;
  export let clickable = false;
  export let interactive = false;
  export let title = '';
  export let removable = true;
  export let renameable = false;
  export let removeTitle = 'Remove tag';
  export let renameTitle = 'Rename tag';

  const dispatch = createEventDispatcher<{
    activate: void;
    remove: void;
    rename: void;
  }>();

  function activate() {
    if (!interactive) return;
    dispatch('activate');
  }

  function handleKeydown(event: KeyboardEvent) {
    if (!interactive) return;
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    dispatch('activate');
  }

  function emitAction(event: Event, action: 'remove' | 'rename') {
    event.preventDefault();
    event.stopPropagation();
    dispatch(action);
  }
</script>

<!-- svelte-ignore a11y-no-noninteractive-tabindex -->
<!-- svelte-ignore a11y-no-noninteractive-element-to-interactive-role -->
<span
  class="tag-chip {kind}"
  class:promoted
  class:clickable
  role={interactive ? 'button' : undefined}
  tabindex={interactive ? 0 : undefined}
  title={title || undefined}
  on:click={activate}
  on:keydown={handleKeydown}
>
  <span class="tag-label">{label}</span>
  {#if count}
    <span class="tag-count">{count}</span>
  {/if}
  {#if renameable}
    <button
      class="chip-action chip-rename"
      type="button"
      title={renameTitle}
      aria-label={renameTitle}
      on:click={(event) => emitAction(event, 'rename')}
    >
      <IconPencil size={10} />
    </button>
  {/if}
  {#if removable}
    <button
      class="chip-action chip-remove"
      type="button"
      title={removeTitle}
      aria-label={removeTitle}
      on:click={(event) => emitAction(event, 'remove')}
    >
      <IconTrash size={10} />
    </button>
  {/if}
</span>

<style>
  .tag-chip {
      --chip-color: var(--text-main);
      --chip-border: var(--border-dim);
      --chip-bg: rgba(255, 255, 255, 0.05);
      --chip-hover-border: rgba(255, 255, 255, 0.2);
      --chip-hover-bg: rgba(255, 255, 255, 0.08);
      --chip-promoted-bg: #8b949e;
      --chip-promoted-border: #c9d1d9;
      --chip-promoted-color: #0d1117;
      --chip-promoted-count-bg: #0d1117;
      --chip-promoted-count-color: #8b949e;
      --chip-promoted-action-color: rgba(13, 17, 23, 0.7);
      --chip-promoted-action-border: rgba(13, 17, 23, 0.2);
      --chip-promoted-action-hover-bg: rgba(13, 17, 23, 0.1);
      --chip-promoted-action-hover-color: #0d1117;
      display: inline-flex;
      align-items: center;
      height: 26px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 600;
      background: var(--chip-bg);
      color: var(--chip-color);
      border: 1px solid var(--chip-border);
      user-select: none;
      overflow: hidden;
  }

  .tag-chip.clickable { cursor: pointer; }

  .tag-label {
      display: flex;
      align-items: center;
      padding: 0 8px;
      height: 100%;
  }

  .tag-count {
      display: inline-grid;
      place-items: center;
      line-height: 1;
      color: var(--text-muted);
      background: rgba(255, 255, 255, 0.08);
      border-radius: 10px;
      font-size: 10px;
      font-weight: 600;
      min-width: 18px;
      height: 18px;
      padding: 0 6px;
      margin-left: -2px;
      margin-right: 6px;
  }

  .chip-action {
      display: inline-grid;
      place-items: center;
      width: 0;
      height: 26px !important;
      align-self: stretch !important;
      margin: 0 !important;
      padding: 0 !important;
      border: none !important;
      background: transparent;
      color: var(--text-muted);
      cursor: pointer;
      opacity: 0;
      border-radius: 0 !important;
      box-sizing: border-box !important;
      transition: width 0.12s ease, opacity 0.12s ease;
  }

  .tag-chip:hover .chip-action,
  .tag-chip:focus-within .chip-action {
      width: 24px;
      opacity: 1;
      border: none !important;
      border-left: 1px solid var(--chip-border) !important;
      color: var(--text-muted);
  }

  .tag-chip:hover .chip-rename + .chip-remove,
  .tag-chip:focus-within .chip-rename + .chip-remove {
      margin-left: 0 !important;
  }

  .tag-chip:hover .tag-count,
  .tag-chip:focus-within .tag-count {
      margin-right: 2px;
  }

  .chip-remove:hover {
      background: rgba(248, 81, 73, 0.15) !important;
      color: var(--accent-danger) !important;
      border: none !important;
      border-left: 1px solid rgba(255, 255, 255, 0.08) !important;
  }

  .chip-rename:hover {
      background: rgba(255, 255, 255, 0.08) !important;
      color: var(--accent-primary) !important;
      border: none !important;
      border-left: 1px solid rgba(255, 255, 255, 0.08) !important;
  }

  .tag-chip:hover {
      border-color: var(--chip-hover-border);
      background: var(--chip-hover-bg);
      color: var(--text-bright);
  }

  .tag-chip:hover .tag-count {
      color: var(--text-bright);
      background: rgba(255, 255, 255, 0.15);
  }

  .tag-chip.topic {
      --chip-color: var(--accent-purple);
      --chip-border: rgba(163, 113, 247, 0.4);
      --chip-bg: rgba(163, 113, 247, 0.07);
      --chip-hover-border: var(--accent-purple);
      --chip-hover-bg: rgba(163, 113, 247, 0.12);
      --chip-promoted-bg: var(--accent-purple);
      --chip-promoted-border: #c9a0ff;
      --chip-promoted-color: #ffffff;
      --chip-promoted-count-bg: #ffffff;
      --chip-promoted-count-color: var(--accent-purple);
      --chip-promoted-action-color: rgba(255, 255, 255, 0.7);
      --chip-promoted-action-border: rgba(255, 255, 255, 0.25);
      --chip-promoted-action-hover-bg: rgba(255, 255, 255, 0.15);
      --chip-promoted-action-hover-color: #ffffff;
  }

  .tag-chip.rating {
      --chip-color: var(--accent-warning);
      --chip-border: rgba(240, 139, 44, 0.35);
      --chip-bg: rgba(240, 139, 44, 0.07);
      --chip-hover-border: var(--accent-warning);
      --chip-hover-bg: rgba(240, 139, 44, 0.12);
      --chip-promoted-bg: var(--accent-warning);
      --chip-promoted-border: #ffb454;
      --chip-promoted-color: #ffffff;
      --chip-promoted-count-bg: #ffffff;
      --chip-promoted-count-color: var(--accent-warning);
      --chip-promoted-action-color: rgba(255, 255, 255, 0.7);
      --chip-promoted-action-border: rgba(255, 255, 255, 0.25);
      --chip-promoted-action-hover-bg: rgba(255, 255, 255, 0.15);
      --chip-promoted-action-hover-color: #ffffff;
  }

  .tag-chip.character {
      --chip-color: var(--accent-primary);
      --chip-border: rgba(31, 111, 235, 0.35);
      --chip-bg: rgba(31, 111, 235, 0.07);
      --chip-hover-border: var(--accent-primary);
      --chip-hover-bg: rgba(31, 111, 235, 0.12);
      --chip-promoted-bg: var(--accent-primary);
      --chip-promoted-border: #58a6ff;
      --chip-promoted-color: #ffffff;
      --chip-promoted-count-bg: #ffffff;
      --chip-promoted-count-color: var(--accent-primary);
      --chip-promoted-action-color: rgba(255, 255, 255, 0.7);
      --chip-promoted-action-border: rgba(255, 255, 255, 0.25);
      --chip-promoted-action-hover-bg: rgba(255, 255, 255, 0.15);
      --chip-promoted-action-hover-color: #ffffff;
  }

  .tag-chip.visual {
      --chip-color: var(--text-main);
      --chip-border: var(--border-dim);
      --chip-bg: rgba(255, 255, 255, 0.04);
      --chip-hover-border: rgba(255, 255, 255, 0.25);
      --chip-hover-bg: rgba(255, 255, 255, 0.08);
  }

  .tag-chip.promoted {
      background: var(--chip-promoted-bg) !important;
      border-color: var(--chip-promoted-border) !important;
      color: var(--chip-promoted-color) !important;
  }

  .tag-chip.promoted .tag-count {
      background: var(--chip-promoted-count-bg) !important;
      color: var(--chip-promoted-count-color) !important;
  }

  .tag-chip.promoted .chip-action {
      color: var(--chip-promoted-action-color) !important;
      border: none !important;
      border-left: 1px solid var(--chip-promoted-action-border) !important;
  }

  .tag-chip.promoted .chip-action:hover {
      background: var(--chip-promoted-action-hover-bg) !important;
      color: var(--chip-promoted-action-hover-color) !important;
      border: none !important;
      border-left: 1px solid var(--chip-promoted-action-border) !important;
  }
</style>
