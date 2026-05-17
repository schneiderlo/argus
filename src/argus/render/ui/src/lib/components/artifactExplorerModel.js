// @ts-nocheck
/** @typedef {import('../types').SearchStatePayload} SearchStatePayload */

/**
 * @param {SearchStatePayload | null | undefined} state
 * @returns {boolean}
 */
export function hasArtifactExplorerData(state) {
    const bundle = state?.research_bundle;
    if (!bundle) return false;
    return Boolean(
        bundle.search_space_frame ||
            bundle.coverage_ledger ||
            bundle.proposal_briefs?.length ||
            bundle.triage_reports?.length ||
            bundle.deep_dive_docs?.length ||
            bundle.adversarial_reviews?.length ||
            bundle.comparison_matrices?.length ||
            bundle.hybrid_assessments?.length ||
            bundle.final_decision_doc ||
            bundle.decision_summary_markdown ||
            bundle.decision_report_markdown
    );
}

/**
 * @param {SearchStatePayload | null | undefined} state
 * @returns {{items: object[], defaultItemId: string | null, stats: object} | null}
 */
export function deriveArtifactExplorer(state) {
    if (!hasArtifactExplorerData(state)) return null;

    const bundle = state.research_bundle ?? {};
    const items = [];
    const proposalById = new Map(
        (bundle.proposal_briefs ?? []).map((proposal) => [proposal.proposal_id, proposal])
    );
    const deepDivesByProposalId = groupBy(bundle.deep_dive_docs ?? [], (doc) => doc.proposal_id);
    const reviewsByProposalId = groupBy(bundle.adversarial_reviews ?? [], (review) => review.proposal_id);
    const latestTriage = lastItem(bundle.triage_reports ?? []);
    const triageDecisionByProposalId = new Map(
        (latestTriage?.decisions ?? []).map((decision) => [decision.proposal_id, decision])
    );
    const finalDecision = bundle.final_decision_doc ?? null;
    const roleByProposalId = buildDecisionRoleMap(finalDecision);
    const cellsById = new Map(
        (bundle.coverage_ledger?.cells ?? []).map((cell) => [cell.cell_id, cell])
    );

    addGroup(items, 'frame', 'Search Frame', 'frame');
    if (bundle.search_space_frame) {
        addItem(items, {
            id: `frame:${bundle.search_space_frame.frame_id}`,
            parentId: 'frame',
            label: 'Problem Frame',
            kind: 'frame',
            status: 'scaffold',
            summary: bundle.search_space_frame.target_decision,
            sections: [
                section('Problem Statement', bundle.search_space_frame.problem_statement),
                section('Hard Gates', bundle.search_space_frame.hard_gates),
                section('Soft Criteria', bundle.search_space_frame.soft_criteria),
                section('Baseline Options', bundle.search_space_frame.baseline_options),
                section('Coverage Plan', bundle.search_space_frame.coverage_plan),
            ],
            badges: [bundle.search_space_frame.frame_id],
        });
    }
    if (bundle.coverage_ledger) {
        addItem(items, {
            id: `ledger:${bundle.coverage_ledger.ledger_id}`,
            parentId: 'frame',
            label: 'Coverage Ledger',
            kind: 'ledger',
            status: 'coverage',
            summary: bundle.coverage_ledger.coverage_summary,
            sections: [
                section('Next Questions', bundle.coverage_ledger.next_questions),
                section(
                    'Cells',
                    (bundle.coverage_ledger.cells ?? []).map(
                        (cell) =>
                            `${cell.label} (${cell.cell_id}) - ${cell.coverage_status}; uncertainty ${percent(cell.uncertainty)}, hard-gate risk ${percent(cell.hard_gate_risk)}, evidence ${percent(cell.evidence_strength)}`
                    )
                ),
            ],
            badges: [bundle.coverage_ledger.ledger_id],
        });
        for (const cell of bundle.coverage_ledger.cells ?? []) {
            addItem(items, {
                id: `cell:${cell.cell_id}`,
                parentId: `ledger:${bundle.coverage_ledger.ledger_id}`,
                label: cell.label,
                kind: 'cell',
                status: cell.coverage_status,
                summary: cell.hypothesis,
                sections: [
                    section('Axis Assignments', Object.entries(cell.axis_assignments ?? {}).map(([axis, value]) => `${humanize(axis)}: ${value}`)),
                    section('Incumbents', cell.incumbent_proposal_ids?.map((proposalId) => proposalLabel(proposalById, proposalId)) ?? []),
                    section('Notes', cell.notes ?? []),
                ],
                badges: [cell.cell_id, `${percent(cell.evidence_strength)} evidence`],
            });
        }
    }

    addGroup(items, 'proposals', 'Proposals', 'proposal');
    for (const proposal of bundle.proposal_briefs ?? []) {
        const triage = triageDecisionByProposalId.get(proposal.proposal_id) ?? null;
        const role = roleByProposalId.get(proposal.proposal_id) ?? null;
        const cell = cellsById.get(proposal.cell_id) ?? null;
        addItem(items, {
            id: `proposal:${proposal.proposal_id}`,
            parentId: 'proposals',
            label: proposal.title,
            kind: 'proposal',
            status: role ?? triage?.disposition ?? 'seeded',
            summary: proposal.summary,
            sections: [
                section('Thesis', proposal.candidate?.thesis),
                section('Mechanism', proposal.candidate?.mechanism),
                section('Cell', cell ? `${cell.label} (${cell.cell_id})` : proposal.cell_id),
                section('Seed Rationale', proposal.seed_rationale),
                section('Open Questions', proposal.open_questions),
                section('Evidence', proposal.evidence),
                section('Latest Triage', triage?.rationale ?? null),
                section('Follow-up', triage?.follow_up ?? null),
            ],
            badges: compact([proposal.proposal_id, role, triage?.disposition]),
        });
        addItem(items, {
            id: `proposal:${proposal.proposal_id}:brief`,
            parentId: `proposal:${proposal.proposal_id}`,
            label: 'Brief',
            kind: 'brief',
            status: 'brief',
            summary: proposal.seed_rationale,
            sections: [
                section('Summary', proposal.summary),
                section('Assumptions', proposal.candidate?.assumptions),
                section('Strengths', proposal.candidate?.strengths),
                section('Failure Modes', proposal.candidate?.failure_modes),
                section('Unknowns', proposal.candidate?.unknowns),
            ],
            badges: [proposal.proposal_id],
        });
        for (const doc of deepDivesByProposalId.get(proposal.proposal_id) ?? []) {
            addItem(items, {
                id: `deep-dive:${doc.doc_id}`,
                parentId: `proposal:${proposal.proposal_id}`,
                label: 'Deep Dive',
                kind: 'deep_dive',
                status: 'deepened',
                summary: doc.executive_summary,
                sections: [
                    section('Detailed Mechanism', doc.detailed_mechanism),
                    section('Implementation Plan', doc.implementation_plan),
                    section('Assumptions', doc.assumptions),
                    section('Key Unknowns', doc.key_unknowns),
                    section('Supporting Evidence', doc.supporting_evidence),
                ],
                badges: [doc.doc_id],
            });
            if (doc.technical_dossier_markdown) {
                addItem(items, {
                    id: `technical-dossier:${doc.doc_id}`,
                    parentId: `proposal:${proposal.proposal_id}`,
                    label: 'Technical Dossier',
                    kind: 'technical_dossier',
                    status: 'technical',
                    summary: 'Standalone technical note with mechanism, formulas, implementation hooks, and ablation design.',
                    markdown: doc.technical_dossier_markdown,
                    badges: [doc.doc_id],
                });
            }
        }
        for (const review of reviewsByProposalId.get(proposal.proposal_id) ?? []) {
            addItem(items, {
                id: `review:${review.review_id}`,
                parentId: `proposal:${proposal.proposal_id}`,
                label: 'Red-Team Review',
                kind: 'review',
                status: review.verdict,
                summary: review.summary,
                sections: [
                    section('Verdict', review.verdict),
                    section('Hidden Dependencies', review.hidden_dependencies),
                    section('Failure Modes', review.failure_modes),
                    section('Mitigations', review.mitigations),
                    section('Evidence', review.evidence),
                    section('Confidence', percent(review.confidence)),
                ],
                badges: [review.review_id],
            });
        }
    }

    addGroup(items, 'comparisons', 'Comparisons', 'comparison');
    for (const matrix of bundle.comparison_matrices ?? []) {
        addItem(items, {
            id: `comparison:${matrix.matrix_id}`,
            parentId: 'comparisons',
            label: 'Comparison Matrix',
            kind: 'comparison',
            status: 'matrix',
            summary: matrix.summary,
            sections: [
                section('Criteria', matrix.criteria),
                section(
                    'Rows',
                    matrix.rows.map((row) => `${proposalLabel(proposalById, row.proposal_id)}: ${row.takeaway}`)
                ),
            ],
            badges: [matrix.matrix_id],
        });
    }
    for (const hybrid of bundle.hybrid_assessments ?? []) {
        addItem(items, {
            id: `hybrid:${hybrid.assessment_id}`,
            parentId: 'comparisons',
            label: hybrid.hybrid_name,
            kind: 'hybrid',
            status: hybrid.verdict,
            summary: hybrid.summary,
            sections: [
                section('Source Proposals', hybrid.source_proposal_ids?.map((proposalId) => proposalLabel(proposalById, proposalId))),
                section('Seam Hypothesis', hybrid.seam_hypothesis),
                section('Repaired Failure Mode', hybrid.repaired_failure_mode),
                section('Complementary Strengths', hybrid.complementary_strengths),
                section('Complexity Tax', hybrid.complexity_tax),
                section('Open Questions', hybrid.open_questions),
            ],
            badges: [hybrid.assessment_id],
        });
    }

    addGroup(items, 'final', 'Final Decision', 'decision');
    if (bundle.decision_summary_markdown) {
        addItem(items, {
            id: 'final:summary',
            parentId: 'final',
            label: 'Decision Summary',
            kind: 'decision_summary',
            status: 'summary',
            summary: 'Provider-authored decision summary.',
            markdown: bundle.decision_summary_markdown,
        });
    }
    if (bundle.decision_report_markdown) {
        addItem(items, {
            id: 'final:memo',
            parentId: 'final',
            label: 'Final Memo',
            kind: 'decision_memo',
            status: 'memo',
            summary: 'Full provider-authored decision memo.',
            markdown: bundle.decision_report_markdown,
        });
    }
    if (finalDecision) {
        addItem(items, {
            id: `final:${finalDecision.decision_id}`,
            parentId: 'final',
            label: 'Decision Object',
            kind: 'decision_doc',
            status: 'selected',
            summary: finalDecision.summary,
            sections: [
                section('Selected', proposalLabel(proposalById, finalDecision.selected_proposal_id)),
                section('Runner-up', proposalLabel(proposalById, finalDecision.runner_up_proposal_id)),
                section('Conservative', proposalLabel(proposalById, finalDecision.conservative_proposal_id)),
                section('High Upside', proposalLabel(proposalById, finalDecision.high_upside_proposal_id)),
                section('Decision Rule', finalDecision.decision_rule),
                section('Assumptions', finalDecision.assumptions),
                section('Top Risks', finalDecision.top_risks),
                section('Mitigations', finalDecision.mitigations),
                section('First Spike', finalDecision.first_spike),
                section('Kill Criteria', finalDecision.kill_criteria),
                section('Next Experiments', finalDecision.next_experiments),
                section('Reversal Conditions', finalDecision.reversal_conditions),
            ],
            badges: [finalDecision.decision_id],
        });
    }

    addGroup(items, 'runtime', 'Runtime Evidence', 'runtime');
    for (const decision of bundle.scheduler_decisions ?? []) {
        addItem(items, {
            id: `scheduler:${decision.decision_id}`,
            parentId: 'runtime',
            label: `Scheduler: ${humanize(decision.action)}`,
            kind: 'scheduler',
            status: decision.action,
            summary: decision.rationale,
            sections: [
                section('Remaining Budget', String(decision.remaining_budget)),
                section('Priority Score', percent(decision.priority_score)),
                section('Target Cells', decision.target_cell_ids),
                section('Target Proposals', decision.target_proposal_ids?.map((proposalId) => proposalLabel(proposalById, proposalId))),
                section('Signals', decision.signals),
            ],
            badges: [decision.decision_id],
        });
    }

    const visibleItems = annotateDepth(items);
    return {
        items: visibleItems,
        defaultItemId:
            visibleItems.find((item) => item.kind === 'technical_dossier')?.id ??
            visibleItems.find((item) => item.kind === 'decision_memo')?.id ??
            visibleItems.find((item) => item.kind === 'decision_summary')?.id ??
            visibleItems.find((item) => !item.isGroup)?.id ??
            null,
        stats: {
            proposals: bundle.proposal_briefs?.length ?? 0,
            deepDives: bundle.deep_dive_docs?.length ?? 0,
            technicalDossiers: (bundle.deep_dive_docs ?? []).filter((doc) => doc.technical_dossier_markdown).length,
            reviews: bundle.adversarial_reviews?.length ?? 0,
        },
    };
}

