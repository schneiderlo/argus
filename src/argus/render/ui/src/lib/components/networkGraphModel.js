/** @typedef {import('../types').SearchNode} SearchNode */
/** @typedef {import('../types').SearchStatePayload} SearchStatePayload */
/** @typedef {import('vis-network').Node} VisNode */
/** @typedef {import('vis-network').Edge} VisEdge */

const WINNER_BORDER = {
    dark: '#34d399',
    light: '#059669'
};

const MIGRATION_EDGE = {
    dark: '#f59e0b',
    light: '#d97706'
};

const NOVELTY_ACCENT = {
    dark: {
        high: 'rgba(52, 211, 153, 0.32)',
        medium: 'rgba(96, 165, 250, 0.26)',
        low: 'rgba(248, 113, 113, 0.24)'
    },
    light: {
        high: 'rgba(5, 150, 105, 0.22)',
        medium: 'rgba(37, 99, 235, 0.18)',
        low: 'rgba(220, 38, 38, 0.16)'
    }
};

const DEFAULT_STYLE = {
    bg: '#151515',
    border: 'rgba(255,255,255,0.2)',
    text: '#fafafa'
};

const DEFAULT_GET_STYLE = () => DEFAULT_STYLE;
const LABEL_PRIMARY_MAX_LENGTH = 38;
const LABEL_META_MAX_LENGTH = 52;
/** @type {Record<string, string>} */
const COMPACT_ACTION_LABELS = {
    frame_problem: 'frame',
    frame_search_space: 'frame',
    generate_seed: 'seed',
    seed_cell_proposals: 'seed',
    stress_test: 'stress',
    compress_learning: 'compress',
    triage_proposals: 'triage',
    deepen_family: 'deepen',
    redteam_family: 'red-team',
    assess_hybrid: 'hybrid',
    write_final_decision: 'decision'
};

/**
 * @param {SearchStatePayload | null | undefined} state
 * @returns {Set<string>}
 */
export function winnerLineageNodeIds(state) {
    const nodes = state?.nodes ?? {};
    const lineage = new Set(state?.winner_ids ?? []);
    const stack = [...lineage];

    while (stack.length > 0) {
        const nodeId = stack.pop();
        if (!nodeId) {
            continue;
        }
        const node = nodes[nodeId];
        if (!node || !Array.isArray(node.parent_ids)) {
            continue;
        }
        for (const parentId of node.parent_ids) {
            if (!lineage.has(parentId)) {
                lineage.add(parentId);
                stack.push(parentId);
            }
        }
    }

    return lineage;
}

/**
 * @param {SearchNode} node
 * @param {{
 *   isWinner?: boolean;
 *   inWinnerLineage?: boolean;
 * }} [context]
 * @returns {string}
 */
export function buildNodeLabel(node, context = {}) {
    const primary = truncateText(
        normalizeText(node?.candidate?.thesis || humanizeAction(node?.action_type || 'node')),
        LABEL_PRIMARY_MAX_LENGTH
    );

    /** @type {string[]} */
    const meta = [];
    if (context.isWinner) {
        meta.push('winner');
    } else if (context.inWinnerLineage) {
        meta.push('path');
    }
    meta.push(compactActionLabel(node?.action_type || 'node'));
    if (typeof node?.island_id === 'string' && node.island_id.trim()) {
        meta.push(normalizeText(node.island_id));
    }
    const rawTotalScore = node?.score?.total_score;
    const totalScore = hasFiniteNumber(rawTotalScore) ? Number(rawTotalScore) : null;
    if (totalScore !== null) {
        meta.push(totalScore.toFixed(2));
    }
    meta.push(noveltyOverlay(node?.novelty_score ?? 0));

    return [
        `<b>${escapeHtml(primary)}</b>`,
        escapeHtml(truncateText(meta.join(' / '), LABEL_META_MAX_LENGTH))
    ].join('\n');
}

/**
 * @param {SearchStatePayload | null | undefined} state
 * @param {{
 *   isLightMode?: boolean;
 *   getStyle?: (status: string) => {bg: string; border: string; text: string};
 * }} [options]
 * @returns {{nodes: VisNode[]; edges: VisEdge[]}}
 */
