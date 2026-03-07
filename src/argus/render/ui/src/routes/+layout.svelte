<script lang="ts">
	import { onMount } from 'svelte';
	import { initTheme } from '$lib/stores.svelte';
	import TopBar from '$lib/components/TopBar.svelte';
	import '../app.css';

	let { children } = $props();

	onMount(() => {
		initTheme();
	});
</script>

<div class="app-layout">
	<TopBar />
	{@render children()}
</div>
