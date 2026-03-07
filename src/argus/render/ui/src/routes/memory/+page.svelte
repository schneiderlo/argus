<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchMemory } from '$lib/api';

  let memoryData: any = $state(null);
  let isLoading = $state(true);

  onMount(async () => {
      memoryData = await fetchMemory();
      isLoading = false;
  });

  const getProviderStats = (data: any) => {
      if (!data?.routing_stats?.stats) return [];
      return Object.entries(data.routing_stats.stats).map(([name, stat]: [string, any]) => {
          const totalAttempts = stat.trials || 0;
          const totalWins = stat.wins || 0;
          const winRate = totalAttempts > 0 ? (totalWins / totalAttempts) * 100 : 0;
          return { name, totalAttempts, totalWins, winRate };
      }).sort((a, b) => b.winRate - a.winRate);
  };

  const getLearningNotes = (data: any) => {
      if (!data?.learning_memory?.entries) return [];
      return data.learning_memory.entries; // assuming latest first if Python sorted it, else we sort here
  };
</script>

<svelte:head>
  <title>Argus · Memory Ledger</title>
</svelte:head>

<div class="ledger-container">
  <div class="content-wrapper">
      <header class="page-header">
          <h1>Learning Memory Ledger</h1>
          <p>Cross-run compressed knowledge and provider win-rate analytics.</p>
      </header>

      {#if isLoading}
          <div class="loading-state">Syncing neural indices...</div>
      {:else}
          <div class="split-layout">
              <!-- Left Column: Provider Stats -->
              <div class="column provider-stats-col">
                  <h2 class="section-title">
                      <span class="icon">⚡</span> Provider Telemetry
                  </h2>
                  <div class="card provider-card">
                      {#if getProviderStats(memoryData).length === 0}
                          <div class="empty-state text-sm">No provider history recorded.</div>
                      {:else}
                          <ul class="provider-list">
                              {#each getProviderStats(memoryData) as provider}
                                  <li class="provider-item">
                                      <div class="provider-header">
                                          <span class="provider-name">{provider.name}</span>
                                          <span class="provider-winrate">{provider.winRate.toFixed(1)}% Win Rate</span>
                                      </div>
                                      <div class="progress-track" title="{provider.totalWins} wins / {provider.totalAttempts} total">
                                          <div class="progress-fill" style="width: {provider.winRate}%;"></div>
                                      </div>
                                      <div class="provider-meta">
                                          <span>Trials: <span class="data-value">{provider.totalAttempts}</span></span>
                                          <span>Wins: <span class="data-value">{provider.totalWins}</span></span>
                                      </div>
                                  </li>
                              {/each}
                          </ul>
                      {/if}
                  </div>
              </div>

              <!-- Right Column: Learning Notes -->
              <div class="column learning-notes-col">
                  <h2 class="section-title">
                      <span class="icon">🧠</span> Compressed Patterns
                  </h2>
                  <div class="notes-feed">
                      {#if getLearningNotes(memoryData).length === 0}
                          <div class="card empty-state">The learning memory is currently empty.</div>
                      {:else}
                          {#each getLearningNotes(memoryData) as note}
                              <div class="card note-card">
                                  <div class="note-header">
                                      <span class="note-type">{note.note_type.replace('_', ' ')}</span>
                                      {#if note.discovery_run_id}
                                          <span class="note-source">From: {note.discovery_run_id}</span>
                                      {/if}
                                  </div>
                                  <p class="note-text">{note.text}</p>
                              </div>
                          {/each}
                      {/if}
                  </div>
              </div>
          </div>
      {/if}
  </div>
</div>

<style>
  .ledger-container {
      flex: 1;
      overflow-y: auto;
      padding: 40px;
  }

  .content-wrapper {
      max-width: 1400px;
      margin: 0 auto;
      padding-bottom: 80px;
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

  .split-layout {
      display: grid;
      grid-template-columns: 350px 1fr;
      gap: 32px;
      align-items: start;
  }

  @media (max-width: 900px) {
      .split-layout {
          grid-template-columns: 1fr;
      }
  }

  .section-title {
      font-size: 14px;
      font-weight: 600;
      color: var(--ink-tertiary);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
  }

  .card {
      background: var(--surface-color);
      border: 1px solid var(--border-heavy);
      border-radius: 12px;
      padding: 24px;
      box-shadow: var(--shadow-glow);
  }

  /* Provider Telemetry List */
  .provider-list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 24px;
  }

  .provider-item {
      display: flex;
      flex-direction: column;
      gap: 8px;
  }

  .provider-header {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
  }

  .provider-name {
      font-weight: 600;
      color: var(--ink-primary);
      font-size: 15px;
  }

  .provider-winrate {
      font-family: var(--font-mono);
      font-size: 13px;
      font-weight: 500;
      color: #34d399;
  }

  .progress-track {
      height: 6px;
      background: rgba(255, 255, 255, 0.05);
      border-radius: 3px;
      overflow: hidden;
  }

  :global(.light-mode) .progress-track {
      background: rgba(0, 0, 0, 0.05);
  }

  .progress-fill {
      height: 100%;
      background: #10b981;
      border-radius: 3px;
      transition: width 1s cubic-bezier(0.1, 0.7, 0.1, 1);
  }

  .provider-meta {
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      color: var(--ink-secondary);
      text-transform: uppercase;
      letter-spacing: 0.05em;
  }

  .data-value {
      font-family: var(--font-mono);
      color: var(--ink-primary);
      margin-left: 4px;
      font-weight: 500;
  }

  /* Learning Notes Feed */
  .notes-feed {
      display: flex;
      flex-direction: column;
      gap: 16px;
  }

  .note-card {
      background: rgba(139, 92, 246, 0.05);
      border-color: rgba(139, 92, 246, 0.2);
      transition: transform 0.2s, box-shadow 0.2s;
  }
  
  :global(.light-mode) .note-card {
      background: rgba(139, 92, 246, 0.02);
  }

  .note-card:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 30px rgba(0,0,0,0.1);
      border-color: rgba(139, 92, 246, 0.4);
  }

  .note-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
  }

  .note-type {
      display: inline-block;
      padding: 4px 10px;
      background: rgba(168, 85, 247, 0.15);
      color: #c084fc;
      border: 1px solid #9333ea;
      border-radius: 4px;
      font-family: var(--font-mono);
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
  }

  .note-source {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--ink-tertiary);
  }

  .note-text {
      font-size: 15px;
      line-height: 1.6;
      color: var(--ink-primary);
  }

  /* Empty States */
  .empty-state {
      text-align: center;
      color: var(--ink-secondary);
      padding: 40px 20px;
  }

  .text-sm {
      font-size: 13px;
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
