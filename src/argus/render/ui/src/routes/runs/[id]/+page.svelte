<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { page } from '$app/stores';
  import { fetchState } from '$lib/api';
  import { uiState } from '$lib/stores.svelte';

  import NetworkGraph from '$lib/components/NetworkGraph.svelte';
  import NodeSidebar from '$lib/components/NodeSidebar.svelte';

  let syncInterval: number;
  let isRunning = true;
  
  // Track current run ID from URL
  let currentRunId = $derived($page.params.id);

  $effect(() => {
      // When the URL parameter changes, update the active run and trigger a sync
      if (currentRunId && currentRunId !== untrack(() => uiState.activeRunId)) {
          uiState.activeRunId = currentRunId;
          uiState.selectedNodeId = null; // reset selection on navigation
          sync();
      }
  });

  async function sync() {
      if (!isRunning || !uiState.activeRunId) return;
      const state = await fetchState(uiState.activeRunId);
      if (state) {
          uiState.searchState = state;
      }
  }

  onMount(() => {
      // Start polling map
      syncInterval = setInterval(sync, 1000) as unknown as number;

      return () => {
          isRunning = false;
          if (syncInterval) clearInterval(syncInterval);
      };
  });
</script>

<svelte:head>
  <title>Argus · Observer Graph</title>
</svelte:head>

<div class="main-content">
  <NetworkGraph />
  <NodeSidebar />
</div>
