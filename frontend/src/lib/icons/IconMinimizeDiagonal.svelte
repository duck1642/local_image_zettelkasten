<script lang="ts">
  import IconBase from './IconBase.svelte';
  export let size = 14;
  export let strokeWidth = 2.5;
  export let title = '';
  export let className = '';
</script>

<IconBase {size} {strokeWidth} {title} {className}>
  <path d="M4 14h6v6M20 10h-6V4M14 10l7-7M10 14l-7 7"></path>
</IconBase>