function addGroup(items, id, label, kind) {
    items.push({
        id,
        parentId: null,
        label,
        kind,
        status: kind,
        summary: null,
        sections: [],
        badges: [],
        isGroup: true,
    });
}

function addItem(items, item) {
    items.push({
        sections: [],
        badges: [],
        markdown: null,
        isGroup: false,
        ...item,
    });
}

function annotateDepth(items) {
    const byId = new Map(items.map((item) => [item.id, item]));
    return items.map((item) => {
        let depth = 0;
        let parentId = item.parentId;
        while (parentId && byId.has(parentId)) {
            depth += 1;
            parentId = byId.get(parentId)?.parentId ?? null;
        }
        return { ...item, depth };
    });
}

function section(label, value) {
    if (value === null || value === undefined) {
        return null;
    }
    if (Array.isArray(value)) {
        const values = value.filter((item) => typeof item === 'string' && item.trim());
        if (!values.length) return null;
        return { label, values };
    }
    if (typeof value === 'string') {
        const text = value.trim();
        if (!text || text === '—') return null;
        return { label, text };
    }
    return { label, text: String(value) };
}

function groupBy(values, keyFn) {
    const groups = new Map();
    for (const value of values) {
        const key = keyFn(value);
        const group = groups.get(key) ?? [];
        group.push(value);
        groups.set(key, group);
    }
    return groups;
}

