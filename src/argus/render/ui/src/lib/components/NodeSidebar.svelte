<script lang="ts">
  import { uiState, getStyle } from '$lib/stores.svelte';
  import { pruneNode } from '$lib/api';

  const selectedNode = $derived(uiState.selectedNodeId && uiState.searchState?.nodes ? uiState.searchState.nodes[uiState.selectedNodeId] : null);
  const nodeStyle = $derived(selectedNode ? getStyle(selectedNode.lifecycle_status) : null);

  async function handlePrune() {
      if (!selectedNode || !uiState.searchState?.manifest?.run_id) return;
      const success = await pruneNode(uiState.searchState.manifest.run_id, selectedNode.node_id);
      if (success && uiState.searchState && uiState.searchState.nodes && uiState.searchState.nodes[selectedNode.node_id]) {
          uiState.searchState.nodes[selectedNode.node_id].lifecycle_status = 'pruned';
      }
  }

  const canPrune = $derived(selectedNode && !['pruned', 'rejected', 'failed'].includes(selectedNode.lifecycle_status));
  let isResizing = $state(false);
  let sidebarWidth = $state(450);

  function startResize(e: MouseEvent) {
      isResizing = true;
      e.preventDefault();
  }

  function doResize(e: MouseEvent) {
      if (!isResizing) return;
      let newWidth = window.innerWidth - e.clientX;
      if (newWidth < 300) newWidth = 300;
      if (newWidth > window.innerWidth - 300) newWidth = window.innerWidth - 300;
      sidebarWidth = newWidth;
  }

  function stopResize() {
      isResizing = false;
  }
</script>

<svelte:window onmousemove={doResize} onmouseup={stopResize} />
<svelte:body class:resizing={isResizing} />

