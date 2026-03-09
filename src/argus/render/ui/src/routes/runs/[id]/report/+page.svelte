<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { fetchRunStatus, fetchState } from '$lib/api';
  import { renderRichMarkdown } from '$lib/markdown';
  import { uiState } from '$lib/stores.svelte';
  import type {
      FinalDecisionDoc,
      FinalRecommendation,
      PairwiseDecisionArtifact,
      ProposalBrief,
      ResearchArtifactBundle,
      SearchNode,
  } from '$lib/types';

  let currentRunId = $derived($page.params.id);
  let isLoading = $state(true);
  let refreshInterval: number | undefined;

  const statusLabel = () => {
      const status = uiState.searchState?.manifest?.status;
      if (status === 'completed') return 'Completed';
      if (status === 'failed') return 'Failed';
      return 'In Progress';
  };

  const statusClass = () => {
      const status = uiState.searchState?.manifest?.status;
      if (status === 'completed') return 'success';
      if (status === 'failed') return 'failed';
      return 'running';
  };

  const isFinished = () => uiState.searchState?.manifest?.status === 'completed';

  const getNode = (nodeId: string | null | undefined): SearchNode | null => {
      if (!nodeId || !uiState.searchState?.nodes) return null;
      return uiState.searchState.nodes[nodeId] ?? null;
  };

  const finalRecommendation = (): FinalRecommendation | null => uiState.searchState?.final_recommendation ?? null;
  const researchBundle = (): ResearchArtifactBundle | null => uiState.searchState?.research_bundle ?? null;
  const finalDecision = (): FinalDecisionDoc | null => researchBundle()?.final_decision_doc ?? null;
  const proposalBriefs = (): ProposalBrief[] => researchBundle()?.proposal_briefs ?? [];
  const hasResearchArtifacts = () => {
      const bundle = researchBundle();
      return Boolean(
          bundle &&
              (
                  bundle.search_space_frame ||
                  bundle.coverage_ledger ||
                  bundle.scheduler_decisions.length ||
                  bundle.proposal_briefs.length ||
                  bundle.triage_reports.length ||
                  bundle.deep_dive_docs.length ||
                  bundle.adversarial_reviews.length ||
                  bundle.comparison_matrices.length ||
                  bundle.hybrid_assessments.length ||
                  bundle.final_decision_doc
              )
      );
  };

  const winner = () => {
      const recommendation = finalRecommendation();
      return getNode(recommendation?.best_bet_node_id ?? uiState.searchState?.winner_ids?.[0]);
  };

  const conservativeOption = () => getNode(finalRecommendation()?.conservative_node_id);
  const highUpsideOption = () => getNode(finalRecommendation()?.high_upside_node_id);

  const rejectedButInsightful = () =>
      (finalRecommendation()?.rejected_but_insightful_ids ?? [])
          .map((nodeId: string) => getNode(nodeId))
          .filter((node): node is SearchNode => node !== null);

  const recommendationSummary = () =>
      researchBundle()?.decision_summary_markdown ??
      uiState.searchState?.summary_markdown ??
      finalRecommendation()?.summary_markdown ??
      null;

  const researchDecisionMemo = () => researchBundle()?.decision_report_markdown ?? null;
  const pairwiseDecisions = (): PairwiseDecisionArtifact[] => finalRecommendation()?.pairwise_decisions ?? [];

  const objectiveWinnerId = (objectiveName: string, recommendation: FinalRecommendation | null): string | null => {
      if (!recommendation) return null;
      if (objectiveName === 'best_overall') return recommendation.best_bet_node_id;
      if (objectiveName === 'conservative_option') return recommendation.conservative_node_id;
      if (objectiveName === 'high_upside_option') return recommendation.high_upside_node_id;
      return null;
  };

  const pairwiseDecisionGroups = () => {
      const recommendation = finalRecommendation();
      const groups = new Map<
          string,
          {
              selectionLabel: string;
              objectiveName: string;
              objectiveDescription: string;
              winnerNode: SearchNode | null;
              decisions: PairwiseDecisionArtifact[];
          }
      >();

      for (const decision of pairwiseDecisions()) {
          const existing = groups.get(decision.objective_name);
          if (existing) {
              existing.decisions.push(decision);
              continue;
          }
          groups.set(decision.objective_name, {
              selectionLabel: decision.selection_label,
              objectiveName: decision.objective_name,
              objectiveDescription: decision.objective_description,
              winnerNode: getNode(objectiveWinnerId(decision.objective_name, recommendation)),
              decisions: [decision],
          });
      }

      return Array.from(groups.values());
  };

  const searchProfile = () => {
      const value = uiState.searchState?.manifest?.metadata?.search_profile;
      return typeof value === 'string' && value.trim() ? value : null;
  };

  const islandCount = () => {
      const value = uiState.searchState?.manifest?.metadata?.island_count;
      return typeof value === 'number' ? value : null;
  };

  const searchProfileLabel = () => {
      const profile = searchProfile();
      if (profile === 'portfolio') return 'Portfolio';
      if (profile === 'balanced') return 'Balanced';
      if (!profile) return null;
      return profile.charAt(0).toUpperCase() + profile.slice(1);
  };

  const summaryHtml = () => {
      const summary = recommendationSummary();
      return summary ? renderRichMarkdown(summary) : null;
  };

  const decisionMemoHtml = () => {
      const memo = researchDecisionMemo();
      return memo ? renderRichMarkdown(memo) : null;
  };

  const detailList = (values: string[] | undefined | null) =>
      Array.isArray(values) ? values.filter((value) => typeof value === 'string' && value.trim()) : [];

  const proposalById = (proposalId: string | null | undefined): ProposalBrief | null => {
      if (!proposalId) return null;
      return proposalBriefs().find((proposal) => proposal.proposal_id === proposalId) ?? null;
  };

  const proposalLabel = (proposalId: string | null | undefined) => {
      const proposal = proposalById(proposalId);
      return proposal ? `${proposal.title} (${proposal.proposal_id})` : proposalId ?? '—';
  };

  const humanize = (value: string | null | undefined) => {
      if (!value) return '—';
      return value
          .replaceAll('_', ' ')
          .replace(/\b\w/g, (match) => match.toUpperCase());
  };

  const percent = (value: number | null | undefined) =>
      typeof value === 'number' ? `${Math.round(value * 100)}%` : '—';

  $effect(() => {
      if (currentRunId && currentRunId !== uiState.activeRunId) {
          uiState.activeRunId = currentRunId;
          loadData();
      }
  });

  async function loadData() {
      isLoading = true;
      if (uiState.activeRunId) {
          const [state, status] = await Promise.all([
              fetchState(uiState.activeRunId),
              fetchRunStatus(uiState.activeRunId),
          ]);
          if (state) {
              uiState.searchState = state;
          }
          uiState.runStatus = status;
      }
      isLoading = false;
  }

  onMount(() => {
      refreshInterval = window.setInterval(() => {
          if (uiState.runStatus?.status === 'running' || uiState.searchState?.manifest?.status === 'running') {
              void loadData();
          }
      }, 3000);

      if (!uiState.searchState && currentRunId) {
          void loadData();
      } else {
          isLoading = false;
      }

      return () => {
          if (refreshInterval) {
              window.clearInterval(refreshInterval);
          }
      };
  });
