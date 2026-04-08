// @ts-nocheck
import assert from 'node:assert/strict';
import test from 'node:test';

import {
    deriveResearchBoard,
    hasResearchBoardData,
} from './researchBoardModel.js';

const sampleState = {
    root_id: 'node-0001',
    nodes: {
        'node-0001': {
            node_id: 'node-0001',
            parent_ids: [],
            depth: 0,
            action_type: 'frame_search_space',
            provider_name: 'codex',
            island_id: 'balanced',
            candidate: {
                thesis: 'Frame the search around sabotage, catastrophe, asymmetry, and crowd-chaos families.',
                mechanism: 'Use a research scaffold to compare concept lanes before deepening one.',
                assumptions: [],
                strengths: [],
                failure_modes: [],
                unknowns: [],
                implementation_shape: null,
                evidence: [],
            },
            score: { total_score: 0.77 },
            novelty_score: 1,
            lifecycle_status: 'archived',
            metadata: {},
            created_at: '2026-04-07T23:47:37Z',
        },
        'node-0002': {
            node_id: 'node-0002',
            parent_ids: ['node-0001'],
            depth: 1,
            action_type: 'seed_cell_proposals',
            provider_name: 'codex',
            island_id: 'balanced',
            candidate: {
                thesis: 'A bomb-delivery brawl produces betrayal and public reversals.',
                mechanism: 'One unstable shared objective makes cooperation temporary and theft attractive.',
                assumptions: [],
                strengths: [],
                failure_modes: [],
                unknowns: [],
                implementation_shape: null,
                evidence: [],
            },
            novelty_score: 0.12,
            lifecycle_status: 'rejected',
            metadata: {
                proposal_id: 'seed_c1_last_mile_bomb_v1',
                novelty: {
                    summary: 'Near-duplicate of the archived Fragile Cargo Sabotage direction.',
                    nearest_neighbor_id: 'node-0001',
                },
            },
            termination_reason:
                'Rejected by novelty gate: Near-duplicate of the archived Fragile Cargo Sabotage direction.',
            created_at: '2026-04-07T23:59:44Z',
        },
        'node-0008': {
            node_id: 'node-0008',
            parent_ids: ['node-0001'],
            depth: 1,
            action_type: 'seed_cell_proposals',
            provider_name: 'codex',
            island_id: 'balanced',
            candidate: {
                thesis: 'A mall crowd-collapse game can deliver feed-stopping clips.',
                mechanism: 'Players redirect a neutral crowd into domino floor failures.',
                assumptions: [],
                strengths: [],
                failure_modes: [],
                unknowns: [],
                implementation_shape: null,
                evidence: [],
            },
            novelty_score: 0.87,
            lifecycle_status: 'admitted',
            metadata: {
                proposal_id: 'seed_c3_flash_sale_stampede_v1',
            },
            created_at: '2026-04-08T00:05:52Z',
        },
        'node-0009': {
            node_id: 'node-0009',
            parent_ids: ['node-0001'],
            depth: 1,
            action_type: 'seed_cell_proposals',
            provider_name: 'codex',
            island_id: 'balanced',
            candidate: {
                thesis: 'A rooftop pole-vault delivery race is clean but too safe.',
                mechanism: 'Movement skill drives a courier race across gaps.',
                assumptions: [],
                strengths: [],
                failure_modes: [],
                unknowns: [],
                implementation_shape: null,
                evidence: [],
            },
            novelty_score: 0.54,
            lifecycle_status: 'archived',
            metadata: {
                proposal_id: 'seed_c6_pole_vault_pizza_v1',
            },
            created_at: '2026-04-08T00:06:10Z',
        },
    },
    research_bundle: {
        search_space_frame: {
            frame_id: 'frame_browser_game_jam_2026_v1',
            target_decision: 'Choose the browser game family to deepen into a final jam concept.',
            problem_statement: 'Find a concept that wins on virality, judges, and one-month scope.',
        },
        coverage_ledger: {
            cells: [
                { cell_id: 'c1_fragile_cargo_sabotage', label: 'Fragile Cargo Sabotage' },
                { cell_id: 'c3_crowd_collapse_riot', label: 'Crowd Collapse Riot' },
                { cell_id: 'c6_absurd_stunt_race', label: 'Absurd Stunt Race' },
            ],
        },
        proposal_briefs: [
            {
                proposal_id: 'seed_c1_last_mile_bomb_v1',
                cell_id: 'c1_fragile_cargo_sabotage',
                title: 'Last-Mile Bomb',
                summary: 'Carry one giant live bomb through a destructible route while players steal the final glory.',
                candidate: { thesis: 'Bomb loop', mechanism: '', assumptions: [], strengths: [], failure_modes: [], unknowns: [], implementation_shape: null, evidence: [] },
                seed_rationale: 'Best representative for the sabotage lane.',
                open_questions: [],
                evidence: [],
                parent_node_ids: ['node-0001'],
            },
            {
                proposal_id: 'seed_c3_flash_sale_stampede_v1',
                cell_id: 'c3_crowd_collapse_riot',
                title: 'Flash Sale Stampede',
                summary: 'Redirect a crowd of shoppers to collapse the floor under your rivals.',
                candidate: { thesis: 'Mall collapse', mechanism: '', assumptions: [], strengths: [], failure_modes: [], unknowns: [], implementation_shape: null, evidence: [] },
                seed_rationale: 'Jam-sized crowd-chaos variant.',
                open_questions: [],
                evidence: [],
                parent_node_ids: ['node-0001'],
            },
            {
                proposal_id: 'seed_c6_pole_vault_pizza_v1',
                cell_id: 'c6_absurd_stunt_race',
                title: 'Pole Vault Pizza',
                summary: 'Launch couriers across rooftops with giant poles for the fastest intact pizza drop.',
                candidate: { thesis: 'Pole vault race', mechanism: '', assumptions: [], strengths: [], failure_modes: [], unknowns: [], implementation_shape: null, evidence: [] },
                seed_rationale: 'Useful shipability control, but low ceiling.',
                open_questions: [],
                evidence: [],
                parent_node_ids: ['node-0001'],
            },
        ],
        triage_reports: [
            {
                report_id: 'triage-round-1',
                frame_id: 'frame_browser_game_jam_2026_v1',
                decisions: [
                    {
                        proposal_id: 'seed_c1_last_mile_bomb_v1',
                        disposition: 'survive',
                        rationale: 'Best overall balance of virality and scope.',
                        follow_up: 'Resolve fairness and payout split.',
                    },
                    {
                        proposal_id: 'seed_c3_flash_sale_stampede_v1',
                        disposition: 'eliminate',
                        rationale: 'Too queue-fragile for the jam hard gates.',
                    },
                    {
                        proposal_id: 'seed_c6_pole_vault_pizza_v1',
                        disposition: 'eliminate',
                        rationale: 'Dominated by stronger story-yield families.',
                    },
                ],
                survivor_ids: ['seed_c1_last_mile_bomb_v1'],
                unexplored_cell_ids: [],
                summary: 'Last-Mile Bomb is the current lead, while Flash Sale Stampede is cut on execution risk.',
                next_actions: [],
            },
        ],
        deep_dive_docs: [],
        adversarial_reviews: [],
        comparison_matrices: [],
        hybrid_assessments: [],
        scheduler_decisions: [],
        final_decision_doc: {
            decision_id: 'decision-1',
            frame_id: 'frame_browser_game_jam_2026_v1',
            selected_proposal_id: 'seed_c1_last_mile_bomb_v1',
            high_upside_proposal_id: 'seed_c3_flash_sale_stampede_v1',
            summary: 'Pick Last-Mile Bomb, keep Flash Sale Stampede as the upside benchmark.',
            decision_rule: 'Prefer strong story yield unless crowd chaos clears scope risk.',
            assumptions: [],
            top_risks: [],
            mitigations: [],
            first_spike: [],
            kill_criteria: [],
            next_experiments: [],
            reversal_conditions: [],
            rejected_proposal_ids: [],
        },
        decision_summary_markdown: null,
        decision_report_markdown: null,
    },
};

