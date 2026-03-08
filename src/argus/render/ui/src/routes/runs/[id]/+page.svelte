<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { page } from '$app/stores';
  import { fetchRunEvents, fetchRunStatus, fetchState } from '$lib/api';
  import { uiState } from '$lib/stores.svelte';

  import EventTape from '$lib/components/EventTape.svelte';
  import NetworkGraph from '$lib/components/NetworkGraph.svelte';
  import NodeSidebar from '$lib/components/NodeSidebar.svelte';

  let liveInterval: number | undefined;
  let isMounted = true;
  let tickCount = 0;
  
  let currentRunId = $derived($page.params.id);

  $effect(() => {
      if (currentRunId && currentRunId !== untrack(() => uiState.activeRunId)) {
          uiState.activeRunId = currentRunId;
          uiState.selectedNodeId = null;
          uiState.searchState = null;
          uiState.runStatus = null;
          uiState.runEvents = [];
          tickCount = 0;
          void syncState();
          void syncLiveData();
      }
  });

  async function syncState() {
      if (!isMounted || !uiState.activeRunId) return;
      const state = await fetchState(uiState.activeRunId);
      if (state) {
          uiState.searchState = state;
      }
  }

  async function syncLiveData() {
      if (!isMounted || !uiState.activeRunId) return;

      const [status, events] = await Promise.all([
          fetchRunStatus(uiState.activeRunId),
          fetchRunEvents(uiState.activeRunId, 120),
      ]);

      if (status) {
          uiState.runStatus = status;
      }
      uiState.runEvents = events;

      tickCount += 1;
      const shouldReconcile =
          !uiState.searchState ||
          (status?.status === 'running' && tickCount % 5 === 0) ||
          (!!status && uiState.searchState?.manifest?.status !== status.status);

      if (shouldReconcile) {
          await syncState();
      }
  }

  onMount(() => {
      void syncState();
      void syncLiveData();
      liveInterval = window.setInterval(() => {
          void syncLiveData();
      }, 1000);

      return () => {
          isMounted = false;
          if (liveInterval) {
              window.clearInterval(liveInterval);
          }
      };
  });
</script>

<svelte:head>
  <title>Argus · Observer Graph</title>
</svelte:head>

<div class="run-shell">
  <div class="main-content">
      <div class="graph-stage">
          <NetworkGraph />
      </div>
      <NodeSidebar />
  </div>
  <EventTape />
</div>

<style>
  .run-shell {
      display: flex;
      flex: 1;
      min-height: 0;
      flex-direction: column;
  }

  .main-content {
      display: flex;
      flex: 1;
      min-height: 0;
  }

  .graph-stage {
      position: relative;
      flex: 1;
      min-width: 0;
      min-height: 0;
  }
</style>
