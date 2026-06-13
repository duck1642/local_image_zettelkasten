<script lang="ts">
  import { toastStore } from './toastStore';
  import { IconCheckCircle, IconAlertTriangle, IconInfoCircle, IconClose } from './icons';

  function dismiss(id: string) {
    toastStore.dismiss(id);
  }
</script>

<div class="toaster-container">
  {#each $toastStore as toast (toast.id)}
    <div class="toast-card {toast.type}" role="alert">
      <div class="toast-icon">
        {#if toast.type === 'success'}
          <IconCheckCircle size={14} />
        {:else if toast.type === 'warning'}
          <IconAlertTriangle size={14} />
        {:else if toast.type === 'error'}
          <IconAlertTriangle size={14} />
        {:else}
          <IconInfoCircle size={14} />
        {/if}
      </div>
      <div class="toast-content">
        <div class="toast-title">{toast.title}</div>
        <div class="toast-message">{toast.message}</div>
      </div>
      <button class="toast-close" type="button" on:click={() => dismiss(toast.id)} aria-label="Dismiss">
        <IconClose size={10} />
      </button>
    </div>
  {/each}
</div>

<style>
  .toaster-container {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    gap: 8px;
    align-items: flex-end;
    pointer-events: none;
  }

  .toast-card {
    pointer-events: auto;
    width: 320px;
    background: rgba(22, 27, 34, 0.88);
    backdrop-filter: blur(8px);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
    padding: 12px 14px;
    display: flex;
    align-items: flex-start;
    gap: 10px;
    box-sizing: border-box;
  }

  .toast-icon {
    flex-shrink: 0;
    display: inline-flex;
    margin-top: 1px;
  }

  .toast-card.success .toast-icon {
    color: var(--accent-success);
  }
  .toast-card.warning .toast-icon {
    color: var(--accent-warning);
  }
  .toast-card.error .toast-icon {
    color: var(--accent-danger);
  }
  .toast-card.info .toast-icon {
    color: var(--accent-primary);
  }

  .toast-content {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .toast-title {
    color: var(--text-bright);
    font-size: 12.5px;
    font-weight: 600;
    line-height: 1.3;
  }

  .toast-message {
    color: var(--text-main);
    font-size: 11.5px;
    line-height: 1.4;
    overflow-wrap: break-word;
  }

  .toast-close {
    flex-shrink: 0;
    background: transparent;
    border: 0;
    padding: 0;
    width: 18px;
    height: 18px;
    display: inline-grid;
    place-items: center;
    color: var(--text-muted);
    border-radius: 4px;
    cursor: pointer;
  }

  .toast-close:hover {
    background: rgba(255, 255, 255, 0.06);
    color: var(--text-bright);
  }
</style>
