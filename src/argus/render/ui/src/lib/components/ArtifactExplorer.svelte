<script lang="ts">
  // @ts-nocheck
  import { renderRichMarkdown } from '$lib/markdown';
  import { deriveArtifactExplorer } from '$lib/components/artifactExplorerModel.js';
  import type { SearchStatePayload } from '$lib/types';

  let { state: runState }: { state: SearchStatePayload | null } = $props();

  const explorer = $derived(deriveArtifactExplorer(runState));
  let selectedId = $state<string | null>(null);

  const selectedItem = $derived(
      explorer?.items.find((item) => item.id === selectedId) ??
          explorer?.items.find((item) => item.id === explorer.defaultItemId) ??
          explorer?.items.find((item) => !item.isGroup) ??
          null
  );

  $effect(() => {
      if (!explorer) {
          selectedId = null;
          return;
      }
      if (!selectedId || !explorer.items.some((item) => item.id === selectedId)) {
          selectedId = explorer.defaultItemId;
      }
  });

  function selectItem(item) {
      if (item.isGroup) return;
      selectedId = item.id;
  }

  function itemOffset(depth: number) {
      return `padding-left: ${12 + depth * 18}px;`;
  }

  function renderedMarkdown(markdown: string | null | undefined) {
      return markdown ? renderRichMarkdown(markdown) : '';
  }
</script>

