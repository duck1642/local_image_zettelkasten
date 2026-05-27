<script lang="ts">
  import { IconServer } from './icons';
  export let runtime: any;
</script>

{#if runtime}
  <div class="workspace-panel">
    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
      <h4 class="settings-section-title" style="margin: 0; display: flex; align-items: center; gap: 8px;">
        <span style="display: inline-block; vertical-align: text-bottom;">
          <IconServer size={14} />
        </span>
        Active Workspace Session
      </h4>
      <span class="active-badge">Online</span>
    </div>
    <div class="workspace-grid">
      <span>Session Mode</span>
      <strong>{runtime.workspace_label || runtime.workspace_mode || 'Default Workspace'}</strong>
      
      <span>Config File</span>
      <code style="font-family: 'Consolas', monospace; font-size: 11px;">{runtime.config_path}</code>
      
      <span>Root Path</span>
      <code style="font-family: 'Consolas', monospace; font-size: 11px;">{runtime.config_root}</code>
      
      <span>Topics Dir</span>
      <code style="font-family: 'Consolas', monospace; font-size: 11px;">{runtime.topic_root}</code>
      
      <span>Media Vault</span>
      <strong>{runtime.active_vault_name || runtime.active_vault || 'Default'}</strong>
      
      <span>Vault Path</span>
      <code style="font-family: 'Consolas', monospace; font-size: 11px;">{runtime.active_vault_root}</code>
    </div>
    {#if runtime.env_override}
      <div class="restart-banner" style="margin-top: 12px; padding: 8px 12px; background: rgba(210, 153, 34, 0.05); border: 1px solid rgba(210, 153, 34, 0.15); border-radius: 6px;">
        ⚠️ Environment override is active. Registry changes apply only after restarting without LMZ_CONFIG_PATH.
      </div>
    {/if}
    <slot />
  </div>
{/if}
