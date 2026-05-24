<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import InspectorTagChip from './InspectorTagChip.svelte';

  export let rating = '';
  export let characters: string[] = [];
  export let general: string[] = [];
  export let wdTagCounts: Record<string, number> | undefined = undefined;
  export let draftTopics: string[] = [];
  export let savedTopics: string[] = [];
  export let isAlreadyTopic: (value: string, saved: string[]) => boolean = () => false;
  export let isTagPromoted: (value: string, draft: string[], saved: string[]) => boolean = () => false;

  const dispatch = createEventDispatcher();

  function countFor(value: string) {
    const count = wdTagCounts?.[value];
    return typeof count === 'number' && count > 0 ? count : null;
  }
</script>

<div class="group-container">
  <!-- svelte-ignore a11y-label-has-associated-control -->
  <label class="section-label">WD Suggestions</label>

  <div class="tags-list suggestions-wrap">
    {#if rating}
      <InspectorTagChip
        label={rating}
        kind="rating"
        count={countFor(rating)}
        clickable={!isAlreadyTopic(rating, savedTopics)}
        promoted={isTagPromoted(rating, draftTopics, savedTopics)}
        interactive
        title={isAlreadyTopic(rating, savedTopics) ? "Already a topic" : "Promote to topic"}
        removeTitle="Remove WD tag"
        on:activate={() => dispatch('promote', rating)}
        on:remove={() => dispatch('remove', { kind: 'rating', value: rating })}
      />
    {/if}

    {#each (characters || []) as tag}
      <InspectorTagChip
        label={tag}
        kind="character"
        count={countFor(tag)}
        clickable={!isAlreadyTopic(tag, savedTopics)}
        promoted={isTagPromoted(tag, draftTopics, savedTopics)}
        interactive
        title={isAlreadyTopic(tag, savedTopics) ? "Already a topic" : "Promote to topic"}
        removeTitle="Remove WD tag"
        on:activate={() => dispatch('promote', tag)}
        on:remove={() => dispatch('remove', { kind: 'character', value: tag })}
      />
    {/each}

    {#each (general || []) as tag}
      <InspectorTagChip
        label={tag}
        kind="visual"
        count={countFor(tag)}
        clickable={!isAlreadyTopic(tag, savedTopics)}
        promoted={isTagPromoted(tag, draftTopics, savedTopics)}
        interactive
        title={isAlreadyTopic(tag, savedTopics) ? "Already a topic" : "Promote to topic"}
        removeTitle="Remove WD tag"
        on:activate={() => dispatch('promote', tag)}
        on:remove={() => dispatch('remove', { kind: 'general', value: tag })}
      />
    {/each}
  </div>

  {#if !rating && (!characters || characters.length === 0) && (!general || general.length === 0)}
    <div class="value-text">No suggestions</div>
  {/if}
</div>

<style>
  .group-container {
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-radius: 8px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .section-label { font-size: 11px; color: var(--text-muted); font-weight: 500; }

  .tags-list { display: flex; flex-wrap: wrap; gap: 6px; }

  .value-text {
    color: #6a737d;
    font-style: italic;
    font-weight: normal;
    font-size: 13px;
    padding: 2px 0;
  }
</style>
