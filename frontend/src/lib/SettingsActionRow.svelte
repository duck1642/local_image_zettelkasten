<script lang="ts">
  import type { Snippet } from 'svelte';

  let {
    title = '',
    status = '',
    actionLabel = '',
    busyLabel = '',
    busy = false,
    disabled = false,
    primary = false,
    danger = false,
    actionTitle = '',
    onAction = () => {},
    actionIcon,
    details
  }: {
    title?: string;
    status?: string;
    actionLabel?: string;
    busyLabel?: string;
    busy?: boolean;
    disabled?: boolean;
    primary?: boolean;
    danger?: boolean;
    actionTitle?: string;
    onAction?: () => void;
    actionIcon?: Snippet;
    details?: Snippet;
  } = $props();

  const buttonText = $derived(busy && busyLabel ? busyLabel : actionLabel);
</script>

<div class="settings-action-row">
  <button
    class="settings-action-row-button"
    class:primary
    class:danger
    type="button"
    title={actionTitle || actionLabel}
    disabled={busy || disabled}
    onclick={onAction}
  >
    {#if actionIcon}{@render actionIcon()}{/if}
    {buttonText}
  </button>
  <div class="settings-action-row-copy">
    <span class="settings-action-row-title">{title}</span>
    <span class="settings-action-row-status">{status}</span>
    {#if details}{@render details()}{/if}
  </div>
</div>
