<script lang="ts">
  import type { Snippet } from 'svelte';
  const { children }: { children: Snippet } = $props();
</script>

{@render children()}

<style>
  :global(*, *::before, *::after) { box-sizing: border-box; margin: 0; padding: 0; }
  :global(html) { scroll-behavior: smooth; }
  :global(::-webkit-scrollbar) { width: 4px; height: 4px; }
  :global(::-webkit-scrollbar-track) { background: transparent; }
  :global(::-webkit-scrollbar-thumb) { background: #3f3f46; border-radius: 2px; }
</style>
