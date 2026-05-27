<script lang="ts">
  import { TILE_MIN_WIDTH_CEILING, TILE_MIN_WIDTH_FLOOR } from './layout';
  import { config, configDirty, configSaving, saveCurrentConfig, updateConfig } from './configStore';

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
</script>

<div class="section-card">
  <h4 class="settings-section-title">Vault Display Settings</h4>
  <div class="form-grid">
    <label for="settings-layout-mode">
      Vault Layout Mode
      <div class="micro-desc">Choose between standard grid alignment or staggered masonry.</div>
    </label>
    <select id="settings-layout-mode" value={$config.ui.vault_layout_mode} on:change={(event) => setConfig((draft) => draft.ui.vault_layout_mode = textValue(event))}>
      <option value="masonry">Masonry</option>
      <option value="grid">Grid</option>
    </select>

    <label for="settings-tile-min-width">
      Vault Min Tile Width
      <div class="micro-desc">Controls the base sizing of media cards in your library.</div>
    </label>
    <div class="slider-container">
      <input
        id="settings-tile-min-width"
        type="range"
        min={TILE_MIN_WIDTH_FLOOR}
        max={TILE_MIN_WIDTH_CEILING}
        step="10"
        value={$config.ui.vault_tile_min_width}
        on:input={(event) => setConfig((draft) => draft.ui.vault_tile_min_width = numberValue(event))}
      />
      <span class="slider-value">{$config.ui.vault_tile_min_width}px</span>
    </div>
  </div>
</div>

<div class="section-card">
  <h4 class="settings-section-title">AI Tagging Engine</h4>
  <div class="form-grid">
    <label for="settings-flatten-transparency">
      Image Transcoding
      <div class="micro-desc">Handling transparent PNG/WEBP layers.</div>
    </label>
    <div class="checkbox-group">
      <label class="check-label" id="settings-flatten-transparency">
        <input type="checkbox" checked={$config.processing.flatten_transparency} on:change={(event) => setConfig((draft) => draft.processing.flatten_transparency = checkedValue(event))} />
        Flatten Transparency
      </label>
    </div>

    <label for="settings-enable-tagging">
      Auto Tagging
      <div class="micro-desc">Enables local AI-powered object detection and tag ingest.</div>
    </label>
    <div class="checkbox-group">
      <label class="check-label" id="settings-enable-tagging">
        <input type="checkbox" checked={$config.tagging.enabled} on:change={(event) => setConfig((draft) => draft.tagging.enabled = checkedValue(event))} />
        Enable WD Tagging
      </label>
    </div>

    <label for="settings-model-repo">
      Tag Model Repo
      <div class="micro-desc">HuggingFace repository ID for the tagging model weights.</div>
    </label>
    <input id="settings-model-repo" type="text" value={$config.tagging.model_repo} on:input={(event) => setConfig((draft) => draft.tagging.model_repo = textValue(event))} />

    <label for="settings-tag-device">
      Tag Device
      <div class="micro-desc">Hardware accelerator device to bind for AI inference.</div>
    </label>
    <select id="settings-tag-device" value={$config.tagging.device} on:change={(event) => setConfig((draft) => draft.tagging.device = textValue(event))}>
      <option value="cpu">cpu</option>
      <option value="cuda">cuda</option>
      <option value="auto">auto</option>
    </select>

    <label for="settings-tag-threshold">
      Tag Threshold
      <div class="micro-desc">Inference confidence cutoff for auto-generated suggestions.</div>
    </label>
    <div class="slider-container">
      <input
        id="settings-tag-threshold"
        type="range"
        min="0.05"
        max="1.0"
        step="0.05"
        value={$config.tagging.threshold}
        on:input={(event) => setConfig((draft) => draft.tagging.threshold = numberValue(event))}
      />
      <span class="slider-value">{Number($config.tagging.threshold).toFixed(2)}</span>
    </div>

    <label for="settings-max-tags">
      Max Ingest Tags
      <div class="micro-desc">Maximum number of suggestions to associate per media file.</div>
    </label>
    <input id="settings-max-tags" type="number" value={$config.tagging.max_tags} on:input={(event) => setConfig((draft) => draft.tagging.max_tags = numberValue(event))} />
  </div>
</div>

<div class="save-bar" class:dirty={$configDirty}>
  <div class="save-info">
    {#if $configDirty}
      <span class="status-label unsaved">You have unsaved changes.</span>
    {:else}
      <span class="micro-desc">All system configurations are up-to-date.</span>
    {/if}
  </div>
  <button class="primary" on:click={saveCurrentConfig} disabled={!$configDirty || $configSaving}>
    {$configSaving ? 'Saving...' : 'Save Settings'}
  </button>
</div>
