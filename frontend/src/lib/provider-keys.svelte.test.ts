import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import.meta.env.VITE_API_BASE = 'http://api.test';

const { ProviderKeysStore, toRows } = await import('./provider-keys.svelte');

type Res = Awaited<ReturnType<typeof import('./api').fetchProviderKeys>>;

const res = (over: Partial<Res> = {}): Res => ({
	providers: ['groq', 'deepseek', 'anthropic', 'local'],
	default: 'anthropic',
	keys: [],
	...over
});

const ok = (body: unknown) =>
	({ ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve(body) }) as Response;

const err = (status: number, detail: string) =>
	({
		ok: false,
		status,
		statusText: 'Error',
		headers: new Headers(),
		json: () => Promise.resolve({ detail })
	}) as Response;

let fetchSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
	fetchSpy = vi.fn();
	vi.stubGlobal('fetch', fetchSpy);
});

afterEach(() => {
	vi.unstubAllGlobals();
});

const bodyOf = (call: number) =>
	JSON.parse((fetchSpy.mock.calls[call][1] as RequestInit).body as string);

describe('toRows', () => {
	it('treats a revoked row as not configured', () => {
		const rows = toRows(
			res({
				providers: ['groq', 'anthropic'],
				keys: [
					{ provider: 'groq', created_at: '2026-01-01T00:00:00', revoked_at: null },
					{ provider: 'anthropic', created_at: '2026-01-01T00:00:00', revoked_at: '2026-02-01T00:00:00' }
				]
			})
		);
		expect(rows.map((r) => r.status)).toEqual(['configured', 'revoked']);
	});

	it('reports a provider with no key row as unset', () => {
		expect(toRows(res({ providers: ['groq'] }))[0].status).toBe('unset');
	});

	it('emits exactly the server catalogue, in order', () => {
		const rows = toRows(res());
		expect(rows.map((r) => r.provider)).toEqual(['groq', 'deepseek', 'anthropic', 'local']);
		expect(rows.filter((r) => r.isDefault).map((r) => r.provider)).toEqual(['anthropic']);
	});

	it('offers only local when LLM_LOCAL_ONLY filtered the registry', () => {
		const rows = toRows(res({ providers: ['local'], default: 'local' }));
		expect(rows.map((r) => r.provider)).toEqual(['local']);
	});

	it('drops key rows for providers absent from the catalogue', () => {
		// LLM_LOCAL_ONLY turned on after the user configured groq: the row is
		// still active in the DB but PUT would now reject it.
		const rows = toRows(
			res({
				providers: ['local'],
				default: 'local',
				keys: [{ provider: 'groq', created_at: '2026-01-01T00:00:00', revoked_at: null }]
			})
		);
		expect(rows.map((r) => r.provider)).toEqual(['local']);
		expect(rows[0].status).toBe('unset');
	});
});

describe('ProviderKeysStore.load', () => {
	it('hides the section on a 404 from _require_multi_user', async () => {
		fetchSpy.mockResolvedValueOnce(err(404, 'Not found'));
		const store = new ProviderKeysStore();
		await store.load();
		expect(store.supported).toBe(false);
		expect(store.rows).toEqual([]);
	});

	it('hides the section on a 401', async () => {
		fetchSpy.mockResolvedValueOnce(err(401, 'Not authenticated'));
		const store = new ProviderKeysStore();
		await store.load();
		expect(store.supported).toBe(false);
	});

	it('keeps the section usable on any other failure', async () => {
		fetchSpy.mockResolvedValueOnce(err(500, 'Database unavailable'));
		const store = new ProviderKeysStore();
		await store.load();
		expect(store.supported).toBe(true);
		expect(store.error).toBe('Database unavailable');
	});
});

