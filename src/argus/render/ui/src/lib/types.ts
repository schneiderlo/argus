export type RunStatus = 'created' | 'running' | 'completed' | 'failed';

export interface RunManifest {
    run_id: string;
    provider_name: string;
    budget: number;
    status: RunStatus;
    created_at: string;
    updated_at: string;
    metadata: Record<string, unknown>;
    error: string | null;
}

export interface ProblemSpec {
    request: string;
    constraints: string[];
    success_criteria: string[];
    context: Record<string, unknown>;
}

export interface Candidate {
    thesis: string;
    mechanism: string;
    assumptions: string[];
    strengths: string[];
    failure_modes: string[];
    unknowns: string[];
    implementation_shape: string | null;
    evidence: string[];
}

export interface ScoreVector {
    hard_constraint_pass: boolean;
    hard_constraint_reasons: string[];
    distinctiveness: number;
    usefulness: number;
    specificity: number;
    plausibility: number;
    implementation_tractability: number;
    upside: number;
    adversarial_robustness: number;
    evidence_quality: number;
    total_score: number;
    confidence_estimate: number;
}

export interface Critique {
    hidden_dependencies: string[];
    kill_shots: string[];
    sharp_edges: string[];
    summary: string;
}

export interface SearchNode {
    node_id: string;
    parent_ids: string[];
    depth: number;
    action_type: string;
    provider_name: string;
    island_id?: string | null;
    candidate: Candidate;
    score?: ScoreVector | null;
    critique?: Critique | null;
    novelty_score: number;
    lifecycle_status: string;
    metadata: Record<string, unknown>;
    termination_reason?: string;
    created_at: string;
}

export interface SearchIsland {
    island_id: string;
    label: string;
    description: string;
    archive_ids: string[];
    frontier_ids: string[];
    pruned_ids: string[];
}

export interface LearningNote {
    note_id: string;
    note_type: string;
    text: string;
    source_node_ids: string[];
}

export interface FinalRecommendation {
    best_bet_node_id: string;
    conservative_node_id: string | null;
    high_upside_node_id: string | null;
    rejected_but_insightful_ids: string[];
    summary_markdown: string;
    next_experiments: string[];
    assumptions: string[];
    failure_modes: string[];
    reversal_conditions: string[];
    pairwise_decisions: PairwiseDecisionArtifact[];
}

export interface PairwiseDecisionArtifact {
    selection_label: string;
    objective_name: string;
    objective_description: string;
    left_node_id: string;
    right_node_id: string;
    winner_node_id: string;
    summary: string;
    decisive_advantages: string[];
    decisive_risks: string[];
    confidence: number;
}

export interface SearchAxis {
    axis_id: string;
    label: string;
    description: string;
    options: string[];
    rationale?: string;
}

export interface SearchCell {
    cell_id: string;
    label: string;
    axis_assignments: Record<string, string>;
    hypothesis: string;
    coverage_status: string;
    uncertainty: number;
    hard_gate_risk: number;
    evidence_strength: number;
    incumbent_proposal_ids: string[];
    notes: string[];
}

export interface SearchSpaceFrame {
    frame_id: string;
    problem_statement: string;
    target_decision: string;
    hard_gates: string[];
    soft_criteria: string[];
    baseline_options: string[];
    axes: SearchAxis[];
    coverage_plan: string[];
    notes: string[];
}

export interface CoverageLedger {
    ledger_id: string;
    frame_id: string;
    cells: SearchCell[];
    coverage_summary: string;
    next_questions: string[];
    updated_at: string;
}

export interface ProposalBrief {
    proposal_id: string;
    cell_id: string;
    title: string;
    summary: string;
    candidate: Candidate;
    seed_rationale: string;
    open_questions: string[];
    evidence: string[];
    parent_node_ids: string[];
}

export interface ProposalTriageDecision {
    proposal_id: string;
    disposition: string;
    rationale: string;
    merged_into_proposal_id?: string;
    follow_up?: string;
}

export interface TriageReport {
    report_id: string;
    frame_id: string;
    decisions: ProposalTriageDecision[];
    survivor_ids: string[];
    unexplored_cell_ids: string[];
    summary: string;
    next_actions: string[];
}

export interface DeepDiveDoc {
    doc_id: string;
    proposal_id: string;
    title: string;
    executive_summary: string;
    detailed_mechanism: string;
    implementation_plan: string[];
    key_unknowns: string[];
    supporting_evidence: string[];
    assumptions: string[];
}

export interface AdversarialReview {
    review_id: string;
    proposal_id: string;
    thesis_under_test: string;
    hidden_dependencies: string[];
    failure_modes: string[];
    mitigations: string[];
    summary: string;
    verdict: string;
    confidence: number;
    evidence: string[];
}

