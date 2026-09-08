<script lang="ts">
	import { onDestroy, onMount, tick } from 'svelte';
	import {
		createShare,
		fetchProviders,
		generateSummary,
		streamSummary,
		type ProviderInfo,
		type Repo,
		type SummaryParams
	} from '$lib/api';
	import { sortSummaryEntries, type SummaryEntry, type SummaryStatus } from '$lib/summary-view';
	import { toasts } from '$lib/toast.svelte';
	import SummaryReader from './SummaryReader.svelte';
	import SummaryStats from './SummaryStats.svelte';

	let {
		repos,
		resultActive = $bindable(false),
		onOpenRepos
	}: {
		repos: Repo[];
		resultActive?: boolean;
		onOpenRepos?: () => void;
	} = $props();

	let repoName = $state('');
	let range = $state('7');
	let customSince = $state('');
	let customUntil = $state('');
	let author = $state('');
	let useAi = $state(true);
	let selectedProvider = $state('');
	let providers = $state<ProviderInfo[]>([]);
	let generating = $state(false);
	let sharing = $state(false);
	let error = $state<string | null>(null);
	let resultHeading = $state<HTMLHeadingElement>();
	let didFocusResults = false;

	type RepoSummary = {
		text: string;
		provider: string;
		model: string;
		status: SummaryStatus;
	};
	type ResultStats = {
		total: number;
		byRepo: Record<string, number>;
		byDay: Record<string, number>;
		period: { since: string | null; until: string | null };
	};

	let stats = $state<ResultStats | null>(null);
	let summaries = $state<Record<string, RepoSummary>>({});
	let logByRepo = $state<Record<string, string> | null>(null);
	let isAiResult = $state(false);
	let lastParams: SummaryParams | null = null;
	let controller: AbortController | undefined;

	const rangeInvalid = $derived(
		range === 'custom' && !!customSince && !!customUntil && customSince > customUntil
	);
	const hasResult = $derived(stats !== null);
	const summaryEntries = $derived.by((): SummaryEntry[] => {
		const currentStats = stats;
		if (!currentStats) return [];
		if (isAiResult) {
			return Object.entries(summaries).map(([repo, summary]) => ({
				repo,
				commits: currentStats.byRepo[repo] ?? 0,
				text: summary.text,
				kind: 'ai',
				status: summary.status,
				provider: summary.provider,
				model: summary.model
			}));
		}
		return Object.entries(logByRepo ?? {}).map(([repo, text]) => ({
			repo,
			commits: currentStats.byRepo[repo] ?? 0,
			text,
			kind: 'log',
			status: 'complete'
		}));
	});

	const BRAILLE = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷'];
	let spinnerIdx = 0;
	let spinnerFrame = $state(BRAILLE[0]);
	let spinnerInterval: ReturnType<typeof setInterval> | undefined;

	$effect(() => {
		if (generating) {
			spinnerIdx = 0;
			spinnerInterval = setInterval(() => {
				spinnerIdx = (spinnerIdx + 1) % BRAILLE.length;
				spinnerFrame = BRAILLE[spinnerIdx];
			}, 100);
		} else if (spinnerInterval) {
			clearInterval(spinnerInterval);
		}
		return () => {
			if (spinnerInterval) clearInterval(spinnerInterval);
		};
	});

	onMount(async () => {
		try {
			const data = await fetchProviders();
			providers = data.providers;
			selectedProvider = data.default;
		} catch {
			// The provider selector is optional when the endpoint is unavailable.
		}
	});

	onDestroy(() => controller?.abort());

	function sinceDate(days: number): string {
		const date = new Date();
		date.setDate(date.getDate() - days);
		return date.toISOString().slice(0, 10);
	}

	function buildCliEcho(): string {
		const parts = ['surgite'];
		if (repoName) parts.push(`--repo ${repoName}`);
		const custom = range === 'custom';
		if (custom && customSince) parts.push(`--since ${customSince}`);
		else if (!custom) parts.push(`--since ${range}.days.ago`);
		if (custom && customUntil) parts.push(`--until ${customUntil}`);
		if (author.trim()) parts.push(`--author "${author.trim()}"`);
		if (useAi) {
			parts.push('--summarize');
			if (selectedProvider) parts.push(`--provider ${selectedProvider}`);
		}
		return `$ ${parts.join(' ')}`;
	}

	function currentParams(): SummaryParams {
		const custom = range === 'custom';
		return {
			repo: repoName || undefined,
			since: custom ? customSince || undefined : sinceDate(Number(range)),
			until: custom ? customUntil || undefined : undefined,
			author: author.trim() || undefined,
			ai: useAi,
			provider: useAi ? selectedProvider || undefined : undefined
		};
	}

	async function revealResults() {
		if (didFocusResults) return;
		didFocusResults = true;
		resultActive = true;
		await tick();
		const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		resultHeading?.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
		resultHeading?.focus({ preventScroll: true });
	}

	function setStats(next: ResultStats) {
		stats = next;
		if (next.total > 0) void revealResults();
		else resultActive = false;
	}

	async function generate() {
		controller?.abort();
		controller = new AbortController();
		generating = true;
		error = null;
		stats = null;
		summaries = {};
		logByRepo = null;
		isAiResult = useAi;
		didFocusResults = false;
		const params = currentParams();
		lastParams = params;

		try {
			if (useAi) {
				await streamSummary(
					params,
					{
						onMeta: (meta) => {
							setStats({
								total: meta.total_commits,
								byRepo: meta.by_repo,
								byDay: meta.by_day,
								period: meta.period
							});
							summaries = Object.fromEntries(
								meta.repos.map((repo) => [
									repo,
									{ text: '', provider: meta.provider, model: meta.model, status: 'waiting' as const }
								])
							);
						},
						onDelta: (repo, text) => {
							if (summaries[repo]) {
								summaries[repo].text += text;
								summaries[repo].status = 'streaming';
							}
						},
						onRepoDone: (repo, provider, model) => {
							if (summaries[repo]) {
								summaries[repo].provider = provider;
								summaries[repo].model = model;
								summaries[repo].status = 'complete';
							}
						},
						onRepoError: (repo, detail) => {
							if (summaries[repo]) {
								summaries[repo].text = detail;
								summaries[repo].status = 'error';
							}
						}
					},
					controller.signal
				);
			} else {
				const result = await generateSummary(params, controller.signal);
				setStats({
					total: result.total_commits,
					byRepo: result.by_repo,
					byDay: result.by_day,
					period: result.period
				});
				logByRepo = result.log_by_repo;
			}
		} catch (cause) {
			if (cause instanceof DOMException && cause.name === 'AbortError') return;
			error = cause instanceof Error ? cause.message : 'Failed to generate summary';
		} finally {
			generating = false;
		}
	}

	function asMarkdown(): string {
		return sortSummaryEntries(summaryEntries)
			.map((entry) =>
				entry.kind === 'ai'
					? `## ${entry.repo}\n\n${entry.text}`
					: `## ${entry.repo}\n\n\`\`\`\n${entry.text}\n\`\`\``
			)
			.join('\n\n');
	}

	async function copyMarkdown() {
		try {
			await navigator.clipboard.writeText(asMarkdown());
			toasts.success('copied as markdown');
		} catch {
			toasts.error('could not copy — clipboard needs a secure (HTTPS) context');
		}
	}

	async function share() {
		if (!lastParams) return;
		sharing = true;
		try {
			const { slug, expires_at } = await createShare(lastParams);
			await navigator.clipboard.writeText(`${location.origin}/s/${slug}`);
			toasts.success(`share link copied (expires ${new Date(expires_at).toLocaleDateString()})`);
		} catch (cause) {
			toasts.error(cause instanceof Error ? cause.message : 'could not create share link');
		} finally {
			sharing = false;
		}
	}

	const inputCls = 'border border-border bg-bg px-2 py-1.5 text-sm text-fg';
	const actionCls =
		'inline-flex items-center gap-1 border border-border px-3 py-1 text-xs text-fg-muted transition hover:bg-surface hover:text-fg disabled:opacity-50';
