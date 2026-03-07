<script lang="ts">
  import { uiState, toggleTheme, getStyle } from '$lib/stores.svelte';

  const isRunning = $derived(uiState.searchState?.manifest?.status === 'running');
  const statusTheme = $derived(isRunning ? getStyle('pending') : getStyle('archived'));
  const budgetSpent = $derived(uiState.searchState?.budget_spent || 0);
  const budgetTotal = $derived(uiState.searchState?.manifest?.budget || 1);
  const budgetPercentage = $derived(Math.min(100, (budgetSpent / budgetTotal) * 100));
  const stepCount = $derived(uiState.searchState?.step_count || 0);
</script>

<div id="top-bar">
  <h1 class="system-title">ARGUS SEARCH RUNTIME</h1>
  
  <div id="run-status">
      {#if uiState.searchState}
          <span class="status-badge" style="color: {statusTheme.border}; box-shadow: 0 0 10px {statusTheme.border}40;">
              {uiState.searchState.manifest.status.toUpperCase()}
          </span>

          <div style="display: flex; flex-direction: column; width: 160px;">
              <div style="display: flex; justify-content: space-between; align-items: baseline;">
                  <span class="metric-label">Token Budget</span>
                  <span class="metric-value">{budgetSpent} / {budgetTotal}</span>
              </div>
              <div class="budget-track">
                  <div class="budget-fill" style="width: {budgetPercentage}%;"></div>
              </div>
          </div>

          <div style="display: flex; align-items: baseline; gap: 8px;">
              <span class="metric-label">Steps</span>
              <span class="metric-value">{stepCount}</span>
          </div>
      {/if}
  </div>

  <div style="margin-left: auto; display: flex; align-items: center;">
      <button class="action-button" onclick={toggleTheme} style="padding: 6px 12px; font-size: 12px; width: auto; background: transparent;">
          {uiState.isLightMode ? 'Dark Mode' : 'Light Mode'}
      </button>
  </div>
</div>

<style>
  #top-bar {
      height: 60px;
      backdrop-filter: var(--glass-blur);
      -webkit-backdrop-filter: var(--glass-blur);
      background: var(--surface-color);
      border-bottom: 1px solid var(--border-heavy);
      display: flex;
      align-items: center;
      padding: 0 24px;
      z-index: 100;
  }

  .system-title {
      font-weight: 700;
      font-size: 16px;
      letter-spacing: 0.15em;
      margin-right: 40px;
      color: var(--ink-primary);
  }

  #run-status {
      display: flex;
      align-items: center;
      gap: 32px;
  }

  /* Metrics & UI elements */
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

  .metric-label {
      font-size: 11px;
      color: var(--ink-secondary);
      text-transform: uppercase;
      letter-spacing: 0.05em;
  }

  .metric-value {
      font-family: var(--font-mono);
      font-size: 14px;
      font-weight: 500;
      color: var(--ink-primary);
  }

  .budget-track {
      height: 4px;
      background: var(--border-heavy);
      border-radius: 2px;
      margin-top: 6px;
      overflow: hidden;
  }

  .budget-fill {
      height: 100%;
      background: var(--ink-primary);
      transition: width 0.3s ease;
  }
  
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
</style>
