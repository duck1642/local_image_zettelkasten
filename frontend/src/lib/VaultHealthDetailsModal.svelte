<script lang="ts">
  import { countValues, detailValues, healthKindLabel } from './settingsUtils';

  export let healthReport: any;
  export let repairErrors: Array<{ hash: string; storage_id: string; status: string; error: string }> = [];
  export let onClose: () => void;
  const DETAIL_LIMIT = 100;

  function closeOnBackdrop(event: MouseEvent) {
    if (event.target === event.currentTarget) onClose();
  }

  function exceedsDetailLimit(value: any) {
    return countValues(value) > DETAIL_LIMIT;
  }

  function hasTruncatedDetails() {
    return (
      exceedsDetailLimit(healthReport.details?.missing_files || healthReport.missing_files)
      || exceedsDetailLimit(healthReport.orphans)
      || exceedsDetailLimit(healthReport.stale_index_rows)
      || (healthReport.facet_drift || []).length > DETAIL_LIMIT
      || (healthReport.hash_mismatches || []).length > DETAIL_LIMIT
      || (healthReport.bad_storage_ids || []).length > DETAIL_LIMIT
      || (healthReport.broken_topic_links || []).length > DETAIL_LIMIT
      || exceedsDetailLimit(healthReport.review_mismatches)
      || repairErrors.length > DETAIL_LIMIT
    );
  }
</script>

<div class="modal-backdrop" role="presentation" on:click={closeOnBackdrop}>
  <div class="health-modal" role="dialog" aria-modal="true" aria-label="Vault Health Details" tabindex="-1">
    <div class="modal-header">
      <h4>Vault Health Details</h4>
      <button type="button" on:click={onClose}>Close</button>
    </div>
    <div class="health-detail sleek-scrollbar">
      {#if countValues(healthReport.missing_files)}
        <div class="health-section-title">Missing Files</div>
        {#each detailValues(healthReport.details?.missing_files || healthReport.missing_files) as row}
          <div class="health-row">
            <span>{healthKindLabel(row.kind)}</span>
            <code title={row.value}>{row.value}</code>
          </div>
        {/each}
      {/if}
      {#if countValues(healthReport.orphans)}
        <div class="health-section-title">Orphans</div>
        {#each detailValues(healthReport.orphans) as row}
          <div class="health-row">
            <span>{healthKindLabel(row.kind)}</span>
            <code title={row.value}>{row.value}</code>
          </div>
        {/each}
      {/if}
      {#if countValues(healthReport.stale_index_rows)}
        <div class="health-section-title">Stale Index Rows</div>
        {#each detailValues(healthReport.stale_index_rows) as row}
          <div class="health-row">
            <span>{healthKindLabel(row.kind)}</span>
            <code>{row.value}</code>
          </div>
        {/each}
      {/if}
      {#if (healthReport.facet_drift || []).length}
        <div class="health-section-title">Facet Drift</div>
        {#each healthReport.facet_drift.slice(0, DETAIL_LIMIT) as row}
          <div class="health-row"><span>Facet</span><code>{row}</code></div>
        {/each}
      {/if}
      {#if (healthReport.hash_mismatches || []).length}
        <div class="health-section-title">Hash Mismatches</div>
        {#each healthReport.hash_mismatches.slice(0, DETAIL_LIMIT) as row}
          <div class="health-row"><span>Asset</span><code title={row}>{row}</code></div>
        {/each}
      {/if}
      {#if (healthReport.bad_storage_ids || []).length}
        <div class="health-section-title">Bad Storage IDs</div>
        {#each healthReport.bad_storage_ids.slice(0, DETAIL_LIMIT) as row}
          <div class="health-row"><span>Item hash</span><code title={row}>{row}</code></div>
        {/each}
      {/if}
      {#if (healthReport.broken_topic_links || []).length}
        <div class="health-section-title">Broken Topic Links</div>
        {#each healthReport.broken_topic_links.slice(0, DETAIL_LIMIT) as row}
          <div class="health-row"><span>Topic</span><code title={row}>{row}</code></div>
        {/each}
      {/if}
      {#if countValues(healthReport.review_mismatches)}
        <div class="health-section-title">Review Mismatches</div>
        {#each detailValues(healthReport.review_mismatches) as row}
          <div class="health-row"><span>{healthKindLabel(row.kind)}</span><code title={row.value}>{row.value}</code></div>
        {/each}
      {/if}
      {#if (healthReport.workspace_dictionary_drift?.missing_in_dictionary || 0) + (healthReport.workspace_dictionary_drift?.unused_in_vault || 0) > 0}
        <div class="health-section-title">Dictionary Drift</div>
        {#if healthReport.workspace_dictionary_drift?.missing_in_dictionary}
          <div class="health-row"><span>Missing in dict</span><code>{healthReport.workspace_dictionary_drift.missing_in_dictionary} tags</code></div>
        {/if}
        {#if healthReport.workspace_dictionary_drift?.unused_in_vault}
          <div class="health-row"><span>Unused in workspace</span><code>{healthReport.workspace_dictionary_drift.unused_in_vault} tags</code></div>
        {/if}
      {/if}
      {#if repairErrors.length}
        <div class="health-section-title">WD Tagging Errors ({repairErrors.length})</div>
        {#each repairErrors.slice(0, DETAIL_LIMIT) as err}
          <div class="health-row">
            <span>{err.status || 'error'}</span>
            <code title={err.error}>{err.error}</code>
          </div>
        {/each}
      {/if}
      {#if hasTruncatedDetails()}
        <div class="health-truncation-note">Showing first {DETAIL_LIMIT} items.</div>
      {/if}
    </div>
  </div>
</div>
