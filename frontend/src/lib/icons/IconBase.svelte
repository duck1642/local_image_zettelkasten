<script lang="ts">
  export let size = 14;
  export let strokeWidth = 2.5;
  export let title = '';
  export let className = '';
</script>

<svg
  class={className || undefined}
  viewBox="0 0 24 24"
  width={size}
  height={size}
  stroke="currentColor"
  stroke-width={strokeWidth}
  fill="none"
  stroke-linecap="round"
  stroke-linejoin="round"
  focusable="false"
  aria-hidden={title ? undefined : 'true'}
>
  {#if title}
    <title>{title}</title>
  {/if}
  <slot />
</svg>
