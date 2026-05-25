<script lang="ts">
  import type { StatsScopeMode, StatsSortMode } from './types';
  import { IconFilter } from '../icons';

  export let sortMode: StatsSortMode;
  export let scopeMode: StatsScopeMode;
  export let letterFilter = 'all';
  export let alphabetFilterOpen = false;
  export let letterFilters: string[] = [];
  export let searchText = '';
  export let showLetterFilter = false;
  export let showScopeFilter = false;
  export let onSort: (mode: StatsSortMode) => void;
  export let onScope: (mode: StatsScopeMode) => void;
  export let onLetter: (value: string) => void;
  export let onAlphabetToggle: (value: boolean) => void;
  export let onSearchInput: () => void;

  let filterOpen = false;
  $: filterActive = scopeMode !== 'used' || sortMode !== 'popularity' || alphabetFilterOpen;

  function isEditableTarget(target: EventTarget | null) {
    const element = target as HTMLElement | null;
    if (!element) return false;
    const tagName = element.tagName.toLowerCase();
    return tagName === 'input' || tagName === 'textarea' || tagName === 'select' || element.isContentEditable;
  }

  function handleStatsShortcut(event: KeyboardEvent) {
    if (event.ctrlKey || event.altKey || event.metaKey || !event.shiftKey) return;
    if (isEditableTarget(event.target)) return;
    if (event.key.toLowerCase() !== 'f') return;
    event.preventDefault();
    filterOpen = !filterOpen;
  }
</script>

<svelte:window on:keydown={handleStatsShortcut} />

<div class="stats-controls">
  <input
    class="stats-search"
    type="text"
    bind:value={searchText}
    on:input={onSearchInput}
    placeholder="Search stats..."
  />
  <div class="stats-filter-wrap">
    <button
      class="stats-filter-button"
      class:active={filterOpen || filterActive}
      type="button"
      title="Filter stats (Shift+F)"
      aria-label="Filter stats"
      aria-expanded={filterOpen}
      on:click={() => filterOpen = !filterOpen}
    >
      <IconFilter size={14} strokeWidth={2.2} />
    </button>

    {#if filterOpen}
      <div class="stats-filter-popover">
        {#if showScopeFilter}
          <div class="filter-section">
            <div class="filter-label">Scope</div>
            <div class="scope-tabs compact">
              <button type="button" class:active={scopeMode === 'used'} on:click={() => onScope('used')}>
                Used
              </button>
              <button type="button" class:active={scopeMode === 'all'} on:click={() => onScope('all')}>
                All
              </button>
            </div>
          </div>
        {/if}

        <div class="filter-section">
          <div class="filter-label">Sort</div>
          <div class="sort-tabs compact">
            <button type="button" class:active={sortMode === 'popularity'} on:click={() => onSort('popularity')}>
              Popularity
            </button>
            <button type="button" class:active={sortMode === 'alphabetical'} on:click={() => onSort('alphabetical')}>
              Alphabetical
            </button>
          </div>
        </div>

        {#if showLetterFilter}
          <div class="filter-section">
            <label class="filter-toggle">
              <span>A-Z</span>
              <input
                type="checkbox"
                checked={alphabetFilterOpen}
                on:change={(event) => onAlphabetToggle((event.currentTarget as HTMLInputElement).checked)}
              />
            </label>

            {#if alphabetFilterOpen}
              <div class="letter-tabs" aria-label="First character filter">
                {#each letterFilters as letter}
                  <button
                    type="button"
                    class="letter-tab"
                    class:active={letterFilter === letter}
                    on:click={() => onLetter(letter)}
                  >
                    {letter === 'all' ? 'All' : letter.toUpperCase()}
                  </button>
                {/each}
              </div>
            {/if}
          </div>
        {/if}
      </div>
    {/if}
  </div>
</div>
