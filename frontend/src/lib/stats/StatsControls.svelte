<script lang="ts">
  import type { StatsScopeMode, StatsSortMode } from './types';

  export let sortMode: StatsSortMode;
  export let scopeMode: StatsScopeMode;
  export let letterFilter = 'all';
  export let letterFilters: string[] = [];
  export let searchText = '';
  export let showLetterFilter = false;
  export let showScopeFilter = false;
  export let onSort: (mode: StatsSortMode) => void;
  export let onScope: (mode: StatsScopeMode) => void;
  export let onLetter: (value: string) => void;
  export let onSearchInput: () => void;
</script>

<div class="stats-controls">
  {#if showScopeFilter}
    <div class="scope-tabs">
      <button type="button" class:active={scopeMode === 'used'} on:click={() => onScope('used')}>
        Used
      </button>
      <button type="button" class:active={scopeMode === 'all'} on:click={() => onScope('all')}>
        All
      </button>
    </div>
  {/if}
  <div class="sort-tabs">
    <button type="button" class:active={sortMode === 'popularity'} on:click={() => onSort('popularity')}>
      Popularity
    </button>
    <button type="button" class:active={sortMode === 'alphabetical'} on:click={() => onSort('alphabetical')}>
      Alphabetical
    </button>
  </div>
  <input
    class="stats-search"
    type="text"
    bind:value={searchText}
    on:input={onSearchInput}
    placeholder="Search stats..."
  />
</div>

{#if showLetterFilter}
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
