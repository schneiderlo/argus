import type {
    MemoryPayload,
    ProgressEventPayload,
    RunManifest,
    RunStatusPayload,
    SearchStatePayload,
} from '$lib/types';

let statusApiSupported: boolean | null = null;

async function fetchJson<T>(url: string): Promise<T | null> {
    try {
        const res = await fetch(url);
        if (!res.ok) return null;
        const json = await res.json();
        if (json.error) return null;
        return json as T;
    } catch (err) {
        console.error(`Error fetching ${url}:`, err);
        return null;
    }
}

export async function fetchState(runId: string | null = null): Promise<SearchStatePayload | null> {
    const url = runId && runId !== 'latest' ? `/api/runs/${runId}/state` : '/api/state';
    return fetchJson<SearchStatePayload>(url);
}

export async function fetchDefaultRunId(): Promise<string | null> {
    try {
        const res = await fetch('/api/default-run');
        if (!res.ok) return null;
        const json = await res.json();
        return typeof json.run_id === 'string' ? json.run_id : null;
    } catch (err) {
        console.error("Error fetching default run ID:", err);
        return null;
    }
}

export async function listRuns(): Promise<RunManifest[]> {
    const json = await fetchJson<RunManifest[]>('/api/runs');
    return Array.isArray(json) ? json : [];
}

export async function fetchMemory(): Promise<MemoryPayload | null> {
    return fetchJson<MemoryPayload>('/api/memory');
}

function currentActionFromEvents(events: ProgressEventPayload[]): string | null {
    for (let index = events.length - 1; index >= 0; index -= 1) {
        const event = events[index];
        const action = event.payload.action;
        if (
            (event.kind === 'stage_started' || event.kind === 'provider_invocation') &&
            typeof action === 'string' &&
            action.trim()
        ) {
            return action.trim();
        }
    }
    return null;
}

function synthesizeRunStatus(
    state: SearchStatePayload,
    events: ProgressEventPayload[],
): RunStatusPayload {
    const manifest = state.manifest;
    return {
        run_id: manifest.run_id,
        status: manifest.status,
        provider_name: manifest.provider_name,
        created_at: manifest.created_at,
        updated_at: manifest.updated_at,
        request: state.problem_spec.request,
        budget: manifest.budget,
        budget_spent: state.budget_spent,
        step_count: state.step_count,
        node_count: Object.keys(state.nodes).length,
        archive_count: state.archive_ids.length,
        frontier_count: state.frontier_ids.length,
        pruned_count: state.pruned_ids.length,
        winner_count: state.winner_ids.length,
        current_action: currentActionFromEvents(events),
        active_provider_invocation_count: 0,
        active_provider_invocations: [],
        recent_provider_invocations: [],
    };
}

export async function fetchRunStatus(runId: string | null = null): Promise<RunStatusPayload | null> {
    const url = runId && runId !== 'latest' ? `/api/runs/${runId}/status` : '/api/status';
    if (statusApiSupported === false) {
        const [state, events] = await Promise.all([
            fetchState(runId),
            fetchRunEvents(runId, 40),
        ]);
        return state ? synthesizeRunStatus(state, events) : null;
    }
    try {
        const res = await fetch(url);
        if (res.ok) {
            statusApiSupported = true;
            const json = await res.json();
            if (json.error) return null;
            return json as RunStatusPayload;
        }
        if (res.status === 404) {
            statusApiSupported = false;
            const [state, events] = await Promise.all([
                fetchState(runId),
                fetchRunEvents(runId, 40),
            ]);
            return state ? synthesizeRunStatus(state, events) : null;
        }
        return null;
    } catch (err) {
        console.error(`Error fetching ${url}:`, err);
        return null;
    }
}

export async function fetchRunEvents(
    runId: string | null = null,
    limit = 80,
): Promise<ProgressEventPayload[]> {
    const suffix = `?limit=${encodeURIComponent(String(limit))}`;
    const url = runId && runId !== 'latest' ? `/api/runs/${runId}/events${suffix}` : `/api/events${suffix}`;
    const json = await fetchJson<ProgressEventPayload[]>(url);
    return Array.isArray(json) ? json : [];
}

export async function pruneNode(runId: string, nodeId: string) {
    try {
        const res = await fetch(`/api/runs/${runId}/prune`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ node_id: nodeId })
        });
        return res.ok;
    } catch (e) {
        console.error("Failed to prune:", e);
        return false;
    }
}
