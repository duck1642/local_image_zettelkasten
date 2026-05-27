<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import OnlineIngestion from './OnlineIngestion.svelte';
  import LocalIngestion from './LocalIngestion.svelte';
  import './ingestion.css';

  type IngestMode = 'online' | 'local';
  type DropRequest = {
    id: string;
    session_id: string;
    accepted_paths: string[];
    skipped: Array<{ path: string; reason: string }>;
    summary: { received: number; accepted: number; skipped: number };
    source_tab: string;
  };

  export let dropRequest: DropRequest | null = null;
  const dispatch = createEventDispatcher<{ modechange: { mode: IngestMode } }>();

  let ingestMode: IngestMode = 'online';
  let lastModeEmitted: IngestMode | null = null;

  $: if (ingestMode !== lastModeEmitted) {
    lastModeEmitted = ingestMode;
    dispatch('modechange', { mode: ingestMode });
  }
</script>

<div class="ingestion-container">
  <div class="mode-switch">
    <button class:active={ingestMode === 'online'} on:click={() => ingestMode = 'online'}>Online</button>
    <button class:active={ingestMode === 'local'} on:click={() => ingestMode = 'local'}>Local</button>
  </div>

  {#if ingestMode === 'online'}
    <OnlineIngestion />
  {:else}
    <LocalIngestion {dropRequest} />
  {/if}
</div>
