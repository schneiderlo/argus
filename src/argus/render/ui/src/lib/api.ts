export async function fetchState(runId: string | null = null) {
    try {
        const url = runId && runId !== "latest" ? `/api/runs/${runId}/state` : '/api/state';
        const res = await fetch(url);
        if (!res.ok) return null;
        const json = await res.json();
        if (json.error) return null;
        return json;
    } catch (err) {
        console.error("Error fetching state:", err);
        return null;
    }
}

export async function fetchDefaultRunId() {
    try {
        const res = await fetch('/api/runs/default-run');
        if (!res.ok) return null;
        const json = await res.json();
        return json.run_id || null;
    } catch (err) {
        console.error("Error fetching default run ID:", err);
        return null;
    }
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
