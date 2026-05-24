<script lang="ts">
  import IconBase from './IconBase.svelte';
  export let size = 14;
  export let strokeWidth = 2.5;
  export let title = '';
  export let className = '';
</script>

<IconBase {size} {strokeWidth} {title} {className}>
  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
  <path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
</IconBase>
