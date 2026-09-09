import { ingestRepo, listRepos, type Repo, type RepoList } from './api';
import { toasts } from './toast.svelte';

type PendingSync = { repo: Repo; attemptAt: string | null };

export class RepoSyncManager {
	private pending = new Map<number, PendingSync>();
	private controller: AbortController | null = null;
	private polling = false;

	constructor(
		private readonly onRepos: (data: RepoList) => void,
		private readonly onSyncingChange: (ids: Set<number>) => void
	) {}

	get syncingIds(): Set<number> {
		return new Set(this.pending.keys());
	}

	sync(repos: Repo[]): void {
		for (const repo of repos) {
			if (this.pending.has(repo.id)) continue;
			this.pending.set(repo.id, { repo, attemptAt: repo.last_ingest_attempt_at });
			void this.request(repo);
		}
		this.publish();
		void this.poll();
	}

	/** Watch the initial BackgroundTask already queued by POST /repos. */
	trackInitialIngest(repo: Repo): void {
		if (repo.last_ingest_attempt_at || this.pending.has(repo.id)) return;
		this.pending.set(repo.id, { repo, attemptAt: null });
		this.publish();
		void this.poll();
	}

	destroy(): void {
		this.controller?.abort();
		this.controller = null;
		this.pending.clear();
		this.publish();
	}

	private publish(): void {
		this.onSyncingChange(new Set(this.pending.keys()));
	}

	private async request(repo: Repo): Promise<void> {
		try {
			await ingestRepo(repo.id);
		} catch (cause) {
			if ((cause as Error & { status?: number }).status === 409) return;
			if (this.pending.delete(repo.id)) {
				toasts.error(cause instanceof Error ? `${repo.name}: ${cause.message}` : `${repo.name}: sync failed`);
				this.publish();
			}
		}
	}

	private async poll(): Promise<void> {
		if (this.polling || this.pending.size === 0) return;
		this.polling = true;
		const controller = new AbortController();
		this.controller = controller;
		const deadline = Date.now() + 120_000;
		try {
			while (!controller.signal.aborted && this.pending.size && Date.now() < deadline) {
				await delay(2_000, controller.signal);
				if (controller.signal.aborted) return;
				try {
					const data = await listRepos(controller.signal);
					this.onRepos(data);
					this.completeFinished(data.repos);
				} catch (cause) {
					if (controller.signal.aborted) return;
					// A temporary list failure should not hide an active background sync.
					console.warn('Could not poll repository sync status', cause);
				}
			}
			if (!controller.signal.aborted && this.pending.size) {
				for (const { repo } of this.pending.values()) {
					toasts.error(`${repo.name}: sync continues in the background`);
				}
				this.pending.clear();
				this.publish();
			}
		} finally {
			if (this.controller === controller) this.controller = null;
			this.polling = false;
		}
	}

	private completeFinished(repos: Repo[]): void {
		const byId = new Map(repos.map((repo) => [repo.id, repo]));
		for (const [id, pending] of this.pending) {
			const current = byId.get(id);
			if (current && current.last_ingest_attempt_at === pending.attemptAt) continue;
			this.pending.delete(id);
			if (!current) continue;
			if (current.last_ingest_error) toasts.error(`${current.name}: sync failed`);
			else toasts.success(`synced ${current.name}`);
		}
		this.publish();
	}
}

function delay(ms: number, signal: AbortSignal): Promise<void> {
	return new Promise((resolve) => {
		const finish = () => {
			clearTimeout(timer);
			signal.removeEventListener('abort', finish);
			resolve();
		};
		const timer = setTimeout(finish, ms);
		signal.addEventListener('abort', finish, { once: true });
	});
}