<div id="sidebar-wrapper" class:resizing={isResizing}>
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div id="resizer" class:active={isResizing} onmousedown={startResize}></div>
  <div id="sidebar" style="width: {sidebarWidth}px;">
      <div class="sidebar-content" id="node-panel">
          {#if !selectedNode}
              <div class="empty-state">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="12" cy="12" r="10"></circle>
                      <line x1="12" y1="16" x2="12" y2="12"></line>
                      <line x1="12" y1="8" x2="12.01" y2="8"></line>
                  </svg>
                  Awaiting node selection
              </div>
          {:else}
              <div class="node-header">
                  <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                      <h2 class="node-action">{selectedNode.action_type.replace('_', ' ')}</h2>
                      {#if nodeStyle}
                          <span class="status-badge" style="color: {nodeStyle.border}; box-shadow: 0 0 10px {nodeStyle.border}40;">
                              {selectedNode.lifecycle_status}
                          </span>
                      {/if}
                  </div>
                  <div class="node-id">{selectedNode.node_id}</div>
                  <div class="provider-tag">{selectedNode.provider_name}</div>
              </div>

              {#if selectedNode.termination_reason}
                  <div class="section-label" style="color: {nodeStyle?.text};">Decision Reason</div>
                  <div class="decision-card">{selectedNode.termination_reason}</div>
              {/if}

              {#if selectedNode.candidate}
                  <div class="section-label">Candidate Concept</div>
                  <div class="data-card">
                      <p class="thesis-text">{selectedNode.candidate.thesis}</p>
                      <div class="mechanism-text">{selectedNode.candidate.mechanism}</div>
                  </div>
              {/if}

              {#if selectedNode.score}
                  <div class="section-label">Evaluation Matrix</div>
                  <div class="score-matrix">
                      <div class="score-cell">
                          <span class="score-cell-label">Total Score</span>
                          <span class="score-cell-value" style="text-shadow: 0 0 15px rgba(255,255,255,0.3);">{selectedNode.score.total_score?.toFixed(2) || 'N/A'}</span>
                      </div>
                      <div class="score-cell">
                          <span class="score-cell-label">Confidence</span>
                          <span class="score-cell-value">{((selectedNode.score.confidence_estimate || 0) * 100).toFixed(0)}%</span>
                      </div>
                      <div class="score-cell">
                          <span class="score-cell-label">Usefulness</span>
                          <span class="score-cell-value">{selectedNode.score.usefulness?.toFixed(2) || '0.00'}</span>
                      </div>
                      <div class="score-cell">
                          <span class="score-cell-label">Distinctiveness</span>
                          <span class="score-cell-value">{selectedNode.score.distinctiveness?.toFixed(2) || '0.00'}</span>
                      </div>
                  </div>

                  {#if !selectedNode.score.hard_constraint_pass && selectedNode.score.hard_constraint_reasons?.length > 0}
                      <div class="section-label" style="color: #f87171; margin-top: 24px;">Hard Constraints Failed</div>
                      <div class="critique-card">
                          <ul style="margin: 0; padding-left: 20px;">
                              {#each selectedNode.score.hard_constraint_reasons as reason}
                                  <li>{reason}</li>
                              {/each}
                          </ul>
                      </div>
                  {/if}
              {/if}

              {#if selectedNode.critique}
                  <div class="section-label" style="color: #f87171; margin-top: 24px;">Critique</div>
                  <div class="critique-card">
                      {#if selectedNode.critique.summary}
                          <div><strong>Summary:</strong> {selectedNode.critique.summary}</div>
                      {/if}
                      {#if selectedNode.critique.kill_shots?.length > 0}
                          <div style="margin-top: 12px;"><strong>Kill Shots:</strong></div>
                          <ul style="margin: 4px 0 0 0; padding-left: 20px;">
                              {#each selectedNode.critique.kill_shots as ks}
                                  <li>{ks}</li>
                              {/each}
                          </ul>
                      {/if}
                      {#if selectedNode.critique.sharp_edges?.length > 0}
                          <div style="margin-top: 12px;"><strong>Sharp Edges:</strong></div>
                          <ul style="margin: 4px 0 0 0; padding-left: 20px;">
                              {#each selectedNode.critique.sharp_edges as edge}
                                  <li>{edge}</li>
                              {/each}
                          </ul>
                      {/if}
                      {#if selectedNode.critique.hidden_dependencies?.length > 0}
                          <div style="margin-top: 12px;"><strong>Hidden Dependencies:</strong></div>
                          <ul style="margin: 4px 0 0 0; padding-left: 20px;">
                              {#each selectedNode.critique.hidden_dependencies as dep}
                                  <li>{dep}</li>
                              {/each}
                          </ul>
                      {/if}
                  </div>
              {/if}

              {#if canPrune}
                  <button class="action-button destructive" onclick={handlePrune}>Terminate Branch</button>
              {:else}
                  <button class="action-button" disabled>Branch Terminated</button>
              {/if}
          {/if}
      </div>
  </div>
</div>

<style>
  #sidebar-wrapper {
      position: relative;
      display: flex;
  }

  #sidebar {
      width: 450px;
      min-width: 300px;
      max-width: 800px;
      background: var(--surface-color);
      backdrop-filter: var(--glass-blur);
      -webkit-backdrop-filter: var(--glass-blur);
      border-left: 1px solid var(--border-heavy);
      display: flex;
      flex-direction: column;
      z-index: 50;
  }

  #resizer {
      width: 6px;
      cursor: col-resize;
      background: transparent;
      transition: background 0.2s;
      z-index: 60;
      position: absolute;
      left: -3px;
      top: 0;
      bottom: 0;
  }

  #resizer:hover, #resizer.active {
      background: var(--border-heavy);
  }

  /* When resizing, prevent text selection globally */
  :global(body.resizing) {
      cursor: col-resize !important;
      user-select: none;
  }

  .sidebar-content {
      padding: 32px;
      overflow-y: auto;
      flex: 1;
  }

  /* Node Header */
  .node-header {
      margin-bottom: 32px;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--border-subtle);
  }

  .node-action {
      font-size: 24px;
      font-weight: 600;
      letter-spacing: 0.02em;
      text-transform: capitalize;
      color: var(--ink-primary);
  }

  .node-id {
      font-family: var(--font-mono);
      font-size: 13px;
      color: var(--ink-secondary);
      margin-top: 8px;
  }

  .provider-tag {
      display: inline-flex;
      align-items: center;
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 500;
      color: #a78bfa;
      background: rgba(139, 92, 246, 0.1);
      border: 1px solid rgba(139, 92, 246, 0.3);
      padding: 4px 10px;
      border-radius: 6px;
      margin-top: 12px;
      box-shadow: 0 0 10px rgba(139, 92, 246, 0.1);
      letter-spacing: 0.04em;
  }

  .provider-tag::before {
      content: '♦';
      margin-right: 6px;
      font-size: 10px;
  }

  /* Status Badges */
  .status-badge {
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.05em;
      padding: 4px 10px;
      border: 1px solid currentColor;
      border-radius: 4px;
      text-transform: uppercase;
  }

  /* Data Cards */
  .section-label {
      font-size: 12px;
      font-weight: 600;
      color: var(--ink-secondary);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      margin-bottom: 12px;
  }

  .data-card, .decision-card, .critique-card {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 32px;
  }
  
  :global(.light-mode) .data-card, 
  :global(.light-mode) .decision-card, 
  :global(.light-mode) .critique-card {
      background: rgba(0, 0, 0, 0.02);
  }

  .decision-card {
      border-color: currentColor;
      background: rgba(0, 0, 0, 0.2);
  }

  .thesis-text {
      font-size: 16px;
      font-weight: 500;
      line-height: 1.5;
      color: var(--ink-primary);
      margin-bottom: 16px;
  }

  .mechanism-text {
      font-size: 14px;
      line-height: 1.6;
      color: var(--ink-secondary);
  }

  /* Matrix Layout */
  .score-matrix {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 32px;
  }

  .score-cell {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 16px;
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
      margin-bottom: 4px;
  }

  .score-cell-value {
      font-family: var(--font-mono);
      font-size: 20px;
      font-weight: 600;
      color: var(--ink-primary);
  }

  /* Empty State */
  .empty-state {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100%;
      color: var(--ink-tertiary);
      font-family: var(--font-mono);
      font-size: 13px;
      text-align: center;
      letter-spacing: 0.05em;
      text-transform: uppercase;
  }

  .empty-state svg {
      width: 32px;
      height: 32px;
      margin-bottom: 24px;
      opacity: 0.4;
      filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.5));
  }

  /* Buttons */
  .action-button {
      background: var(--ink-primary);
      color: var(--bg-base);
      border: none;
      padding: 10px 16px;
      border-radius: 6px;
      font-family: var(--font-ui);
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
      width: 100%;
      margin-top: 16px;
      transition: opacity 0.2s;
  }

  .action-button:hover:not(:disabled) {
      opacity: 0.9;
  }

  .action-button:disabled {
      background: var(--border-heavy);
      color: var(--ink-secondary);
      cursor: not-allowed;
  }

  .action-button.destructive {
      background: transparent;
      color: #f87171;
      border: 1px solid #f87171;
  }

  .action-button.destructive:hover {
      background: rgba(248, 113, 113, 0.1);
  }
</style>
