<script lang="ts">
  import IconBase from './IconBase.svelte';
  export let size = 14;
  export let strokeWidth = 2.5;
  export let title = '';
  export let className = '';
</script>

<IconBase {size} {strokeWidth} {title} {className}>
  <polygon points="23 7 16 12 23 17 23 7"></polygon>
  <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
</IconBase>
