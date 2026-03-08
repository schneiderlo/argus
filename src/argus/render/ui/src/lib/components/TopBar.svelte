<script lang="ts">
  import { page } from '$app/stores';
  import { uiState, toggleTheme, getStyle } from '$lib/stores.svelte';

  let now = $state(Date.now());

  const isRunning = $derived((uiState.runStatus?.status ?? uiState.searchState?.manifest?.status) === 'running');
  const statusTheme = $derived(isRunning ? getStyle('pending') : getStyle('archived'));
  const budgetSpent = $derived(uiState.runStatus?.budget_spent ?? uiState.searchState?.budget_spent ?? 0);
  const budgetTotal = $derived(uiState.runStatus?.budget ?? uiState.searchState?.manifest?.budget ?? 1);
  const budgetPercentage = $derived(Math.min(100, (budgetSpent / budgetTotal) * 100));
  const stepCount = $derived(uiState.runStatus?.step_count ?? uiState.searchState?.step_count ?? 0);
  const currentAction = $derived(uiState.runStatus?.current_action ?? null);
  const activeInvocations = $derived(uiState.runStatus?.active_provider_invocation_count ?? 0);
  const archiveCount = $derived(uiState.runStatus?.archive_count ?? uiState.searchState?.archive_ids?.length ?? 0);
  const frontierCount = $derived(uiState.runStatus?.frontier_count ?? uiState.searchState?.frontier_ids?.length ?? 0);
  const winnerCount = $derived(uiState.runStatus?.winner_count ?? uiState.searchState?.winner_ids?.length ?? 0);
  const elapsed = $derived.by(() => {
      const createdAt = uiState.runStatus?.created_at ?? uiState.searchState?.manifest?.created_at;
      if (!createdAt) return null;
      const start = new Date(createdAt).getTime();
      if (Number.isNaN(start)) return null;
      const endSource = isRunning ? now : new Date(uiState.runStatus?.updated_at ?? uiState.searchState?.manifest?.updated_at ?? createdAt).getTime();
      const totalSeconds = Math.max(0, Math.floor((endSource - start) / 1000));
      const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
      const seconds = String(totalSeconds % 60).padStart(2, '0');
      return `${minutes}:${seconds}`;
  });

  // Derived routing helpers
  const currentPath = $derived($page.url.pathname);
  const isDashboard = $derived(currentPath === '/');
  const isMemory = $derived(currentPath === '/memory');
  const isRunGraph = $derived(currentPath.startsWith('/runs/') && !currentPath.includes('/report'));
  const isRunReport = $derived(currentPath.startsWith('/runs/') && currentPath.includes('/report'));
  const activeRunParam = $derived($page.params.id);

  $effect(() => {
      if (!isRunning) return;
      now = Date.now();
      const interval = window.setInterval(() => {
          now = Date.now();
      }, 1000);
      return () => window.clearInterval(interval);
  });
</script>