function buildDecisionRoleMap(finalDecision) {
    const roles = new Map();
    if (!finalDecision) return roles;
    setRole(roles, finalDecision.selected_proposal_id, 'winner');
    setRole(roles, finalDecision.runner_up_proposal_id, 'runner-up');
    setRole(roles, finalDecision.conservative_proposal_id, 'conservative');
    setRole(roles, finalDecision.high_upside_proposal_id, 'high-upside');
    for (const proposalId of finalDecision.rejected_proposal_ids ?? []) {
        setRole(roles, proposalId, 'rejected');
    }
    return roles;
}

function setRole(roles, proposalId, role) {
    if (typeof proposalId === 'string' && proposalId.trim() && !roles.has(proposalId)) {
        roles.set(proposalId, role);
    }
}

function proposalLabel(proposalById, proposalId) {
    if (typeof proposalId !== 'string' || !proposalId.trim()) return '—';
    const proposal = proposalById.get(proposalId);
    return proposal ? `${proposal.title} (${proposal.proposal_id})` : proposalId;
}

function lastItem(values) {
    return values.length ? values[values.length - 1] : null;
}

function compact(values) {
    return values.filter((value) => typeof value === 'string' && value.trim());
}

function humanize(value) {
    if (!value) return '—';
    return String(value)
        .replaceAll('_', ' ')
        .replaceAll('-', ' ')
        .replace(/\b\w/g, (match) => match.toUpperCase());
}

function percent(value) {
    return typeof value === 'number' ? `${Math.round(value * 100)}%` : '—';
}