describe('ProviderKeysStore.save', () => {
	it('sends exactly { provider, key } and re-reads the list', async () => {
		fetchSpy.mockResolvedValueOnce(ok({ configured: true }));
		fetchSpy.mockResolvedValueOnce(
			ok(res({ keys: [{ provider: 'groq', created_at: '2026-01-01T00:00:00', revoked_at: null }] }))
		);
		const store = new ProviderKeysStore();
		expect(await store.save('groq', 'gsk_x')).toBe(true);

		const init = fetchSpy.mock.calls[0][1] as RequestInit;
		expect(init.method).toBe('PUT');
		expect((init.headers as Record<string, string>)['X-Requested-With']).toBe('surgite-web');
		expect(bodyOf(0)).toEqual({ provider: 'groq', key: 'gsk_x' });
		expect(fetchSpy.mock.calls[1][0]).toBe('http://api.test/settings/provider-keys');
		expect(store.rows.find((r) => r.provider === 'groq')?.status).toBe('configured');
		expect(store.errors.groq).toBeUndefined();
	});

	it('records the server detail per row and leaves the rest alone', async () => {
		fetchSpy.mockResolvedValueOnce(ok(res()));
		const store = new ProviderKeysStore();
		await store.load();
		const before = store.rows;

		fetchSpy.mockResolvedValueOnce(err(400, 'key is required unless clear=true'));
		expect(await store.save('groq', '')).toBe(false);

		expect(store.errors.groq).toBe('key is required unless clear=true');
		expect(store.errors.anthropic).toBeUndefined();
		expect(store.rows).toBe(before);
		expect(store.error).toBeNull();
	});

	it('clears a stale row error on the next attempt', async () => {
		const store = new ProviderKeysStore();
		fetchSpy.mockResolvedValueOnce(err(502, 'Bad gateway'));
		await store.save('groq', 'gsk_x');
		expect(store.errors.groq).toBe('Bad gateway');

		fetchSpy.mockResolvedValueOnce(ok({ configured: true }));
		fetchSpy.mockResolvedValueOnce(ok(res()));
		await store.save('groq', 'gsk_x');
		expect(store.errors.groq).toBeUndefined();
	});

	it('marks only the acting provider busy while in flight', async () => {
		let release: (r: Response) => void = () => {};
		fetchSpy.mockReturnValueOnce(new Promise<Response>((r) => (release = r)));
		const store = new ProviderKeysStore();
		const pending = store.save('groq', 'gsk_x');
		expect(store.busy).toEqual({ groq: true });

		release(ok({ configured: true }));
		fetchSpy.mockResolvedValueOnce(ok(res()));
		await pending;
		expect(store.busy).toEqual({});
	});

	it('never retains the key, on success or failure', async () => {
		const secret = 'gsk_secret_value';

		fetchSpy.mockResolvedValueOnce(ok({ configured: true }));
		fetchSpy.mockResolvedValueOnce(
			ok(res({ keys: [{ provider: 'groq', created_at: '2026-01-01T00:00:00', revoked_at: null }] }))
		);
		const store = new ProviderKeysStore();
		await store.save('groq', secret);
		expect(JSON.stringify({ ...store })).not.toContain(secret);

		fetchSpy.mockResolvedValueOnce(err(502, 'Bad gateway'));
		await store.save('groq', secret);
		expect(JSON.stringify({ ...store })).not.toContain(secret);
	});
});

describe('ProviderKeysStore.revoke', () => {
	it('sends exactly { provider, clear: true } with no key field', async () => {
		fetchSpy.mockResolvedValueOnce(ok({ configured: false }));
		fetchSpy.mockResolvedValueOnce(
			ok(
				res({
					keys: [
						{ provider: 'groq', created_at: '2026-01-01T00:00:00', revoked_at: '2026-02-01T00:00:00' }
					]
				})
			)
		);
		const store = new ProviderKeysStore();
		expect(await store.revoke('groq')).toBe(true);

		const body = bodyOf(0);
		expect(body).toEqual({ provider: 'groq', clear: true });
		expect('key' in body).toBe(false);
		expect(store.rows.find((r) => r.provider === 'groq')?.status).toBe('revoked');
	});

	it('surfaces a failure on the row without changing it', async () => {
		fetchSpy.mockResolvedValueOnce(err(400, "Unknown provider 'groq'"));
		const store = new ProviderKeysStore();
		expect(await store.revoke('groq')).toBe(false);
		expect(store.errors.groq).toBe("Unknown provider 'groq'");
	});
});
