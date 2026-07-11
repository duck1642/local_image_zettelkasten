<script lang="ts">
  import { IconAlertTriangle, IconServer } from './icons';
  export let runtime: any;
</script>

{#if runtime?.loaded && runtime.workspace && runtime.vault}
  <div class="workspace-panel">
    <div class="settings-panel-header">
      <h4 class="settings-section-title settings-title-inline">
        <span class="settings-title-icon">
          <IconServer size={14} />
        </span>
        Active Workspace Session
      </h4>
      <span class="active-badge">Online</span>
    </div>
    <div class="workspace-grid">
      <span>Root Path</span>
      <code class="settings-code">{runtime.workspace.root}</code>
      
      <span>Topics Dir</span>
      <code class="settings-code">{runtime.workspace.topics_root}</code>
      
      <span>Media Vault</span>
      <strong>{runtime.vault.name || runtime.vault.id || 'Default'}</strong>
      
      <span>Vault Path</span>
      <code class="settings-code">{runtime.vault.root}</code>
    </div>
    {#if runtime.env_override}
      <div class="restart-banner settings-inline-banner">
        <IconAlertTriangle size={12} />
        <span>Environment override is active. Registry changes apply only after restarting without LMZ_CONFIG_PATH.</span>
      </div>
    {/if}
  </div>
{/if}
