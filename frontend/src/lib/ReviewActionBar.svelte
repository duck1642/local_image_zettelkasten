<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { IconCopy, IconEye, IconRefresh, IconReplace, IconTrash } from './icons';

  export let section: 'pending' | 'cleanup' = 'pending';
  export let acting = false;

  const dispatch = createEventDispatcher();

  function handleAction(action: 'keep' | 'delete' | 'variant' | 'replace') {
    dispatch('action', { action });
  }

  function handleRetryCleanup() {
    dispatch('retryCleanup');
  }
</script>

<div class="action-bar">
  {#if section === 'cleanup'}
    <button class="action-big retry-btn" on:click={handleRetryCleanup} disabled={acting}>
      <IconRefresh size={14} />
      <span>Retry Cleanup & Delete Staged File</span>
    </button>
  {:else}
    <!-- Keep: Leaves file in review staging -->
    <button class="action-big keep-btn" on:click={() => handleAction('keep')} disabled={acting}>
      <IconEye size={14} />
      <span>Keep Staged</span>
    </button>
    <!-- Save Variant: Ingests new variant cleanly without replacing matching vault item -->
    <button class="action-big variant-btn" on:click={() => handleAction('variant')} disabled={acting}>
      <IconCopy size={14} />
      <span>Save as Variant</span>
    </button>
    <!-- Replace: Replaces the duplicate matching file in Vault, preserving manual YAML tags -->
    <button class="action-big replace-btn" on:click={() => handleAction('replace')} disabled={acting}>
      <IconReplace size={14} />
      <span>Replace Vault Copy</span>
    </button>
    <!-- Delete: Deletes the staged file from Review immediately -->
    <button class="action-big delete-btn" on:click={() => handleAction('delete')} disabled={acting}>
      <IconTrash size={14} />
      <span>Delete Staged</span>
    </button>
  {/if}
</div>

<style>
  .action-bar {
    display: flex;
    gap: 12px;
    padding: 9px 16px;
    background: rgba(0, 0, 0, 0.2);
    border-top: 1px solid var(--border-dim);
    box-sizing: border-box;
    height: 48px;
    align-items: center;
    width: 100%;
  }

  .action-big {
    flex: 1;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    font-weight: 700;
    font-size: 11px;
    border-radius: 4px;
    cursor: pointer;
  }

  .action-big:hover:not(:disabled) {
    border-color: rgba(255, 255, 255, 0.2);
  }

  .action-big:disabled {
    cursor: not-allowed;
    opacity: 0.4;
  }

  .keep-btn {
    background: rgba(139, 148, 158, 0.1);
    color: var(--text-bright);
    border: 1px solid var(--border-dim);
  }
  .keep-btn:hover:not(:disabled) {
    background: rgba(139, 148, 158, 0.18);
  }

  .variant-btn {
    background: rgba(35, 134, 54, 0.12);
    color: #3fb950;
    border: 1px solid rgba(56, 139, 60, 0.3);
  }
  .variant-btn:hover:not(:disabled) {
    background: var(--accent-success);
    color: white;
    border-color: var(--accent-success);
  }

  .replace-btn {
    background: rgba(210, 153, 34, 0.12);
    color: var(--accent-warning);
    border: 1px solid rgba(210, 153, 34, 0.3);
  }
  .replace-btn:hover:not(:disabled) {
    background: var(--accent-warning);
    color: #0d1117;
    border-color: var(--accent-warning);
  }

  .retry-btn {
    background: rgba(210, 153, 34, 0.12);
    color: var(--accent-warning);
    border: 1px solid rgba(210, 153, 34, 0.3);
    width: 100%;
  }
  .retry-btn:hover:not(:disabled) {
    background: var(--accent-warning);
    color: #0d1117;
    border-color: var(--accent-warning);
  }

  .delete-btn {
    background: rgba(248, 81, 73, 0.12);
    color: #f85149;
    border: 1px solid rgba(248, 81, 73, 0.3);
  }
  .delete-btn:hover:not(:disabled) {
    background: var(--accent-danger);
    color: white;
    border-color: var(--accent-danger);
  }
</style>
