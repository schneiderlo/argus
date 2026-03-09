<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchMemory } from '$lib/api';
  import type { MemoryPayload, ReusableLearningNote, RoutingEntry } from '$lib/types';

  type EvidenceFilter = 'all' | 'outcome' | 'mixed' | 'search';

  type RoutingCell = {
      providerName: string;
      actionName: string;
      invocationCount: number;
      averageReward: number;
      winnerContributionCount: number;
      providerFailureCount: number;
      lastRunId: string | null;
  };

  type RoutingMatrixRow = {
      providerName: string;
      totalInvocations: number;
      totalReward: number;
      cells: Array<RoutingCell | null>;
  };

  type RoutingMatrix = {
      providers: string[];
      actions: string[];
      rows: RoutingMatrixRow[];
      topCells: RoutingCell[];
  };

  let memoryData: MemoryPayload | null = $state(null);
  let isLoading = $state(true);
  let evidenceFilter: EvidenceFilter = $state('all');

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

  const formatCompactNumber = (value: number) =>
      new Intl.NumberFormat(undefined, {
          notation: 'compact',
          maximumFractionDigits: value >= 100 ? 0 : 1,
      }).format(value);

  const getLearningNotes = (data: MemoryPayload | null) => data?.learning_memory?.entries ?? [];

  const classifyEvidenceProfile = (note: ReusableLearningNote): Exclude<EvidenceFilter, 'all'> => {
      const evidenceSources = new Set(note.evidence_sources ?? []);
      const hasOutcome = evidenceSources.has('outcome_feedback');
      const hasSearch = evidenceSources.has('search_run');

      if (hasOutcome && hasSearch) return 'mixed';
      if (hasOutcome) return 'outcome';
      return 'search';
  };

  const evidenceProfileLabel = (profile: Exclude<EvidenceFilter, 'all'>) => {
      if (profile === 'outcome') return 'Outcome-backed';
      if (profile === 'mixed') return 'Mixed evidence';
      return 'Search-only';
  };

  const noteMatchesEvidenceFilter = (
      note: ReusableLearningNote,
      filter: EvidenceFilter,
  ) => filter === 'all' || classifyEvidenceProfile(note) === filter;

  const getEvidenceFilterOptions = (data: MemoryPayload | null) => {
      const notes = getLearningNotes(data);
      const counts = {
          all: notes.length,
          outcome: notes.filter((note) => classifyEvidenceProfile(note) === 'outcome').length,
          mixed: notes.filter((note) => classifyEvidenceProfile(note) === 'mixed').length,
          search: notes.filter((note) => classifyEvidenceProfile(note) === 'search').length,
      };

      return [
          {
              id: 'all' as const,
              label: 'All priors',
              description: 'Every reusable learning note in shared memory.',
              count: counts.all,
          },
          {
              id: 'outcome' as const,
              label: 'Outcome-backed',
              description: 'Learnings backed by shipped experiment feedback.',
              count: counts.outcome,
          },
          {
              id: 'mixed' as const,
              label: 'Mixed evidence',
              description: 'Learnings reinforced by both search and shipped outcomes.',
              count: counts.mixed,
          },
          {
              id: 'search' as const,
              label: 'Search-only',
              description: 'Priors seen during Argus search but not yet validated in the field.',
              count: counts.search,
          },
      ];
  };

  const getFilteredLearningNotes = (
      data: MemoryPayload | null,
      filter: EvidenceFilter,
  ) =>
      getLearningNotes(data)
          .filter((note) => noteMatchesEvidenceFilter(note, filter))
          .sort(
              (left, right) =>
                  (right.observation_count ?? 0) - (left.observation_count ?? 0) ||
                  (right.last_seen_at ?? '').localeCompare(left.last_seen_at ?? '') ||
                  left.note_id.localeCompare(right.note_id)
          );

  const normalizeRoutingEntries = (data: MemoryPayload | null): RoutingCell[] =>
      (data?.routing_stats?.entries ?? [])
          .map((entry: RoutingEntry) => ({
              providerName: entry.provider_name,
              actionName: entry.action_name,
              invocationCount: entry.invocation_count ?? 0,
              averageReward:
                  entry.invocation_count && entry.invocation_count > 0
                      ? (entry.total_reward ?? 0) / entry.invocation_count
                      : 0,
              winnerContributionCount: entry.winner_contribution_count ?? 0,
              providerFailureCount: entry.provider_failure_count ?? 0,
              lastRunId: entry.last_run_id ?? null,
          }))
          .sort(
              (left, right) =>
                  right.invocationCount - left.invocationCount ||
                  right.averageReward - left.averageReward ||
                  left.providerName.localeCompare(right.providerName) ||
                  left.actionName.localeCompare(right.actionName)
          );

  const buildRoutingMatrix = (data: MemoryPayload | null): RoutingMatrix => {
      const entries = normalizeRoutingEntries(data);
      if (entries.length === 0) {
          return { providers: [], actions: [], rows: [], topCells: [] };
      }

      const providerTotals = new Map<string, number>();
      const actionTotals = new Map<string, number>();
      const cellByKey = new Map<string, RoutingCell>();

      for (const entry of entries) {
          providerTotals.set(
              entry.providerName,
              (providerTotals.get(entry.providerName) ?? 0) + entry.invocationCount
          );
          actionTotals.set(
              entry.actionName,
              (actionTotals.get(entry.actionName) ?? 0) + entry.invocationCount
          );
          cellByKey.set(`${entry.providerName}::${entry.actionName}`, entry);
      }

      const providers = Array.from(providerTotals.keys()).sort(
          (left, right) =>
              (providerTotals.get(right) ?? 0) - (providerTotals.get(left) ?? 0) ||
              left.localeCompare(right)
      );
      const actions = Array.from(actionTotals.keys()).sort(
          (left, right) =>
              (actionTotals.get(right) ?? 0) - (actionTotals.get(left) ?? 0) ||
              left.localeCompare(right)
      );

      const rows = providers.map((providerName) => {
          const cells = actions.map(
              (actionName) => cellByKey.get(`${providerName}::${actionName}`) ?? null
          );
          const providerEntries = cells.filter((cell): cell is RoutingCell => cell !== null);
          return {
              providerName,
              totalInvocations: providerEntries.reduce(
                  (total, cell) => total + cell.invocationCount,
                  0
              ),
              totalReward: providerEntries.reduce(
                  (total, cell) => total + cell.averageReward * cell.invocationCount,
                  0
              ),
              cells,
          };
      });

      return {
          providers,
          actions,
          rows,
          topCells: [...entries]
              .sort(
                  (left, right) =>
                      right.averageReward - left.averageReward ||
                      right.winnerContributionCount - left.winnerContributionCount ||
                      right.invocationCount - left.invocationCount ||
                      left.providerName.localeCompare(right.providerName) ||
                      left.actionName.localeCompare(right.actionName)
              )
              .slice(0, 4),
      };
  };

  const routingMatrix = (data: MemoryPayload | null) => buildRoutingMatrix(data);
