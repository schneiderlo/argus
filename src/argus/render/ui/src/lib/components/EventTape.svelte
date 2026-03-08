<script lang="ts">
  import { uiState } from '$lib/stores.svelte';
  import type { ProgressEventPayload } from '$lib/types';

  const visibleEvents = $derived(uiState.runEvents.slice(-12).reverse());

  function formatTimestamp(value: string) {
      const date = new Date(value);
      return Number.isNaN(date.getTime())
          ? value
          : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  function eventTone(event: ProgressEventPayload) {
      if (event.kind === 'node_admitted' || event.kind === 'selection_finalized') return 'positive';
      if (event.kind === 'node_rejected' || event.kind === 'node_failed' || event.kind === 'provider_failed') {
          return 'negative';
      }
      return 'neutral';
  }

  function eventLabel(event: ProgressEventPayload) {
      const payload = event.payload;
      const nodeId = typeof payload.node_id === 'string' ? payload.node_id : null;
      const thesis = typeof payload.thesis === 'string' ? payload.thesis : null;
      const action = typeof payload.action === 'string' ? payload.action.replaceAll('_', ' ') : null;
      const winner = typeof payload.winner_node_id === 'string' ? payload.winner_node_id : null;
      const provider = typeof payload.provider === 'string' ? payload.provider : null;
      const reason = typeof payload.reason === 'string' ? payload.reason : null;

      if (event.kind === 'stage_started') {
          const label = typeof payload.label === 'string' ? payload.label : action;
          return label ? `Stage started: ${label}` : 'Stage started';
      }
      if (event.kind === 'stage_completed') {
          const label = typeof payload.label === 'string' ? payload.label : action;
          return label ? `Stage completed: ${label}` : 'Stage completed';
      }
      if (event.kind === 'node_admitted' && nodeId) {
          return `${nodeId} admitted${thesis ? `: ${thesis}` : ''}`;
      }
      if ((event.kind === 'node_rejected' || event.kind === 'node_failed') && nodeId) {
          return `${nodeId} ${event.kind === 'node_rejected' ? 'rejected' : 'failed'}${reason ? `: ${reason}` : ''}`;
      }
      if (event.kind === 'pairwise_decision' && winner) {
          return `Pairwise winner: ${winner}`;
      }
      if (event.kind === 'provider_failed' && provider) {
          return `${provider} failed${action ? ` during ${action}` : ''}`;
      }
      if (event.kind === 'selection_finalized') {
          return 'Winner selection finalized';
      }
      if (event.kind === 'run_completed') {
          return 'Run completed';
      }
      if (event.kind === 'run_failed') {
          return 'Run failed';
      }
      return event.kind.replaceAll('_', ' ');
  }
</script>

<section class="event-tape">
  <div class="tape-header">
      <div>
          <div class="eyebrow">Live Feed</div>
          <h2>Event Tape</h2>
      </div>
      <div class="event-count">{uiState.runEvents.length} events</div>
  </div>

  {#if visibleEvents.length === 0}
      <div class="empty-state">No progress events recorded for this run yet.</div>
  {:else}
      <div class="event-list">
          {#each visibleEvents as event (event.timestamp + event.kind + JSON.stringify(event.payload))}
              <article class="event-card {eventTone(event)}">
                  <div class="event-meta">
                      <span class="event-kind">{event.kind.replaceAll('_', ' ')}</span>
                      <span class="event-time">{formatTimestamp(event.timestamp)}</span>
                  </div>
                  <div class="event-body">{eventLabel(event)}</div>
              </article>
          {/each}
      </div>
  {/if}
</section>

<style>
  .event-tape {
      border-top: 1px solid var(--border-heavy);
      background:
          linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0)),
          var(--surface-color);
      padding: 18px 24px 24px;
  }

  .tape-header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 14px;
  }

  .eyebrow {
      color: var(--ink-tertiary);
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      margin-bottom: 4px;
  }

  .tape-header h2 {
      margin: 0;
      font-size: 18px;
      color: var(--ink-primary);
  }

  .event-count {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--ink-secondary);
  }

  .event-list {
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  }

  .event-card {
      border: 1px solid var(--border-subtle);
      border-left-width: 3px;
      border-radius: 10px;
      padding: 12px 14px;
      background: rgba(255, 255, 255, 0.02);
      min-height: 84px;
  }

  :global(.light-mode) .event-card {
      background: rgba(0, 0, 0, 0.02);
  }

  .event-card.positive {
      border-left-color: #34d399;
  }

  .event-card.negative {
      border-left-color: #f87171;
  }

  .event-card.neutral {
      border-left-color: #60a5fa;
  }

  .event-meta {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
  }

  .event-kind,
  .event-time {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--ink-tertiary);
      text-transform: uppercase;
      letter-spacing: 0.08em;
  }

  .event-body {
      color: var(--ink-primary);
      font-size: 14px;
      line-height: 1.4;
  }

  .empty-state {
      color: var(--ink-secondary);
      font-size: 14px;
      padding: 16px 0 6px;
  }
</style>
