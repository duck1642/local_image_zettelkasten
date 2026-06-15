<script lang="ts">
  import type { Snippet } from 'svelte';

  let {
    title = '',
    description = '',
    icon,
    children
  }: {
    title?: string;
    description?: string;
    icon?: Snippet;
    children?: Snippet;
  } = $props();
</script>

<section class="settings-section">
  <div class="settings-section-header">
    <div class="settings-section-title-row">
      <span class="settings-section-icon">
        {#if icon}{@render icon()}{/if}
      </span>
      <h4 class="settings-section-heading">{title}</h4>
    </div>
    {#if description}
      <p class="settings-section-description">{description}</p>
    {/if}
  </div>
  {#if children}{@render children()}{/if}
</section>
