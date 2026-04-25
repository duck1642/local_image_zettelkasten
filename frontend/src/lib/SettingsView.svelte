<script lang="ts">
  import { onMount } from 'svelte';
  let config: any = null;
  let loading = true;
  let saving = false;

  async function loadConfig() {
    loading = true;
    try {
      const res = await fetch('http://localhost:8000/api/config');
      config = await res.json();
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
    } finally { saving = false; }
  }

  onMount(loadConfig);
</script>

<div class="settings-container">
  {#if loading}
    <div class="centered">Loading...</div>
  {:else if config}
    <h3>System Settings</h3>
    
    <div class="form">
      <div class="field">
        <label>Command Prefix</label>
        <input type="text" bind:value={config.ui.prefixes.command} />
      </div>
      <div class="field">
        <label>Artist Prefix</label>
        <input type="text" bind:value={config.ui.prefixes.artist} />
      </div>
      <div class="field">
        <label>Tag Prefix</label>
        <input type="text" bind:value={config.ui.prefixes.tag} />
      </div>
      <div class="field">
        <label>Platform Prefix</label>
        <input type="text" bind:value={config.ui.prefixes.platform} />
      </div>

      <div class="field">
        <label>Vault Layout</label>
        <select bind:value={config.ui.vault_layout}>
            <option value="masonry">masonry</option>
            <option value="grid">grid</option>
        </select>
      </div>

      <div class="checkbox-group">
          <label><input type="checkbox" /> Flatten Transparency</label>
          <label><input type="checkbox" bind:checked={config.tagging.enabled} /> Enable Tagging</label>
      </div>

      <div class="field">
        <label>Tag Model Repo</label>
        <input type="text" bind:value={config.tagging.model_repo} />
      </div>

      <div class="field">
        <label>Tag Device</label>
        <select bind:value={config.tagging.device}>
            <option value="cpu">cpu</option>
            <option value="cuda">cuda</option>
            <option value="auto">auto</option>
        </select>
      </div>

      <div class="row">
          <div class="field half">
            <label>Tag Threshold</label>
            <input type="number" step="0.05" bind:value={config.tagging.threshold} />
          </div>
          <div class="field half">
            <label>Tag Max Tags</label>
            <input type="number" bind:value={config.tagging.max_tags} />
          </div>
      </div>

      <button class="primary save-large" on:click={saveConfig} disabled={saving}>
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

  h3 { color: var(--text-bright); margin-bottom: 25px; }

  .form {
    display: flex;
    flex-direction: column;
    gap: 15px;
    max-width: 100%;
  }

  .field { display: flex; align-items: center; gap: 20px; }
  .field label { width: 150px; font-size: 13px; color: var(--text-main); }
  .field input, .field select { flex-grow: 1; background: var(--bg-panel); border: 1px solid var(--border-dim); }

  .checkbox-group { margin-left: 170px; display: flex; flex-direction: column; gap: 10px; }
  .checkbox-group label { display: flex; align-items: center; gap: 10px; cursor: pointer; }

  .row { display: flex; gap: 20px; }
  .field.half { flex: 1; }

  .save-large {
    margin-top: 20px;
    padding: 12px;
    width: 100%;
    font-size: 14px;
  }

  .centered { flex-grow: 1; display: flex; align-items: center; justify-content: center; color: var(--text-muted); }
</style>
