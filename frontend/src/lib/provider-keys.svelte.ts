// State for the provider-keys settings subsection. Kept out of the component
// so vitest can drive it under `environment: 'node'` without a Svelte
// component test framework — same reasoning as lib/validation.ts, same shape
// as lib/repo-sync.ts.
//
// The raw key never lands here: `save()` takes it as an argument and hands it
// straight to the request. Nothing on this class ever holds key material.
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

/** One row per provider in the server's visible registry, in server order.
 *
 * A key row counts as `configured` only while `revoked_at` is null — the API
 * returns revoked rows too, so a plain "is there a row?" check would report a
 * revoked provider as configured.
 *
 * Key rows for providers missing from the catalogue are dropped. That happens
 * when an operator turns on LLM_LOCAL_ONLY after a user configured a hosted
 * provider: the row stays active in the DB, but PUT now rejects that provider,
 * so a revoke button on it would be guaranteed to fail. */
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
	// null = not probed yet. false = the deployment doesn't have this feature,
	// so the caller renders nothing at all.
	supported = $state<boolean | null>(null);
	loading = $state(false);
	// Section-level failure: the form still renders so the user can retry.
	error = $state<string | null>(null);
	rows = $state<ProviderRow[]>([]);
	// Both keyed by provider, so one row's failure can't disturb another's.
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
			// 404 is _require_multi_user; 401 means there's no session to act
			// under. Neither is actionable in the form, so hide it.
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

	/** `key` is an argument only — it is never assigned to this instance. */
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
			// PUT answers with { configured } only, so created_at can only come
			// from a re-read. That also means no display state is ever derived
			// from the key the user just submitted.
			this.rows = toRows(await fetchProviderKeys());
			return true;
		} catch (cause) {
			// Leave `rows` alone: a failed write must not disturb the rest of
			// the section.
			this.errors = { ...this.errors, [provider]: message(cause, fallback) };
			return false;
		} finally {
			const { [provider]: _done, ...others } = this.busy;
			this.busy = others;
		}
	}
}
