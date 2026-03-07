<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { fetchState } from '$lib/api';
  import { uiState } from '$lib/stores.svelte';

  let currentRunId = $derived($page.params.id);
  let isLoading = $state(true);

  // Derive the winner from the state
  const isFinished = $derived(uiState.searchState?.manifest?.status === 'success' || uiState.searchState?.manifest?.status === 'completed');
  const winnerNode = $derived(() => {
    if (!uiState.searchState?.nodes || !uiState.searchState?.manifest?.winner_id) return null;
    return uiState.searchState.nodes[uiState.searchState.manifest.winner_id];
  });
  
  const winner = $derived(winnerNode());

  $effect(() => {
      if (currentRunId && currentRunId !== uiState.activeRunId) {
          uiState.activeRunId = currentRunId;
          loadData();
      }
  });

  async function loadData() {
      isLoading = true;
      if (uiState.activeRunId) {
          const state = await fetchState(uiState.activeRunId);
          if (state) {
              uiState.searchState = state;
          }
      }
      isLoading = false;
  }

  onMount(() => {
      if (!uiState.searchState && currentRunId) {
          loadData();
      } else {
          isLoading = false;
      }
  });
</script>

<svelte:head>
  <title>Argus · Final Report</title>
</svelte:head>

<div class="report-container">
  <div class="content-wrapper">
      <header class="page-header">
          <h1>Final Recommendation Report</h1>
          <p>
              Run: <span class="run-id">{currentRunId}</span>
              {#if isFinished}
                  <span class="status-badge success" style="margin-left: 12px;">Completed</span>
              {:else}
                  <span class="status-badge running" style="margin-left: 12px;">In Progress</span>
              {/if}
          </p>
      </header>

      {#if isLoading}
          <div class="loading-state">Loading run data...</div>
      {:else if !isFinished}
          <div class="empty-state">
              <div class="empty-icon">⏳</div>
              <h2>Search In Progress</h2>
              <p>The final recommendation will be available once the Argus search loop concludes.</p>
              <a href="/runs/{currentRunId}" class="action-button mt-4" style="text-decoration: none; display: inline-block;">Return to Observer Graph</a>
          </div>
      {:else if !winner}
          <div class="empty-state">
              <div class="empty-icon">⚠️</div>
              <h2>No Winner Selected</h2>
              <p>The search loop concluded without designating a winning candidate.</p>
          </div>
      {:else}
          <div class="report-card winner-card">
              <div class="card-header">
                  <div class="winner-trophy">🏆</div>
                  <div>
                      <h2 style="margin: 0; font-size: 24px;">Winning Candidate</h2>
                      <div class="node-id" style="margin-top: 4px;">Node: {winner.node_id}</div>
                  </div>
              </div>

              <div class="section-label">Thesis</div>
              <p class="thesis-text">{winner.candidate.thesis}</p>
              
              <div class="section-label">Mechanism</div>
              <div class="mechanism-text">{winner.candidate.mechanism}</div>
              
              <div class="divider"></div>
              
              <div class="section-label">Evaluation Matrix</div>
              <div class="score-matrix">
                  <div class="score-cell">
                      <span class="score-cell-label">Total Score</span>
                      <span class="score-cell-value" style="color: #34d399;">{winner.score.total_score?.toFixed(2) || 'N/A'}</span>
                  </div>
                  <div class="score-cell">
                      <span class="score-cell-label">Confidence</span>
                      <span class="score-cell-value">{((winner.score.confidence_estimate || 0) * 100).toFixed(0)}%</span>
                  </div>
                  <div class="score-cell">
                      <span class="score-cell-label">Usefulness</span>
                      <span class="score-cell-value">{winner.score.usefulness?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div class="score-cell">
                      <span class="score-cell-label">Distinctiveness</span>
                      <span class="score-cell-value">{winner.score.distinctiveness?.toFixed(2) || '0.00'}</span>
                  </div>
              </div>

              {#if winner.critique?.summary}
                  <div class="section-label">Evaluation Summary</div>
                  <div class="critique-text">{winner.critique.summary}</div>
              {/if}
          </div>
      {/if}
  </div>
</div>

<style>
  .report-container {
      flex: 1;
      overflow-y: auto;
      padding: 40px;
      background: var(--bg-base);
  }

  .content-wrapper {
      max-width: 900px;
      margin: 0 auto;
  }

  .page-header {
      margin-bottom: 40px;
  }

  .page-header h1 {
      font-size: 32px;
      font-weight: 700;
      color: var(--ink-primary);
      margin-bottom: 8px;
  }

  .page-header p {
      color: var(--ink-secondary);
      font-size: 16px;
      display: flex;
      align-items: center;
  }

  .run-id {
      font-family: var(--font-mono);
      color: var(--ink-primary);
      margin-left: 8px;
  }

  .status-badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 4px;
      font-family: var(--font-mono);
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
  }

  .status-badge.running {
      background: rgba(234, 179, 8, 0.15);
      color: #facc15;
      border: 1px solid #ca8a04;
  }

  .status-badge.success {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid #059669;
  }
  
  .node-id {
      font-family: var(--font-mono);
      font-size: 13px;
      color: var(--ink-secondary);
  }

  .report-card {
      background: var(--surface-color);
      border: 1px solid var(--border-heavy);
      border-radius: 12px;
      padding: 40px;
      box-shadow: var(--shadow-glow);
  }
  
  .winner-card {
      border-color: rgba(16, 185, 129, 0.3);
      background: linear-gradient(180deg, rgba(16, 185, 129, 0.05) 0%, rgba(0,0,0,0) 200px), var(--surface-color);
  }

  .card-header {
      display: flex;
      align-items: center;
      gap: 20px;
      margin-bottom: 40px;
  }

  .winner-trophy {
      font-size: 48px;
      line-height: 1;
      filter: drop-shadow(0 4px 10px rgba(0,0,0,0.5));
  }

  .section-label {
      font-size: 12px;
      font-weight: 600;
      color: var(--ink-tertiary);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      margin-bottom: 12px;
  }

  .thesis-text {
      font-size: 20px;
      font-weight: 500;
      line-height: 1.5;
      color: var(--ink-primary);
      margin-bottom: 24px;
  }

  .mechanism-text {
      font-size: 16px;
      line-height: 1.6;
      color: var(--ink-secondary);
      margin-bottom: 32px;
      white-space: pre-wrap;
  }

  .critique-text {
      font-size: 15px;
      line-height: 1.6;
      color: var(--ink-primary);
      background: rgba(255, 255, 255, 0.03);
      padding: 20px;
      border-radius: 8px;
      border: 1px solid var(--border-subtle);
  }

  :global(.light-mode) .critique-text {
      background: rgba(0, 0, 0, 0.02);
  }

  .divider {
      height: 1px;
      background: var(--border-subtle);
      margin: 40px 0;
  }

  /* Matrix Layout */
  .score-matrix {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 32px;
  }

  @media (max-width: 768px) {
      .score-matrix {
          grid-template-columns: 1fr 1fr;
      }
  }

  .score-cell {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
  }
  
  :global(.light-mode) .score-cell {
      background: rgba(0, 0, 0, 0.02);
  }

  .score-cell-label {
      font-size: 11px;
      color: var(--ink-secondary);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 8px;
  }

  .score-cell-value {
      font-family: var(--font-mono);
      font-size: 28px;
      font-weight: 600;
      color: var(--ink-primary);
  }

  /* Empty State */
  .empty-state {
      padding: 80px 0;
      text-align: center;
      background: var(--surface-color);
      border: 1px dashed var(--border-heavy);
      border-radius: 12px;
  }

  .empty-icon {
      font-size: 48px;
      margin-bottom: 24px;
      opacity: 0.8;
  }

  .empty-state h2 {
      font-size: 20px;
      color: var(--ink-primary);
      margin-bottom: 8px;
  }

  .empty-state p {
      color: var(--ink-secondary);
  }

  .loading-state {
      padding: 80px;
      text-align: center;
      color: var(--ink-tertiary);
      font-family: var(--font-mono);
      text-transform: uppercase;
      letter-spacing: 0.1em;
  }
  
  .action-button {
      background: var(--ink-primary);
      color: var(--bg-base);
      border: none;
      padding: 10px 20px;
      border-radius: 6px;
      font-family: var(--font-ui);
      font-weight: 600;
      font-size: 14px;
      cursor: pointer;
      margin-top: 16px;
      transition: opacity 0.2s;
  }

  .action-button:hover {
      opacity: 0.9;
  }
</style>
