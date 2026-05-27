<script lang="ts">
  import IconBase from './IconBase.svelte';
  export let size = 14;
  export let strokeWidth = 2.5;
  export let title = '';
  export let className = '';
</script>

<IconBase {size} {strokeWidth} {title} {className}>
  <!-- Top Tier -->
  <rect x="2" y="2" width="20" height="6" rx="1" />
  <line x1="6" y1="5" x2="6" y2="5" stroke-linecap="round" />
  <line x1="10" y1="5" x2="14" y2="5" />
  
  <!-- Middle Tier -->
  <rect x="2" y="9" width="20" height="6" rx="1" />
  <line x1="6" y1="12" x2="6" y2="12" stroke-linecap="round" />
  <line x1="10" y1="12" x2="14" y2="12" />
  
  <!-- Bottom Tier -->
  <rect x="2" y="16" width="20" height="6" rx="1" />
  <line x1="6" y1="19" x2="6" y2="19" stroke-linecap="round" />
  <line x1="10" y1="19" x2="14" y2="19" />
</IconBase>
