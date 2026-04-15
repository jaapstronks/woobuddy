import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

const libDir = fileURLToPath(new URL('./src/lib', import.meta.url));

export default defineConfig({
	plugins: [svelte()],
	resolve: {
		// Svelte 5 runes files live in `.svelte.ts`; code imports them as
		// `$lib/foo.svelte` (the `.ts` suffix is dropped). Vite's default
		// extension list only tries appending suffixes to bare specifiers,
		// so we add a dedicated alias that maps `.svelte` imports in
		// `$lib/stores/` back to `.svelte.ts` on disk. Narrow enough to not
		// clash with real `.svelte` component files (which do not live in
		// `stores/`).
		alias: [
			{
				find: /^\$lib\/stores\/(.+)\.svelte$/,
				replacement: path.join(libDir, 'stores') + path.sep + '$1.svelte.ts'
			},
			{
				find: '$lib',
				replacement: libDir
			}
		]
	},
	test: {
		include: ['src/**/*.test.ts'],
		environment: 'node'
	}
});
