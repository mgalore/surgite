export interface SummaryPeriod {
	since: string | null;
	until: string | null;
}

export function activeDayCount(byDay: Record<string, number>): number {
	return Object.keys(byDay).length;
}

function shortDate(value: string): string {
	return new Intl.DateTimeFormat('en', {
		month: 'short',
		day: 'numeric',
		timeZone: 'UTC'
	}).format(new Date(`${value}T00:00:00Z`));
}

export function formatPeriod(period: SummaryPeriod): string {
	if (period.since && period.until) return `${shortDate(period.since)} – ${shortDate(period.until)}`;
	if (period.since) return `since ${shortDate(period.since)}`;
	if (period.until) return `through ${shortDate(period.until)}`;
	return 'all time';
}
