<script lang="ts">
  import { createEventDispatcher, tick } from 'svelte';
  import InspectorTagChip from './InspectorTagChip.svelte';
  import { IconPlus } from './icons';

  export let draftTopics: string[] = [];
  export let savedTopics: string[] = [];
  export let topicCounts: Record<string, number> | undefined = undefined;
  export let inputOpen = false;
  export let inputValue = '';
  export let suggestions: { value: string; count?: number }[] = [];
  export let suggestionsOpen = false;
  export let suggestionsLoading = false;
  export let activeSuggestionIndex = -1;
  export let normalizeLabel: (value: string) => string = (value) => value;

  const dispatch = createEventDispatcher();

  let topicInputElement: HTMLInputElement | undefined;
  let wasInputOpen = false;
  let topicRows: { tag: string; count: number | null; unsaved: boolean }[] = [];

  $: if (inputOpen && !wasInputOpen) {
    wasInputOpen = true;
    void focusInput();
  } else if (!inputOpen) {
    wasInputOpen = false;
  }

  $: {
    const savedKeys = new Set((savedTopics || []).map((topic) => topic.toLocaleLowerCase()));
    topicRows = (draftTopics || []).map((tag) => ({
      tag,
      count: countFor(tag),
      unsaved: !savedKeys.has(tag.toLocaleLowerCase())
    }));
  }

  async function focusInput() {
    await tick();
    topicInputElement?.focus();
  }

  function countFor(value: string) {
    const count = topicCounts?.[value];
    return typeof count === 'number' && count > 0 ? count : null;
  }

  function handleInput(event: Event) {
    const target = event.target as HTMLInputElement;
    dispatch('inputChange', target.value);
    dispatch('queueSuggestions');
  }
</script>

<div class="group-container">
  <!-- svelte-ignore a11y-label-has-associated-control -->
  <div class="section-heading">
    <label class="section-label">My Topics</label>
    <button class="add-topic-btn" type="button" title="Add topic" aria-label="Add topic" on:click={() => dispatch('openInput')}>
      <IconPlus size={14} />
    </button>
  </div>
  {#if inputOpen}
    <div class="topic-input-wrap">
      <div class="topic-input-row">
        <input
          bind:this={topicInputElement}
          type="text"
          class="topic-input"
          value={inputValue}
          placeholder="Topic"
          on:input={handleInput}
          on:focus={() => dispatch('fetchSuggestions')}
          on:keydown={(event) => dispatch('inputKeydown', event)}
          on:blur={() => dispatch('inputBlur')}
        />
        <button class="topic-confirm-btn" type="button" title="Add topic" aria-label="Add topic" on:mousedown|preventDefault on:click={() => dispatch('add')}>
          <IconPlus size={14} />
        </button>
      </div>
      {#if suggestionsOpen}
        <div class="topic-suggestions sleek-scrollbar" role="listbox">
          {#each suggestions as suggestion, index}
            <button
              type="button"
              class:active={index === activeSuggestionIndex}
              role="option"
              aria-selected={index === activeSuggestionIndex}
              on:mousedown|preventDefault
              on:mouseenter={() => dispatch('suggestionHover', index)}
              on:click={() => dispatch('selectSuggestion', suggestion.value)}
            >
              <span>{normalizeLabel(suggestion.value)}</span>
              {#if suggestion.count}
                <span class="suggestion-count">{suggestion.count}</span>
              {/if}
            </button>
          {/each}
        </div>
      {:else if suggestionsLoading}
        <div class="topic-suggestions loading sleek-scrollbar">Loading...</div>
      {/if}
    </div>
  {/if}
  <div class="tags-list">
    {#each topicRows as row (row.tag)}
      <InspectorTagChip
        label={row.tag}
        kind="topic"
        count={row.count}
        promoted={row.unsaved}
        clickable={row.unsaved}
        interactive={row.unsaved}
        title={row.unsaved ? "Click to revert topic promotion" : ""}
        renameable
        renameTitle="Rename topic"
        removeTitle="Remove topic"
        on:activate={() => dispatch('removeTopic', row.tag)}
        on:rename={() => dispatch('renameTopic', row.tag)}
        on:remove={() => dispatch('removeTopic', row.tag)}
      />
    {/each}
    {#if topicRows.length === 0}
      <div class="value-text">No topics</div>
    {/if}
  </div>
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

  .section-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .add-topic-btn {
    display: inline-grid;
    place-items: center;
    width: 24px;
    height: 24px;
    padding: 0;
    border-radius: 6px;
    border: 1px solid transparent;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
  }

  .add-topic-btn:hover,
  .add-topic-btn:focus-visible {
    border-color: rgba(163, 113, 247, 0.35);
    background: rgba(163, 113, 247, 0.08);
    color: var(--accent-purple);
  }

  .topic-confirm-btn {
    display: inline-grid;
    place-items: center;
    width: 22px;
    height: 22px;
    padding: 0;
    border-radius: 6px;
    border: 1px solid rgba(163, 113, 247, 0.4);
    background: rgba(163, 113, 247, 0.07);
    color: var(--accent-purple);
    cursor: pointer;
  }

  .topic-confirm-btn:hover {
    border-color: var(--accent-purple);
    background: rgba(163, 113, 247, 0.12);
    color: var(--text-bright);
  }

  .topic-input-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .topic-input-wrap {
    position: relative;
  }

  .topic-input {
    flex: 1;
    min-width: 0;
    height: 26px;
    padding: 3px 8px;
    font-size: 12px;
  }

  .topic-suggestions {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    right: 28px;
    z-index: 20;
    max-height: 180px;
    overflow-y: auto;
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    background: var(--bg-panel);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.35);
    padding: 4px 0;
  }

  .topic-suggestions.loading {
    padding: 7px 10px;
    color: var(--text-muted);
    font-size: 12px;
  }

  .topic-suggestions button {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    border: 0;
    border-radius: 0;
    background: transparent;
    color: var(--text-main);
    padding: 7px 10px;
    font-size: 12px;
    text-align: left;
    cursor: pointer;
  }

  .topic-suggestions button:hover,
  .topic-suggestions button.active {
    background: rgba(163, 113, 247, 0.18);
    color: var(--text-bright);
  }

  .suggestion-count {
    color: var(--text-muted);
    font-size: 11px;
  }

  .tags-list { display: flex; flex-wrap: wrap; gap: 6px; }

  .value-text {
    color: #6a737d;
    font-style: italic;
    font-weight: normal;
    font-size: 13px;
    padding: 2px 0;
  }

  input { background: var(--bg-input); border: 1px solid #30363d; font-weight: 500; }
</style>
