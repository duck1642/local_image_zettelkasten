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

<div class="form-grid">
  <label for="settings-layout-mode">Vault Layout Mode</label>
  <select id="settings-layout-mode" value={$config.ui.vault_layout_mode} on:change={(event) => setConfig((draft) => draft.ui.vault_layout_mode = textValue(event))}>
    <option value="masonry">Masonry</option>
    <option value="grid">Grid</option>
  </select>

  <label for="settings-tile-min-width">Vault Min Tile Width</label>
  <input
    id="settings-tile-min-width"
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

  <label for="settings-model-repo">Tag Model Repo</label>
  <input id="settings-model-repo" type="text" value={$config.tagging.model_repo} on:input={(event) => setConfig((draft) => draft.tagging.model_repo = textValue(event))} />

  <label for="settings-tag-device">Tag Device</label>
  <select id="settings-tag-device" value={$config.tagging.device} on:change={(event) => setConfig((draft) => draft.tagging.device = textValue(event))}>
    <option value="cpu">cpu</option>
    <option value="cuda">cuda</option>
    <option value="auto">auto</option>
  </select>

  <label for="settings-tag-threshold">Tag Threshold</label>
  <div class="multi-input">
    <input id="settings-tag-threshold" type="number" step="0.05" value={$config.tagging.threshold} on:input={(event) => setConfig((draft) => draft.tagging.threshold = numberValue(event))} />
    <label class="inline-label" for="settings-max-tags">Max Tags</label>
    <input id="settings-max-tags" type="number" value={$config.tagging.max_tags} on:input={(event) => setConfig((draft) => draft.tagging.max_tags = numberValue(event))} />
  </div>

  <div class="grid-spacer"></div>
  <button class="save-large" class:primary={$configDirty} on:click={saveCurrentConfig} disabled={!$configDirty || $configSaving}>
    {$configSaving ? 'Saving...' : 'Save Settings'}
  </button>
</div>
