<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { page } from '$app/stores';
  import { fetchRunStatus, fetchState } from '$lib/api';
  import { uiState } from '$lib/stores.svelte';

  import NetworkGraph from '$lib/components/NetworkGraph.svelte';
  import NodeSidebar from '$lib/components/NodeSidebar.svelte';
  import ResearchBoard from '$lib/components/ResearchBoard.svelte';
  import { hasResearchBoardData } from '$lib/components/researchBoardModel.js';

  let liveInterval: number | undefined;
  let isMounted = true;
  let tickCount = 0;
  let viewMode = $state<'research' | 'graph'>('graph');
  let viewTouched = $state(false);
  
  let currentRunId = $derived($page.params.id);
  const hasResearchView = $derived(hasResearchBoardData(uiState.searchState));

  $effect(() => {
      if (currentRunId && currentRunId !== untrack(() => uiState.activeRunId)) {
          uiState.activeRunId = currentRunId;
          uiState.selectedNodeId = null;
          uiState.searchState = null;
          uiState.runStatus = null;
          tickCount = 0;
          viewMode = 'graph';
          viewTouched = false;
          void syncState();
          void syncLiveData();
      }
  });

  $effect(() => {
      if (!hasResearchView) {
          viewMode = 'graph';
          return;
      }
      if (!viewTouched) {
          viewMode = 'research';
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

      const status = await fetchRunStatus(uiState.activeRunId);

      if (status) {
          uiState.runStatus = status;
      }

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

  function setViewMode(nextView: 'research' | 'graph') {
      viewTouched = true;
      viewMode = nextView;
  }
</script>

<svelte:head>
  <title>Argus · Observer Graph</title>
</svelte:head>

<div class="run-shell">
  {#if hasResearchView}
      <div class="view-toolbar">
          <button
              type="button"
              class:view-active={viewMode === 'research'}
              onclick={() => setViewMode('research')}
          >
              Concept Board
          </button>
          <button
              type="button"
              class:view-active={viewMode === 'graph'}
              onclick={() => setViewMode('graph')}
          >
              Execution Graph
          </button>
      </div>
  {/if}
  <div class="main-content">
      <div class="graph-stage">
          {#if hasResearchView && viewMode === 'research'}
              <ResearchBoard state={uiState.searchState} />
          {:else}
              <NetworkGraph />
          {/if}
      </div>
      <NodeSidebar />
  </div>
</div>

<style>
  .run-shell {
      display: flex;
      flex: 1;
      min-height: 0;
      height: calc(100vh - 60px);
      flex-direction: column;
      overflow: hidden;
  }

  .main-content {
      display: flex;
      flex: 1;
      min-height: 0;
      overflow: hidden;
  }

  .view-toolbar {
      display: flex;
      gap: 10px;
      padding: 18px 22px 0;
  }

  .view-toolbar button {
      border-radius: 999px;
      border: 1px solid var(--border-heavy);
      background: var(--surface-color);
      color: var(--ink-secondary);
      padding: 10px 14px;
      font-family: var(--font-mono);
      font-size: 0.76rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      cursor: pointer;
  }

  .view-toolbar button.view-active {
      color: var(--ink-primary);
      border-color: var(--color-admitted-border);
      box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-admitted-border) 35%, transparent);
  }

  .graph-stage {
      position: relative;
      flex: 1;
      min-width: 0;
      min-height: 320px;
  }
</style>
