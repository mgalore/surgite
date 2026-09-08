<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { fetchShare, generateSummary, type Summary } from '$lib/api';
	import type { SummaryEntry } from '$lib/summary-view';
	import SummaryReader from '$lib/components/SummaryReader.svelte';
	import SummaryStats from '$lib/components/SummaryStats.svelte';

	let loading = $state(true);
	let error = $state<string | null>(null);
	let result = $state<Summary | null>(null);
	const entries = $derived.by((): SummaryEntry[] => {
		const currentResult = result;
		if (!currentResult) return [];
		if (currentResult.ai_summaries) {
			return Object.entries(currentResult.ai_summaries).map(([repo, summary]) => ({
				repo,
				commits: currentResult.by_repo[repo] ?? 0,
				text: summary.summary,
				kind: 'ai',
				status: 'complete',
				provider: summary.provider,
				model: summary.model
			}));
		}
		return Object.entries(currentResult.log_by_repo ?? {}).map(([repo, text]) => ({
			repo,
			commits: currentResult.by_repo[repo] ?? 0,
			text,
			kind: 'log',
			status: 'complete'
		}));
	});

	onMount(async () => {
		const slug = page.params.slug;
		if (!slug) {
			error = 'Missing share link';
			loading = false;
			return;
		}
		try {
			const shared = await fetchShare(slug);
			result = await generateSummary(shared.params);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not load shared summary';
		} finally {
			loading = false;
		}
	});
</script>

<svelte:head><title>shared summary — surgite</title></svelte:head>

<main class="mx-auto min-h-screen max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
	<div class="border border-border bg-surface">
		<div class="flex items-center justify-between gap-2 border-b border-border px-3 py-2"><span class="flex-1 text-xs text-fg-muted">surgite</span></div>
		<div class="px-4 py-6 sm:px-6">
			<div class="flex items-center gap-2"><span class="text-accent" aria-hidden="true">&gt;_</span><h1 class="text-lg font-semibold text-fg">shared summary</h1></div>
			<p class="mt-1 text-sm text-fg-muted">A read-only standup summary shared via link. <a href="/" class="text-accent underline hover:text-accent-hover">open surgite ❯</a></p>
			<div class="mt-1 border-b border-dashed border-border-subtle"></div>

			{#if loading}
				<p class="mt-4 text-sm text-fg-muted">⣾ loading shared summary…</p>
			{:else if error}
				<p class="mt-4 text-sm text-err">{error}</p>
			{:else if result}
				{#if result.total_commits === 0}
					<p class="mt-4 text-sm text-fg-muted">No commits in this period.</p>
				{:else}
					<SummaryStats totalCommits={result.total_commits} byRepo={result.by_repo} byDay={result.by_day} period={result.period} />
					<SummaryReader {entries} />
				{/if}
			{/if}
		</div>
	</div>
</main>
