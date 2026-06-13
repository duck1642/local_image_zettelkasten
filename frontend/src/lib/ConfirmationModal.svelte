<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { IconClose } from './icons';

  export let open = false;
  export let title = 'Confirm Action';
  export let message = '';
  export let confirmLabel = 'Confirm';
  export let cancelLabel = 'Cancel';
  export let danger = false;
  export let busy = false;

  const dispatch = createEventDispatcher<{
    confirm: void;
    cancel: void;
  }>();

  function handleCancel() {
    if (busy) return;
    dispatch('cancel');
  }

  function handleConfirm() {
    if (busy) return;
    dispatch('confirm');
  }
</script>

{#if open}
  <div class="modal-backdrop" role="presentation" on:click={handleCancel}>
    <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <div
      class="confirm-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
      tabindex="-1"
      on:click|stopPropagation
    >
      <div class="modal-header">
        <h4 id="confirm-title">{title}</h4>
        <button class="close-btn" type="button" on:click={handleCancel} disabled={busy} aria-label="Close">
          <IconClose size={12} />
        </button>
      </div>
      <div class="modal-body">
        {#if message}
          <p>{message}</p>
        {/if}
        <slot />
      </div>
      <div class="modal-footer">
        <button class="cancel-btn" type="button" on:click={handleCancel} disabled={busy}>{cancelLabel}</button>
        <button
          type="button"
          class:danger
          class:primary={!danger}
          on:click={handleConfirm}
          disabled={busy}
        >
          {confirmLabel}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(1, 4, 9, 0.72);
    padding: 24px;
  }

  .confirm-modal {
    width: min(440px, calc(100vw - 32px));
    display: flex;
    flex-direction: column;
    gap: 16px;
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    box-shadow: 0 18px 60px rgba(0, 0, 0, 0.45);
    padding: 18px;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .modal-header h4 {
    margin: 0;
    color: var(--text-bright);
    font-size: 14px;
    font-weight: 600;
  }

  .modal-body {
    font-size: 13px;
    color: var(--text-main);
    line-height: 1.5;
  }

  :global(.confirm-modal .warning-text) {
    color: var(--accent-danger);
    font-weight: 500;
    margin-top: 8px;
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
  }

  button {
    font-family: inherit;
    font-size: 12px;
    font-weight: 600;
    padding: 6px 12px;
    border-radius: 6px;
    cursor: pointer;
  }

  .close-btn {
    display: inline-grid;
    place-items: center;
    background: transparent;
    border: 0;
    width: 24px;
    height: 24px;
    padding: 0;
    color: var(--text-muted);
    border-radius: 4px;
    cursor: pointer;
  }

  .close-btn:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.06);
    color: var(--text-bright);
  }

  .cancel-btn {
    background: transparent;
    border: 1px solid var(--border-dim);
    color: var(--text-main);
  }

  .cancel-btn:hover:not(:disabled) {
    border-color: var(--border-hover);
    color: var(--text-bright);
  }

  button.danger {
    background: rgba(218, 54, 51, 0.15);
    border: 1px solid rgba(218, 54, 51, 0.45);
    color: #ff7b72;
  }

  button.danger:hover:not(:disabled) {
    background: var(--accent-danger);
    border-color: var(--accent-danger);
    color: #ffffff;
  }

  button.primary {
    background: var(--accent-primary);
    border: 1px solid var(--accent-primary);
    color: #ffffff;
  }

  button.primary:hover:not(:disabled) {
    background: #1f6feb;
    border-color: #388bfd;
  }

  button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
</style>
