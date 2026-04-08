// @ts-nocheck
/** @typedef {import('../types').ProposalBrief} ProposalBrief */
/** @typedef {import('../types').ProposalTriageDecision} ProposalTriageDecision */
/** @typedef {import('../types').SearchNode} SearchNode */
/** @typedef {import('../types').SearchStatePayload} SearchStatePayload */

const STATUS_PRIORITY = {
    winner: 6,
    admitted: 5,
    archived: 4,
    rejected: 3,
    failed: 2,
    pruned: 1
};

/**
 * @param {SearchStatePayload | null | undefined} state
 * @returns {boolean}
 */
export function hasResearchBoardData(state) {
    const bundle = state?.research_bundle;
    if (!bundle) {
        return false;
    }
    return Boolean(
        bundle.search_space_frame ||
            bundle.coverage_ledger ||
            bundle.proposal_briefs?.length ||
            bundle.triage_reports?.length ||
            bundle.final_decision_doc
    );
}

/**
 * @param {SearchStatePayload | null | undefined} state
 * @returns {object | null}
 */
export function deriveResearchBoard(state) {
    if (!hasResearchBoardData(state)) {
        return null;
    }

    const bundle = state?.research_bundle ?? {};
    const nodes = state?.nodes ?? {};
    const rootNode = state?.root_id ? nodes[state.root_id] ?? null : null;
    const frame = bundle.search_space_frame ?? null;
    const latestTriage = lastItem(bundle.triage_reports);
    const finalDecision = bundle.final_decision_doc ?? null;
    const cellsById = new Map(
        (bundle.coverage_ledger?.cells ?? []).map((cell) => [cell.cell_id, cell])
    );
    const nodeIndex = buildProposalNodeIndex(nodes);
    const roleByProposalId = buildDecisionRoleMap(finalDecision);
    const triageDecisionByProposalId = new Map(
        (latestTriage?.decisions ?? []).map((decision) => [decision.proposal_id, decision])
    );

    const proposalCards = (bundle.proposal_briefs ?? []).map((proposal) =>
        buildProposalCard(proposal, {
            node: bestProposalNode(nodeIndex.get(proposal.proposal_id) ?? []),
            cell: cellsById.get(proposal.cell_id) ?? null,
            triageDecision: triageDecisionByProposalId.get(proposal.proposal_id) ?? null,
            decisionRole: roleByProposalId.get(proposal.proposal_id) ?? null,
            rootId: state?.root_id ?? null,
        })
    );
    const proposalCardById = new Map(proposalCards.map((card) => [card.proposalId, card]));

    const shortlistIds = uniqueStrings(
        finalDecision
            ? [
                  finalDecision.selected_proposal_id,
                  finalDecision.runner_up_proposal_id,
                  finalDecision.conservative_proposal_id,
                  finalDecision.high_upside_proposal_id,
              ]
            : latestTriage?.survivor_ids ?? []
    );
    const eliminatedIds = uniqueStrings([
        ...(latestTriage?.decisions ?? [])
            .filter((decision) => decision.disposition !== 'survive')
            .map((decision) => decision.proposal_id),
        ...(finalDecision?.rejected_proposal_ids ?? []),
    ]).filter((proposalId) => !shortlistIds.includes(proposalId));

    const shortlistCards = shortlistIds
        .map((proposalId) => proposalCardById.get(proposalId))
        .filter(Boolean);
    const eliminatedCards = eliminatedIds
        .map((proposalId) => proposalCardById.get(proposalId))
        .filter(Boolean);

    return {
        headline:
            finalDecision?.summary ??
            latestTriage?.summary ??
            bundle.decision_summary_markdown ??
            frame?.target_decision ??
            null,
        currentFrameCard: buildFrameCard({
            frame,
            rootNode,
        }),
        seededCards: proposalCards,
        shortlistCards,
        eliminatedCards,
        finalDecisionCards: shortlistIds.length > 0 && finalDecision ? shortlistCards : [],
        hasFinalDecision: Boolean(finalDecision),
        currentReadLabel: finalDecision ? 'Decision' : 'Current Read',
        currentReadText:
            finalDecision?.summary ??
            latestTriage?.summary ??
            bundle.decision_summary_markdown ??
            null,
        stats: {
            seededCount: proposalCards.length,
            shortlistCount: shortlistCards.length,
            eliminatedCount: eliminatedCards.length,
        },
    };
}

