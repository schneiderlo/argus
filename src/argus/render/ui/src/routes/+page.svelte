<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchState, fetchDefaultRunId } from '$lib/api';
  import { uiState, initTheme } from '$lib/stores.svelte';

  import TopBar from '$lib/components/TopBar.svelte';
  import NetworkGraph from '$lib/components/NetworkGraph.svelte';
  import NodeSidebar from '$lib/components/NodeSidebar.svelte';

  onMount(() => {
      initTheme();
      
      let isRunning = true;
      let syncInterval: number;

      async function boot() {
          if (!uiState.activeRunId) {
              const runId = await fetchDefaultRunId();
              if (runId) {
                  uiState.activeRunId = runId;
              }
          }

          async function sync() {
              if (!isRunning || !uiState.activeRunId) return;
              const state = await fetchState(uiState.activeRunId);
              if (state) {
                  uiState.searchState = state;
              }
          }

          // Initial fetch
          await sync();

          // Start polling map
          syncInterval = setInterval(sync, 1000) as unknown as number;
      }

      boot();

      return () => {
          isRunning = false;
          if (syncInterval) clearInterval(syncInterval);
      };
  });
</script>

<svelte:head>
  <title>Argus · Command Center</title>
</svelte:head>

<div class="app-layout">
  <TopBar />
  <div class="main-content">
      <NetworkGraph />
      <NodeSidebar />
  </div>
</div>
