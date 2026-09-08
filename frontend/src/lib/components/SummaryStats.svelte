<script lang="ts">
	import { activeDayCount, formatPeriod, type SummaryPeriod } from '$lib/stats';

	let {
		totalCommits,
		byRepo,
		byDay,
		period
	}: {
		totalCommits: number;
		byRepo: Record<string, number>;
		byDay: Record<string, number>;
		period: SummaryPeriod;
	} = $props();

	const activeDays = $derived(activeDayCount(byDay));
	const repoCount = $derived(Object.keys(byRepo).length);
	const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;
</script>

<div class="mt-3 border border-border bg-surface px-4 py-3 text-xs text-fg-muted">
	<span class="text-fg">{plural(totalCommits, 'commit')}</span>
	· {plural(repoCount, 'repo')}
	· {plural(activeDays, 'active day')}
	· {formatPeriod(period)}
</div>
