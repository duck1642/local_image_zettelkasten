<script lang="ts">
  import IconBase from './IconBase.svelte';
  export let size = 14;
  export let strokeWidth = 2.5;
  export let title = '';
  export let className = '';
</script>

<IconBase {size} {strokeWidth} {title} {className}>
  <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
  <circle cx="8.5" cy="8.5" r="1.5"></circle>
  <polyline points="21 15 16 10 5 21"></polyline>
</IconBase>