<div id="top-bar">
  <div class="logo-area">
      <a href="/" class="system-title" class:active={isDashboard}>
          ARGUS COMMAND CENTER
      </a>
      
      <div class="nav-links">
          <a href="/" class="nav-link" class:active={isDashboard}>Dashboard</a>
          <a href="/memory" class="nav-link" class:active={isMemory}>Memory Ledger</a>
      </div>
  </div>
  
  <div id="run-context-controls">
      {#if activeRunParam}
          <div class="run-tabs">
              <a href="/runs/{activeRunParam}" class="run-tab" class:active={isRunGraph}>Observer Graph</a>
              <a href="/runs/{activeRunParam}/report" class="run-tab" class:active={isRunReport}>Final Report</a>
          </div>
      {/if}

      {#if uiState.searchState && (isRunGraph || isRunReport)}
          <div class="run-status">
              <span class="status-badge" style="color: {statusTheme.border}; box-shadow: 0 0 10px {statusTheme.border}40;">
                  {(uiState.runStatus?.status ?? uiState.searchState.manifest.status).toUpperCase()}
              </span>

              <div class="metric-container">
                  <div class="metric-header">
                      <span class="metric-label">Search Budget</span>
                      <span class="metric-value">{budgetSpent} / {budgetTotal}</span>
                  </div>
                  <div class="budget-track">
                      <div class="budget-fill" style="width: {budgetPercentage}%;"></div>
                  </div>
              </div>

              <div class="metric-container compact">
                  <span class="metric-label">Steps</span>
                  <span class="metric-value">{stepCount}</span>
              </div>

              <div class="metric-container compact wide">
                  <span class="metric-label">Current</span>
                  <span class="metric-value action-value">{currentAction ?? 'Idle'}</span>
              </div>

              <div class="metric-container compact">
                  <span class="metric-label">Active</span>
                  <span class="metric-value">{activeInvocations}</span>
              </div>

              <div class="metric-container compact">
                  <span class="metric-label">Elapsed</span>
                  <span class="metric-value">{elapsed ?? '--:--'}</span>
              </div>

              <div class="metric-container compact counts">
                  <span class="metric-label">A/F/W</span>
                  <span class="metric-value">{archiveCount}/{frontierCount}/{winnerCount}</span>
              </div>
          </div>
      {/if}
  </div>

  <div class="utility-controls">
      <button class="action-button theme-toggle" onclick={toggleTheme}>
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
      justify-content: space-between;
      padding: 0 24px;
      z-index: 100;
  }

  .logo-area {
      display: flex;
      align-items: center;
      gap: 32px;
  }

  .system-title {
      font-weight: 700;
      font-size: 16px;
      letter-spacing: 0.15em;
      color: var(--ink-primary);
      text-decoration: none;
      transition: color 0.2s;
  }

  .system-title:hover {
      color: #60a5fa;
  }

  .nav-links {
      display: flex;
      gap: 20px;
  }

  .nav-link {
      font-size: 13px;
      font-weight: 500;
      color: var(--ink-secondary);
      text-decoration: none;
      padding: 6px 12px;
      border-radius: 6px;
      transition: all 0.2s;
  }

  .nav-link:hover {
      color: var(--ink-primary);
      background: rgba(255, 255, 255, 0.05);
  }

  :global(.light-mode) .nav-link:hover {
      background: rgba(0, 0, 0, 0.05);
  }

  .nav-link.active {
      color: #60a5fa;
      background: rgba(59, 130, 246, 0.1);
  }

  #run-context-controls {
      display: flex;
      align-items: center;
      gap: 32px;
      flex: 1;
      justify-content: center;
  }

  .run-tabs {
      display: flex;
      background: rgba(0, 0, 0, 0.2);
      border-radius: 8px;
      padding: 4px;
      border: 1px solid var(--border-subtle);
  }

  :global(.light-mode) .run-tabs {
      background: rgba(0, 0, 0, 0.05);
  }

  .run-tab {
      font-size: 13px;
      font-weight: 500;
      color: var(--ink-secondary);
      text-decoration: none;
      padding: 6px 16px;
      border-radius: 6px;
      transition: all 0.2s;
  }

  .run-tab:hover {
      color: var(--ink-primary);
  }

  .run-tab.active {
      color: var(--ink-primary);
      background: var(--surface-color);
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  }

  .run-status {
      display: flex;
      align-items: center;
      gap: 24px;
      padding-left: 24px;
      border-left: 1px solid var(--border-subtle);
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

  .metric-container {
      display: flex;
      flex-direction: column;
      width: 160px;
  }

  .metric-container.compact {
      width: auto;
      flex-direction: row;
      align-items: baseline;
      gap: 8px;
  }

  .metric-container.compact.wide {
      min-width: 180px;
  }

  .metric-container.compact.counts {
      min-width: 86px;
  }

  .metric-header {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
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

  .action-value {
      max-width: 180px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
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
  
  .utility-controls {
      display: flex;
      align-items: center;
  }

  .action-button {
      background: var(--ink-primary);
      color: var(--bg-base);
      border: none;
      border-radius: 6px;
      font-family: var(--font-ui);
      font-weight: 600;
      cursor: pointer;
      transition: opacity 0.2s;
  }

  .action-button.theme-toggle {
      padding: 6px 12px;
      font-size: 12px;
      background: transparent;
      color: var(--ink-primary);
      border: 1px solid var(--border-heavy);
  }

  .action-button:hover {
      opacity: 0.8;
  }
</style>
