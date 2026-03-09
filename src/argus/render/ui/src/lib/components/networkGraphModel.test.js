// @ts-nocheck
import assert from 'node:assert/strict';
import test from 'node:test';

import {
    buildNodeLabel,
    deriveGraphPresentation,
    winnerLineageNodeIds
} from './networkGraphModel.js';

const styleForStatus = (status) => ({
    bg: `bg:${status}`,
    border: `border:${status}`,
    text: `text:${status}`
});

const sampleState = {
    winner_ids: ['node-0003'],
    nodes: {
        'node-0001': {
            node_id: 'node-0001',
            parent_ids: [],
            depth: 0,
            action_type: 'frame_problem',
            provider_name: 'codex',
            island_id: 'balanced',
            candidate: {
                thesis: 'Frame the retention problem around repeatable weekly value.',
                mechanism: 'Define the real target loop before testing tactics.',
                assumptions: [],
                strengths: [],
                failure_modes: [],
                unknowns: [],
                implementation_shape: null,
                evidence: []
            },
            score: { total_score: 0.81 },
            novelty_score: 0.79,
            lifecycle_status: 'admitted',
            metadata: {},
            created_at: '2026-03-08T12:00:00Z'
        },
        'node-0002': {
            node_id: 'node-0002',
            parent_ids: ['node-0001'],
            depth: 1,
            action_type: 'generate_seed',
            provider_name: 'codex',
            island_id: 'balanced',
            candidate: {
                thesis: 'Build a steady ritual for weekly planning and reporting.',
                mechanism: 'Anchor retention in a recurring operating loop.',
                assumptions: [],
                strengths: [],
                failure_modes: [],
                unknowns: [],
                implementation_shape: null,
                evidence: []
            },
            novelty_score: 0.63,
            lifecycle_status: 'admitted',
            metadata: {},
            created_at: '2026-03-08T12:02:00Z'
        },
        'node-0003': {
            node_id: 'node-0003',
            parent_ids: ['node-0001'],
            depth: 1,
            action_type: 'migrate',
            provider_name: 'codex',
            island_id: 'upside',
            candidate: {
                thesis: 'Launch an upside ritual that turns weekly reviews into a shared market moment.',
                mechanism: 'Move the balanced ritual into a more social and prestige-driven wrapper.',
                assumptions: [],
                strengths: [],
                failure_modes: [],
                unknowns: [],
                implementation_shape: null,
                evidence: []
            },
            score: { total_score: 0.92 },
            novelty_score: 0.82,
            lifecycle_status: 'winner',
            metadata: {
                migration: {
                    source_island_id: 'balanced',
                    source_island_label: 'Balanced',
                    source_node_id: 'node-0002',
                    destination_island_id: 'upside',
                    destination_island_label: 'Upside'
                }
            },
            created_at: '2026-03-08T12:05:00Z'
        },
        'node-0004': {
            node_id: 'node-0004',
            parent_ids: ['node-0001'],
            depth: 1,
            action_type: 'mutate',
            provider_name: 'codex',
            island_id: 'balanced',
            candidate: {
                thesis: 'Retry the same ritual with a minor copy change.',
                mechanism: 'Rephrase the leading idea without changing the mechanism.',
                assumptions: [],
                strengths: [],
                failure_modes: [],
                unknowns: [],
                implementation_shape: null,
                evidence: []
            },
            novelty_score: 0.12,
            lifecycle_status: 'rejected',
            metadata: {
                novelty: {
                    summary: 'Near-duplicate of node-0002.'
                }
            },
            created_at: '2026-03-08T12:06:00Z',
            termination_reason: 'Rejected by novelty gate: Near-duplicate of node-0002.'
        }
    }
};

test('winnerLineageNodeIds returns winners and their ancestors only', () => {
    const lineage = [...winnerLineageNodeIds(sampleState)].sort();

    assert.deepEqual(lineage, ['node-0001', 'node-0003']);
});

test('buildNodeLabel prioritizes the idea thesis and overlays winner, island, migration, and novelty context', () => {
    const label = buildNodeLabel(sampleState.nodes['node-0003'], {
        isWinner: true,
        inWinnerLineage: true
    });

    assert.match(label, /^<b>Launch an upside ritual that turns weekly reviews into\.\.\.<\/b>/);
    assert.match(label, /migrate \| node-0003 \| score 0.92/);
    assert.match(label, /winner \| island upside \| migrated balanced -&gt; upside \| novelty 82 novel/);
});

test('deriveGraphPresentation adds migration overlays and highlights winner lineage', () => {
    const presentation = deriveGraphPresentation(sampleState, {
        isLightMode: false,
        getStyle: styleForStatus
    });

    const winnerNode = presentation.nodes.find((node) => node.id === 'node-0003');
    const lineageNode = presentation.nodes.find((node) => node.id === 'node-0001');
    const sourceNode = presentation.nodes.find((node) => node.id === 'node-0002');
    const lineageEdge = presentation.edges.find((edge) => edge.id === 'parent:node-0001->node-0003');
    const migrationEdge = presentation.edges.find((edge) => edge.id === 'migration:node-0002->node-0003');

    assert.ok(winnerNode);
    assert.equal(winnerNode.color.border, '#34d399');
    assert.equal(winnerNode.borderWidth, 3.8);
    assert.equal(winnerNode.shadow.color, 'rgba(52, 211, 153, 0.32)');

    assert.ok(lineageNode);
    assert.equal(lineageNode.color.border, '#34d399');

    assert.ok(sourceNode);
    assert.equal(sourceNode.color.border, 'border:admitted');

    assert.ok(lineageEdge);
    assert.equal(lineageEdge.width, 4);
    assert.equal(lineageEdge.color.color, '#34d399');
    assert.equal(lineageEdge.label, 'winner');

    assert.ok(migrationEdge);
    assert.deepEqual(migrationEdge.dashes, [10, 6]);
    assert.equal(migrationEdge.label, 'migrate balanced -> upside');
    assert.equal(migrationEdge.color.color, '#f59e0b');
});
