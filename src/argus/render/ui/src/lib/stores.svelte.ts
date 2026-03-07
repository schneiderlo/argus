export const uiState = $state({
    isLightMode: false,
    selectedNodeId: null as string | null,
    activeRunId: null as string | null,
    searchState: null as any,
});

export const styleMap = {
    dark: {
        winner: { bg: '#0a1b17', border: '#34d399', text: '#6ee7b7' },
        admitted: { bg: '#0e1523', border: '#60a5fa', text: '#93c5fd' },
        pending: { bg: '#201a0b', border: '#facc15', text: '#fef08a' },
        rejected: { bg: '#200f11', border: '#f87171', text: '#fca5a5' },
        failed: { bg: '#21140c', border: '#fb923c', text: '#fdba74' },
        archived: { bg: '#191123', border: '#c084fc', text: '#e9d5ff' },
        pruned: { bg: '#18181b', border: '#9ca3af', text: '#d1d5db' },
        default: { bg: '#151515', border: 'rgba(255,255,255,0.2)', text: '#fafafa' }
    },
    light: {
        winner: { bg: '#d2ebe3', border: '#059669', text: '#065f46' },
        admitted: { bg: '#d8e3f5', border: '#2563eb', text: '#1e40af' },
        pending: { bg: '#f2ead1', border: '#ca8a04', text: '#854d0e' },
        rejected: { bg: '#f3dada', border: '#dc2626', text: '#991b1b' },
        failed: { bg: '#f5e1d3', border: '#ea580c', text: '#9a3412' },
        archived: { bg: '#e9dcf5', border: '#9333ea', text: '#581c87' },
        pruned: { bg: '#e7e8ea', border: '#4b5563', text: '#1f2937' },
        default: { bg: '#e8e8e9', border: 'rgba(0,0,0,0.2)', text: '#18181b' }
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
