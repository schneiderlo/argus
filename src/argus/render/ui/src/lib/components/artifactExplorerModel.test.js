// @ts-nocheck
import assert from 'node:assert/strict';
import test from 'node:test';

import {
    deriveArtifactExplorer,
    hasArtifactExplorerData,
} from './artifactExplorerModel.js';

const state = {
    nodes: {},
    research_bundle: {
        search_space_frame: {
            frame_id: 'frame-nanochat',
            problem_statement: 'Find cross-domain nanochat experiments.',
            target_decision: 'Pick the first experiment portfolio.',
            hard_gates: ['Must map to nanochat hooks.'],
            soft_criteria: ['Speedrun relevance.'],
            baseline_options: ['Plain AdamW baseline.'],
            axes: [],
            coverage_plan: ['Cover optimizer and data-selection mechanisms.'],
            notes: [],
        },
        coverage_ledger: {
            ledger_id: 'ledger-nanochat',
            frame_id: 'frame-nanochat',
            coverage_summary: 'Optimizer and data cells are represented.',
            next_questions: ['Does the optimizer idea survive FP16 stability?'],
            updated_at: '2026-05-17T17:31:38Z',
            cells: [
                {
                    cell_id: 'opt_thermo',
                    label: 'Optimizer Thermodynamics',
                    axis_assignments: { mechanism: 'optimizer' },
                    hypothesis: 'Noise scaled by optimizer state may widen minima.',
                    coverage_status: 'redteamed',
                    uncertainty: 0.42,
                    hard_gate_risk: 0.31,
                    evidence_strength: 0.61,
                    incumbent_proposal_ids: ['prop-opt-thermo-01'],
                    notes: ['Needs stability ablation.'],
                },
            ],
        },
        proposal_briefs: [
            {
                proposal_id: 'prop-opt-thermo-01',
                cell_id: 'opt_thermo',
                title: 'Fluctuation-Dissipation AdamW',
                summary: 'Tie injected Langevin noise to AdamW variance state.',
                candidate: {
                    thesis: 'AdamW variance can self-anneal optimizer noise.',
                    mechanism: 'Use exp_avg_sq as a local temperature proxy.',
                    assumptions: ['Variance proxy is stable enough.'],
                    strengths: ['Tiny code delta.'],
                    failure_modes: ['Late noise can dominate decayed LR.'],
                    unknowns: ['Correct beta scale.'],
                    implementation_shape: 'Patch scripts/base_train.py.',
                    evidence: ['Prior art requires verification.'],
                },
                seed_rationale: 'High-leverage optimizer cell representative.',
                open_questions: ['Does it beat AdamW under val_bpb?'],
                evidence: ['verification_needed'],
                parent_node_ids: ['node-0001'],
            },
        ],
        triage_reports: [
            {
                report_id: 'triage-001',
                frame_id: 'frame-nanochat',
                decisions: [
                    {
                        proposal_id: 'prop-opt-thermo-01',
                        disposition: 'survive',
                        rationale: 'Best speedrun upside with a small code delta.',
                        follow_up: 'Deepen math and stability path.',
                    },
                ],
                survivor_ids: ['prop-opt-thermo-01'],
                unexplored_cell_ids: [],
                summary: 'Optimizer family survives.',
                next_actions: [],
            },
        ],
        deep_dive_docs: [
            {
                doc_id: 'dd-opt-thermo-01',
                proposal_id: 'prop-opt-thermo-01',
                title: 'Fluctuation-Dissipation AdamW',
                executive_summary: 'Self-anneal noise with AdamW variance state.',
                detailed_mechanism: 'Inject noise proportional to sqrt(exp_avg_sq) and active LR.',
                implementation_plan: ['Patch base_train.py after optimizer.step().'],
                key_unknowns: ['Noise scale.'],
                supporting_evidence: ['verification_needed'],
                assumptions: ['AdamW state is populated for all params.'],
                technical_dossier_markdown:
                    '# Technical Dossier\n\n## Mathematical Rule or Formula\nnoise = beta * sqrt(v_t) * sqrt(lr_t)',
            },
        ],
        adversarial_reviews: [
            {
                review_id: 'rev-opt-thermo-01',
                proposal_id: 'prop-opt-thermo-01',
                thesis_under_test: 'AdamW variance can self-anneal optimizer noise.',
                hidden_dependencies: ['LR coupling must be correct.'],
                failure_modes: ['Late-stage divergence.'],
                mitigations: ['Scale by sqrt(lr_t).'],
                summary: 'Survives only with LR coupling.',
                verdict: 'proceed_with_caution',
                confidence: 0.64,
                evidence: ['verification_needed'],
            },
        ],
        comparison_matrices: [
            {
                matrix_id: 'matrix-001',
                frame_id: 'frame-nanochat',
                criteria: ['speedrun_relevance'],
                rows: [
                    {
                        proposal_id: 'prop-opt-thermo-01',
                        criterion_scores: { speedrun_relevance: 0.82 },
                        advantages: ['Small patch.'],
                        liabilities: ['Stability risk.'],
                        takeaway: 'Worth first ablation.',
                    },
                ],
                summary: 'Optimizer thermodynamics is the first bet.',
            },
        ],
        hybrid_assessments: [],
        scheduler_decisions: [
            {
                decision_id: 'schedule-001',
                action: 'deepen',
                rationale: 'Deepen the optimizer survivor.',
                remaining_budget: 20,
                priority_score: 0.77,
                target_cell_ids: [],
                target_proposal_ids: ['prop-opt-thermo-01'],
                signals: ['High upside and medium hard-gate risk.'],
                selected_at: '2026-05-17T17:40:00Z',
            },
        ],
        final_decision_doc: {
            decision_id: 'decision-001',
            frame_id: 'frame-nanochat',
            selected_proposal_id: 'prop-opt-thermo-01',
            runner_up_proposal_id: null,
            conservative_proposal_id: null,
            high_upside_proposal_id: 'prop-opt-thermo-01',
            summary: 'Run the optimizer thermodynamics ablation first.',
            decision_rule: 'Prefer small code deltas with measurable val_bpb upside.',
            assumptions: [],
            top_risks: [],
            mitigations: [],
            first_spike: [],
            kill_criteria: [],
            next_experiments: [],
            reversal_conditions: [],
            rejected_proposal_ids: [],
        },
        decision_summary_markdown: '# Decision Summary\nRun optimizer thermodynamics first.',
        decision_report_markdown: '# Final Memo\nUse the technical dossier as source of truth.',
    },
};

