// FastAPI serves a prerendered client-side shell.
export const ssr = false;
export const prerender = true;

import { redirect } from '@sveltejs/kit';
import { fetchCurrentUser } from '$lib/api';
import type { CurrentUser } from '$lib/api';

const PUBLIC = ['/login', '/signup', '/password-reset', '/health', '/s/'];

function isPublic(pathname: string): boolean {
	return PUBLIC.some((p) => pathname === p || pathname.startsWith(p));
}

export async function load({
	url
}: {
	url: URL;
}): Promise<{ user: CurrentUser | null }> {
	if (isPublic(url.pathname)) return { user: null };
	try {
		const user = await fetchCurrentUser();
		return { user };
	} catch (e) {
		// Do not turn transient API failures into login redirects.
		if ((e as { status?: number }).status === 401) {
			throw redirect(302, '/login?retry=1');
		}
		throw e;
	}
}
