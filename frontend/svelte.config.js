import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		// Remove this override when Svelte 6 makes runes universal.
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		// FastAPI serves the static SPA bundle.
		adapter: adapter({ fallback: '200.html' })
	}
};

export default config;