</script>

<svelte:head>
  <title>Argus · Memory Ledger</title>
</svelte:head>

<div class="ledger-container">
  <div class="content-wrapper">
      <header class="page-header">
          <h1>Learning Memory Ledger</h1>
          <p>Cross-run reusable priors, outcome-backed evidence, and provider routing telemetry.</p>
      </header>

      {#if isLoading}
          <div class="loading-state">Syncing memory ledgers...</div>
      {:else}
          <div class="summary-grid">
              <div class="summary-card">
                  <div class="summary-label">Reusable Priors</div>
                  <div class="summary-value">{formatCompactNumber(getLearningNotes(memoryData).length)}</div>
                  <div class="summary-detail">Stored learnings available for future runs.</div>
              </div>
              <div class="summary-card">
                  <div class="summary-label">Outcome-backed</div>
                  <div class="summary-value">
                      {formatCompactNumber(
                          getLearningNotes(memoryData).filter(
                              (note) => classifyEvidenceProfile(note) === 'outcome'
                          ).length
                      )}
                  </div>
                  <div class="summary-detail">Priors grounded in shipped experiment feedback.</div>
              </div>
              <div class="summary-card">
                  <div class="summary-label">Mixed Evidence</div>
                  <div class="summary-value">
                      {formatCompactNumber(
                          getLearningNotes(memoryData).filter(
                              (note) => classifyEvidenceProfile(note) === 'mixed'
                          ).length
                      )}
                  </div>
                  <div class="summary-detail">Patterns reinforced by both search and outcomes.</div>
              </div>
              <div class="summary-card">
                  <div class="summary-label">Provider x Action Cells</div>
                  <div class="summary-value">
                      {formatCompactNumber(normalizeRoutingEntries(memoryData).length)}
                  </div>
                  <div class="summary-detail">Distinct routed provider/action histories on record.</div>
              </div>
          </div>

          <div class="split-layout">
              <div class="column matrix-column">
                  <h2 class="section-title">
                      <span class="icon">▦</span> Provider x Action Matrix
                  </h2>
                  <div class="card">
                      {#if routingMatrix(memoryData).providers.length === 0}
                          <div class="empty-state text-sm">No provider routing history recorded.</div>
                      {:else}
                          <p class="section-intro">
                              Each cell shows average reward and invocation volume for a single
                              provider/action pair, so routing performance stays visible at the
                              action boundary instead of collapsing into provider-only totals.
                          </p>
                          <div class="matrix-scroll">
                              <table class="matrix-table">
                                  <thead>
                                      <tr>
                                          <th>Provider</th>
                                          {#each routingMatrix(memoryData).actions as action}
                                              <th>{labelize(action)}</th>
                                          {/each}
                                      </tr>
                                  </thead>
                                  <tbody>
                                      {#each routingMatrix(memoryData).rows as row}
                                          <tr>
                                              <th scope="row" class="provider-cell">
                                                  <div class="provider-name">{row.providerName}</div>
                                                  <div class="provider-meta">
                                                      {row.totalInvocations} invocations
                                                  </div>
                                              </th>
                                              {#each row.cells as cell}
                                                  {#if cell}
                                                      <td
                                                          class={`matrix-metric ${cell.averageReward > 0.75 ? 'is-strong' : ''} ${cell.averageReward < 0 ? 'is-risky' : ''}`}
                                                      >
                                                          <div class="metric-value">
                                                              {cell.averageReward.toFixed(2)}
                                                          </div>
                                                          <div class="metric-detail">
                                                              {cell.invocationCount} inv
                                                          </div>
                                                          <div class="metric-detail">
                                                              {cell.winnerContributionCount} winner contrib
                                                          </div>
                                                          {#if cell.providerFailureCount > 0}
                                                              <div class="metric-warning">
                                                                  {cell.providerFailureCount} fail
                                                              </div>
                                                          {/if}
                                                      </td>
                                                  {:else}
                                                      <td class="matrix-empty">—</td>
                                                  {/if}
                                              {/each}
                                          </tr>
                                      {/each}
                                  </tbody>
                              </table>
                          </div>

                          <div class="top-cells">
                              <div class="subsection-label">Strongest Routed Cells</div>
                              <div class="top-cell-grid">
                                  {#each routingMatrix(memoryData).topCells as cell}
                                      <div class="top-cell-card">
                                          <div class="top-cell-header">
                                              <span>{cell.providerName}</span>
                                              <span>{labelize(cell.actionName)}</span>
                                          </div>
                                          <div class="top-cell-value">
                                              Reward {cell.averageReward.toFixed(2)}
                                          </div>
                                          <div class="top-cell-meta">
                                              {cell.invocationCount} invocations · {cell.winnerContributionCount}
                                              winner contrib
                                          </div>
                                          {#if cell.lastRunId}
                                              <div class="top-cell-meta">Last run: {cell.lastRunId}</div>
                                          {/if}
                                      </div>
                                  {/each}
                              </div>
                          </div>
                      {/if}
                  </div>
              </div>

              <div class="column notes-column">
                  <h2 class="section-title">
                      <span class="icon">◈</span> Reusable Priors
                  </h2>
                  <div class="filter-bar">
                      {#each getEvidenceFilterOptions(memoryData) as option}
                          <button
                              class:active={evidenceFilter === option.id}
                              class="filter-chip"
                              onclick={() => {
                                  evidenceFilter = option.id;
                              }}
                              type="button"
                          >
                              <span>{option.label}</span>
                              <span class="chip-count">{option.count}</span>
                          </button>
                      {/each}
                  </div>
                  <div class="filter-caption">
                      {
                          getEvidenceFilterOptions(memoryData).find(
                              (option) => option.id === evidenceFilter
                          )?.description
                      }
                  </div>

                  <div class="notes-feed">
                      {#if getFilteredLearningNotes(memoryData, evidenceFilter).length === 0}
                          <div class="card empty-state">
                              No learning notes match the current provenance filter.
                          </div>
                      {:else}
                          {#each getFilteredLearningNotes(memoryData, evidenceFilter) as note}
                              <div class="card note-card">
                                  <div class="note-header">
                                      <span class="note-type">{labelize(note.note_type)}</span>
                                      <span class={`note-evidence ${classifyEvidenceProfile(note)}`}>
                                          {evidenceProfileLabel(classifyEvidenceProfile(note))}
                                      </span>
                                  </div>
                                  <div class="note-meta-row">
                                      <span class="note-source">
                                          {note.observation_count ?? 0} observations
                                      </span>
                                      {#if formatDate(note.last_seen_at)}
                                          <span class="note-updated">
                                              Updated {formatDate(note.last_seen_at)}
                                          </span>
                                      {/if}
                                  </div>
                                  <p class="note-text">{note.text}</p>
                                  <div class="note-provenance">
                                      {#if note.evidence_sources?.length}
                                          <span>
                                              Evidence: {note.evidence_sources.map(labelize).join(', ')}
                                          </span>
                                      {/if}
                                      {#if note.source_run_ids?.length}
                                          <span>Runs: {formatRunIds(note.source_run_ids)}</span>
                                      {/if}
                                  </div>
                                  {#if note.problem_statements?.length}
                                      <p class="note-problem">Seen in: {note.problem_statements[0]}</p>
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
      max-width: 1440px;
      margin: 0 auto;
      padding-bottom: 80px;
  }

  .page-header {
      margin-bottom: 32px;
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
      max-width: 720px;
  }

  .summary-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 32px;
  }

  .summary-card {
      background:
          linear-gradient(180deg, rgba(22, 163, 74, 0.10), rgba(15, 23, 42, 0.18)),
          var(--surface-color);
      border: 1px solid var(--border-heavy);
      border-radius: 14px;
      padding: 20px;
      box-shadow: var(--shadow-glow);
  }

  :global(.light-mode) .summary-card {
      background:
          linear-gradient(180deg, rgba(22, 163, 74, 0.08), rgba(255, 255, 255, 0.92)),
          var(--surface-color);
  }

  .summary-label {
      color: var(--ink-tertiary);
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      margin-bottom: 10px;
  }

  .summary-value {
      color: var(--ink-primary);
      font-size: 34px;
      font-weight: 700;
      line-height: 1;
      margin-bottom: 10px;
  }

  .summary-detail {
      color: var(--ink-secondary);
      font-size: 13px;
      line-height: 1.5;
  }

  .split-layout {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.8fr);
      gap: 28px;
      align-items: start;
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
      border-radius: 14px;
      padding: 24px;
      box-shadow: var(--shadow-glow);
  }

  .section-intro {
      margin: 0 0 18px;
      color: var(--ink-secondary);
      line-height: 1.6;
  }

  .matrix-scroll {
      overflow-x: auto;
      margin: 0 -4px;
      padding: 0 4px;
  }

  .matrix-table {
      width: 100%;
      border-collapse: collapse;
      min-width: 720px;
  }

  .matrix-table th,
  .matrix-table td {
      border-bottom: 1px solid var(--border-subtle);
      padding: 14px 12px;
      vertical-align: top;
      text-align: left;
  }

  .matrix-table thead th {
      color: var(--ink-tertiary);
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      background: rgba(15, 23, 42, 0.18);
      position: sticky;
      top: 0;
  }

  :global(.light-mode) .matrix-table thead th {
      background: rgba(15, 23, 42, 0.04);
  }

  .provider-cell {
      min-width: 140px;
  }

  .provider-name {
      color: var(--ink-primary);
      font-size: 15px;
      font-weight: 600;
      margin-bottom: 4px;
  }

  .provider-meta {
      color: var(--ink-tertiary);
      font-family: var(--font-mono);
      font-size: 12px;
  }

  .matrix-metric {
      min-width: 120px;
      background: rgba(59, 130, 246, 0.06);
  }

  :global(.light-mode) .matrix-metric {
      background: rgba(59, 130, 246, 0.04);
  }

  .matrix-metric.is-strong {
      background: rgba(22, 163, 74, 0.12);
  }

  .matrix-metric.is-risky {
      background: rgba(220, 38, 38, 0.10);
  }

  .metric-value {
      color: var(--ink-primary);
      font-family: var(--font-mono);
      font-size: 20px;
      font-weight: 600;
      margin-bottom: 4px;
  }

  .metric-detail {
      color: var(--ink-secondary);
      font-size: 12px;
      line-height: 1.4;
  }

  .metric-warning {
      color: #f59e0b;
      font-size: 12px;
      font-weight: 600;
      margin-top: 6px;
  }

  .matrix-empty {
      color: var(--ink-tertiary);
      text-align: center;
      font-family: var(--font-mono);
  }

  .top-cells {
      margin-top: 22px;
      padding-top: 22px;
      border-top: 1px solid var(--border-subtle);
  }

  .subsection-label {
      color: var(--ink-tertiary);
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      margin-bottom: 14px;
  }

  .top-cell-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
  }

  .top-cell-card {
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 16px;
      background: rgba(255, 255, 255, 0.04);
  }

  :global(.light-mode) .top-cell-card {
      background: rgba(15, 23, 42, 0.03);
  }

  .top-cell-header {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: var(--ink-primary);
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 8px;
  }

  .top-cell-value {
      color: #38bdf8;
      font-family: var(--font-mono);
      font-size: 18px;
      margin-bottom: 6px;
  }

  .top-cell-meta {
      color: var(--ink-secondary);
      font-size: 12px;
      line-height: 1.4;
  }

  .filter-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 10px;
  }

  .filter-chip {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      border: 1px solid var(--border-heavy);
      border-radius: 999px;
      padding: 10px 14px;
      background: var(--surface-color);
      color: var(--ink-secondary);
      cursor: pointer;
      transition: border-color 0.2s, color 0.2s, transform 0.2s;
  }

  .filter-chip:hover,
  .filter-chip.active {
      color: var(--ink-primary);
      border-color: rgba(56, 189, 248, 0.5);
      transform: translateY(-1px);
  }

  .chip-count {
      font-family: var(--font-mono);
      color: var(--ink-tertiary);
  }

  .filter-caption {
      color: var(--ink-secondary);
      font-size: 13px;
      line-height: 1.5;
      margin-bottom: 18px;
  }

  .notes-feed {
      display: flex;
      flex-direction: column;
      gap: 14px;
  }

  .note-card {
      background:
          linear-gradient(180deg, rgba(56, 189, 248, 0.06), rgba(15, 23, 42, 0.14)),
          var(--surface-color);
      transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
  }

  :global(.light-mode) .note-card {
      background:
          linear-gradient(180deg, rgba(56, 189, 248, 0.05), rgba(255, 255, 255, 0.92)),
          var(--surface-color);
  }

  .note-card:hover {
      transform: translateY(-2px);
      border-color: rgba(56, 189, 248, 0.4);
      box-shadow: 0 10px 36px rgba(15, 23, 42, 0.14);
  }

  .note-header,
  .note-meta-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
  }

  .note-header {
      margin-bottom: 10px;
  }

  .note-type,
  .note-evidence {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 5px 10px;
      font-family: var(--font-mono);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
  }

  .note-type {
      border: 1px solid rgba(56, 189, 248, 0.4);
      color: #7dd3fc;
      background: rgba(56, 189, 248, 0.12);
  }

  .note-evidence.outcome {
      color: #86efac;
      background: rgba(22, 163, 74, 0.14);
      border: 1px solid rgba(22, 163, 74, 0.35);
  }

  .note-evidence.mixed {
      color: #fcd34d;
      background: rgba(245, 158, 11, 0.15);
      border: 1px solid rgba(245, 158, 11, 0.35);
  }

  .note-evidence.search {
      color: #cbd5e1;
      background: rgba(100, 116, 139, 0.18);
      border: 1px solid rgba(100, 116, 139, 0.35);
  }

  .note-source,
  .note-updated {
      color: var(--ink-tertiary);
      font-family: var(--font-mono);
      font-size: 12px;
  }

  .note-text {
      color: var(--ink-primary);
      font-size: 15px;
      line-height: 1.6;
      margin: 12px 0;
  }

  .note-provenance {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 16px;
      color: var(--ink-secondary);
      font-size: 12px;
      line-height: 1.5;
  }

  .note-problem {
      margin: 12px 0 0;
      color: var(--ink-secondary);
      font-size: 13px;
      line-height: 1.5;
  }

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

  @media (max-width: 1100px) {
      .summary-grid {
          grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .split-layout {
          grid-template-columns: 1fr;
      }
  }

  @media (max-width: 720px) {
      .ledger-container {
          padding: 24px 16px 40px;
      }

      .summary-grid {
          grid-template-columns: 1fr;
      }

      .top-cell-grid {
          grid-template-columns: 1fr;
      }
  }
</style>
