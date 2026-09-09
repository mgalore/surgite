import { describe, expect, it } from 'vitest';
import type { Repo } from './api';
import { repoFreshness, reposInScope, resultNeedsRefresh } from './repo-freshness';

const repo = (overrides: Partial<Repo> = {}): Repo => ({
	id: 1,
	name: 'demo',
	clone_url: 'https://example.com/demo.git',
	added_at: null,
	last_ingested_at: '2026-05-19T12:00:00Z',
	last_ingest_attempt_at: '2026-05-19T12:00:00Z',
	last_ingest_error: null,
	...overrides
});

describe('repository freshness', () => {
	it('uses syncing, failure, never, stale, then current precedence', () => {
		const now = Date.parse('2026-05-19T12:10:00Z');
		expect(repoFreshness(repo({ last_ingest_error: 'failed' }), 60, true, now).status).toBe('syncing');
		expect(repoFreshness(repo({ last_ingest_error: 'failed' }), 60, false, now).status).toBe('failed');
		expect(repoFreshness(repo({ last_ingested_at: null, last_ingest_error: null }), 60, false, now).status).toBe('never');
		expect(repoFreshness(repo(), 600, false, now).status).toBe('stale');
		expect(repoFreshness(repo(), 601, false, now).status).toBe('current');
	});

	it('does not time-label successful sources stale while automatic sync is disabled', () => {
		expect(repoFreshness(repo(), null, false, Date.parse('2027-05-19T12:00:00Z')).status).toBe('current');
	});

	it('limits freshness operations to the active repository filter', () => {
		const other = repo({ id: 2, name: 'other' });
		expect(reposInScope([repo(), other], 'other')).toEqual([other]);
		expect(reposInScope([repo(), other], '')).toEqual([repo(), other]);
	});

	it('marks a result for refresh when its source has synced since generation', () => {
		expect(resultNeedsRefresh('2026-05-19T12:00:00Z', repo({ last_ingested_at: '2026-05-19T12:01:00Z' }))).toBe(true);
		expect(resultNeedsRefresh('2026-05-19T12:01:00Z', repo())).toBe(false);
	});
});
