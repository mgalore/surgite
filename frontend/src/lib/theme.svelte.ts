// Synced with the pre-paint theme script in app.html.
import { browser } from '$app/environment';

export interface ThemeDef {
	id: string;
	label: string;
	bg: string;
	accent: string;
}

export const THEMES: ThemeDef[] = [
	{ id: 'github-dark', label: 'GitHub Dark', bg: '#0d1117', accent: '#2f81f7' },
	{ id: 'light', label: 'Light', bg: '#ffffff', accent: '#0969da' },
	{ id: 'nord', label: 'Nord', bg: '#2e3440', accent: '#88c0d0' },
	{ id: 'catppuccin', label: 'Catppuccin Mocha', bg: '#1e1e2e', accent: '#89b4fa' },
	{ id: 'solarized', label: 'Solarized Dark', bg: '#002b36', accent: '#268bd2' },
	{ id: 'terminal', label: 'Terminal', bg: '#0c0c0c', accent: '#ffb000' }
];

const DEFAULT = 'github-dark';
const IDS = new Set(THEMES.map((t) => t.id));

function initial(): string {
	if (!browser) return DEFAULT;
	const stored = localStorage.getItem('theme');
	return stored && IDS.has(stored) ? stored : DEFAULT;
}

class ThemeState {
	current = $state<string>(initial());

	get label(): string {
		return THEMES.find((t) => t.id === this.current)?.label ?? this.current;
	}

	set(id: string) {
		if (!IDS.has(id)) return;
		this.current = id;
		if (!browser) return;
		document.documentElement.setAttribute('data-theme', id);
		localStorage.setItem('theme', id);
	}
}

export const theme = new ThemeState();

if (browser) theme.set(theme.current);
