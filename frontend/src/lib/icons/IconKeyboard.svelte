<script lang="ts">
  import IconBase from './IconBase.svelte';
  export let size = 14;
  export let strokeWidth = 2.5;
  export let title = '';
  export let className = '';
</script>

<IconBase {size} {strokeWidth} {title} {className}>
  <rect x="2" y="4" width="20" height="16" rx="2" ry="2"></rect>
  <line x1="6" y1="8" x2="6.01" y2="8"></line>
  <line x1="10" y1="8" x2="10.01" y2="8"></line>
  <line x1="14" y1="8" x2="14.01" y2="8"></line>
  <line x1="18" y1="8" x2="18.01" y2="8"></line>
  <line x1="6" y1="12" x2="6.01" y2="12"></line>
  <line x1="10" y1="12" x2="10.01" y2="12"></line>
  <line x1="14" y1="12" x2="14.01" y2="12"></line>
  <line x1="18" y1="12" x2="18.01" y2="12"></line>
  <line x1="7" y1="16" x2="17" y2="16"></line>
</IconBase>
