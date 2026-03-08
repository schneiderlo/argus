<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { fetchState } from '$lib/api';
  import { renderRichMarkdown } from '$lib/markdown';
  import { uiState } from '$lib/stores.svelte';

  let currentRunId = $derived($page.params.id);
  let isLoading = $state(true);

  const statusLabel = () => {
      const status = uiState.searchState?.manifest?.status;
      if (status === 'completed') return 'Completed';
      if (status === 'failed') return 'Failed';
      return 'In Progress';
  };

  const statusClass = () => {
      const status = uiState.searchState?.manifest?.status;
      if (status === 'completed') return 'success';
      if (status === 'failed') return 'failed';
      return 'running';
  };

  const isFinished = () => uiState.searchState?.manifest?.status === 'completed';

  const getNode = (nodeId: string | null | undefined) => {
      if (!nodeId || !uiState.searchState?.nodes) return null;
      return uiState.searchState.nodes[nodeId] ?? null;
  };

  const finalRecommendation = () => uiState.searchState?.final_recommendation ?? null;

  const winner = () => {
      const recommendation = finalRecommendation();
      return getNode(recommendation?.best_bet_node_id ?? uiState.searchState?.winner_ids?.[0]);
  };

  const conservativeOption = () => getNode(finalRecommendation()?.conservative_node_id);
  const highUpsideOption = () => getNode(finalRecommendation()?.high_upside_node_id);

  const rejectedButInsightful = () =>
      (finalRecommendation()?.rejected_but_insightful_ids ?? [])
          .map((nodeId: string) => getNode(nodeId))
          .filter(Boolean);

  const recommendationSummary = () =>
      uiState.searchState?.summary_markdown ??
      finalRecommendation()?.summary_markdown ??
      null;

  const summaryHtml = () => {
      const summary = recommendationSummary();
      return summary ? renderRichMarkdown(summary) : null;
  };

  const detailList = (values: string[] | undefined | null) =>
      Array.isArray(values) ? values.filter((value) => typeof value === 'string' && value.trim()) : [];

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
              <span class="status-badge {statusClass()}" style="margin-left: 12px;">{statusLabel()}</span>
          </p>
      </header>

      {#if isLoading}
          <div class="loading-state">Loading run data...</div>
      {:else if !isFinished()}
          <div class="empty-state">
              <div class="empty-icon">⏳</div>
              <h2>Search In Progress</h2>
              <p>The final recommendation will be available once the Argus search loop concludes.</p>
              <a href="/runs/{currentRunId}" class="action-button mt-4" style="text-decoration: none; display: inline-block;">Return to Observer Graph</a>
          </div>
      {:else if !winner()}
          <div class="empty-state">
              <div class="empty-icon">⚠️</div>
              <h2>No Winner Selected</h2>
              <p>The search loop concluded without designating a winning candidate.</p>
          </div>
      {:else}
          {@const recommendation = finalRecommendation()}
          {@const winnerNode = winner()}
          {@const conservativeNode = conservativeOption()}
          {@const highUpsideNode = highUpsideOption()}
          {@const rejectedNodes = rejectedButInsightful()}
          <div class="report-card winner-card">
              <div class="card-header">
                  <div class="winner-trophy">🏆</div>
                  <div>
                      <h2 style="margin: 0; font-size: 24px;">Best Bet</h2>
                      <div class="node-id" style="margin-top: 4px;">Node: {winnerNode.node_id}</div>
                  </div>
              </div>

              <div class="section-label">Thesis</div>
              <p class="thesis-text">{winnerNode.candidate.thesis}</p>
              
              <div class="section-label">Mechanism</div>
              <div class="mechanism-text">{winnerNode.candidate.mechanism}</div>
              
              <div class="divider"></div>
              
              <div class="section-label">Evaluation Matrix</div>
              <div class="score-matrix">
                  <div class="score-cell">
                      <span class="score-cell-label">Total Score</span>
                      <span class="score-cell-value" style="color: #34d399;">{winnerNode.score?.total_score?.toFixed(2) || 'N/A'}</span>
                  </div>
                  <div class="score-cell">
                      <span class="score-cell-label">Confidence</span>
                      <span class="score-cell-value">{((winnerNode.score?.confidence_estimate || 0) * 100).toFixed(0)}%</span>
                  </div>
                  <div class="score-cell">
                      <span class="score-cell-label">Usefulness</span>
                      <span class="score-cell-value">{winnerNode.score?.usefulness?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div class="score-cell">
                      <span class="score-cell-label">Distinctiveness</span>
                      <span class="score-cell-value">{winnerNode.score?.distinctiveness?.toFixed(2) || '0.00'}</span>
                  </div>
              </div>

              {#if winnerNode.critique?.summary}
                  <div class="section-label">Evaluation Summary</div>
                  <div class="critique-text">{winnerNode.critique.summary}</div>
              {/if}
          </div>

          {#if recommendationSummary()}
              <div class="report-card summary-card">
                  <div class="summary-header">
                      <div>
                          <div class="section-label">Recommendation Summary</div>
                          <h2>Decision Memo</h2>
                      </div>
                      <div class="summary-kicker">Structured markdown rendered from persisted artifacts</div>
                  </div>
                  <div class="summary-markdown">{@html summaryHtml()}</div>
              </div>
          {/if}

          {#if conservativeNode || highUpsideNode || rejectedNodes.length > 0}
              <div class="option-grid">
                  {#if conservativeNode}
                      <div class="report-card option-card">
                          <div class="section-label">Conservative Option</div>
                          <div class="node-id">{conservativeNode.node_id}</div>
                          <p class="option-thesis">{conservativeNode.candidate.thesis}</p>
                      </div>
                  {/if}
                  {#if highUpsideNode}
                      <div class="report-card option-card">
                          <div class="section-label">High Upside Option</div>
                          <div class="node-id">{highUpsideNode.node_id}</div>
                          <p class="option-thesis">{highUpsideNode.candidate.thesis}</p>
                      </div>
                  {/if}
                  {#if rejectedNodes.length > 0}
                      <div class="report-card option-card">
                          <div class="section-label">Rejected But Insightful</div>
                          <div class="rejected-list">
                              {#each rejectedNodes as node}
                                  <div class="rejected-item">
                                      <div class="node-id">{node.node_id}</div>
                                      <p class="option-thesis">{node.candidate.thesis}</p>
                                  </div>
                              {/each}
                          </div>
                      </div>
                  {/if}
              </div>
          {/if}

          {#if recommendation}
              <div class="option-grid details-grid">
                  {#if detailList(recommendation.assumptions).length > 0}
                      <div class="report-card detail-card">
                          <div class="section-label">Assumptions</div>
                          <ul class="detail-list">
                              {#each detailList(recommendation.assumptions) as item}
                                  <li>{item}</li>
                              {/each}
                          </ul>
                      </div>
                  {/if}
                  {#if detailList(recommendation.failure_modes).length > 0}
                      <div class="report-card detail-card">
                          <div class="section-label">Failure Modes</div>
                          <ul class="detail-list">
                              {#each detailList(recommendation.failure_modes) as item}
                                  <li>{item}</li>
                              {/each}
                          </ul>
                      </div>
                  {/if}
                  {#if detailList(recommendation.reversal_conditions).length > 0}
                      <div class="report-card detail-card">
                          <div class="section-label">Reversal Conditions</div>
                          <ul class="detail-list">
                              {#each detailList(recommendation.reversal_conditions) as item}
                                  <li>{item}</li>
                              {/each}
                          </ul>
                      </div>
                  {/if}
                  {#if detailList(recommendation.next_experiments).length > 0}
                      <div class="report-card detail-card">
                          <div class="section-label">Next Experiments</div>
                          <ul class="detail-list">
                              {#each detailList(recommendation.next_experiments) as item}
                                  <li>{item}</li>
                              {/each}
                          </ul>
                      </div>
                  {/if}
              </div>
          {/if}
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

  .status-badge.failed {
      background: rgba(239, 68, 68, 0.15);
      color: #f87171;
      border: 1px solid #dc2626;
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

  .summary-card,
  .option-card,
  .detail-card {
      margin-top: 24px;
      padding: 28px;
  }

  .summary-card {
      position: relative;
      overflow: hidden;
      background:
          radial-gradient(circle at top right, rgba(96, 165, 250, 0.14), transparent 32%),
          linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0)),
          var(--surface-color);
  }

  .summary-card::before {
      content: '';
      position: absolute;
      inset: 0 auto 0 0;
      width: 4px;
      background: linear-gradient(180deg, #60a5fa, #34d399 55%, transparent);
      opacity: 0.9;
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

  .summary-markdown {
      font-size: 16px;
      line-height: 1.8;
      color: var(--ink-primary);
      max-width: 72ch;
  }

  .summary-header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 24px;
      margin-bottom: 24px;
      padding-bottom: 18px;
      border-bottom: 1px solid var(--border-subtle);
  }

  .summary-header h2 {
      margin: 0;
      font-size: clamp(28px, 4vw, 40px);
      line-height: 1;
      letter-spacing: -0.03em;
      color: var(--ink-primary);
  }

  .summary-kicker {
      max-width: 24ch;
      text-align: right;
      font-size: 11px;
      line-height: 1.5;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--ink-tertiary);
      font-family: var(--font-mono);
  }

  @media (max-width: 720px) {
      .summary-header {
          align-items: flex-start;
          flex-direction: column;
      }

      .summary-kicker {
          max-width: none;
          text-align: left;
      }
  }

  .summary-markdown :global(h1),
  .summary-markdown :global(h2),
  .summary-markdown :global(h3),
  .summary-markdown :global(h4) {
      margin: 1.75em 0 0.7em;
      line-height: 1.12;
      letter-spacing: -0.03em;
      color: var(--ink-primary);
  }

  .summary-markdown :global(h1) {
      font-size: clamp(32px, 4vw, 46px);
  }

  .summary-markdown :global(h2) {
      font-size: clamp(24px, 3vw, 30px);
      padding-top: 0.4em;
      border-top: 1px solid var(--border-subtle);
  }

  .summary-markdown :global(h3) {
      font-size: 19px;
  }

  .summary-markdown :global(p) {
      margin: 0 0 1.1em;
      color: var(--ink-secondary);
      text-wrap: pretty;
  }

  .summary-markdown :global(strong) {
      color: var(--ink-primary);
      font-weight: 700;
  }

  .summary-markdown :global(em) {
      color: var(--ink-primary);
      font-style: italic;
  }

  .summary-markdown :global(ul),
  .summary-markdown :global(ol) {
      margin: 0 0 1.4em;
      padding-left: 1.4rem;
      color: var(--ink-secondary);
  }

  .summary-markdown :global(li) {
      margin: 0.45em 0;
      padding-left: 0.2rem;
  }

  .summary-markdown :global(li::marker) {
      color: #60a5fa;
  }

  .summary-markdown :global(blockquote) {
      margin: 1.6em 0;
      padding: 1rem 1.1rem 1rem 1.25rem;
      border-left: 3px solid rgba(96, 165, 250, 0.7);
      background: rgba(96, 165, 250, 0.08);
      border-radius: 0 14px 14px 0;
  }

  .summary-markdown :global(blockquote p) {
      color: var(--ink-primary);
      margin-bottom: 0.7em;
  }

  .summary-markdown :global(blockquote p:last-child) {
      margin-bottom: 0;
  }

  .summary-markdown :global(code) {
      font-family: var(--font-mono);
      font-size: 0.92em;
      padding: 0.15em 0.42em;
      border-radius: 0.45rem;
      background: rgba(255, 255, 255, 0.06);
      color: #c4b5fd;
  }

  .summary-markdown :global(pre) {
      margin: 1.5em 0;
      padding: 1.1rem 1.2rem 1.2rem;
      border-radius: 16px;
      border: 1px solid var(--border-heavy);
      background: rgba(5, 10, 24, 0.82);
      overflow-x: auto;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
  }

  .summary-markdown :global(pre code) {
      display: block;
      padding: 0;
      background: transparent;
      color: #d4d4d8;
      line-height: 1.65;
  }

  .summary-markdown :global(.code-language) {
      margin-bottom: 0.9rem;
      font-family: var(--font-mono);
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #93c5fd;
  }

  .summary-markdown :global(a) {
      color: #7dd3fc;
      text-decoration: none;
      border-bottom: 1px solid rgba(125, 211, 252, 0.4);
  }

  .summary-markdown :global(a:hover) {
      border-bottom-color: rgba(125, 211, 252, 0.85);
  }

  .summary-markdown :global(hr) {
      border: 0;
      height: 1px;
      margin: 1.8em 0;
      background: linear-gradient(90deg, transparent, var(--border-heavy), transparent);
  }

  :global(.light-mode) .summary-card {
      background:
          radial-gradient(circle at top right, rgba(37, 99, 235, 0.1), transparent 32%),
          linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(255, 255, 255, 0.86)),
          var(--surface-color);
  }

  :global(.light-mode) .summary-markdown :global(code) {
      background: rgba(0, 0, 0, 0.05);
      color: #6d28d9;
  }

  :global(.light-mode) .summary-markdown :global(pre) {
      background: #10131c;
  }

  :global(.light-mode) .summary-markdown :global(blockquote) {
      background: rgba(37, 99, 235, 0.06);
  }

  .option-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 24px;
      margin-top: 24px;
  }

  .details-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  @media (max-width: 900px) {
      .option-grid,
      .details-grid {
          grid-template-columns: 1fr;
      }
  }

  .option-thesis {
      margin: 12px 0 0;
      color: var(--ink-primary);
      line-height: 1.6;
  }

  .rejected-list {
      display: flex;
      flex-direction: column;
      gap: 16px;
  }

  .rejected-item + .rejected-item {
      padding-top: 16px;
      border-top: 1px solid var(--border-subtle);
  }

  .detail-list {
      margin: 0;
      padding-left: 20px;
      color: var(--ink-primary);
      line-height: 1.7;
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