export function deriveGraphPresentation(state, options = {}) {
    if (!state?.nodes) {
        return { nodes: [], edges: [] };
    }

    const isLightMode = options.isLightMode ?? false;
    const getStyle = options.getStyle ?? DEFAULT_GET_STYLE;
    const lineage = winnerLineageNodeIds(state);
    const winnerIds = new Set(state.winner_ids ?? []);
    const nodeIds = Object.keys(state.nodes).sort();

    /** @type {VisEdge[]} */
    const edges = [];
    for (const nodeId of nodeIds) {
        const node = state.nodes[nodeId];
        const parentIds = Array.isArray(node.parent_ids) ? [...node.parent_ids].sort() : [];
        for (const parentId of parentIds) {
            edges.push(buildParentEdge(parentId, node, { isLightMode, lineage, winnerIds }));
        }
        const migrationEdge = buildMigrationEdge(node, state, isLightMode);
        if (migrationEdge) {
            edges.push(migrationEdge);
        }
    }

    /** @type {VisNode[]} */
    const nodes = nodeIds.map((nodeId) => {
        const node = state.nodes[nodeId];
        return buildVisNode(node, {
            isLightMode,
            getStyle,
            isWinner: winnerIds.has(nodeId),
            inWinnerLineage: lineage.has(nodeId)
        });
    });

    return { nodes, edges };
}

/**
 * @param {SearchNode} node
 * @param {{
 *   isLightMode: boolean;
 *   getStyle: (status: string) => {bg: string; border: string; text: string};
 *   isWinner: boolean;
 *   inWinnerLineage: boolean;
 * }} context
 * @returns {VisNode}
 */
function buildVisNode(node, context) {
    const style = context.getStyle(node.lifecycle_status) || DEFAULT_STYLE;
    const winnerBorder = context.isLightMode ? WINNER_BORDER.light : WINNER_BORDER.dark;
    const accentColor = noveltyAccentColor(node.novelty_score, context.isLightMode);
    const borderColor = context.isWinner || context.inWinnerLineage ? winnerBorder : style.border;
    /** @type {VisNode} */
    const nodeConfig = {
        id: node.node_id,
        level: hasFiniteNumber(node.depth) ? Number(node.depth) : 0,
        label: buildNodeLabel(node, {
            isWinner: context.isWinner,
            inWinnerLineage: context.inWinnerLineage
        }),
        title: buildNodeTitle(node, {
            isWinner: context.isWinner,
            inWinnerLineage: context.inWinnerLineage
        }),
        borderWidth: context.isWinner ? 3.8 : context.inWinnerLineage ? 3.0 : 1.6 + Math.max(0, node.novelty_score) * 1.4,
        color: {
            background: style.bg,
            border: borderColor,
            highlight: {
                background: style.bg,
                border: borderColor
            },
            hover: {
                background: style.bg,
                border: borderColor
            }
        },
        font: {
            multi: 'html',
            color: style.text
        },
        shadow: {
            enabled: true,
            color: accentColor,
            size: context.isWinner ? 24 : context.inWinnerLineage ? 18 : 14,
            x: 0,
            y: 0
        }
    };

    if (node.lifecycle_status === 'pruned' || node.lifecycle_status === 'rejected') {
        nodeConfig.shapeProperties = { borderDashes: [4, 4] };
        nodeConfig.font = {
            multi: 'html',
            color: context.isLightMode ? 'rgba(0,0,0,0.45)' : 'rgba(255,255,255,0.45)'
        };
    }

    return nodeConfig;
}

/**
 * @param {string} parentId
 * @param {SearchNode} child
 * @param {{
 *   isLightMode: boolean;
 *   lineage: Set<string>;
 *   winnerIds: Set<string>;
 * }} context
 * @returns {VisEdge}
 */
