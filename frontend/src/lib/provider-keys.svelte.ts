import {
	clearProviderKey,
	fetchProviderKeys,
	setProviderKey,
	type ProviderKeysResponse
} from './api';

export type ProviderRowStatus = 'configured' | 'revoked' | 'unset';

export interface ProviderRow {
	provider: string;
	status: ProviderRowStatus;
	created_at: string | null;
	revoked_at: string | null;
	isDefault: boolean;
}

/** Merge visible providers with their active key rows. */
export function toRows(res: ProviderKeysResponse): ProviderRow[] {
	return res.providers.map((provider) => {
		const key = res.keys.find((k) => k.provider === provider);
		const status: ProviderRowStatus = !key ? 'unset' : key.revoked_at ? 'revoked' : 'configured';
		return {
			provider,
			status,
			created_at: key?.created_at ?? null,
			revoked_at: key?.revoked_at ?? null,
			isDefault: provider === res.default
		};
	});
}

const status = (e: unknown): number | undefined =>
	typeof e === 'object' && e !== null ? (e as { status?: number }).status : undefined;

const message = (e: unknown, fallback: string): string =>
	e instanceof Error && e.message ? e.message : fallback;

export class ProviderKeysStore {
	supported = $state<boolean | null>(null);
	loading = $state(false);
	error = $state<string | null>(null);
	rows = $state<ProviderRow[]>([]);
	errors = $state<Record<string, string>>({});
	busy = $state<Record<string, boolean>>({});

	async load(): Promise<void> {
		this.loading = true;
		try {
			this.rows = toRows(await fetchProviderKeys());
			this.supported = true;
			this.error = null;
		} catch (cause) {
			const code = status(cause);
			if (code === 404 || code === 401) {
				this.supported = false;
				this.rows = [];
			} else {
				this.supported = true;
				this.error = message(cause, 'Failed to load provider keys');
			}
		} finally {
			this.loading = false;
		}
	}

	async save(provider: string, key: string): Promise<boolean> {
		return this.run(provider, 'Failed to save key', async () => {
			await setProviderKey(provider, key);
		});
	}

	async revoke(provider: string): Promise<boolean> {
		return this.run(provider, 'Failed to revoke key', async () => {
			await clearProviderKey(provider);
		});
	}

	private async run(provider: string, fallback: string, act: () => Promise<void>): Promise<boolean> {
		this.busy = { ...this.busy, [provider]: true };
		const { [provider]: _cleared, ...rest } = this.errors;
		this.errors = rest;
		try {
			await act();
			this.rows = toRows(await fetchProviderKeys());
			return true;
		} catch (cause) {
			this.errors = { ...this.errors, [provider]: message(cause, fallback) };
			return false;
		} finally {
			const { [provider]: _done, ...others } = this.busy;
			this.busy = others;
		}
	}
}
