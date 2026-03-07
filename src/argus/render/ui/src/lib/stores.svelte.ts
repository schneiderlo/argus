export const uiState = $state({
    isLightMode: false,
    selectedNodeId: null as string | null,
    activeRunId: null as string | null,
    searchState: null as any,
});

export const styleMap = {
    dark: {
        winner: { bg: 'rgba(16, 185, 129, 0.1)', border: '#34d399', text: '#6ee7b7' },
        admitted: { bg: 'rgba(59, 130, 246, 0.1)', border: '#60a5fa', text: '#93c5fd' },
        pending: { bg: 'rgba(234, 179, 8, 0.1)', border: '#facc15', text: '#fef08a' },
        rejected: { bg: 'rgba(239, 68, 68, 0.1)', border: '#f87171', text: '#fca5a5' },
        failed: { bg: 'rgba(249, 115, 22, 0.1)', border: '#fb923c', text: '#fdba74' },
        archived: { bg: 'rgba(168, 85, 247, 0.1)', border: '#c084fc', text: '#e9d5ff' },
        pruned: { bg: 'rgba(156, 163, 175, 0.1)', border: '#9ca3af', text: '#d1d5db' },
        default: { bg: 'rgba(255, 255, 255, 0.05)', border: 'rgba(255,255,255,0.2)', text: '#fafafa' }
    },
    light: {
        winner: { bg: 'rgba(16, 185, 129, 0.15)', border: '#059669', text: '#065f46' },
        admitted: { bg: 'rgba(59, 130, 246, 0.15)', border: '#2563eb', text: '#1e40af' },
        pending: { bg: 'rgba(234, 179, 8, 0.15)', border: '#ca8a04', text: '#854d0e' },
        rejected: { bg: 'rgba(239, 68, 68, 0.15)', border: '#dc2626', text: '#991b1b' },
        failed: { bg: 'rgba(249, 115, 22, 0.15)', border: '#ea580c', text: '#9a3412' },
        archived: { bg: 'rgba(168, 85, 247, 0.15)', border: '#9333ea', text: '#581c87' },
        pruned: { bg: 'rgba(156, 163, 175, 0.15)', border: '#4b5563', text: '#1f2937' },
        default: { bg: 'rgba(0, 0, 0, 0.05)', border: 'rgba(0,0,0,0.2)', text: '#18181b' }
    }
};

export function getStyle(status: string) {
    const map = uiState.isLightMode ? styleMap.light : styleMap.dark;
    return map[status as keyof typeof map] || map.default;
}

// Ensure local storage sync on init
export function initTheme() {
    if (typeof window !== 'undefined') {
        const stored = localStorage.getItem('theme');
        uiState.isLightMode = stored === 'light';
        if (uiState.isLightMode) {
            document.documentElement.classList.add('light-mode');
        }
    }
}

export function toggleTheme() {
    uiState.isLightMode = !uiState.isLightMode;
    if (uiState.isLightMode) {
        document.documentElement.classList.add('light-mode');
        localStorage.setItem('theme', 'light');
    } else {
        document.documentElement.classList.remove('light-mode');
        localStorage.setItem('theme', 'dark');
    }
}
