<script lang="ts">
  import type { FacetItem, FacetKind } from './types';
  import { IconMerge, IconPencil, IconTrash } from '../icons';

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
                  <IconPencil size={12} />
                </button>
                {#if activeKind === 'topic'}
                  <button
                    type="button"
                    class="chip-action action-merge"
                    title={`Merge ${item.value}`}
                    aria-label={`Merge ${item.value}`}
                    on:click|stopPropagation={() => onOpenMetadataAction(activeKind, 'merge', item.value)}
                  >
                    <IconMerge size={12} />
                  </button>
                {/if}
                <button
                  type="button"
                  class="chip-action action-delete"
                  title={`Delete ${item.value}`}
                  aria-label={`Delete ${item.value}`}
                  on:click|stopPropagation={() => onOpenMetadataAction(activeKind, 'delete', item.value)}
                >
                  <IconTrash size={12} />
                </button>
              </span>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>
