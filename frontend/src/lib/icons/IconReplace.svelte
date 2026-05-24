<script lang="ts">
  import IconBase from './IconBase.svelte';
  export let size = 14;
  export let strokeWidth = 2.5;
  export let title = '';
  export let className = '';
</script>

<IconBase {size} {strokeWidth} {title} {className}>
  <polyline points="17 1 21 5 17 9"></polyline>
  <path d="M3 11V9a4 4 0 0 1 4-4h14"></path>
  <polyline points="7 23 3 19 7 15"></polyline>
  <path d="M21 13v2a4 4 0 0 1-4 4H3"></path>
</IconBase>