function buildParentEdge(parentId, child, context) {
    const isTerminal = child.lifecycle_status === 'pruned' || child.lifecycle_status === 'rejected';
    const isWinnerLineageEdge = context.lineage.has(parentId) && context.lineage.has(child.node_id);
    const color = isWinnerLineageEdge
        ? (context.isLightMode ? WINNER_BORDER.light : WINNER_BORDER.dark)
        : (context.isLightMode ? 'rgba(24, 24, 27, 0.25)' : 'rgba(244, 244, 245, 0.20)');
    const title = isWinnerLineageEdge
        ? `Winner lineage: ${parentId} -> ${child.node_id}`
        : `Parent link: ${parentId} -> ${child.node_id}`;

    return {
        id: `parent:${parentId}->${child.node_id}`,
        from: parentId,
        to: child.node_id,
        width: isWinnerLineageEdge ? 4 : 2,
        color: {
            color,
            highlight: color,
            hover: color,
            opacity: isTerminal ? 0.35 : 1
        },
        dashes: isTerminal ? [4, 4] : false,
        title,
        label: context.winnerIds.has(child.node_id) ? 'winner' : undefined,
        font: isWinnerLineageEdge
            ? {
                  align: 'top',
                  color,
                  size: 11
              }
            : undefined
    };
}

/**
 * @param {SearchNode} node
 * @param {SearchStatePayload} state
 * @param {boolean} isLightMode
 * @returns {VisEdge | null}
 */
function buildMigrationEdge(node, state, isLightMode) {
    const migration = migrationMetadata(node);
    if (!migration || !state.nodes[migration.sourceNodeId]) {
        return null;
    }

    const parentIds = Array.isArray(node.parent_ids) ? node.parent_ids : [];
    if (parentIds.includes(migration.sourceNodeId)) {
        return null;
    }

    const color = isLightMode ? MIGRATION_EDGE.light : MIGRATION_EDGE.dark;
    return {
        id: `migration:${migration.sourceNodeId}->${node.node_id}`,
        from: migration.sourceNodeId,
        to: node.node_id,
        width: 3,
        dashes: [10, 6],
        label: `migrate ${migration.sourceIslandId} -> ${migration.destinationIslandId}`,
        font: {
            align: 'top',
            color,
            size: 11,
            strokeWidth: 0
        },
        color: {
            color,
            highlight: color,
            hover: color,
            opacity: 0.95
        },
        smooth: {
            enabled: true,
            type: 'curvedCW',
            roundness: 0.28
        },
        title: (
            `Migration overlay: ${migration.sourceIslandLabel} (${migration.sourceIslandId}) -> ` +
            `${migration.destinationIslandLabel} (${migration.destinationIslandId}) from ${migration.sourceNodeId}`
        )
    };
}

/**
 * @param {SearchNode} node
 * @param {{isWinner: boolean; inWinnerLineage: boolean}} context
 * @returns {string}
 */
function buildNodeTitle(node, context) {
    /** @type {string[]} */
    const lines = [
        `Thesis: ${normalizeText(node.candidate?.thesis || node.node_id)}`,
        `Action: ${humanizeAction(node.action_type)}`,
        `Node: ${node.node_id}`,
        `Status: ${normalizeText(node.lifecycle_status)}`,
        `Novelty: ${formatPercent(node.novelty_score)} (${noveltyBand(node.novelty_score)})`
    ];

    if (typeof node.island_id === 'string' && node.island_id.trim()) {
        lines.push(`Island: ${normalizeText(node.island_id)}`);
    }
    if (hasFiniteNumber(node.score?.total_score)) {
        lines.push(`Score: ${Number(node.score?.total_score).toFixed(2)}`);
    }
    if (context.isWinner) {
        lines.push('Winner: yes');
    } else if (context.inWinnerLineage) {
        lines.push('Winner path: yes');
    }
    const migration = migrationMetadata(node);
    if (migration) {
        lines.push(
            `Migration: ${migration.sourceIslandLabel} (${migration.sourceIslandId}) -> ` +
                `${migration.destinationIslandLabel} (${migration.destinationIslandId}) from ${migration.sourceNodeId}`
        );
    }
    if (typeof node.termination_reason === 'string' && node.termination_reason.trim()) {
        lines.push(`Decision: ${normalizeText(node.termination_reason)}`);
    }

    return lines.join('\n');
}

/**
 * @param {SearchNode} node
 * @returns {{
 *   sourceIslandId: string;
 *   sourceIslandLabel: string;
 *   sourceNodeId: string;
 *   destinationIslandId: string;
 *   destinationIslandLabel: string;
 * } | null}
 */
