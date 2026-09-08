import { describe, expect, it } from 'vitest';
import {
	parseSummaryLayout,
	resolveActiveRepo,
	sortSummaryEntries,
	summaryPreview,
	type SummaryEntry
} from './summary-view';

const entries: SummaryEntry[] = [
	{ repo: 'zeta', commits: 2, text: 'z', kind: 'ai', status: 'complete' },
	{ repo: 'alpha', commits: 5, text: 'a', kind: 'ai', status: 'complete' },
	{ repo: 'beta', commits: 5, text: 'b', kind: 'log', status: 'complete' }
];

describe('summary view helpers', () => {
	it('orders entries by commit count and then repository name', () => {
		expect(sortSummaryEntries(entries).map((entry) => entry.repo)).toEqual(['alpha', 'beta', 'zeta']);
	});

	it('keeps a valid active repository and otherwise chooses the first entry', () => {
		const sorted = sortSummaryEntries(entries);
		expect(resolveActiveRepo(sorted, 'zeta')).toBe('zeta');
		expect(resolveActiveRepo(sorted, 'missing')).toBe('alpha');
		expect(resolveActiveRepo([], null)).toBeNull();
	});

	it('uses focus as the safe layout fallback', () => {
		expect(parseSummaryLayout('grid')).toBe('grid');
		expect(parseSummaryLayout('focus')).toBe('focus');
		expect(parseSummaryLayout('unexpected')).toBe('focus');
		expect(parseSummaryLayout(null)).toBe('focus');
	});

	it('turns markdown into a bounded plain-text preview', () => {
		expect(summaryPreview('## Heading\n\n- **Ship** [the change](https://example.com)')).toBe(
			'Heading Ship the change'
		);
		const preview = summaryPreview('a'.repeat(260));
		expect(preview).toHaveLength(240);
		expect(preview.endsWith('…')).toBe(true);
	});
});
