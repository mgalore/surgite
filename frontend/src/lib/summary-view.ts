export type SummaryKind = 'ai' | 'log';
export type SummaryStatus = 'waiting' | 'streaming' | 'complete' | 'error';
export type SummaryLayout = 'focus' | 'grid';

export interface SummaryEntry {
	repo: string;
	commits: number;
	text: string;
	kind: SummaryKind;
	status: SummaryStatus;
	provider?: string;
	model?: string;
}

export function sortSummaryEntries(entries: SummaryEntry[]): SummaryEntry[] {
	return [...entries].sort((a, b) => b.commits - a.commits || a.repo.localeCompare(b.repo));
}

export function resolveActiveRepo(entries: SummaryEntry[], selected: string | null): string | null {
	if (selected && entries.some((entry) => entry.repo === selected)) return selected;
	return entries[0]?.repo ?? null;
}

export function parseSummaryLayout(value: string | null): SummaryLayout {
	return value === 'grid' ? 'grid' : 'focus';
}

export function summaryPreview(text: string, limit = 240): string {
	const plain = text
		.replace(/```/g, '')
		.replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
		.replace(/^[\s>*#-]+|^\d+[.)]\s*/gm, '')
		.replace(/[*_`~]/g, '')
		.replace(/\s+/g, ' ')
		.trim();
	if (plain.length <= limit) return plain;
	return `${plain.slice(0, Math.max(0, limit - 1)).trimEnd()}…`;
}