function migrationMetadata(node) {
    const metadata = asObject(node?.metadata);
    if (!metadata) {
        return null;
    }
    const migration = asObject(metadata.migration);
    if (!migration) {
        return null;
    }
    const sourceIslandId = asNonEmptyString(migration.source_island_id);
    const sourceIslandLabel = asNonEmptyString(migration.source_island_label) ?? sourceIslandId;
    const sourceNodeId = asNonEmptyString(migration.source_node_id);
    const destinationIslandId = asNonEmptyString(migration.destination_island_id);
    const destinationIslandLabel =
        asNonEmptyString(migration.destination_island_label) ?? destinationIslandId;
    if (!sourceIslandId || !sourceNodeId || !destinationIslandId) {
        return null;
    }
    const normalizedSourceIslandLabel = sourceIslandLabel ?? sourceIslandId;
    const normalizedDestinationIslandLabel = destinationIslandLabel ?? destinationIslandId;
    return {
        sourceIslandId,
        sourceIslandLabel: normalizedSourceIslandLabel,
        sourceNodeId,
        destinationIslandId,
        destinationIslandLabel: normalizedDestinationIslandLabel
    };
}

/**
 * @param {unknown} value
 * @returns {Record<string, unknown> | null}
 */
function asObject(value) {
    return typeof value === 'object' && value !== null ? /** @type {Record<string, unknown>} */ (value) : null;
}

/**
 * @param {unknown} value
 * @returns {string | null}
 */
function asNonEmptyString(value) {
    if (typeof value !== 'string') {
        return null;
    }
    const normalized = normalizeText(value);
    return normalized ? normalized : null;
}

/**
 * @param {unknown} value
 * @returns {boolean}
 */
function hasFiniteNumber(value) {
    return typeof value === 'number' && Number.isFinite(value);
}

/**
 * @param {string} value
 * @returns {string}
 */
function humanizeAction(value) {
    return normalizeText(value).replaceAll('_', ' ') || 'node';
}

/**
 * @param {number} score
 * @returns {string}
 */
function noveltyOverlay(score) {
    return `${noveltyBand(score)} ${formatPercent(score)}`;
}

/**
 * @param {number} score
 * @returns {string}
 */
function noveltyBand(score) {
    if (score >= 0.75) {
        return 'novel';
    }
    if (score >= 0.45) {
        return 'adjacent';
    }
    return 'duplicate-risk';
}

/**
 * @param {number} score
 * @param {boolean} isLightMode
 * @returns {string}
 */
function noveltyAccentColor(score, isLightMode) {
    const palette = isLightMode ? NOVELTY_ACCENT.light : NOVELTY_ACCENT.dark;
    if (score >= 0.75) {
        return palette.high;
    }
    if (score >= 0.45) {
        return palette.medium;
    }
    return palette.low;
}

/**
 * @param {unknown} value
 * @returns {string}
 */
function normalizeText(value) {
    if (typeof value !== 'string') {
        return '';
    }
    return value.replace(/\s+/g, ' ').trim();
}

/**
 * @param {number} value
 * @returns {string}
 */
function formatPercent(value) {
    if (!hasFiniteNumber(value)) {
        return '0';
    }
    return String(Math.round(Math.max(0, Math.min(1, value)) * 100));
}

/**
 * @param {string} value
 * @param {number} maxLength
 * @returns {string}
 */
function truncateText(value, maxLength) {
    const normalized = normalizeText(value);
    if (normalized.length <= maxLength) {
        return normalized;
    }
    const sliceLength = Math.max(0, maxLength - 3);
    const boundaryIndex = normalized.lastIndexOf(' ', sliceLength);
    const endIndex = boundaryIndex >= Math.floor(maxLength * 0.55) ? boundaryIndex : sliceLength;
    return `${normalized.slice(0, endIndex).trimEnd()}...`;
}

/**
 * @param {string} value
 * @returns {string}
 */
function compactActionLabel(value) {
    const normalized = normalizeText(value);
    return COMPACT_ACTION_LABELS[normalized] ?? humanizeAction(normalized);
}

/**
 * @param {string} value
 * @returns {string}
 */
function escapeHtml(value) {
    return value
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}