/**
 * @param {{
 *   frame: object | null;
 *   rootNode: SearchNode | null;
 * }} context
 * @returns {object | null}
 */
function buildFrameCard(context) {
    const { frame, rootNode } = context;
    if (!frame && !rootNode) {
        return null;
    }

    return {
        id: frame?.frame_id ?? rootNode?.node_id ?? 'research-frame',
        title: 'Search Frame',
        summary:
            frame?.target_decision ??
            rootNode?.candidate?.thesis ??
            'Research framing scaffold',
        detail:
            frame?.problem_statement ??
            rootNode?.candidate?.mechanism ??
            'This node defines the search lanes and comparison rubric.',
        note:
            'Research scaffold. This sets the families Argus will compare; it is not itself a shippable game concept.',
        nodeId: rootNode?.node_id ?? null,
        statusTone: 'archived',
        statusLabel: 'scaffold',
        badges: compactBadges([
            frame?.frame_id,
            rootNode?.node_id,
            rootNode?.action_type,
        ]),
    };
}

/**
 * @param {ProposalBrief} proposal
 * @param {{
 *   node: SearchNode | null;
 *   cell: object | null;
 *   triageDecision: ProposalTriageDecision | null;
 *   decisionRole: string | null;
 *   rootId: string | null;
 * }} context
 * @returns {object}
 */
function buildProposalCard(proposal, context) {
    const { node, cell, triageDecision, decisionRole, rootId } = context;
    const lifecycleStatus = normalizeLifecycleStatus(node?.lifecycle_status);
    const novelty = readNovelty(node);
    const rejectedByFrame =
        lifecycleStatus === 'rejected' && novelty?.nearestNeighborId && novelty.nearestNeighborId === rootId;

    const roleInfo = rolePresentation(decisionRole);
    const triageInfo = triagePresentation(triageDecision?.disposition ?? null);

    let statusLabel = roleInfo.label ?? triageInfo.label ?? lifecycleStatus ?? 'seeded';
    let statusTone = roleInfo.tone ?? triageInfo.tone ?? lifecycleStatus ?? 'archived';
    if (statusLabel === 'archived') {
        statusLabel = 'seeded';
    }

    const reason =
        triageDecision?.rationale ??
        node?.termination_reason ??
        novelty?.summary ??
        proposal.seed_rationale ??
        null;
    const systemNote = rejectedByFrame
        ? `Novelty gate compared this proposal against the frame node ${rootId}.`
        : null;

    return {
        id: proposal.proposal_id,
        proposalId: proposal.proposal_id,
        nodeId: node?.node_id ?? null,
        title: proposal.title,
        summary: proposal.summary,
        thesis: proposal.candidate?.thesis ?? null,
        cellId: proposal.cell_id,
        cellLabel: normalizeText(cell?.label ?? proposal.cell_id),
        statusLabel,
        statusTone,
        roleLabel: roleInfo.label ?? null,
        reason,
        systemNote,
        followUp: triageDecision?.follow_up ?? null,
        badges: compactBadges([
            proposal.proposal_id,
            proposal.cell_id,
            node?.node_id,
        ]),
    };
}

/**
 * @param {Record<string, SearchNode>} nodes
 * @returns {Map<string, SearchNode[]>}
 */
function buildProposalNodeIndex(nodes) {
    const index = new Map();
    for (const node of Object.values(nodes)) {
        const proposalId = readProposalId(node);
        if (!proposalId) {
            continue;
        }
        const bucket = index.get(proposalId) ?? [];
        bucket.push(node);
        index.set(proposalId, bucket);
    }
    return index;
}

/**
 * @param {SearchNode[]} nodes
 * @returns {SearchNode | null}
 */
function bestProposalNode(nodes) {
    if (!nodes.length) {
        return null;
    }
    return [...nodes].sort(compareNodesForPresentation)[0] ?? null;
}

/**
 * @param {SearchNode} left
 * @param {SearchNode} right
 * @returns {number}
 */
function compareNodesForPresentation(left, right) {
    const statusGap =
        (STATUS_PRIORITY[normalizeLifecycleStatus(right?.lifecycle_status)] ?? 0) -
        (STATUS_PRIORITY[normalizeLifecycleStatus(left?.lifecycle_status)] ?? 0);
    if (statusGap !== 0) {
        return statusGap;
    }

    const depthGap = Number(right?.depth ?? 0) - Number(left?.depth ?? 0);
    if (depthGap !== 0) {
        return depthGap;
    }

    return String(right?.created_at ?? '').localeCompare(String(left?.created_at ?? ''));
}

