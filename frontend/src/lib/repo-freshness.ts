import type { Repo } from './api';

export type RepoFreshnessStatus = 'syncing' | 'failed' | 'never' | 'stale' | 'current';

export interface RepoFreshness {
	status: RepoFreshnessStatus;
	needsAttention: boolean;
}

export function repoFreshness(
	repo: Repo,
	staleAfterSeconds: number | null,
	syncing = false,
	now = Date.now()
): RepoFreshness {
	if (syncing) return { status: 'syncing', needsAttention: false };
	if (repo.last_ingest_error) return { status: 'failed', needsAttention: true };
	if (!repo.last_ingested_at) return { status: 'never', needsAttention: true };
	if (
		staleAfterSeconds !== null &&
		now - new Date(repo.last_ingested_at).getTime() >= staleAfterSeconds * 1000
	) {
		return { status: 'stale', needsAttention: true };
	}
	return { status: 'current', needsAttention: false };
}

export function reposInScope(repos: Repo[], repoName: string): Repo[] {
	return repoName ? repos.filter((repo) => repo.name === repoName) : repos;
}

export function resultNeedsRefresh(sourceSyncedAt: string | undefined, repo: Repo | undefined): boolean {
	if (!repo?.last_ingested_at) return false;
	if (!sourceSyncedAt) return true;
	return new Date(repo.last_ingested_at).getTime() > new Date(sourceSyncedAt).getTime();
}
