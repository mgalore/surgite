<script lang="ts">
	import { onMount } from 'svelte';

	let { onclose }: { onclose: () => void } = $props();
	let dialog: HTMLDivElement;
	let previousFocus: HTMLElement | null = null;

	function close() {
		onclose();
	}

	function handleKey(e: KeyboardEvent) {
		if (e.key === 'Escape' || e.key === 'q') {
			close();
			return;
		}

		if (e.key !== 'Tab') return;
		const focusable = [...dialog.querySelectorAll<HTMLElement>(
			'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
		)].filter((element) => !element.hidden);
		const first = focusable[0];
		const last = focusable.at(-1);

		if (!first || !last) {
			e.preventDefault();
			dialog.focus();
		} else if (e.shiftKey && document.activeElement === first) {
			e.preventDefault();
			last.focus();
		} else if (!e.shiftKey && document.activeElement === last) {
			e.preventDefault();
			first.focus();
		}
	}

	onMount(() => {
		previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
		dialog.focus();
		return () => previousFocus?.focus();
	});
</script>

<svelte:window onkeydown={handleKey} />

<div
	class="fixed inset-0 z-50 flex items-center justify-center bg-bg/80 p-4"
	role="dialog"
	aria-modal="true"
	aria-label="Help"
	tabindex="-1"
	bind:this={dialog}
>
	<button class="absolute inset-0 cursor-default" aria-label="Close help" onclick={close} tabindex="-1"></button>
	<div class="relative w-full max-w-lg border border-border bg-surface p-6 text-sm text-fg">
		<div class="mb-4 flex items-center justify-between">
			<h2 class="text-base font-semibold text-fg">:help</h2>
			<button onclick={close} class="text-fg-muted hover:text-fg" aria-label="Close help">✕</button>
		</div>
		<div class="space-y-3 text-fg-muted">
			<p><span class="text-fg">surgite</span> generates standup summaries from your git commit history.</p>
			<div>
				<p class="text-fg">Commands:</p>
				<p>  <span class="text-accent">❯ add-repo</span>        — register a git repository</p>
				<p>  <span class="text-accent">❯ generate</span>        — fetch latest commits and summarize the selected range</p>
			</div>
			<div>
				<p class="text-fg">Keyboard:</p>
				<p>  <span class="text-accent">F1</span>               — toggle this help</p>
				<p>  <span class="text-accent">↑↑↓↓←→←→BA</span>    — ???</p>
			</div>
			<p class="text-fg-faint">Press <span class="text-fg-muted">Esc</span> or <span class="text-fg-muted">q</span> to close.</p>
		</div>
	</div>
</div>