</script>

<svelte:head>
  <title>Argus · Final Report</title>
</svelte:head>

<div class="report-container">
  <div class="content-wrapper">
      <header class="page-header">
          <h1>Final Recommendation Report</h1>
          <p>
              Run: <span class="run-id">{currentRunId}</span>
              <span class="status-badge {statusClass()}" style="margin-left: 12px;">{statusLabel()}</span>
          </p>
          {#if !isFinished()}
              <p class="live-note">This report refreshes automatically while the run is still executing.</p>
          {/if}
          {#if searchProfileLabel() || islandCount() !== null}
              <div class="run-meta-row">
                  {#if searchProfileLabel()}
                      <span class="meta-pill">Search Profile: {searchProfileLabel()}</span>
                  {/if}
                  {#if islandCount() !== null}
                      <span class="meta-pill">Islands: {islandCount()}</span>
                  {/if}
              </div>
          {/if}
      </header>

      {#if isLoading}
          <div class="loading-state">Loading run data...</div>
      {:else if !isFinished()}
          <div class="empty-state">
              <div class="empty-icon">⏳</div>
              <h2>Search In Progress</h2>
              <p>The final recommendation will be available once the Argus search loop concludes.</p>
              <a href="/runs/{currentRunId}" class="action-button mt-4" style="text-decoration: none; display: inline-block;">Return to Observer Graph</a>
          </div>
      {:else if !winner() && !hasResearchArtifacts()}
          <div class="empty-state">
              <div class="empty-icon">⚠️</div>
              <h2>No Winner Selected</h2>
              <p>The search loop concluded without designating a winning candidate.</p>
          </div>
      {:else}
          {@const recommendation = finalRecommendation()}
          {@const winnerNode = winner()}
          {@const conservativeNode = conservativeOption()}
          {@const highUpsideNode = highUpsideOption()}
          {@const rejectedNodes = rejectedButInsightful()}
          {@const bundle = researchBundle()}
          {@const researchDecision = finalDecision()}
          {@const pairwiseGroups = pairwiseDecisionGroups()}
          {#if winnerNode}
              <div class="report-card winner-card">
                  <div class="card-header">
                      <div class="winner-trophy">🏆</div>
                      <div>
                          <h2 style="margin: 0; font-size: 24px;">Best Bet</h2>
                          <div class="node-id" style="margin-top: 4px;">Node: {winnerNode.node_id}</div>
                      </div>
                  </div>

                  <div class="section-label">Thesis</div>
                  <p class="thesis-text">{winnerNode.candidate.thesis}</p>
                  
                  <div class="section-label">Mechanism</div>
                  <div class="mechanism-text">{winnerNode.candidate.mechanism}</div>
                  
                  <div class="divider"></div>
                  
                  <div class="section-label">Evaluation Matrix</div>
                  <div class="score-matrix">
                      <div class="score-cell">
                          <span class="score-cell-label">Total Score</span>
                          <span class="score-cell-value" style="color: #34d399;">{winnerNode.score?.total_score?.toFixed(2) || 'N/A'}</span>
                      </div>
                      <div class="score-cell">
                          <span class="score-cell-label">Confidence</span>
                          <span class="score-cell-value">{((winnerNode.score?.confidence_estimate || 0) * 100).toFixed(0)}%</span>
                      </div>
                      <div class="score-cell">
                          <span class="score-cell-label">Usefulness</span>
                          <span class="score-cell-value">{winnerNode.score?.usefulness?.toFixed(2) || '0.00'}</span>
                      </div>
                      <div class="score-cell">
                          <span class="score-cell-label">Distinctiveness</span>
                          <span class="score-cell-value">{winnerNode.score?.distinctiveness?.toFixed(2) || '0.00'}</span>
                      </div>
                  </div>

                  {#if winnerNode.critique?.summary}
                      <div class="section-label">Evaluation Summary</div>
                      <div class="critique-text">{winnerNode.critique.summary}</div>
                  {/if}
              </div>

              {#if recommendationSummary()}
                  <div class="report-card summary-card">
                      <div class="summary-header">
                          <div>
                              <div class="section-label">Recommendation Summary</div>
                              <h2>Decision Memo</h2>
                          </div>
                          <div class="summary-kicker">Structured markdown rendered from persisted artifacts</div>
                      </div>
                      <div class="summary-markdown">{@html summaryHtml()}</div>
                  </div>
              {/if}

              {#if pairwiseGroups.length > 0}
                  <div class="report-card research-card">
                      <div class="summary-header">
                          <div>
                              <div class="section-label">Pairwise Tournament</div>
                              <h2>Finalist Head-To-Head Decisions</h2>
                          </div>
                          <div class="summary-kicker">Structured adaptive-runtime ranking artifacts</div>
                      </div>
                      <div class="artifact-stack">
                          {#each pairwiseGroups as group}
                              <div class="artifact-card">
                                  <div class="artifact-title-row">
                                      <h3>{group.selectionLabel}</h3>
                                      <span class="artifact-tag">{humanize(group.objectiveName)}</span>
                                  </div>
                                  <p class="detail-paragraph">{group.objectiveDescription}</p>
                                  {#if group.winnerNode}
                                      <p class="detail-paragraph">
                                          <strong>Winner:</strong> {group.winnerNode.candidate.thesis} ({group.winnerNode.node_id})
                                      </p>
                                  {/if}
                                  <div class="artifact-grid compact-grid" style="margin-top: 18px;">
                                      {#each group.decisions as decision}
                                          {@const leftNode = getNode(decision.left_node_id)}
                                          {@const rightNode = getNode(decision.right_node_id)}
                                          {@const winnerSideNode = getNode(decision.winner_node_id)}
                                          <div class="artifact-card nested-card">
                                              <div class="artifact-title-row">
                                                  <h3>{leftNode?.candidate.thesis ?? decision.left_node_id}</h3>
                                                  <span class="artifact-tag">vs {rightNode?.node_id ?? decision.right_node_id}</span>
                                              </div>
                                              <p class="detail-paragraph">
                                                  <strong>Matchup:</strong>
                                                  {leftNode?.node_id ?? decision.left_node_id} vs {rightNode?.node_id ?? decision.right_node_id}
                                              </p>
                                              <p class="detail-paragraph">
                                                  <strong>Winner:</strong> {winnerSideNode?.candidate.thesis ?? decision.winner_node_id}
                                              </p>
                                              <p class="detail-paragraph">{decision.summary}</p>
                                              <div class="metric-row">
                                                  <span>Confidence {percent(decision.confidence)}</span>
                                              </div>
                                              {#if decision.decisive_advantages.length > 0}
                                                  <div class="section-label" style="margin-top: 18px;">Decisive Advantages</div>
                                                  <ul class="detail-list">
                                                      {#each decision.decisive_advantages as item}
                                                          <li>{item}</li>
                                                      {/each}
                                                  </ul>
                                              {/if}
                                              {#if decision.decisive_risks.length > 0}
                                                  <div class="section-label" style="margin-top: 18px;">Decisive Risks</div>
                                                  <ul class="detail-list">
                                                      {#each decision.decisive_risks as item}
                                                          <li>{item}</li>
                                                      {/each}
                                                  </ul>
                                              {/if}
                                          </div>
                                      {/each}
                                  </div>
                              </div>
                          {/each}
                      </div>
                  </div>
              {/if}

              {#if bundle?.search_space_frame}
                  <div class="report-card research-card">
                      <div class="summary-header">
                          <div>
                              <div class="section-label">Research Artifact Bundle</div>
                              <h2>Search Space Frame</h2>
                          </div>
                          <div class="summary-kicker">Typed framing persisted under the run directory</div>
                      </div>
                      <p class="research-lead">{bundle.search_space_frame.problem_statement}</p>
                      <div class="option-grid details-grid">
                          <div class="report-card detail-card nested-card">
                              <div class="section-label">Target Decision</div>
                              <p class="detail-paragraph">{bundle.search_space_frame.target_decision}</p>
                          </div>
                          <div class="report-card detail-card nested-card">
                              <div class="section-label">Baseline Options</div>
                              <ul class="detail-list">
                                  {#each detailList(bundle.search_space_frame.baseline_options) as item}
                                      <li>{item}</li>
                                  {/each}
                              </ul>
                          </div>
                          <div class="report-card detail-card nested-card">
                              <div class="section-label">Hard Gates</div>
                              <ul class="detail-list">
                                  {#each detailList(bundle.search_space_frame.hard_gates) as item}
                                      <li>{item}</li>
                                  {/each}
                              </ul>
                          </div>
                          <div class="report-card detail-card nested-card">
                              <div class="section-label">Soft Criteria</div>
                              <ul class="detail-list">
                                  {#each detailList(bundle.search_space_frame.soft_criteria) as item}
                                      <li>{item}</li>
                                  {/each}
                              </ul>
                          </div>
                      </div>
                      <div class="artifact-grid">
                          {#each bundle.search_space_frame.axes as axis}
                              <div class="artifact-card">
                                  <div class="artifact-title-row">
                                      <h3>{axis.label}</h3>
                                      <span class="artifact-tag">{axis.axis_id}</span>
                                  </div>
                                  <p class="detail-paragraph">{axis.description}</p>
                                  <ul class="detail-list">
                                      {#each axis.options as option}
                                          <li>{option}</li>
                                      {/each}
                                  </ul>
                              </div>
                          {/each}
                      </div>
                      {#if detailList(bundle.search_space_frame.coverage_plan).length > 0}
                          <div class="section-label" style="margin-top: 28px;">Coverage Plan</div>
                          <ul class="detail-list">
                              {#each detailList(bundle.search_space_frame.coverage_plan) as item}
                                  <li>{item}</li>
                              {/each}
                          </ul>
                      {/if}
                  </div>
              {/if}

              {#if bundle?.coverage_ledger}
                  <div class="report-card research-card">
                      <div class="summary-header">
                          <div>
                              <div class="section-label">Coverage Ledger</div>
                              <h2>Cell Status</h2>
                          </div>
                          <div class="summary-kicker">{bundle.coverage_ledger.cells.length} cells tracked</div>
                      </div>
                      <p class="research-lead">{bundle.coverage_ledger.coverage_summary}</p>
                      <div class="artifact-grid">
                          {#each bundle.coverage_ledger.cells as cell}
                              <div class="artifact-card">
                                  <div class="artifact-title-row">
                                      <h3>{cell.label}</h3>
                                      <span class="artifact-tag">{humanize(cell.coverage_status)}</span>
                                  </div>
                                  <p class="detail-paragraph">{cell.hypothesis}</p>
                                  <div class="metric-row">
                                      <span>Uncertainty {percent(cell.uncertainty)}</span>
                                      <span>Hard-Gate Risk {percent(cell.hard_gate_risk)}</span>
                                      <span>Evidence {percent(cell.evidence_strength)}</span>
                                  </div>
                                  <div class="section-label" style="margin-top: 18px;">Axis Assignments</div>
                                  <ul class="detail-list">
                                      {#each Object.entries(cell.axis_assignments) as [axisId, choice]}
                                          <li><strong>{humanize(axisId)}:</strong> {choice}</li>
                                      {/each}
                                  </ul>
                                  {#if cell.incumbent_proposal_ids.length > 0}
                                      <div class="section-label" style="margin-top: 18px;">Incumbents</div>
                                      <ul class="detail-list">
                                          {#each cell.incumbent_proposal_ids as proposalId}
                                              <li>{proposalLabel(proposalId)}</li>
                                          {/each}
                                      </ul>
                                  {/if}
                              </div>
                          {/each}
                      </div>
                      {#if detailList(bundle.coverage_ledger.next_questions).length > 0}
                          <div class="section-label" style="margin-top: 28px;">Open Coverage Questions</div>
                          <ul class="detail-list">
                              {#each detailList(bundle.coverage_ledger.next_questions) as item}
                                  <li>{item}</li>
                              {/each}
                          </ul>
                      {/if}
                  </div>
              {/if}

              {#if bundle && (bundle.proposal_briefs.length > 0 || bundle.triage_reports.length > 0 || bundle.scheduler_decisions.length > 0)}
                  <div class="report-card research-card">
                      <div class="summary-header">
                          <div>
                              <div class="section-label">Research Trace</div>
                              <h2>Families, Triage, And Scheduling</h2>
                          </div>
                          <div class="summary-kicker">Directly rendered from typed research artifacts</div>
                      </div>
                      {#if bundle.proposal_briefs.length > 0}
                          <div class="artifact-grid">
                              {#each bundle.proposal_briefs as proposal}
                                  <div class="artifact-card">
                                      <div class="artifact-title-row">
                                          <h3>{proposal.title}</h3>
                                          <span class="artifact-tag">{proposal.proposal_id}</span>
                                      </div>
                                      <p class="detail-paragraph">{proposal.summary}</p>
                                      <p class="detail-paragraph"><strong>Thesis:</strong> {proposal.candidate.thesis}</p>
                                      <p class="detail-paragraph"><strong>Seed rationale:</strong> {proposal.seed_rationale}</p>
                                      {#if proposal.open_questions.length > 0}
                                          <div class="section-label" style="margin-top: 18px;">Open Questions</div>
                                          <ul class="detail-list">
                                              {#each proposal.open_questions as item}
                                                  <li>{item}</li>
                                              {/each}
                                          </ul>
                                      {/if}
                                  </div>
                              {/each}
                          </div>
                      {/if}
                      {#if bundle.triage_reports.length > 0}
                          {@const latestTriage = bundle.triage_reports[bundle.triage_reports.length - 1]}
                          <div class="section-label" style="margin-top: 28px;">Latest Triage</div>
                          <p class="research-lead">{latestTriage.summary}</p>
                          <div class="artifact-grid compact-grid">
                              {#each latestTriage.decisions as decision}
                                  <div class="artifact-card">
                                      <div class="artifact-title-row">
                                          <h3>{proposalLabel(decision.proposal_id)}</h3>
                                          <span class="artifact-tag">{humanize(decision.disposition)}</span>
                                      </div>
                                      <p class="detail-paragraph">{decision.rationale}</p>
                                      {#if decision.follow_up}
                                          <p class="detail-paragraph"><strong>Follow-up:</strong> {decision.follow_up}</p>
                                      {/if}
                                  </div>
                              {/each}
                          </div>
                      {/if}
                      {#if bundle.scheduler_decisions.length > 0}
                          <div class="section-label" style="margin-top: 28px;">Scheduler Decisions</div>
                          <div class="artifact-grid compact-grid">
                              {#each bundle.scheduler_decisions as decision}
                                  <div class="artifact-card">
                                      <div class="artifact-title-row">
                                          <h3>{humanize(decision.action)}</h3>
                                          <span class="artifact-tag">Priority {percent(decision.priority_score)}</span>
                                      </div>
                                      <p class="detail-paragraph">{decision.rationale}</p>
                                  </div>
                              {/each}
                          </div>
                      {/if}
                  </div>
              {/if}

              {#if bundle && (bundle.deep_dive_docs.length > 0 || bundle.adversarial_reviews.length > 0)}
                  <div class="option-grid details-grid">
                      {#if bundle.deep_dive_docs.length > 0}
                          <div class="report-card detail-card research-card">
                              <div class="section-label">Deep Dives</div>
                              <div class="artifact-stack">
                                  {#each bundle.deep_dive_docs as doc}
                                      <div class="artifact-card">
                                          <div class="artifact-title-row">
                                              <h3>{doc.title}</h3>
                                              <span class="artifact-tag">{proposalLabel(doc.proposal_id)}</span>
                                          </div>
                                          <p class="detail-paragraph">{doc.executive_summary}</p>
                                          <p class="detail-paragraph">{doc.detailed_mechanism}</p>
                                          {#if doc.implementation_plan.length > 0}
                                              <div class="section-label" style="margin-top: 18px;">Implementation Plan</div>
                                              <ul class="detail-list">
                                                  {#each doc.implementation_plan as item}
                                                      <li>{item}</li>
                                                  {/each}
                                              </ul>
                                          {/if}
                                      </div>
                                  {/each}
                              </div>
                          </div>
                      {/if}
                      {#if bundle.adversarial_reviews.length > 0}
                          <div class="report-card detail-card research-card">
                              <div class="section-label">Adversarial Reviews</div>
                              <div class="artifact-stack">
                                  {#each bundle.adversarial_reviews as review}
                                      <div class="artifact-card">
                                          <div class="artifact-title-row">
                                              <h3>{proposalLabel(review.proposal_id)}</h3>
                                              <span class="artifact-tag">{review.verdict}</span>
                                          </div>
                                          <p class="detail-paragraph">{review.summary}</p>
                                          <div class="metric-row">
                                              <span>Confidence {percent(review.confidence)}</span>
                                          </div>
                                          {#if review.failure_modes.length > 0}
                                              <div class="section-label" style="margin-top: 18px;">Failure Modes</div>
                                              <ul class="detail-list">
                                                  {#each review.failure_modes as item}
                                                      <li>{item}</li>
                                                  {/each}
                                              </ul>
                                          {/if}
                                          {#if review.mitigations.length > 0}
                                              <div class="section-label" style="margin-top: 18px;">Mitigations</div>
                                              <ul class="detail-list">
                                                  {#each review.mitigations as item}
                                                      <li>{item}</li>
                                                  {/each}
                                              </ul>
                                          {/if}
                                      </div>
                                  {/each}
                              </div>
                          </div>
                      {/if}
                  </div>
              {/if}

              {#if bundle && (bundle.comparison_matrices.length > 0 || bundle.hybrid_assessments.length > 0 || researchDecision)}
                  <div class="report-card research-card">
                      <div class="summary-header">
                          <div>
                              <div class="section-label">Decision Artifacts</div>
                              <h2>Comparison And Final Decision</h2>
                          </div>
                          <div class="summary-kicker">Pairwise comparison and decision-grade output</div>
                      </div>
                      {#if bundle.comparison_matrices.length > 0}
                          {@const latestMatrix = bundle.comparison_matrices[bundle.comparison_matrices.length - 1]}
                          <p class="research-lead">{latestMatrix.summary}</p>
                          <div class="comparison-table-wrap">
                              <table class="comparison-table">
                                  <thead>
                                      <tr>
                                          <th>Proposal</th>
                                          {#each latestMatrix.criteria as criterion}
                                              <th>{humanize(criterion)}</th>
                                          {/each}
                                          <th>Takeaway</th>
                                      </tr>
                                  </thead>
                                  <tbody>
                                      {#each latestMatrix.rows as row}
                                          <tr>
                                              <td>{proposalLabel(row.proposal_id)}</td>
                                              {#each latestMatrix.criteria as criterion}
                                                  <td>{row.criterion_scores[criterion]?.toFixed(2) ?? '—'}</td>
                                              {/each}
                                              <td>{row.takeaway}</td>
                                          </tr>
                                      {/each}
                                  </tbody>
                              </table>
                          </div>
                      {/if}
                      {#if bundle.hybrid_assessments.length > 0}
                          <div class="section-label" style="margin-top: 28px;">Hybrid Assessments</div>
                          <div class="artifact-grid compact-grid">
                              {#each bundle.hybrid_assessments as hybrid}
                                  <div class="artifact-card">
                                      <div class="artifact-title-row">
                                          <h3>{hybrid.hybrid_name}</h3>
                                          <span class="artifact-tag">{humanize(hybrid.verdict)}</span>
                                      </div>
                                      <p class="detail-paragraph">{hybrid.summary}</p>
                                      <p class="detail-paragraph"><strong>Seam:</strong> {hybrid.seam_hypothesis}</p>
                                      <p class="detail-paragraph"><strong>Complexity tax:</strong> {hybrid.complexity_tax}</p>
                                  </div>
                              {/each}
                          </div>
                      {/if}
                      {#if researchDecision}
                          <div class="option-grid details-grid" style="margin-top: 24px;">
                              <div class="report-card detail-card nested-card">
                                  <div class="section-label">Selection</div>
                                  <ul class="detail-list">
                                      <li><strong>Selected:</strong> {proposalLabel(researchDecision.selected_proposal_id)}</li>
                                      {#if researchDecision.runner_up_proposal_id}
                                          <li><strong>Runner-up:</strong> {proposalLabel(researchDecision.runner_up_proposal_id)}</li>
                                      {/if}
                                      {#if researchDecision.conservative_proposal_id}
                                          <li><strong>Conservative:</strong> {proposalLabel(researchDecision.conservative_proposal_id)}</li>
                                      {/if}
                                      {#if researchDecision.high_upside_proposal_id}
                                          <li><strong>High-upside:</strong> {proposalLabel(researchDecision.high_upside_proposal_id)}</li>
                                      {/if}
                                  </ul>
                              </div>
                              <div class="report-card detail-card nested-card">
                                  <div class="section-label">Decision Rule</div>
                                  <p class="detail-paragraph">{researchDecision.decision_rule}</p>
                              </div>
                              {#if detailList(researchDecision.top_risks).length > 0}
                                  <div class="report-card detail-card nested-card">
                                      <div class="section-label">Top Risks</div>
                                      <ul class="detail-list">
                                          {#each detailList(researchDecision.top_risks) as item}
                                              <li>{item}</li>
                                          {/each}
                                      </ul>
                                  </div>
                              {/if}
                              {#if detailList(researchDecision.mitigations).length > 0}
                                  <div class="report-card detail-card nested-card">
                                      <div class="section-label">Mitigations</div>
                                      <ul class="detail-list">
                                          {#each detailList(researchDecision.mitigations) as item}
                                              <li>{item}</li>
                                          {/each}
                                      </ul>
                                  </div>
                              {/if}
                          </div>
                      {/if}
                  </div>
              {/if}

              {#if researchDecisionMemo() && researchDecisionMemo() !== recommendationSummary()}
                  <div class="report-card summary-card">
                      <div class="summary-header">
                          <div>
                              <div class="section-label">Research Memo</div>
                              <h2>Final Decision Report</h2>
                          </div>
                          <div class="summary-kicker">Provider-authored memo from the full research bundle</div>
                      </div>
                      <div class="summary-markdown">{@html decisionMemoHtml()}</div>
                  </div>
              {/if}

              {#if conservativeNode || highUpsideNode || rejectedNodes.length > 0}
                  <div class="option-grid">
                      {#if conservativeNode}
                          <div class="report-card option-card">
                              <div class="section-label">Conservative Option</div>
                              <div class="node-id">{conservativeNode.node_id}</div>
                              <p class="option-thesis">{conservativeNode.candidate.thesis}</p>
                          </div>
                      {/if}
                      {#if highUpsideNode}
                          <div class="report-card option-card">
                              <div class="section-label">High Upside Option</div>
                              <div class="node-id">{highUpsideNode.node_id}</div>
                              <p class="option-thesis">{highUpsideNode.candidate.thesis}</p>
                          </div>
                      {/if}
                      {#if rejectedNodes.length > 0}
                          <div class="report-card option-card">
                              <div class="section-label">Rejected But Insightful</div>
                              <div class="rejected-list">
                                  {#each rejectedNodes as node}
                                      <div class="rejected-item">
                                          <div class="node-id">{node.node_id}</div>
                                          <p class="option-thesis">{node.candidate.thesis}</p>
                                      </div>
                                  {/each}
                              </div>
                          </div>
                      {/if}
                  </div>
              {/if}

              {#if recommendation}
                  <div class="option-grid details-grid">
                      {#if detailList(recommendation.assumptions).length > 0}
                          <div class="report-card detail-card">
                              <div class="section-label">Assumptions</div>
                              <ul class="detail-list">
                                  {#each detailList(recommendation.assumptions) as item}
                                      <li>{item}</li>
                                  {/each}
                              </ul>
                          </div>
                      {/if}
                      {#if detailList(recommendation.failure_modes).length > 0}
                          <div class="report-card detail-card">
                              <div class="section-label">Failure Modes</div>
                              <ul class="detail-list">
                                  {#each detailList(recommendation.failure_modes) as item}
                                      <li>{item}</li>
                                  {/each}
                              </ul>
                          </div>
                      {/if}
                      {#if detailList(recommendation.reversal_conditions).length > 0}
                          <div class="report-card detail-card">
                              <div class="section-label">Reversal Conditions</div>
                              <ul class="detail-list">
                                  {#each detailList(recommendation.reversal_conditions) as item}
                                      <li>{item}</li>
                                  {/each}
                              </ul>
                          </div>
                      {/if}
                      {#if detailList(recommendation.next_experiments).length > 0}
                          <div class="report-card detail-card">
                              <div class="section-label">Next Experiments</div>
                              <ul class="detail-list">
                                  {#each detailList(recommendation.next_experiments) as item}
                                      <li>{item}</li>
                                  {/each}
                              </ul>
                          </div>
                      {/if}
                  </div>
              {/if}
          {/if}
      {/if}
  </div>
</div>

<style>
  .report-container {
      flex: 1;
      overflow-y: auto;
      padding: 40px;
      background: var(--bg-base);
  }

  .content-wrapper {
      max-width: 900px;
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
      display: flex;
      align-items: center;
  }

  .live-note {
      margin-top: 10px;
      color: var(--ink-tertiary);
      font-size: 13px;
      font-family: var(--font-mono);
      letter-spacing: 0.02em;
  }

  .run-meta-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
  }

  .meta-pill {
      display: inline-flex;
      align-items: center;
      padding: 7px 12px;
      border-radius: 999px;
      border: 1px solid var(--border-subtle);
      background: rgba(255, 255, 255, 0.03);
      color: var(--ink-secondary);
      font-family: var(--font-mono);
      font-size: 11px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
  }

  :global(.light-mode) .meta-pill {
      background: rgba(0, 0, 0, 0.03);
  }

  .run-id {
      font-family: var(--font-mono);
      color: var(--ink-primary);
      margin-left: 8px;
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

  .status-badge.success {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid #059669;
  }

  .status-badge.failed {
      background: rgba(239, 68, 68, 0.15);
      color: #f87171;
      border: 1px solid #dc2626;
  }
  
  .node-id {
      font-family: var(--font-mono);
      font-size: 13px;
      color: var(--ink-secondary);
  }

  .report-card {
      background: var(--surface-color);
      border: 1px solid var(--border-heavy);
      border-radius: 12px;
      padding: 40px;
      box-shadow: var(--shadow-glow);
  }
  
  .winner-card {
      border-color: rgba(16, 185, 129, 0.3);
      background: linear-gradient(180deg, rgba(16, 185, 129, 0.05) 0%, rgba(0,0,0,0) 200px), var(--surface-color);
  }

  .summary-card,
  .option-card,
  .detail-card {
      margin-top: 24px;
      padding: 28px;
  }

  .research-card {
      margin-top: 24px;
  }

  .nested-card {
      margin-top: 0;
      padding: 24px;
      background: rgba(255, 255, 255, 0.02);
      box-shadow: none;
  }

  .summary-card {
      position: relative;
      overflow: hidden;
      background:
          radial-gradient(circle at top right, rgba(96, 165, 250, 0.14), transparent 32%),
          linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0)),
          var(--surface-color);
  }

  .summary-card::before {
      content: '';
      position: absolute;
      inset: 0 auto 0 0;
      width: 4px;
      background: linear-gradient(180deg, #60a5fa, #34d399 55%, transparent);
      opacity: 0.9;
  }

  .card-header {
      display: flex;
      align-items: center;
      gap: 20px;
      margin-bottom: 40px;
  }

  .winner-trophy {
      font-size: 48px;
      line-height: 1;
      filter: drop-shadow(0 4px 10px rgba(0,0,0,0.5));
  }

  .section-label {
      font-size: 12px;
      font-weight: 600;
      color: var(--ink-tertiary);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      margin-bottom: 12px;
  }

  .thesis-text {
      font-size: 20px;
      font-weight: 500;
      line-height: 1.5;
      color: var(--ink-primary);
      margin-bottom: 24px;
  }

  .mechanism-text {
      font-size: 16px;
      line-height: 1.6;
      color: var(--ink-secondary);
      margin-bottom: 32px;
      white-space: pre-wrap;
  }

  .critique-text {
      font-size: 15px;
      line-height: 1.6;
      color: var(--ink-primary);
      background: rgba(255, 255, 255, 0.03);
      padding: 20px;
      border-radius: 8px;
      border: 1px solid var(--border-subtle);
  }

  :global(.light-mode) .critique-text {
      background: rgba(0, 0, 0, 0.02);
  }

  .divider {
      height: 1px;
      background: var(--border-subtle);
      margin: 40px 0;
  }

  .summary-markdown {
      font-size: 16px;
      line-height: 1.8;
      color: var(--ink-primary);
      max-width: 72ch;
  }

  .summary-header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 24px;
      margin-bottom: 24px;
      padding-bottom: 18px;
      border-bottom: 1px solid var(--border-subtle);
  }

  .summary-header h2 {
      margin: 0;
      font-size: clamp(28px, 4vw, 40px);
      line-height: 1;
      letter-spacing: -0.03em;
      color: var(--ink-primary);
  }

  .summary-kicker {
      max-width: 24ch;
      text-align: right;
      font-size: 11px;
      line-height: 1.5;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--ink-tertiary);
      font-family: var(--font-mono);
  }

  @media (max-width: 720px) {
      .summary-header {
          align-items: flex-start;
          flex-direction: column;
      }

      .summary-kicker {
          max-width: none;
          text-align: left;
      }
  }

  .summary-markdown :global(h1),
  .summary-markdown :global(h2),
  .summary-markdown :global(h3),
  .summary-markdown :global(h4) {
      margin: 1.75em 0 0.7em;
      line-height: 1.12;
      letter-spacing: -0.03em;
      color: var(--ink-primary);
  }

  .summary-markdown :global(h1) {
      font-size: clamp(32px, 4vw, 46px);
  }

  .summary-markdown :global(h2) {
      font-size: clamp(24px, 3vw, 30px);
      padding-top: 0.4em;
      border-top: 1px solid var(--border-subtle);
  }

  .summary-markdown :global(h3) {
      font-size: 19px;
  }

  .summary-markdown :global(p) {
      margin: 0 0 1.1em;
      color: var(--ink-secondary);
      text-wrap: pretty;
  }

  .summary-markdown :global(strong) {
      color: var(--ink-primary);
      font-weight: 700;
  }

  .summary-markdown :global(em) {
      color: var(--ink-primary);
      font-style: italic;
  }

  .summary-markdown :global(ul),
  .summary-markdown :global(ol) {
      margin: 0 0 1.4em;
      padding-left: 1.4rem;
      color: var(--ink-secondary);
  }

  .summary-markdown :global(li) {
      margin: 0.45em 0;
      padding-left: 0.2rem;
  }

  .summary-markdown :global(li::marker) {
      color: #60a5fa;
  }

  .summary-markdown :global(blockquote) {
      margin: 1.6em 0;
      padding: 1rem 1.1rem 1rem 1.25rem;
      border-left: 3px solid rgba(96, 165, 250, 0.7);
      background: rgba(96, 165, 250, 0.08);
      border-radius: 0 14px 14px 0;
  }

  .summary-markdown :global(blockquote p) {
      color: var(--ink-primary);
      margin-bottom: 0.7em;
  }

  .summary-markdown :global(blockquote p:last-child) {
      margin-bottom: 0;
  }

  .summary-markdown :global(code) {
      font-family: var(--font-mono);
      font-size: 0.92em;
      padding: 0.15em 0.42em;
      border-radius: 0.45rem;
      background: rgba(255, 255, 255, 0.06);
      color: #c4b5fd;
  }

  .summary-markdown :global(pre) {
      margin: 1.5em 0;
      padding: 1.1rem 1.2rem 1.2rem;
      border-radius: 16px;
      border: 1px solid var(--border-heavy);
      background: rgba(5, 10, 24, 0.82);
      overflow-x: auto;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
  }

  .summary-markdown :global(pre code) {
      display: block;
      padding: 0;
      background: transparent;
      color: #d4d4d8;
      line-height: 1.65;
  }

  .summary-markdown :global(.code-language) {
      margin-bottom: 0.9rem;
      font-family: var(--font-mono);
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #93c5fd;
  }

  .summary-markdown :global(a) {
      color: #7dd3fc;
      text-decoration: none;
      border-bottom: 1px solid rgba(125, 211, 252, 0.4);
  }

  .summary-markdown :global(a:hover) {
      border-bottom-color: rgba(125, 211, 252, 0.85);
  }

  .summary-markdown :global(hr) {
      border: 0;
      height: 1px;
      margin: 1.8em 0;
      background: linear-gradient(90deg, transparent, var(--border-heavy), transparent);
  }

  :global(.light-mode) .summary-card {
      background:
          radial-gradient(circle at top right, rgba(37, 99, 235, 0.1), transparent 32%),
          linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(255, 255, 255, 0.86)),
          var(--surface-color);
  }

  :global(.light-mode) .summary-markdown :global(code) {
      background: rgba(0, 0, 0, 0.05);
      color: #6d28d9;
  }

  :global(.light-mode) .summary-markdown :global(pre) {
      background: #10131c;
  }

  :global(.light-mode) .summary-markdown :global(blockquote) {
      background: rgba(37, 99, 235, 0.06);
  }

  .option-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 24px;
      margin-top: 24px;
  }

  .details-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  @media (max-width: 900px) {
      .option-grid,
      .details-grid {
          grid-template-columns: 1fr;
      }
  }

  .option-thesis {
      margin: 12px 0 0;
      color: var(--ink-primary);
      line-height: 1.6;
  }

  .research-lead {
      margin: 0;
      color: var(--ink-primary);
      line-height: 1.7;
      font-size: 16px;
  }

  .rejected-list {
      display: flex;
      flex-direction: column;
      gap: 16px;
  }

  .rejected-item + .rejected-item {
      padding-top: 16px;
      border-top: 1px solid var(--border-subtle);
  }

  .detail-list {
      margin: 0;
      padding-left: 20px;
      color: var(--ink-primary);
      line-height: 1.7;
  }

  .detail-paragraph {
      margin: 0;
      color: var(--ink-secondary);
      line-height: 1.7;
  }

  .artifact-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
      margin-top: 24px;
  }

  .compact-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .artifact-stack {
      display: flex;
      flex-direction: column;
      gap: 18px;
  }

  @media (max-width: 960px) {
      .artifact-grid,
      .compact-grid {
          grid-template-columns: 1fr;
      }
  }

  .artifact-card {
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 20px;
      background: rgba(255, 255, 255, 0.03);
  }

  :global(.light-mode) .artifact-card,
  :global(.light-mode) .nested-card {
      background: rgba(0, 0, 0, 0.02);
  }

  .artifact-title-row {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
  }

  .artifact-title-row h3 {
      margin: 0;
      font-size: 17px;
      color: var(--ink-primary);
  }

  .artifact-tag {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 999px;
      border: 1px solid var(--border-subtle);
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: var(--ink-tertiary);
      white-space: nowrap;
  }

  .metric-row {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 14px;
      color: var(--ink-tertiary);
      font-family: var(--font-mono);
      font-size: 12px;
  }

  .comparison-table-wrap {
      margin-top: 24px;
      overflow-x: auto;
      border: 1px solid var(--border-heavy);
      border-radius: 12px;
  }

  .comparison-table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      min-width: 720px;
  }

  .comparison-table th,
  .comparison-table td {
      padding: 14px 16px;
      border-bottom: 1px solid var(--border-subtle);
      vertical-align: top;
  }

  .comparison-table th {
      color: var(--ink-tertiary);
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-family: var(--font-mono);
      background: rgba(255, 255, 255, 0.03);
  }

  :global(.light-mode) .comparison-table th {
      background: rgba(0, 0, 0, 0.03);
  }

  .comparison-table tbody tr:last-child td {
      border-bottom: none;
  }

  /* Matrix Layout */
  .score-matrix {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 32px;
  }

  @media (max-width: 768px) {
      .score-matrix {
          grid-template-columns: 1fr 1fr;
      }
  }

  .score-cell {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 20px;
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
      margin-bottom: 8px;
  }

  .score-cell-value {
      font-family: var(--font-mono);
      font-size: 28px;
      font-weight: 600;
      color: var(--ink-primary);
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
      margin-bottom: 24px;
      opacity: 0.8;
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
  
  .action-button {
      background: var(--ink-primary);
      color: var(--bg-base);
      border: none;
      padding: 10px 20px;
      border-radius: 6px;
      font-family: var(--font-ui);
      font-weight: 600;
      font-size: 14px;
      cursor: pointer;
      margin-top: 16px;
      transition: opacity 0.2s;
  }

  .action-button:hover {
      opacity: 0.9;
  }
</style>
