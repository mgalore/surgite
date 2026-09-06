<script lang="ts">
	import { onMount } from 'svelte';
	import { listRepos, type Repo } from '$lib/api';
	import RepoList from '$lib/components/RepoList.svelte';
	import AddRepoForm from '$lib/components/AddRepoForm.svelte';
	import SummaryPanel from '$lib/components/SummaryPanel.svelte';
	import PromptSettings from '$lib/components/PromptSettings.svelte';
	import ThemePicker from '$lib/components/ThemePicker.svelte';
	import UserBadge from '$lib/components/UserBadge.svelte';
	import HelpOverlay from '$lib/components/HelpOverlay.svelte';

	let repos = $state<Repo[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let showHelp = $state(false);

	async function loadRepos() {
		loading = true;
		error = null;
		try {
			repos = await listRepos();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load repos';
		} finally {
			loading = false;
		}
	}

	onMount(loadRepos);

	const KONAMI = ['ArrowUp','ArrowUp','ArrowDown','ArrowDown','ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','b','a'];
	let konamiIdx = 0;

	function handleKey(e: KeyboardEvent) {
		if (e.key === 'F1') { e.preventDefault(); showHelp = !showHelp; return; }

		if (e.key === KONAMI[konamiIdx]) {
			konamiIdx++;
			if (konamiIdx === KONAMI.length) {
				konamiIdx = 0;
				document.documentElement.classList.toggle('crt');
			}
		} else {
			konamiIdx = 0;
		}
	}
</script>

<svelte:head>
	<title>surgite — git standup summaries</title>
	<meta name="description" content="Generate standup summaries from your git commit history." />
</svelte:head>

<svelte:window onkeydown={handleKey} />

<main class="mx-auto min-h-screen max-w-2xl px-4 py-6 sm:px-6 sm:py-10">
	<div class="border border-border bg-surface">
		<div class="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
			<span class="flex-1 text-xs text-fg-muted">
				surgite
			</span>
			<div class="flex items-center gap-2">
				<a href="/summaries" class="text-xs text-fg-muted transition hover:text-fg">summaries</a>
				<UserBadge />
				<ThemePicker />
			</div>
		</div>

		<div class="px-4 py-6 sm:px-6">
			<div class="flex items-center gap-2">
				<span class="text-accent" aria-hidden="true">&gt;_</span>
				<h1 class="text-lg font-semibold text-fg">surgite</h1>
				<span class="cursor" aria-hidden="true"></span>
			</div>
			<p class="mt-1 text-sm text-fg-muted">Generate standup summaries from your git history.</p>
			<div class="mt-1 border-b border-border-subtle border-dashed"></div>
		</div>

		<section class="px-4 pb-2 sm:px-6">
			<h2 class="text-sm text-fg-muted">
				<span class="text-accent">~/repos</span> <span aria-hidden="true">❯</span>
			</h2>
			<AddRepoForm onAdded={loadRepos} />
			<RepoList {repos} {loading} {error} onChanged={loadRepos} />
		</section>

		<section class="px-4 pb-2 sm:px-6">
			<PromptSettings {repos} />
		</section>

		<section class="px-4 pb-6 sm:px-6">
			<SummaryPanel {repos} />
		</section>
	</div>
</main>

{#if showHelp}
	<HelpOverlay onclose={() => (showHelp = false)} />
{/if}
