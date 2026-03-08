import type {
    MemoryPayload,
    ProgressEventPayload,
    RunManifest,
    RunStatusPayload,
    SearchStatePayload,
} from '$lib/types';

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

export async function fetchRunStatus(runId: string | null = null): Promise<RunStatusPayload | null> {
    const url = runId && runId !== 'latest' ? `/api/runs/${runId}/status` : '/api/status';
    return fetchJson<RunStatusPayload>(url);
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
