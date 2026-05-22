<script lang="ts">
  import type { FacetItem, FacetKind } from './types';

  export let activeKind: FacetKind;
  export let visibleItems: FacetItem[] = [];
  export let loading = false;
  export let error = '';
  export let isFacetSelected: (kind: FacetKind, value: string) => boolean;
  export let onToggleFacet: (kind: FacetKind, value: string) => void;
  export let onOpenMetadataAction: (kind: FacetKind, action: 'rename' | 'delete' | 'merge', value: string) => void;
</script>

<div class="stats-list">
  {#if loading}
    <div class="empty-state">Loading...</div>
  {:else if error}
    <div class="empty-state error">{error}</div>
  {:else if visibleItems.length === 0}
    <div class="empty-state">No values</div>
  {:else}
    {#if activeKind === 'platform'}
      {#each visibleItems as item}
        <div class="stats-row">
          <span class="value" title={item.value}>{item.value}</span>
          <span class="count">{item.count}</span>
        </div>
      {/each}
    {:else}
      <div class="chip-cloud">
        {#each visibleItems as item}
          <div class="stat-chip-wrap">
            <button
              type="button"
              class="stat-chip"
              class:has-action={activeKind === 'topic' || activeKind === 'wd_tag'}
              class:selected={isFacetSelected(activeKind, item.value)}
              aria-pressed={isFacetSelected(activeKind, item.value)}
              title={`${item.value} (${item.count})`}
              on:click={() => onToggleFacet(activeKind, item.value)}
            >
              <span class="value">{isFacetSelected(activeKind, item.value) ? `✓ ${item.value}` : item.value}</span>
              <span class="chip-count">{item.count}</span>
            </button>
            {#if activeKind === 'topic' || activeKind === 'wd_tag'}
              <span class="chip-actions">
                <button
                  type="button"
                  class="chip-action"
                  title={`Rename ${item.value}`}
                  aria-label={`Rename ${item.value}`}
                  on:click={() => onOpenMetadataAction(activeKind, 'rename', item.value)}
                >
                  R
                </button>
                {#if activeKind === 'topic'}
                  <button
                    type="button"
                    class="chip-action"
                    title={`Merge ${item.value}`}
                    aria-label={`Merge ${item.value}`}
                    on:click={() => onOpenMetadataAction(activeKind, 'merge', item.value)}
                  >
                    M
                  </button>
                {/if}
                <button
                  type="button"
                  class="chip-action"
                  title={`Delete ${item.value}`}
                  aria-label={`Delete ${item.value}`}
                  on:click={() => onOpenMetadataAction(activeKind, 'delete', item.value)}
                >
                  D
                </button>
              </span>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>
