<script lang="ts">
  import { onMount } from 'svelte';
  import { listRuns } from '$lib/api';
  import { initTheme } from '$lib/stores.svelte';

  let runs: any[] = $state([]);
  let isLoading = $state(true);

  onMount(async () => {
      initTheme();
      runs = await listRuns();
      isLoading = false;
  });

  function formatDate(isoStr: string) {
      if (!isoStr) return 'Unknown';
      const d = new Date(isoStr);
      return Math.floor(Date.now() - d.getTime()) < 86400000 
          ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) 
          : d.toLocaleDateString();
  }
</script>

<svelte:head>
  <title>Argus · Dashboard</title>
</svelte:head>

<div class="dashboard-container">
  <div class="content-wrapper">
      <header class="page-header">
          <h1>Command Dashboard</h1>
          <p>Monitor and inspect active and historical Argus search loops.</p>
      </header>

      {#if isLoading}
          <div class="loading-state">Loading runs...</div>
      {:else if runs.length === 0}
          <div class="empty-state">
              <div class="empty-icon">⌘</div>
              <h2>No Runs Found</h2>
              <p>Execute an Argus search loop to see telemetry here.</p>
          </div>
      {:else}
          <div class="table-container">
              <table class="runs-table">
                  <thead>
                      <tr>
                          <th>Run ID</th>
                          <th>Status</th>
                          <th>Provider</th>
                          <th>Budget Used</th>
                          <th>Created</th>
                          <th>Updated</th>
                      </tr>
                  </thead>
                  <tbody>
                      {#each runs as run}
                          <tr>
                              <td>
                                  <a href="/runs/{run.run_id}" class="run-link">{run.run_id}</a>
                              </td>
                              <td>
                                  <span class="status-badge {run.status}">{run.status}</span>
                              </td>
                              <td class="provider-cell">{run.provider_name}</td>
                              <td class="budget-cell">
                                  {run.budget} 
                                  <span class="budget-unit">tokens</span>
                              </td>
                              <td class="date-cell">{formatDate(run.created_at)}</td>
                              <td class="date-cell">{formatDate(run.updated_at)}</td>
                          </tr>
                      {/each}
                  </tbody>
              </table>
          </div>
      {/if}
  </div>
</div>

<style>
  .dashboard-container {
      flex: 1;
      overflow-y: auto;
      padding: 40px;
  }

  .content-wrapper {
      max-width: 1200px;
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
  }

  /* Table Styles */
  .table-container {
      background: var(--surface-color);
      border: 1px solid var(--border-heavy);
      border-radius: 12px;
      overflow: hidden;
      box-shadow: var(--shadow-glow);
  }

  .runs-table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
  }

  .runs-table th {
      background: rgba(0, 0, 0, 0.2);
      padding: 16px 20px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--ink-tertiary);
      border-bottom: 1px solid var(--border-heavy);
  }

  :global(.light-mode) .runs-table th {
      background: rgba(0, 0, 0, 0.03);
  }

  .runs-table td {
      padding: 16px 20px;
      border-bottom: 1px solid var(--border-subtle);
      vertical-align: middle;
  }

  .runs-table tr:last-child td {
      border-bottom: none;
  }

  .runs-table tbody tr {
      transition: background 0.2s;
  }

  .runs-table tbody tr:hover {
      background: rgba(255, 255, 255, 0.02);
  }

  :global(.light-mode) .runs-table tbody tr:hover {
      background: rgba(0, 0, 0, 0.02);
  }

  .run-link {
      font-family: var(--font-mono);
      font-weight: 600;
      color: #60a5fa;
      text-decoration: none;
      transition: color 0.1s;
  }

  .run-link:hover {
      color: #93c5fd;
      text-decoration: underline;
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

  .status-badge.completed, .status-badge.success {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid #059669;
  }

  .provider-cell, .budget-cell, .date-cell {
      font-family: var(--font-mono);
      font-size: 13px;
      color: var(--ink-secondary);
  }

  .budget-cell {
      color: var(--ink-primary);
  }

  .budget-unit {
      color: var(--ink-tertiary);
      font-size: 11px;
      margin-left: 4px;
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
      color: var(--border-heavy);
      margin-bottom: 24px;
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
</style>
