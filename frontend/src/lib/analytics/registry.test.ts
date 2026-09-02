/**
 * `events.ts` is the single registry of Plausible events: "if an event
 * isn't here, it isn't fired". That only holds if nothing else touches
 * `window.plausible` — #68 found `file-picker/analytics.ts` doing exactly
 * that with three unregistered events. This test keeps the wrapper in
 * `plausible.ts` the only call site.
 */
import { describe, it, expect } from 'vitest';

const SOURCES = import.meta.glob('/src/**/*.{ts,svelte}', {
	query: '?raw',
	import: 'default',
	eager: true
}) as Record<string, string>;

const WRAPPER = '/src/lib/analytics/plausible.ts';

describe('analytics — single event registry', () => {
	it('only plausible.ts touches window.plausible', () => {
		const offenders = Object.entries(SOURCES)
			.filter(([path]) => path !== WRAPPER && !path.endsWith('.test.ts'))
			.filter(([, body]) => /window\s*\.\s*plausible\b/.test(body))
			.map(([path]) => path);
		expect(offenders).toEqual([]);
	});

	it('the wrapper itself is scanned (guards against a moved file)', () => {
		expect(WRAPPER in SOURCES).toBe(true);
		expect(/window\.plausible/.test(SOURCES[WRAPPER])).toBe(true);
	});
});
