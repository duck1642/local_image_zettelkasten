<script lang="ts">
  import type { FacetItem, FacetKind } from './types';

  export let activeKind: FacetKind;
  export let visibleItems: FacetItem[] = [];
  export let loading = false;
  export let error = '';
  export let selectedTopics: string[] = [];
  export let selectedWdTags: string[] = [];
  export let onToggleFacet: (kind: FacetKind, value: string) => void;
  export let onOpenMetadataAction: (kind: FacetKind, action: 'rename' | 'delete' | 'merge', value: string) => void;

  $: isSelected = (value: string) => {
    if (activeKind === 'topic') return selectedTopics.includes(value);
    if (activeKind === 'wd_tag') return selectedWdTags.includes(value);
    return false;
  };
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
          <div class="stat-chip-wrap" class:selected={isSelected(item.value)}>
            <button
              type="button"
              class="stat-chip"
              class:has-action={activeKind === 'topic' || activeKind === 'wd_tag'}
              aria-pressed={isSelected(item.value)}
              title={`${item.value} (${item.count})`}
              on:click={() => onToggleFacet(activeKind, item.value)}
            >
              <span class="value">{item.value}</span>
              <span class="chip-count">{item.count}</span>
            </button>
            {#if activeKind === 'topic' || activeKind === 'wd_tag'}
              <span class="chip-actions">
                <button
                  type="button"
                  class="chip-action action-rename"
                  title={`Rename ${item.value}`}
                  aria-label={`Rename ${item.value}`}
                  on:click|stopPropagation={() => onOpenMetadataAction(activeKind, 'rename', item.value)}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                </button>
                {#if activeKind === 'topic'}
                  <button
                    type="button"
                    class="chip-action action-merge"
                    title={`Merge ${item.value}`}
                    aria-label={`Merge ${item.value}`}
                    on:click|stopPropagation={() => onOpenMetadataAction(activeKind, 'merge', item.value)}
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="18" r="3"></circle><circle cx="6" cy="6" r="3"></circle><path d="M6 9v9a3 3 0 0 0 3 3h3"></path><path d="M18 15V9a6 6 0 0 0-6-6H9"></path></svg>
                  </button>
                {/if}
                <button
                  type="button"
                  class="chip-action action-delete"
                  title={`Delete ${item.value}`}
                  aria-label={`Delete ${item.value}`}
                  on:click|stopPropagation={() => onOpenMetadataAction(activeKind, 'delete', item.value)}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                </button>
              </span>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>
