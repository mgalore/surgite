import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Repo, RepoList } from './api';
import { RepoSyncManager } from './repo-sync';

const repo = (id: number): Repo => ({
	id,
	name: `repo-${id}`,
	clone_url: `https://example.com/repo-${id}.git`,
	added_at: null,
	last_ingested_at: '2026-05-19T12:00:00Z',
	last_ingest_attempt_at: '2026-05-19T12:00:00Z',
	last_ingest_error: null
});

const response = (body: unknown) =>
	({ ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve(body) }) as Response;

describe('RepoSyncManager', () => {
	let fetchSpy: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		vi.useFakeTimers();
		fetchSpy = vi.fn((url: string, init?: RequestInit) => {
			if (init?.method === 'POST') return Promise.resolve(response({ accepted: true }));
			const repos = [repo(1), repo(2)].map((item) => ({
				...item,
				last_ingest_attempt_at: '2026-05-19T12:01:00Z',
				last_ingested_at: '2026-05-19T12:01:00Z'
			}));
			return Promise.resolve(response({ repos, stale_after_seconds: 600 }));
		});
		vi.stubGlobal('fetch', fetchSpy);
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	it('fans out requests and uses one poll to complete every pending repository', async () => {
		const onRepos = vi.fn<(data: RepoList) => void>();
		const onSyncing = vi.fn<(ids: Set<number>) => void>();
		const manager = new RepoSyncManager(onRepos, onSyncing);

		manager.sync([repo(1), repo(2)]);
		await vi.advanceTimersByTimeAsync(2_000);

		expect(fetchSpy.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')).toHaveLength(2);
		expect(fetchSpy.mock.calls.filter(([, init]) => !(init as RequestInit | undefined)?.method)).toHaveLength(1);
		expect(onRepos).toHaveBeenCalledOnce();
		expect(onSyncing).toHaveBeenLastCalledWith(new Set());
		manager.destroy();
	});
});
