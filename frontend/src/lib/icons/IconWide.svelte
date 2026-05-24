<script lang="ts">
  import IconBase from './IconBase.svelte';
  export let size = 14;
  export let strokeWidth = 2.5;
  export let title = '';
  export let className = '';
</script>

<IconBase {size} {strokeWidth} {title} {className}>
  <path d="M4 12h16M7 9l-3 3 3 3M17 9l3 3-3 3"></path>
</IconBase>
