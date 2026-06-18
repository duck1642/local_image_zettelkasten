<script lang="ts">
  import { onMount } from 'svelte';
  import { notificationHistory, type ToastType } from './toastStore';
  import {
    IconAlertTriangle,
    IconBell,
    IconCheckCircle,
    IconInfoCircle,
    IconTrash
  } from './icons';

  let open = false;
  let root: HTMLDivElement;

  $: unreadCount = $notificationHistory.filter(entry => !entry.read).length;

  function formatTime(timestamp: number) {
    return new Intl.DateTimeFormat(undefined, {
      hour: '2-digit',
      minute: '2-digit'
    }).format(timestamp);
  }

  function iconFor(type: ToastType) {
    return type;
  }

  onMount(() => {
    const closeOutside = (event: PointerEvent) => {
      if (open && !root.contains(event.target as Node)) open = false;
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') open = false;
    };
    document.addEventListener('pointerdown', closeOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  });
</script>

<div class="notification-history" bind:this={root}>
  <button
    class="history-toggle"
    class:active={open}
    type="button"
    aria-label="Notifications"
    aria-expanded={open}
    title="Notifications"
    on:click={() => open = !open}
  >
    <IconBell size={13} strokeWidth={2} />
    {#if unreadCount > 0}
      <span class="unread-badge" aria-label={`${unreadCount} unread notifications`}>
        {unreadCount > 99 ? '99+' : unreadCount}
      </span>
    {/if}
  </button>

  {#if open}
    <section class="history-panel" aria-label="Notification history">
      <header>
        <strong>Notifications</strong>
        <div class="history-actions">
          <button
            type="button"
            aria-label="Mark all notifications as read"
            title="Mark all as read"
            disabled={unreadCount === 0}
            on:click={() => notificationHistory.markAllRead()}
          ><IconCheckCircle size={13} strokeWidth={2} /></button>
          <button
            type="button"
            aria-label="Clear notifications"
            title="Clear notifications"
            disabled={$notificationHistory.length === 0}
            on:click={() => notificationHistory.clear()}
          ><IconTrash size={13} strokeWidth={2} /></button>
        </div>
      </header>

      {#if $notificationHistory.length === 0}
        <div class="empty-history">No notifications</div>
      {:else}
        <div class="history-list">
          {#each $notificationHistory as entry (entry.id)}
            <article class:unread={!entry.read} class="history-entry {entry.type}">
              <span class="entry-icon">
                {#if iconFor(entry.type) === 'success'}
                  <IconCheckCircle size={13} strokeWidth={2} />
                {:else if iconFor(entry.type) === 'info'}
                  <IconInfoCircle size={13} strokeWidth={2} />
                {:else}
                  <IconAlertTriangle size={13} strokeWidth={2} />
                {/if}
              </span>
              <div class="entry-content">
                <div class="entry-heading">
                  <strong>{entry.title}</strong>
                  <time datetime={new Date(entry.createdAt).toISOString()}>{formatTime(entry.createdAt)}</time>
                </div>
                <p>{entry.message}</p>
              </div>
            </article>
          {/each}
        </div>
      {/if}
    </section>
  {/if}
</div>

<style>
  .notification-history { position: relative; display: inline-flex; }
  .history-toggle, .history-actions button { border: 0; background: transparent; color: var(--text-muted); display: inline-grid; place-items: center; cursor: pointer; }
  .history-toggle { position: relative; width: 25px; height: 24px; padding: 0; border-left: 1px solid var(--border-dim); border-radius: 0; }
  .history-toggle:hover, .history-toggle.active, .history-actions button:hover:not(:disabled) { color: var(--text-bright); background: rgba(255, 255, 255, 0.06); }
  .history-toggle:focus-visible, .history-actions button:focus-visible { outline: 1px solid var(--accent-primary); outline-offset: -2px; }
  .unread-badge { position: absolute; top: 1px; right: 0; min-width: 12px; height: 12px; padding: 0 3px; box-sizing: border-box; border-radius: 6px; background: var(--accent-primary); color: white; font-size: 8px; line-height: 12px; text-align: center; }
  .history-panel { position: absolute; right: 0; bottom: calc(100% + 6px); width: min(360px, calc(100vw - 24px)); max-height: 380px; display: flex; flex-direction: column; background: var(--bg-panel); border: 1px solid var(--border-dim); border-radius: 6px; box-shadow: 0 10px 28px rgba(0, 0, 0, 0.42); color: var(--text-main); overflow: hidden; z-index: 1000; }
  header { min-height: 36px; padding: 0 8px 0 12px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border-dim); }
  header strong { color: var(--text-bright); font-size: 12px; }
  .history-actions { display: flex; gap: 2px; }
  .history-actions button { width: 28px; height: 28px; padding: 0; border-radius: 4px; }
  .history-actions button:disabled { opacity: 0.35; cursor: default; }
  .history-list { overflow-y: auto; }
  .history-entry { display: flex; gap: 9px; padding: 10px 12px; border-bottom: 1px solid var(--border-dim); background: var(--bg-main); }
  .history-entry:last-child { border-bottom: 0; }
  .history-entry.unread { background: color-mix(in srgb, var(--accent-primary) 7%, var(--bg-main)); }
  .entry-icon { flex: 0 0 auto; margin-top: 1px; }
  .history-entry.success .entry-icon { color: var(--accent-success); }
  .history-entry.warning .entry-icon { color: var(--accent-warning); }
  .history-entry.error .entry-icon { color: var(--accent-danger); }
  .history-entry.info .entry-icon { color: var(--accent-primary); }
  .entry-content { min-width: 0; flex: 1; }
  .entry-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
  .entry-heading strong { color: var(--text-bright); font-size: 11.5px; line-height: 1.35; overflow-wrap: anywhere; }
  time { flex: 0 0 auto; color: var(--text-muted); font-size: 9.5px; }
  p { margin: 2px 0 0; color: var(--text-main); font-size: 10.5px; line-height: 1.4; overflow-wrap: anywhere; }
  .empty-history { padding: 26px 12px; color: var(--text-muted); text-align: center; font-size: 11px; }
</style>
