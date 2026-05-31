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
  export let activateHandler: (() => void) | undefined = undefined;
  export let removeHandler: (() => void) | undefined = undefined;
  export let renameHandler: (() => void) | undefined = undefined;

  const dispatch = createEventDispatcher<{
    activate: void;
    remove: void;
    rename: void;
  }>();
  let pointerActivated = false;

  function activate() {
    if (!interactive) return;
    activateHandler?.();
    dispatch('activate');
  }

  function activatePointer(event: PointerEvent) {
    if (!interactive || event.button !== 0) return;
    if ((event.target as HTMLElement | null)?.closest('.chip-action')) return;
    pointerActivated = true;
    activate();
  }

  function activateClick() {
    if (pointerActivated) {
      pointerActivated = false;
      return;
    }
    activate();
  }

  function stopActionPointer(event: PointerEvent) {
    event.stopPropagation();
  }

  function emitAction(event: Event, action: 'remove' | 'rename') {
    event.preventDefault();
    event.stopPropagation();
    if (action === 'remove') removeHandler?.();
    if (action === 'rename') renameHandler?.();
    dispatch(action);
  }
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<span
  class="tag-chip {kind}"
  class:promoted
  class:clickable
  class:has-actions={removable || renameable}
  class:has-two-actions={removable && renameable}
  title={interactive ? undefined : title || undefined}
  onpointerdown={activatePointer}
  onclick={activateClick}
>
  {#if interactive}
    <button
      class="chip-main"
      type="button"
      title={title || undefined}
      onpointerdown={activatePointer}
      onclick={activateClick}
    >
      <span class="tag-label">{label}</span>
      {#if count}
        <span class="tag-count">{count}</span>
      {/if}
    </button>
  {:else}
    <span class="chip-main">
      <span class="tag-label">{label}</span>
      {#if count}
        <span class="tag-count">{count}</span>
      {/if}
    </span>
  {/if}
  {#if renameable}
    <button
      class="chip-action chip-rename"
      type="button"
      title={renameTitle}
      aria-label={renameTitle}
      onpointerdown={stopActionPointer}
      onclick={(event) => emitAction(event, 'rename')}
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
      onpointerdown={stopActionPointer}
      onclick={(event) => emitAction(event, 'remove')}
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

  .chip-main {
      display: inline-flex;
      align-items: center;
      height: 100%;
      min-width: 0;
      margin: 0;
      padding: 0;
      border: 0;
      border-radius: 0;
      background: transparent;
      color: inherit;
      font: inherit;
      cursor: inherit;
  }

  button.chip-main:focus-visible {
      outline: 1px solid var(--accent-primary);
      outline-offset: -2px;
  }

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
      height: 26px;
      align-self: stretch;
      margin: 0;
      padding: 0;
      border: none;
      background: transparent;
      color: var(--text-muted);
      cursor: pointer;
      opacity: 0;
      pointer-events: none;
      border-radius: 0;
      box-sizing: border-box;
  }

  .tag-chip:hover .chip-action,
  .tag-chip:focus-within .chip-action {
      width: 24px;
      opacity: 1;
      pointer-events: auto;
      border: none;
      border-left: 1px solid var(--chip-border);
      color: var(--text-muted);
  }

  .tag-chip:hover .chip-rename + .chip-remove,
  .tag-chip:focus-within .chip-rename + .chip-remove {
      margin-left: 0;
  }

  .chip-remove:hover {
      background: rgba(248, 81, 73, 0.15);
      color: var(--accent-danger);
      border: none;
      border-left: 1px solid rgba(255, 255, 255, 0.08);
  }

  .chip-rename:hover {
      background: rgba(255, 255, 255, 0.08);
      color: var(--accent-primary);
      border: none;
      border-left: 1px solid rgba(255, 255, 255, 0.08);
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
