<script lang="ts">
  export let selectedFacetCount = 0;
  export let selectedTopicCount = 0;
  export let selectedWdTagCount = 0;
  export let onClear: () => void;
  export let onFilterVault: () => void;
</script>

{#if selectedFacetCount > 0}
  <div class="stats-filter-bar">
    <span>{selectedFacetCount} selected · {selectedTopicCount} topics · {selectedWdTagCount} WD tags</span>
    <div class="filter-actions">
      <button type="button" on:click={onClear}>Clear</button>
      <button type="button" class="primary" on:click={onFilterVault}>Filter Vault</button>
    </div>
  </div>
{/if}
