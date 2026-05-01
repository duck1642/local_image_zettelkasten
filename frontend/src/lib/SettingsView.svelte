<script lang="ts">
  import { onMount } from 'svelte';
  import { TILE_MIN_WIDTH_CEILING, TILE_MIN_WIDTH_FLOOR } from './layout';
  import { config, configDirty, configLoading, configSaving, loadConfig, saveCurrentConfig, updateConfig } from './configStore';
  import { log as uiLog } from './logger';

  function setConfig(mutator: (draft: any) => void) {
    updateConfig(mutator, false);
  }

  function textValue(event: Event) {
    return (event.currentTarget as HTMLInputElement | HTMLSelectElement).value;
  }

  function numberValue(event: Event) {
    return Number((event.currentTarget as HTMLInputElement).value);
  }

  function checkedValue(event: Event) {
    return (event.currentTarget as HTMLInputElement).checked;
  }

  function handleGlobalRefresh(event: Event) {
    const detail = (event as CustomEvent).detail || {};
    if (detail.tab !== 'settings') return;
    if ($configDirty && !confirm('You have unsaved settings. Discard them and refresh?')) return;
    uiLog('INFO', 'Settings view refresh requested');
    loadConfig();
  }

  onMount(() => {
    window.addEventListener('lmz:refresh', handleGlobalRefresh);
    loadConfig();
    return () => window.removeEventListener('lmz:refresh', handleGlobalRefresh);
  });
</script>

<div class="settings-container">
  {#if $configLoading || !$config}
    <div class="centered">Loading...</div>
  {:else}
    <div class="header-row">
      <h3>System Settings</h3>
      {#if $configDirty}
        <span class="status-label unsaved">Unsaved Changes</span>
      {/if}
    </div>

    <div class="form-grid">
      <label>Command Prefix</label>
      <input type="text" value={$config.ui.prefixes.command} on:input={(event) => setConfig((draft) => draft.ui.prefixes.command = textValue(event))} />

      <label>Artist Prefix</label>
      <input type="text" value={$config.ui.prefixes.artist} on:input={(event) => setConfig((draft) => draft.ui.prefixes.artist = textValue(event))} />

      <label>Tag Prefix</label>
      <input type="text" value={$config.ui.prefixes.tag} on:input={(event) => setConfig((draft) => draft.ui.prefixes.tag = textValue(event))} />

      <label>Platform Prefix</label>
      <input type="text" value={$config.ui.prefixes.platform} on:input={(event) => setConfig((draft) => draft.ui.prefixes.platform = textValue(event))} />

      <label>Vault Layout Mode</label>
      <select value={$config.ui.vault_layout_mode} on:change={(event) => setConfig((draft) => draft.ui.vault_layout_mode = textValue(event))}>
        <option value="masonry">Masonry</option>
        <option value="grid">Grid</option>
      </select>

      <label>Vault Min Tile Width</label>
      <input
        type="number"
        min={TILE_MIN_WIDTH_FLOOR}
        max={TILE_MIN_WIDTH_CEILING}
        step="10"
        value={$config.ui.vault_tile_min_width}
        on:input={(event) => setConfig((draft) => draft.ui.vault_tile_min_width = numberValue(event))}
      />

      <div class="grid-spacer"></div>
      <div class="checkbox-group">
        <label class="check-label">
          <input type="checkbox" checked={$config.processing.flatten_transparency} on:change={(event) => setConfig((draft) => draft.processing.flatten_transparency = checkedValue(event))} />
          Flatten Transparency
        </label>
        <label class="check-label">
          <input type="checkbox" checked={$config.tagging.enabled} on:change={(event) => setConfig((draft) => draft.tagging.enabled = checkedValue(event))} />
          Enable Tagging
        </label>
      </div>

      <label>Tag Model Repo</label>
      <input type="text" value={$config.tagging.model_repo} on:input={(event) => setConfig((draft) => draft.tagging.model_repo = textValue(event))} />

      <label>Tag Device</label>
      <select value={$config.tagging.device} on:change={(event) => setConfig((draft) => draft.tagging.device = textValue(event))}>
        <option value="cpu">cpu</option>
        <option value="cuda">cuda</option>
        <option value="auto">auto</option>
      </select>

      <label>Tag Threshold</label>
      <div class="multi-input">
        <input type="number" step="0.05" value={$config.tagging.threshold} on:input={(event) => setConfig((draft) => draft.tagging.threshold = numberValue(event))} />
        <label class="inline-label">Max Tags</label>
        <input type="number" value={$config.tagging.max_tags} on:input={(event) => setConfig((draft) => draft.tagging.max_tags = numberValue(event))} />
      </div>

      <div class="grid-spacer"></div>
      <button class="save-large" class:primary={$configDirty} on:click={saveCurrentConfig} disabled={!$configDirty || $configSaving}>
        {$configSaving ? 'Saving...' : 'Save Settings'}
      </button>
    </div>

    <div class="shortcuts-guide">
      <h4>Keyboard Shortcuts & Search Prefixes</h4>
      <div class="shortcuts-grid">
        <div class="shortcut-row">
          <span class="key">Enter</span>
          <span class="desc">Execute Search</span>
        </div>
        <div class="shortcut-row">
          <span class="key">F5</span>
          <span class="desc">Refresh Active View</span>
        </div>
        <div class="shortcut-row">
          <span class="key">Ctrl+F5</span>
          <span class="desc">Full App Reload</span>
        </div>
        <div class="shortcut-row">
          <span class="key">Esc</span>
          <span class="desc">Close Media Focus</span>
        </div>
        <div class="shortcut-row">
          <span class="key">W</span>
          <span class="desc">Toggle Wide View</span>
        </div>
        <div class="shortcut-row">
          <span class="key">F</span>
          <span class="desc">Toggle Fullscreen</span>
        </div>
        <div class="divider"></div>
        <div class="shortcut-row">
          <span class="key">&gt;grid</span>
          <span class="desc">Switch Vault to Grid Layout</span>
        </div>
        <div class="shortcut-row">
          <span class="key">&gt;masonry</span>
          <span class="desc">Switch Vault to Masonry Layout</span>
        </div>
        <div class="shortcut-row">
          <span class="key">&gt;zoom-in</span>
          <span class="desc">Increase Vault Tile Size</span>
        </div>
        <div class="shortcut-row">
          <span class="key">&gt;zoom-out</span>
          <span class="desc">Decrease Vault Tile Size</span>
        </div>
      </div>
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

  .shortcuts-guide {
    margin-top: 40px;
    padding-top: 25px;
    border-top: 1px solid var(--border-dim);
    max-width: 600px;
  }

  .shortcuts-guide h4 {
    margin: 0 0 15px 0;
    color: var(--text-bright);
    font-size: 14px;
  }

  .shortcuts-grid {
    display: flex;
    flex-direction: column;
    gap: 8px;
    background: var(--bg-panel);
    padding: 15px;
    border-radius: 8px;
    border: 1px solid var(--border-dim);
  }

  .shortcut-row {
    display: flex;
    align-items: center;
    gap: 15px;
  }

  .shortcut-row .key {
    background: var(--bg-main);
    border: 1px solid var(--border-dim);
    padding: 4px 8px;
    border-radius: 4px;
    font-family: 'Consolas', monospace;
    font-size: 11px;
    font-weight: bold;
    color: var(--text-bright);
    min-width: 60px;
    text-align: center;
  }

  .shortcut-row .desc {
    font-size: 13px;
    color: var(--text-muted);
  }

  .divider {
    height: 1px;
    background: var(--border-dim);
    margin: 5px 0;
  }
</style>
