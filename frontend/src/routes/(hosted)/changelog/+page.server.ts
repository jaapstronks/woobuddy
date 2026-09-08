import { loadReleaseNotes, formatDutchDate } from '$lib/content/releases';

/**
 * Server-only so `marked` and the raw markdown stay out of the client
 * bundle: the page is read, not interacted with. The notes are parsed once
 * per server process (module scope in `$lib/content/releases`), so this
 * load is a hand-off, not work.
 *
 * The date is formatted here rather than in the component for the same
 * reason: importing anything from `$lib/content/releases` into a `.svelte`
 * file would pull `marked` back into the client graph.
 * `ssr-no-shoelace.test.ts` asserts that it stays out.
 */
export function load() {
	return {
		notes: loadReleaseNotes().map((note) => ({
			...note,
			dateLabel: formatDutchDate(note.date)
		}))
	};
}
