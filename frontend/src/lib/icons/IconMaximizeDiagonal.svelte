<script lang="ts">
  import IconBase from './IconBase.svelte';
  export let size = 14;
  export let strokeWidth = 2.5;
  export let title = '';
  export let className = '';
</script>

<IconBase {size} {strokeWidth} {title} {className}>
  <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"></path>
</IconBase>