test('hasResearchBoardData requires research artifacts', () => {
    assert.equal(hasResearchBoardData(sampleState), true);
    assert.equal(hasResearchBoardData({ root_id: 'node-1', nodes: {} }), false);
});

test('deriveResearchBoard separates scaffold, shortlist, and root-frame novelty cuts', () => {
    const board = deriveResearchBoard(sampleState);

    assert.ok(board);
    assert.equal(board.currentFrameCard.title, 'Search Frame');
    assert.match(board.currentFrameCard.note, /not itself a shippable game concept/i);

    assert.equal(board.seededCards.length, 3);
    const bombCard = board.seededCards.find((card) => card.proposalId === 'seed_c1_last_mile_bomb_v1');
    const stampedeCard = board.seededCards.find((card) => card.proposalId === 'seed_c3_flash_sale_stampede_v1');
    const pizzaCard = board.seededCards.find((card) => card.proposalId === 'seed_c6_pole_vault_pizza_v1');

    assert.ok(bombCard);
    assert.equal(bombCard.statusLabel, 'selected');
    assert.match(bombCard.systemNote, /compared this proposal against the frame node node-0001/i);

    assert.ok(stampedeCard);
    assert.equal(stampedeCard.statusLabel, 'high upside');
    assert.ok(pizzaCard);
    assert.equal(pizzaCard.statusLabel, 'cut');

    assert.deepEqual(
        board.shortlistCards.map((card) => card.proposalId),
        ['seed_c1_last_mile_bomb_v1', 'seed_c3_flash_sale_stampede_v1']
    );
    assert.deepEqual(
        board.eliminatedCards.map((card) => card.proposalId),
        ['seed_c6_pole_vault_pizza_v1']
    );
});
