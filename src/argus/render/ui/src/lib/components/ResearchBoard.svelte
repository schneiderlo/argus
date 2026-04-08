<script lang="ts">
  // @ts-nocheck
  import { getStyle, uiState } from '$lib/stores.svelte';
  import { deriveResearchBoard } from '$lib/components/researchBoardModel.js';
  import type { SearchStatePayload } from '$lib/types';

  let { state }: { state: SearchStatePayload | null } = $props();

  const board = $derived(deriveResearchBoard(state));
  const currentAction = $derived(uiState.runStatus?.current_action ?? null);

  function selectNode(nodeId: string | null) {
      if (!nodeId) return;
      uiState.selectedNodeId = nodeId;
  }

  function cardStyle(status: string | null | undefined) {
      return getStyle(status ?? 'default');
  }

  function cardVariables(status: string | null | undefined) {
      const style = cardStyle(status);
      return `--card-bg:${style.bg}; --card-border:${style.border}; --card-text:${style.text};`;
  }
</script>

{#if board}
  <div class="board-shell">
      <section class="overview-strip">
          <div class="overview-copy">
              <div class="eyebrow">Research Board</div>
              <h1>{board.currentReadLabel}</h1>
              <p>{board.currentReadText ?? 'Research bundle loaded.'}</p>
          </div>
          <div class="overview-stats">
              <div class="stat-card">
                  <span class="stat-label">Seeded</span>
                  <strong>{board.stats.seededCount}</strong>
              </div>
              <div class="stat-card">
                  <span class="stat-label">Shortlist</span>
                  <strong>{board.stats.shortlistCount}</strong>
              </div>
              <div class="stat-card">
                  <span class="stat-label">Cut</span>
                  <strong>{board.stats.eliminatedCount}</strong>
              </div>
              <div class="stat-card stat-wide">
                  <span class="stat-label">Current Action</span>
                  <strong>{currentAction ?? 'idle'}</strong>
              </div>
          </div>
      </section>

      {#if board.currentFrameCard}
          <section class="section-block">
              <div class="section-heading">
                  <div>
                      <div class="eyebrow">Scaffold</div>
                      <h2>Search Frame</h2>
                  </div>
                  <p>The frame is the map of candidate families. It should not read like a real game pitch.</p>
              </div>
              <button
                  class="frame-card"
                  type="button"
                  style={cardVariables(board.currentFrameCard.statusTone)}
                  data-selected={uiState.selectedNodeId === board.currentFrameCard.nodeId}
                  onclick={() => selectNode(board.currentFrameCard.nodeId)}
              >
                  <div class="card-topline">
                      <span class="status-pill">{board.currentFrameCard.statusLabel}</span>
                      <div class="badge-row">
                          {#each board.currentFrameCard.badges as badge}
                              <span class="meta-badge">{badge}</span>
                          {/each}
                      </div>
                  </div>
                  <h3>{board.currentFrameCard.title}</h3>
                  <p class="card-summary">{board.currentFrameCard.summary}</p>
                  <p class="card-detail">{board.currentFrameCard.detail}</p>
                  <p class="card-note">{board.currentFrameCard.note}</p>
              </button>
          </section>
      {/if}

      <section class="section-block">
          <div class="section-heading">
              <div>
                  <div class="eyebrow">Concept Pool</div>
                  <h2>Seeded Concepts</h2>
              </div>
              <p>Every proposal brief gets a card, even if the runtime node graph made it look like a duplicate.</p>
          </div>

              <div class="cards-grid compact">
                  {#each board.seededCards as card}
                  <button
                      class="concept-card"
                      type="button"
                      style={cardVariables(card.statusTone)}
                      data-selected={uiState.selectedNodeId === card.nodeId}
                      onclick={() => selectNode(card.nodeId)}
                  >
                      <div class="card-topline">
                          <span class="status-pill">{card.statusLabel}</span>
                          <div class="badge-row">
                              {#each card.badges as badge}
                                  <span class="meta-badge">{badge}</span>
                              {/each}
                          </div>
                      </div>
                      <h3>{card.title}</h3>
                      <p class="card-summary">{card.summary}</p>
                      <p class="cell-label">{card.cellLabel}</p>
                      {#if card.reason}
                          <p class="reason-text">{card.reason}</p>
                      {/if}
                      {#if card.systemNote}
                          <p class="system-note">{card.systemNote}</p>
                      {/if}
                  </button>
              {/each}
          </div>
      </section>

      <div class="split-sections">
          <section class="section-block">
              <div class="section-heading">
                  <div>
                      <div class="eyebrow">Decision Track</div>
                      <h2>{board.hasFinalDecision ? 'Decision Stack' : 'Current Shortlist'}</h2>
                  </div>
                  <p>
                      {board.hasFinalDecision
                          ? 'These are the proposals the run elevated into explicit final roles.'
                          : 'These are the families the latest triage pass still considers decision-relevant.'}
                  </p>
              </div>

              <div class="cards-grid">
                  {#if board.shortlistCards.length === 0}
                      <div class="empty-panel">No shortlist yet.</div>
                  {:else}
                      {#each board.shortlistCards as card}
                          <button
                              class="concept-card featured"
                              type="button"
                              style={cardVariables(card.statusTone)}
                              data-selected={uiState.selectedNodeId === card.nodeId}
                              onclick={() => selectNode(card.nodeId)}
                          >
                              <div class="card-topline">
                                  <span class="status-pill">{card.statusLabel}</span>
                                  <div class="badge-row">
                                      {#each card.badges as badge}
                                          <span class="meta-badge">{badge}</span>
                                      {/each}
                                  </div>
                              </div>
                              <h3>{card.title}</h3>
                              <p class="card-summary">{card.summary}</p>
                              {#if card.reason}
                                  <p class="reason-text">{card.reason}</p>
                              {/if}
                              {#if card.followUp}
                                  <p class="follow-up"><strong>Next:</strong> {card.followUp}</p>
                              {/if}
                          </button>
                      {/each}
                  {/if}
              </div>
          </section>

          <section class="section-block">
              <div class="section-heading">
                  <div>
                      <div class="eyebrow">Cuts</div>
                      <h2>Eliminated Concepts</h2>
                  </div>
                  <p>These cards keep the rationale visible, so a rejected node does not disappear into graph noise.</p>
              </div>

              <div class="cards-grid">
                  {#if board.eliminatedCards.length === 0}
                      <div class="empty-panel">No eliminated concepts yet.</div>
                  {:else}
                      {#each board.eliminatedCards as card}
                          <button
                              class="concept-card"
                              type="button"
                              style={cardVariables(card.statusTone)}
                              data-selected={uiState.selectedNodeId === card.nodeId}
                              onclick={() => selectNode(card.nodeId)}
                          >
                              <div class="card-topline">
                                  <span class="status-pill">{card.statusLabel}</span>
                                  <div class="badge-row">
                                      {#each card.badges as badge}
                                          <span class="meta-badge">{badge}</span>
                                      {/each}
                                  </div>
                              </div>
                              <h3>{card.title}</h3>
                              <p class="card-summary">{card.summary}</p>
                              {#if card.reason}
                                  <p class="reason-text">{card.reason}</p>
                              {/if}
                              {#if card.systemNote}
                                  <p class="system-note">{card.systemNote}</p>
                              {/if}
                          </button>
                      {/each}
                  {/if}
              </div>
          </section>
      </div>
  </div>
{/if}

<style>
  .board-shell {
      height: 100%;
      overflow-y: auto;
      padding: 28px;
      display: flex;
      flex-direction: column;
      gap: 24px;
  }

  .overview-strip,
  .section-block,
  .empty-panel,
  .frame-card,
  .concept-card,
  .stat-card {
      background: var(--surface-color);
      backdrop-filter: var(--glass-blur);
      -webkit-backdrop-filter: var(--glass-blur);
      border: 1px solid var(--border-subtle);
      border-radius: 20px;
      box-shadow: var(--shadow-glow);
  }

  .overview-strip {
      padding: 24px;
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr);
      gap: 24px;
  }

  .overview-copy {
      display: flex;
      flex-direction: column;
      gap: 12px;
  }

  .overview-copy h1,
  .section-heading h2,
  .frame-card h3,
  .concept-card h3 {
      font-size: 1.35rem;
      line-height: 1.1;
  }

  .overview-copy p,
  .section-heading p,
  .card-summary,
  .card-detail,
  .card-note,
  .reason-text,
  .system-note,
  .follow-up,
  .cell-label,
  .empty-panel {
      color: var(--ink-secondary);
      line-height: 1.55;
  }

  .overview-stats {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
  }

  .stat-card {
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 8px;
  }

  .stat-wide {
      grid-column: span 2;
  }

  .stat-label,
  .eyebrow {
      font-size: 0.74rem;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--ink-tertiary);
  }

  .stat-card strong {
      font-size: 1.2rem;
      color: var(--ink-primary);
  }

  .section-block {
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 18px;
  }

  .section-heading {
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: flex-end;
  }

  .section-heading > div {
      display: flex;
      flex-direction: column;
      gap: 6px;
  }

  .section-heading p {
      max-width: 520px;
  }

  .frame-card,
  .concept-card {
      width: 100%;
      text-align: left;
      padding: 18px;
      border-color: var(--card-border);
      background:
          linear-gradient(180deg, color-mix(in srgb, var(--card-bg) 78%, transparent), transparent),
          linear-gradient(135deg, color-mix(in srgb, var(--card-border) 14%, transparent), transparent 40%);
      cursor: pointer;
      display: flex;
      flex-direction: column;
      gap: 12px;
      color: var(--ink-primary);
  }

  .frame-card:hover,
  .concept-card:hover {
      transform: translateY(-1px);
      border-color: color-mix(in srgb, var(--card-border) 85%, white 15%);
  }

  .frame-card[data-selected='true'],
  .concept-card[data-selected='true'] {
      border-width: 2px;
      box-shadow: 0 0 0 1px color-mix(in srgb, var(--card-border) 35%, transparent), var(--shadow-glow);
  }

  .featured {
      min-height: 240px;
  }

  .card-topline {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
  }

  .status-pill,
  .meta-badge {
      border-radius: 999px;
      border: 1px solid var(--border-heavy);
      font-family: var(--font-mono);
      font-size: 0.7rem;
      padding: 5px 9px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
  }

  .status-pill {
      color: var(--card-text);
      border-color: color-mix(in srgb, var(--card-border) 65%, transparent);
      background: color-mix(in srgb, var(--card-border) 12%, transparent);
  }

  .badge-row {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 6px;
  }

  .meta-badge {
      color: var(--ink-tertiary);
      background: rgba(255, 255, 255, 0.03);
  }

  .card-note,
  .system-note {
      font-size: 0.92rem;
  }

  .system-note {
      color: var(--card-text);
  }

  .reason-text {
      color: var(--ink-primary);
  }

  .follow-up strong {
      color: var(--ink-primary);
  }

  .cards-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
  }

  .cards-grid.compact {
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  }

  .split-sections {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 24px;
  }

  .empty-panel {
      padding: 24px;
      min-height: 120px;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
  }

  @media (max-width: 1100px) {
      .overview-strip,
      .split-sections,
      .section-heading {
          grid-template-columns: 1fr;
          flex-direction: column;
          align-items: stretch;
      }
  }
</style>
