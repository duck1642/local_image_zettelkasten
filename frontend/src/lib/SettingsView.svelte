<script lang="ts">
  import { onMount } from 'svelte';
  let config: any = null;
  let initialConfigStr: string = '';
  let loading = true;
  let saving = false;

  $: isDirty = config ? JSON.stringify(config) !== initialConfigStr : false;

  async function loadConfig() {
    loading = true;
    try {
      const res = await fetch('http://localhost:8000/api/config');
      config = await res.json();
      initialConfigStr = JSON.stringify(config);
    } finally { loading = false; }
  }

  async function saveConfig() {
    saving = true;
    try {
      await fetch('http://localhost:8000/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      });
      initialConfigStr = JSON.stringify(config);
    } finally { saving = false; }
  }

  onMount(loadConfig);
</script>

<div class="settings-container">
  {#if loading}
    <div class="centered">Loading...</div>
  {:else if config}
    <div class="header-row">
        <h3>System Settings</h3>
        {#if isDirty}
            <span class="status-label unsaved">● Unsaved Changes</span>
        {/if}
    </div>
    
    <div class="form-grid">
      <label>Command Prefix</label>
      <input type="text" bind:value={config.ui.prefixes.command} />

      <label>Artist Prefix</label>
      <input type="text" bind:value={config.ui.prefixes.artist} />

      <label>Tag Prefix</label>
      <input type="text" bind:value={config.ui.prefixes.tag} />

      <label>Platform Prefix</label>
      <input type="text" bind:value={config.ui.prefixes.platform} />

      <label>Vault Layout</label>
      <select bind:value={config.ui.vault_layout}>
          <option value="masonry">masonry</option>
          <option value="grid">grid</option>
      </select>

      <div class="grid-spacer"></div>
      <div class="checkbox-group">
          <label class="check-label"><input type="checkbox" bind:checked={config.processing.flatten_transparency} /> Flatten Transparency</label>
          <label class="check-label"><input type="checkbox" bind:checked={config.tagging.enabled} /> Enable Tagging</label>
      </div>

      <label>Tag Model Repo</label>
      <input type="text" bind:value={config.tagging.model_repo} />

      <label>Tag Device</label>
      <select bind:value={config.tagging.device}>
          <option value="cpu">cpu</option>
          <option value="cuda">cuda</option>
          <option value="auto">auto</option>
      </select>

      <label>Tag Threshold</label>
      <div class="multi-input">
        <input type="number" step="0.05" bind:value={config.tagging.threshold} />
        <label class="inline-label">Max Tags</label>
        <input type="number" bind:value={config.tagging.max_tags} />
      </div>

      <div class="grid-spacer"></div>
      <button class="save-large" class:primary={isDirty} on:click={saveConfig} disabled={!isDirty || saving}>
        {saving ? 'Saving...' : 'Save Settings'}
      </button>
    </div>
  {/if}
</div>

<style>
  .settings-container {
    flex-grow: 1;
    padding: 25px;
    background: var(--bg-main);
    overflow-y: auto;
  }

  h3 { color: var(--text-bright); margin: 0; }

  .header-row {
    display: flex;
    align-items: center;
    gap: 15px;
    margin-bottom: 25px;
  }

  .status-label.unsaved {
    color: var(--accent-warning);
    font-size: 12px;
    font-weight: 600;
  }

  .form-grid {
    display: grid;
    grid-template-columns: 180px 1fr;
    gap: 15px;
    align-items: center;
    max-width: 600px;
  }

  label { font-size: 13px; color: var(--text-main); }
  
  input[type="text"], input[type="number"], select { 
      background: var(--bg-panel); 
      border: 1px solid var(--border-dim); 
      padding: 8px 12px;
      color: var(--text-main);
      border-radius: 6px;
      font-size: 13px;
      width: 100%;
      box-sizing: border-box;
  }

  .grid-spacer { display: block; }

  .checkbox-group { display: flex; flex-direction: column; gap: 10px; }
  .check-label { display: flex; align-items: center; gap: 10px; cursor: pointer; }

  .multi-input { display: flex; gap: 15px; align-items: center; }
  .inline-label { margin-left: 10px; }

  .save-large {
    margin-top: 10px;
    padding: 12px;
    width: 100%;
    font-size: 14px;
  }

  .centered { flex-grow: 1; display: flex; align-items: center; justify-content: center; color: var(--text-muted); }
</style>
