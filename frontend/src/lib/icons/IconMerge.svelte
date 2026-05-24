<script lang="ts">
  import IconBase from './IconBase.svelte';
  export let size = 14;
  export let strokeWidth = 2.5;
  export let title = '';
  export let className = '';
</script>

<IconBase {size} {strokeWidth} {title} {className}>
  <circle cx="18" cy="18" r="3"></circle>
  <circle cx="6" cy="6" r="3"></circle>
  <path d="M6 9v9a3 3 0 0 0 3 3h3"></path>
  <path d="M18 15V9a6 6 0 0 0-6-6H9"></path>
</IconBase>