/**
 * @param {object | null | undefined} finalDecision
 * @returns {Map<string, string>}
 */
function buildDecisionRoleMap(finalDecision) {
    const roles = new Map();
    if (!finalDecision) {
        return roles;
    }

    if (typeof finalDecision.selected_proposal_id === 'string') {
        roles.set(finalDecision.selected_proposal_id, 'selected');
    }
    if (typeof finalDecision.runner_up_proposal_id === 'string') {
        roles.set(finalDecision.runner_up_proposal_id, 'runner_up');
    }
    if (typeof finalDecision.conservative_proposal_id === 'string') {
        roles.set(finalDecision.conservative_proposal_id, 'conservative');
    }
    if (typeof finalDecision.high_upside_proposal_id === 'string') {
        roles.set(finalDecision.high_upside_proposal_id, 'high_upside');
    }
    return roles;
}

/**
 * @param {string | null} role
 * @returns {{label: string | null; tone: string | null}}
 */
function rolePresentation(role) {
    if (role === 'selected') {
        return { label: 'selected', tone: 'winner' };
    }
    if (role === 'runner_up') {
        return { label: 'runner up', tone: 'archived' };
    }
    if (role === 'conservative') {
        return { label: 'conservative', tone: 'admitted' };
    }
    if (role === 'high_upside') {
        return { label: 'high upside', tone: 'admitted' };
    }
    return { label: null, tone: null };
}

/**
 * @param {string | null} disposition
 * @returns {{label: string | null; tone: string | null}}
 */
function triagePresentation(disposition) {
    if (disposition === 'survive') {
        return { label: 'shortlist', tone: 'admitted' };
    }
    if (disposition === 'eliminate') {
        return { label: 'cut', tone: 'rejected' };
    }
    if (disposition === 'collapse') {
        return { label: 'merged', tone: 'rejected' };
    }
    return { label: null, tone: null };
}

/**
 * @param {SearchNode | null | undefined} node
 * @returns {string | null}
 */
function readProposalId(node) {
    const proposalId = node?.metadata?.proposal_id;
    return typeof proposalId === 'string' && proposalId.trim() ? proposalId.trim() : null;
}

/**
 * @param {SearchNode | null | undefined} node
 * @returns {{summary: string | null; nearestNeighborId: string | null} | null}
 */
function readNovelty(node) {
    const novelty = node?.metadata?.novelty;
    if (!novelty || typeof novelty !== 'object') {
        return null;
    }
    return {
        summary:
            typeof novelty.summary === 'string' && novelty.summary.trim()
                ? novelty.summary.trim()
                : null,
        nearestNeighborId:
            typeof novelty.nearest_neighbor_id === 'string' && novelty.nearest_neighbor_id.trim()
                ? novelty.nearest_neighbor_id.trim()
                : null,
    };
}

/**
 * @param {string | null | undefined} value
 * @returns {string}
 */
function normalizeLifecycleStatus(value) {
    return typeof value === 'string' && value.trim() ? value.trim() : 'archived';
}

/**
 * @param {unknown[]} values
 * @returns {string[]}
 */
function uniqueStrings(values) {
    const seen = new Set();
    const result = [];
    for (const value of values) {
        if (typeof value !== 'string' || !value.trim()) {
            continue;
        }
        const normalized = value.trim();
        if (seen.has(normalized)) {
            continue;
        }
        seen.add(normalized);
        result.push(normalized);
    }
    return result;
}

/**
 * @param {Array<string | null | undefined>} values
 * @returns {string[]}
 */
function compactBadges(values) {
    return values
        .filter((value) => typeof value === 'string' && value.trim())
        .map((value) => normalizeText(value))
        .slice(0, 3);
}

/**
 * @template T
 * @param {T[] | null | undefined} values
 * @returns {T | null}
 */
function lastItem(values) {
    if (!Array.isArray(values) || values.length === 0) {
        return null;
    }
    return values[values.length - 1] ?? null;
}

/**
 * @param {string} value
 * @returns {string}
 */
function normalizeText(value) {
    return value.replaceAll('_', ' ');
}
