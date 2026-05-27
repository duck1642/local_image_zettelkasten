<script lang="ts">
  export let runtime: any;
</script>

{#if runtime}
  <div class="workspace-panel">
    <h4>Workspace</h4>
    <div class="workspace-grid">
      <span>Mode</span>
      <strong>{runtime.workspace_label || runtime.workspace_mode || 'Default workspace'}</strong>
      <span>Config</span>
      <code>{runtime.config_path}</code>
      <span>Root</span>
      <code>{runtime.config_root}</code>
      <span>Topics</span>
      <code>{runtime.topic_root}</code>
      <span>Vault</span>
      <strong>{runtime.active_vault_name || runtime.active_vault || 'Default'}</strong>
      <span>Vault Root</span>
      <code>{runtime.active_vault_root}</code>
    </div>
    {#if runtime.env_override}
      <div class="workspace-note">Environment override is active. Registry changes apply only after restarting without LMZ_CONFIG_PATH.</div>
    {/if}
    <slot />
  </div>
{/if}
