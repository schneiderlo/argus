<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchMemory } from '$lib/api';
  import type { MemoryPayload, ReusableLearningNote, RoutingEntry } from '$lib/types';

  let memoryData: MemoryPayload | null = $state(null);
  let isLoading = $state(true);

  onMount(async () => {
      memoryData = await fetchMemory();
      isLoading = false;
  });

  const labelize = (value: string) => value.replaceAll('_', ' ');

  const formatRunIds = (runIds: string[] = []) => {
      if (runIds.length === 0) return null;
      const visible = runIds.slice(0, 2);
      const remainder = runIds.length - visible.length;
      return remainder > 0 ? `${visible.join(', ')} +${remainder} more` : visible.join(', ');
  };

  const formatDate = (value: string | undefined) => {
      if (!value) return null;
      return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value));
  };

  const getProviderStats = (data: MemoryPayload | null) => {
      const entries = data?.routing_stats?.entries ?? [];
      const providers = new Map<string, {
          name: string;
          actionCount: number;
          totalInvocations: number;
          winnerContributions: number;
          strongScores: number;
          providerFailures: number;
          totalReward: number;
          lastRunId: string | null;
      }>();

      for (const entry of entries) {
          const provider = providers.get(entry.provider_name) ?? {
              name: entry.provider_name,
              actionCount: 0,
              totalInvocations: 0,
              winnerContributions: 0,
              strongScores: 0,
              providerFailures: 0,
              totalReward: 0,
              lastRunId: null,
          };
          provider.actionCount += 1;
          provider.totalInvocations += entry.invocation_count ?? 0;
          provider.winnerContributions += entry.winner_contribution_count ?? 0;
          provider.strongScores += entry.strong_score_count ?? 0;
          provider.providerFailures += entry.provider_failure_count ?? 0;
          provider.totalReward += entry.total_reward ?? 0;
          provider.lastRunId = entry.last_run_id ?? provider.lastRunId;
          providers.set(entry.provider_name, provider);
      }

      return Array.from(providers.values())
          .map((provider) => ({
              ...provider,
              contributionRate:
                  provider.totalInvocations > 0
                      ? (provider.winnerContributions / provider.totalInvocations) * 100
                      : 0,
              averageReward:
                  provider.totalInvocations > 0
                      ? provider.totalReward / provider.totalInvocations
                      : 0,
          }))
          .sort(
              (a, b) =>
                  b.averageReward - a.averageReward ||
                  b.contributionRate - a.contributionRate ||
                  b.totalInvocations - a.totalInvocations
          );
  };

  const getLearningNotes = (data: MemoryPayload | null) => {
      if (!data?.learning_memory?.entries) return [];
      return data.learning_memory.entries;
  };
</script>

<svelte:head>
  <title>Argus · Memory Ledger</title>
</svelte:head>

<div class="ledger-container">
  <div class="content-wrapper">
      <header class="page-header">
          <h1>Learning Memory Ledger</h1>
          <p>Cross-run compressed knowledge and provider routing telemetry.</p>
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
                                          <span class="provider-winrate">{provider.contributionRate.toFixed(1)}% Winner Contribution</span>
                                      </div>
                                      <div class="progress-track" title="{provider.winnerContributions} winner contributions / {provider.totalInvocations} invocations">
                                          <div class="progress-fill" style="width: {provider.contributionRate}%;"></div>
                                      </div>
                                      <div class="provider-meta">
                                          <span>Actions: <span class="data-value">{provider.actionCount}</span></span>
                                          <span>Invocations: <span class="data-value">{provider.totalInvocations}</span></span>
                                          <span>Winner contrib: <span class="data-value">{provider.winnerContributions}</span></span>
                                          <span>Avg reward: <span class="data-value">{provider.averageReward.toFixed(2)}</span></span>
                                      </div>
                                      {#if provider.lastRunId}
                                          <div class="provider-run">Last run: {provider.lastRunId}</div>
                                      {/if}
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
                                      <span class="note-type">{labelize(note.note_type)}</span>
                                      <span class="note-source">{note.observation_count ?? 0} observations</span>
                                  </div>
                                  <div class="note-provenance">
                                      {#if note.evidence_sources?.length}
                                          <span>Evidence: {note.evidence_sources.map(labelize).join(', ')}</span>
                                      {/if}
                                      {#if note.source_run_ids?.length}
                                          <span>Runs: {formatRunIds(note.source_run_ids)}</span>
                                      {/if}
                                  </div>
                                  <p class="note-text">{note.text}</p>
                                  {#if note.problem_statements?.length}
                                      <p class="note-problem">Seen in: {note.problem_statements[0]}</p>
                                  {/if}
                                  {#if formatDate(note.last_seen_at)}
                                      <div class="note-updated">Updated: {formatDate(note.last_seen_at)}</div>
                                  {/if}
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
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 16px;
      font-size: 12px;
      color: var(--ink-secondary);
      text-transform: uppercase;
      letter-spacing: 0.05em;
  }

  .provider-run {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--ink-tertiary);
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

  .note-provenance {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 16px;
      margin-bottom: 12px;
      font-size: 12px;
      color: var(--ink-secondary);
  }

  .note-text {
      font-size: 15px;
      line-height: 1.6;
      color: var(--ink-primary);
  }

  .note-problem {
      margin-top: 12px;
      font-size: 13px;
      line-height: 1.5;
      color: var(--ink-secondary);
  }

  .note-updated {
      margin-top: 12px;
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--ink-tertiary);
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
