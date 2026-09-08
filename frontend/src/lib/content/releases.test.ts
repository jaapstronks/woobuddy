/**
 * Gates on the release notes themselves (#101).
 *
 * The notes are hand-written and the loader throws on anything malformed,
 * so these tests are really about failing in CI rather than on the first
 * request to `/changelog` in production.
 */
import { describe, it, expect } from 'vitest';
import { loadReleaseNotes, formatDutchDate } from './releases';

describe('release notes', () => {
	const notes = loadReleaseNotes();

	it('loads every version in src/content/releases (and skips _template.md)', () => {
		expect(notes.length).toBeGreaterThanOrEqual(2);
		expect(notes.map((n) => n.version)).toContain('0.1.0');
		expect(notes.every((n) => !n.version.startsWith('_'))).toBe(true);
	});

	it('sorts newest first, numerically', () => {
		const versions = notes.map((n) => n.version);
		const sorted = [...versions].sort((a, b) => {
			const pa = a.split('.').map(Number);
			const pb = b.split('.').map(Number);
			return pb[0] - pa[0] || pb[1] - pa[1] || pb[2] - pa[2];
		});
		expect(versions).toEqual(sorted);
	});

	it('marks exactly one note as latest, and it is the highest version', () => {
		const latest = notes.filter((n) => n.latest);
		expect(latest).toHaveLength(1);
		expect(latest[0].version).toBe(notes[0].version);
	});

	it('renders markdown to HTML', () => {
		for (const note of notes) {
			expect(note.html).toContain('<p>');
			expect(note.html).not.toContain('###');
		}
	});

	it('keeps em dashes out of the Dutch copy (house style)', () => {
		for (const note of notes) {
			expect(`${note.summary}\n${note.html}`).not.toContain('—');
		}
	});

	it('formats dates in Dutch', () => {
		expect(formatDutchDate('2026-09-09')).toBe('9 september 2026');
		expect(formatDutchDate('2026-04-26')).toBe('26 april 2026');
	});
});
