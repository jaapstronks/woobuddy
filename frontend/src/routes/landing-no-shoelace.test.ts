/**
 * Doctrine gate for the landing page (#68).
 *
 * CLAUDE.md: "The landing page at `/` stays SSR-compatible and does NOT use
 * Shoelace." Until #68 that was false — `ProgressSteps` and
 * `ProviderPickerButtons` pulled `progress-bar.js` in at top level, so Lit
 * was evaluated in Node on every render of `/` and shipped in the landing
 * chunk. This test walks the static import graph from `routes/+page.svelte`
 * (and the root layout / error page it renders inside) and fails on the
 * first reachable module that imports `@shoelace-style`.
 *
 * Same technique as `file-picker/network-isolation.test.ts`: sources are
 * read through Vite's raw glob so we don't need `node:fs` or a full
 * SvelteKit runtime in vitest. Only `$lib/…` and relative specifiers are
 * followed; bare packages and `$app/*` / `$env/*` are leaves.
 */
import { describe, it, expect } from 'vitest';

const SOURCES = import.meta.glob('/src/**/*.{ts,svelte}', {
	query: '?raw',
	import: 'default',
	eager: true
}) as Record<string, string>;

const ENTRYPOINTS = ['/src/routes/+page.svelte', '/src/routes/+layout.svelte', '/src/routes/+error.svelte'];

const IMPORT_RE = /(?:^|\n)\s*(?:import|export)\b[^'"\n]*?from\s*['"]([^'"]+)['"]|(?:^|\n)\s*import\s*['"]([^'"]+)['"]/g;

function specifiers(body: string): string[] {
	const out: string[] = [];
	for (const m of body.matchAll(IMPORT_RE)) out.push(m[1] ?? m[2]);
	return out;
}

function normalize(path: string): string {
	const parts: string[] = [];
	for (const seg of path.split('/')) {
		if (seg === '' || seg === '.') continue;
		if (seg === '..') parts.pop();
		else parts.push(seg);
	}
	return '/' + parts.join('/');
}

/** Map a specifier to a key in SOURCES, or null when it's a leaf (package, $app, $env, css). */
function resolve(spec: string, from: string): string | null {
	let base: string;
	if (spec.startsWith('$lib/')) base = '/src/lib/' + spec.slice('$lib/'.length);
	else if (spec.startsWith('./') || spec.startsWith('../')) {
		base = normalize(from.slice(0, from.lastIndexOf('/')) + '/' + spec);
	} else return null;

	const candidates = [
		base,
		`${base}.ts`,
		`${base}.svelte`,
		`${base}.svelte.ts`,
		`${base}/index.ts`,
		// `$lib/stores/foo.svelte` is `foo.svelte.ts` on disk (see vitest.config.ts).
		base.endsWith('.svelte') ? `${base}.ts` : ''
	];
	return candidates.find((c) => c && c in SOURCES) ?? null;
}

function reachable(entries: string[]): Set<string> {
	const seen = new Set<string>();
	const queue = [...entries];
	while (queue.length) {
		const file = queue.pop()!;
		if (seen.has(file)) continue;
		seen.add(file);
		for (const spec of specifiers(SOURCES[file])) {
			const next = resolve(spec, file);
			if (next && !seen.has(next)) queue.push(next);
		}
	}
	return seen;
}

describe('landing page — no Shoelace in the SSR import graph (#68)', () => {
	for (const entry of ENTRYPOINTS) {
		it(`${entry} exists`, () => {
			expect(entry in SOURCES).toBe(true);
		});
	}

	it('walks a non-trivial graph (guards against the resolver silently matching nothing)', () => {
		const graph = reachable(ENTRYPOINTS);
		expect(graph.size).toBeGreaterThan(10);
		expect(graph.has('/src/lib/components/shared/ProgressSteps.svelte')).toBe(true);
		expect(graph.has('/src/lib/components/shared/ProviderPickerButtons.svelte')).toBe(true);
	});

	it('reaches zero @shoelace-style modules', () => {
		const offenders = [...reachable(ENTRYPOINTS)].filter((file) =>
			specifiers(SOURCES[file]).some((s) => s.startsWith('@shoelace-style'))
		);
		expect(offenders).toEqual([]);
	});

	it('the resolver would catch the review route, which does use Shoelace', () => {
		const offenders = [...reachable(['/src/routes/review/[docId]/+page.svelte'])].filter((file) =>
			specifiers(SOURCES[file]).some((s) => s.startsWith('@shoelace-style'))
		);
		expect(offenders.length).toBeGreaterThan(0);
	});
});
