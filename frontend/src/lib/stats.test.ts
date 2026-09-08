import { describe, expect, it } from 'vitest';
import { activeDayCount, formatPeriod } from './stats';

describe('summary statistics helpers', () => {
	it('counts only days with commits', () => {
		expect(activeDayCount({ '2026-06-01': 3, '2026-06-04': 1 })).toBe(2);
		expect(activeDayCount({})).toBe(0);
	});

	it('formats API dates without a timezone shift', () => {
		expect(formatPeriod({ since: '2026-06-30', until: '2026-07-01' })).toBe('Jun 30 – Jul 1');
		expect(formatPeriod({ since: '2026-06-30', until: null })).toBe('since Jun 30');
		expect(formatPeriod({ since: null, until: null })).toBe('all time');
	});
});