</script>

<section>
	<h2 class="text-sm text-fg-muted"><span class="text-accent">~/summary</span> <span aria-hidden="true">❯</span></h2>

	{#if repos.length === 0 && !hasResult && !generating}
		<div class="mt-3 border border-border bg-bg px-4 py-5">
			<p class="text-sm text-fg-muted">Add a repository before generating a standup summary.</p>
			<button type="button" onclick={() => onOpenRepos?.()} class="mt-3 border border-border bg-surface px-3 py-1.5 text-sm text-fg transition hover:bg-surface-2"><span class="text-accent">❯</span> add repository</button>
		</div>
	{:else}
		<div class="mt-3 flex flex-wrap items-center gap-3">
			<select bind:value={repoName} class={inputCls}>
				<option value="">All repos</option>
				{#each repos as repo (repo.id)}<option value={repo.name}>{repo.name}</option>{/each}
			</select>
			<select bind:value={range} class={inputCls}>
				<option value="7">Last 7 days</option><option value="14">Last 14 days</option><option value="30">Last 30 days</option><option value="custom">Custom range</option>
			</select>
			{#if range === 'custom'}
				<input type="date" bind:value={customSince} max={customUntil || undefined} aria-label="From date" class={inputCls} />
				<span class="text-sm text-fg-muted">to</span>
				<input type="date" bind:value={customUntil} min={customSince || undefined} aria-label="To date" class={inputCls} />
			{/if}
			<input type="text" bind:value={author} placeholder="Author (optional)" aria-label="Filter by author" class="{inputCls} w-44" />
			<label class="flex items-center gap-1.5 text-sm text-fg-muted"><input type="checkbox" bind:checked={useAi} class="accent-accent" /> AI summary</label>
			{#if useAi && providers.length > 0}
				<select bind:value={selectedProvider} class={inputCls}>
					{#each providers as provider (provider.name)}<option value={provider.name}>{provider.name} ({provider.model}){provider.available ? '' : ' — no key'}</option>{/each}
				</select>
			{/if}
			<button onclick={generate} disabled={generating || rangeInvalid} class="border border-border bg-accent px-4 py-1.5 text-sm font-medium text-accent-contrast transition hover:bg-accent-hover disabled:opacity-50">
				{generating ? `${spinnerFrame} generating…` : '❯ generate'}
			</button>
		</div>

		{#if rangeInvalid}<p class="mt-3 text-sm text-err">"From" must be on or before "to".</p>{/if}
		{#if error}
			<p class="mt-3 text-sm text-err">{error}</p>
		{:else if hasResult && stats}
			{#if stats.total === 0}
				<p class="mt-4 text-sm text-fg-muted">No commits in this period.</p>
			{:else}
				<div class="mt-3 flex flex-wrap items-center justify-between gap-2">
					<span class="text-xs text-fg-faint">{buildCliEcho()}</span>
					<div class="flex items-center gap-2">
						<button onclick={copyMarkdown} disabled={generating} class={actionCls}>❯ copy markdown</button>
						<button onclick={share} disabled={generating || sharing} class={actionCls}>{sharing ? 'sharing…' : '❯ share link'}</button>
					</div>
				</div>
				<SummaryStats totalCommits={stats.total} byRepo={stats.byRepo} byDay={stats.byDay} period={stats.period} />
				<h3 bind:this={resultHeading} tabindex="-1" class="mt-4 text-sm font-semibold text-fg">summary results</h3>
				<SummaryReader entries={summaryEntries} />
			{/if}
		{:else if generating}
			<p class="mt-4 text-sm text-fg-muted">{spinnerFrame} preparing summary…</p>
		{:else}
			<p class="mt-4 text-sm text-fg-muted">Pick a range and generate a summary to see it here.</p>
		{/if}
	{/if}
</section>
