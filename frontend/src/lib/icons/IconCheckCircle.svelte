<script lang="ts">
  import IconBase from './IconBase.svelte';
  export let size = 14;
  export let strokeWidth = 2.5;
  export let title = '';
  export let className = '';
</script>

<IconBase {size} {strokeWidth} {title} {className}>
  <circle cx="12" cy="12" r="10"></circle>
  <path d="m9 12 2 2 4-4"></path>
</IconBase>
