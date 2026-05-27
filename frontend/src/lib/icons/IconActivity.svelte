<script lang="ts">
  import IconBase from './IconBase.svelte';
  export let size = 14;
  export let strokeWidth = 2.5;
  export let title = '';
  export let className = '';
</script>

<IconBase {size} {strokeWidth} {title} {className}>
  <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
</IconBase>