test('hasArtifactExplorerData requires research artifacts', () => {
    assert.equal(hasArtifactExplorerData(state), true);
    assert.equal(hasArtifactExplorerData({ nodes: {}, research_bundle: null }), false);
});

test('deriveArtifactExplorer builds artifact-first folder hierarchy', () => {
    const explorer = deriveArtifactExplorer(state);
    assert.ok(explorer);
    assert.equal(explorer.stats.proposals, 1);
    assert.equal(explorer.stats.technicalDossiers, 1);
    assert.equal(explorer.defaultItemId, 'technical-dossier:dd-opt-thermo-01');

    const labels = explorer.items.map((item) => item.label);
    assert.ok(labels.includes('Search Frame'));
    assert.ok(labels.includes('Proposals'));
    assert.ok(labels.includes('Technical Dossier'));
    assert.ok(labels.includes('Runtime Evidence'));

    const proposal = explorer.items.find((item) => item.id === 'proposal:prop-opt-thermo-01');
    const dossier = explorer.items.find((item) => item.id === 'technical-dossier:dd-opt-thermo-01');
    assert.equal(proposal.status, 'winner');
    assert.equal(dossier.parentId, proposal.id);
    assert.match(dossier.markdown, /Mathematical Rule or Formula/);
    assert.equal(dossier.depth, 2);
});