{#if explorer}
  <section class="explorer-shell">
      <div class="explorer-header">
          <div>
              <div class="explorer-eyebrow">Research Artifact Explorer</div>
              <h2>Run Files</h2>
          </div>
          <div class="explorer-stats">
              <span>{explorer.stats.proposals} proposals</span>
              <span>{explorer.stats.deepDives} deep dives</span>
              <span>{explorer.stats.technicalDossiers} technical dossiers</span>
              <span>{explorer.stats.reviews} reviews</span>
          </div>
      </div>

      <div class="explorer-grid">
          <nav class="artifact-tree" aria-label="Research artifact tree">
              {#each explorer.items as item}
                  {#if item.isGroup}
                      <div class="tree-group" style={itemOffset(item.depth)}>
                          <span class="tree-caret">▾</span>
                          <span>{item.label}</span>
                      </div>
                  {:else}
                      <button
                          type="button"
                          class="tree-item"
                          class:selected={selectedItem?.id === item.id}
                          style={itemOffset(item.depth)}
                          onclick={() => selectItem(item)}
                      >
                          <span class="tree-stem"></span>
                          <span class="tree-label">{item.label}</span>
                          <span class="tree-kind">{item.status}</span>
                      </button>
                  {/if}
              {/each}
          </nav>

          <article class="artifact-detail">
              {#if selectedItem}
                  <div class="detail-topline">
                      <span class="detail-kind">{selectedItem.kind}</span>
                      <span class="detail-status">{selectedItem.status}</span>
                  </div>
                  <h3>{selectedItem.label}</h3>
                  {#if selectedItem.summary}
                      <p class="detail-summary">{selectedItem.summary}</p>
                  {/if}
                  {#if selectedItem.badges?.length}
                      <div class="badge-row">
                          {#each selectedItem.badges as badge}
                              <span>{badge}</span>
                          {/each}
                      </div>
                  {/if}

                  {#if selectedItem.markdown}
                      <div class="markdown-detail">{@html renderedMarkdown(selectedItem.markdown)}</div>
                  {:else if selectedItem.sections?.length}
                      <div class="section-stack">
                          {#each selectedItem.sections.filter(Boolean) as section}
                              <section class="detail-section">
                                  <h4>{section.label}</h4>
                                  {#if section.text}
                                      <p>{section.text}</p>
                                  {:else if section.values?.length}
                                      <ul>
                                          {#each section.values as value}
                                              <li>{value}</li>
                                          {/each}
                                      </ul>
                                  {/if}
                              </section>
                          {/each}
                      </div>
                  {:else}
                      <p class="empty-detail">No detail payload is available for this artifact.</p>
                  {/if}
              {:else}
                  <p class="empty-detail">Select an artifact to inspect its details.</p>
              {/if}
          </article>
      </div>
  </section>
{/if}

<style>
  .explorer-shell {
      margin-top: 24px;
      padding: 0;
      border: 1px solid var(--border-heavy);
      border-radius: 12px;
      background: var(--surface-color);
      box-shadow: var(--shadow-glow);
      overflow: hidden;
  }

  .explorer-header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 24px;
      padding: 24px 28px;
      border-bottom: 1px solid var(--border-subtle);
      background: rgba(255, 255, 255, 0.02);
  }

  :global(.light-mode) .explorer-header {
      background: rgba(0, 0, 0, 0.02);
  }

  .explorer-eyebrow,
  .detail-kind,
  .detail-status,
  .tree-kind {
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--ink-tertiary);
  }

  .explorer-header h2 {
      margin: 6px 0 0;
      color: var(--ink-primary);
      font-size: 28px;
      line-height: 1;
  }

  .explorer-stats {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
      max-width: 420px;
  }

  .explorer-stats span,
  .badge-row span {
      padding: 5px 9px;
      border: 1px solid var(--border-subtle);
      border-radius: 999px;
      color: var(--ink-secondary);
      font-family: var(--font-mono);
      font-size: 11px;
  }

  .explorer-grid {
      display: grid;
      grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
      min-height: 560px;
  }

  .artifact-tree {
      border-right: 1px solid var(--border-subtle);
      padding: 14px 0;
      overflow: auto;
  }

  .tree-group,
  .tree-item {
      width: 100%;
      min-height: 34px;
      display: flex;
      align-items: center;
      gap: 8px;
      padding-top: 7px;
      padding-right: 12px;
      padding-bottom: 7px;
      border: 0;
      background: transparent;
      color: var(--ink-secondary);
      text-align: left;
      font: inherit;
  }

  .tree-group {
      margin-top: 6px;
      color: var(--ink-primary);
      font-weight: 700;
      font-size: 13px;
  }

  .tree-item {
      cursor: pointer;
      border-left: 3px solid transparent;
  }

  .tree-item:hover,
  .tree-item.selected {
      background: rgba(96, 165, 250, 0.08);
      color: var(--ink-primary);
      border-left-color: #60a5fa;
  }

  .tree-caret,
  .tree-stem {
      width: 14px;
      color: var(--ink-tertiary);
      flex: 0 0 auto;
  }

  .tree-stem::before {
      content: '└';
  }

  .tree-label {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 13px;
  }

  .tree-kind {
      max-width: 96px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
  }

  .artifact-detail {
      padding: 28px;
      overflow: auto;
  }

  .detail-topline {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
  }

  .detail-status {
      padding: 4px 8px;
      border: 1px solid var(--border-subtle);
      border-radius: 999px;
  }

  .artifact-detail h3 {
      margin: 0 0 14px;
      color: var(--ink-primary);
      font-size: 24px;
      line-height: 1.2;
  }

  .detail-summary,
  .empty-detail {
      color: var(--ink-secondary);
      line-height: 1.7;
      margin: 0 0 18px;
  }

  .badge-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 22px;
  }

  .section-stack {
      display: flex;
      flex-direction: column;
      gap: 18px;
  }

  .detail-section {
      padding-top: 18px;
      border-top: 1px solid var(--border-subtle);
  }

  .detail-section h4 {
      margin: 0 0 10px;
      color: var(--ink-tertiary);
      font-size: 11px;
      font-family: var(--font-mono);
      letter-spacing: 0.1em;
      text-transform: uppercase;
  }

  .detail-section p,
  .detail-section li {
      color: var(--ink-secondary);
      line-height: 1.65;
  }

  .detail-section p {
      margin: 0;
  }

  .detail-section ul {
      margin: 0;
      padding-left: 20px;
  }

  .markdown-detail {
      max-width: 76ch;
      color: var(--ink-primary);
      line-height: 1.75;
  }

  .markdown-detail :global(h1),
  .markdown-detail :global(h2),
  .markdown-detail :global(h3) {
      color: var(--ink-primary);
      line-height: 1.15;
      margin: 1.5em 0 0.65em;
  }

  .markdown-detail :global(p),
  .markdown-detail :global(li) {
      color: var(--ink-secondary);
  }

  .markdown-detail :global(code) {
      font-family: var(--font-mono);
      padding: 0.15em 0.4em;
      border-radius: 5px;
      background: rgba(255, 255, 255, 0.06);
      color: #c4b5fd;
  }

  .markdown-detail :global(pre) {
      overflow-x: auto;
      padding: 16px;
      border-radius: 8px;
      border: 1px solid var(--border-heavy);
      background: rgba(5, 10, 24, 0.82);
  }

  .markdown-detail :global(pre code) {
      padding: 0;
      background: transparent;
      color: #d4d4d8;
  }

  @media (max-width: 900px) {
      .explorer-header {
          align-items: flex-start;
          flex-direction: column;
      }

      .explorer-stats {
          justify-content: flex-start;
      }

      .explorer-grid {
          grid-template-columns: 1fr;
      }

      .artifact-tree {
          max-height: 360px;
          border-right: 0;
          border-bottom: 1px solid var(--border-subtle);
      }
  }
</style>