export interface ComparisonMatrixRow {
    proposal_id: string;
    criterion_scores: Record<string, number>;
    advantages: string[];
    liabilities: string[];
    takeaway: string;
}

export interface ComparisonMatrix {
    matrix_id: string;
    frame_id: string;
    criteria: string[];
    rows: ComparisonMatrixRow[];
    summary: string;
}

export interface HybridAssessment {
    assessment_id: string;
    source_proposal_ids: string[];
    hybrid_name: string;
    seam_hypothesis: string;
    repaired_failure_mode: string;
    complementary_strengths: string[];
    complexity_tax: string;
    expected_upside: string;
    open_questions: string[];
    verdict: string;
    summary: string;
}

export interface FinalDecisionDoc {
    decision_id: string;
    frame_id: string;
    selected_proposal_id: string;
    runner_up_proposal_id?: string;
    conservative_proposal_id?: string;
    high_upside_proposal_id?: string;
    summary: string;
    decision_rule: string;
    assumptions: string[];
    top_risks: string[];
    mitigations: string[];
    first_spike: string[];
    kill_criteria: string[];
    next_experiments: string[];
    reversal_conditions: string[];
    rejected_proposal_ids: string[];
}

export interface SchedulerDecision {
    decision_id: string;
    action: string;
    rationale: string;
    remaining_budget: number;
    priority_score: number;
    target_cell_ids: string[];
    target_proposal_ids: string[];
    signals: string[];
    selected_at: string;
}

export interface ResearchArtifactBundle {
    search_space_frame?: SearchSpaceFrame | null;
    coverage_ledger?: CoverageLedger | null;
    scheduler_decisions: SchedulerDecision[];
    proposal_briefs: ProposalBrief[];
    triage_reports: TriageReport[];
    deep_dive_docs: DeepDiveDoc[];
    adversarial_reviews: AdversarialReview[];
    comparison_matrices: ComparisonMatrix[];
    hybrid_assessments: HybridAssessment[];
    final_decision_doc?: FinalDecisionDoc | null;
    decision_summary_markdown?: string | null;
    decision_report_markdown?: string | null;
}

export interface RoutingEntry {
    provider_name: string;
    action_name: string;
    run_count?: number;
    invocation_count?: number;
    candidate_count?: number;
    scored_node_count?: number;
    admitted_count?: number;
    rejected_count?: number;
    winner_count?: number;
    winner_contribution_count?: number;
    critique_count?: number;
    useful_critique_count?: number;
    learning_note_count?: number;
    strong_score_count?: number;
    provider_failure_count?: number;
    accumulated_score?: number;
    total_reward?: number;
    last_run_id?: string | null;
    last_updated_at?: string;
}

export interface RoutingStats {
    entries: RoutingEntry[];
    updated_at?: string;
}

export interface ReusableLearningNote {
    note_id: string;
    note_type: string;
    text: string;
    evidence_sources?: string[];
    source_run_ids?: string[];
    source_node_refs?: string[];
    problem_statements?: string[];
    observation_count?: number;
    first_seen_at?: string;
    last_seen_at?: string;
}

export interface LearningMemoryPayload {
    entries: ReusableLearningNote[];
    updated_at?: string;
}

export interface MemoryPayload {
    routing_stats?: RoutingStats;
    learning_memory?: LearningMemoryPayload;
}

export interface SearchStatePayload {
    problem_spec: ProblemSpec;
    root_id: string;
    nodes: Record<string, SearchNode>;
    archive_ids: string[];
    frontier_ids: string[];
    pruned_ids: string[];
    winner_ids: string[];
    islands: Record<string, SearchIsland>;
    learning_notes: LearningNote[];
    budget_spent: number;
    step_count: number;
    manifest: RunManifest;
    final_recommendation: FinalRecommendation | null;
    summary_markdown: string | null;
    routing_summary: RoutingStats | null;
    research_bundle?: ResearchArtifactBundle | null;
}

export interface ProviderInvocationSummary {
    invocation_id: string;
    action_name: string;
    state: string;
    started_at: string;
    pid?: number | null;
    elapsed?: string | null;
}

export interface RunStatusPayload {
    run_id: string;
    status: RunStatus;
    provider_name: string;
    created_at: string;
    updated_at: string;
    request: string;
    budget: number;
    budget_spent: number;
    step_count: number;
    node_count: number;
    archive_count: number;
    frontier_count: number;
    pruned_count: number;
    winner_count: number;
    current_action: string | null;
    active_provider_invocation_count: number;
    active_provider_invocations: ProviderInvocationSummary[];
    recent_provider_invocations: ProviderInvocationSummary[];
}

export interface ProgressEventPayload {
    kind: string;
    run_id: string;
    timestamp: string;
    step_count: number;
    budget_spent: number;
    payload: Record<string, string | number | boolean | null | string[]>;
}
