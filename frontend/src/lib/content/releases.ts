/**
 * Release notes for `/changelog` (#101).
 *
 * The repository has two changelogs on purpose. `CHANGELOG.md` is generated
 * by release-please from the Conventional-Commit titles: English, commit
 * granularity, for developers and self-hosters. This one is hand-written
 * Dutch at reader-benefit granularity, for the civil servant doing the
 * redacting. See `docs/reference/versioning.md`.
 *
 * One markdown file per version in `src/content/releases/`, named after the
 * version so the file name is also the anchor on the page. `_template.md`
 * carries the writing rules and is skipped here.
 *
 * The markdown is read through Vite's raw glob and rendered at module load,
 * which means it happens once per server process rather than per request.
 * This module is imported only from `+page.server.ts`, so `marked` never
 * reaches the client bundle.
 */
import { marked } from 'marked';

export interface ReleaseNote {
	/** Semver, e.g. `0.2.0`. Doubles as the anchor id on `/changelog`. */
	version: string;
	/** ISO date the release was cut. */
	date: string;
	/** One sentence, shown under the version heading. */
	summary: string;
	/** True for exactly one note: the most recent release. */
	latest: boolean;
	/** Rendered HTML of the note body. */
	html: string;
}

const FILES = import.meta.glob('/src/content/releases/*.md', {
	query: '?raw',
	import: 'default',
	eager: true
}) as Record<string, string>;

const FRONTMATTER = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/;

/**
 * Parse the small frontmatter dialect the release notes use: flat
 * `key: value` lines, no nesting, no lists. Deliberately not a YAML
 * parser — the files are ours and `_template.md` documents the shape,
 * so an unexpected key is a mistake worth failing the build over rather
 * than a case to support.
 */
function parseFrontmatter(source: string, file: string): { meta: Record<string, string>; body: string } {
	const match = FRONTMATTER.exec(source);
	if (!match) throw new Error(`${file}: missing frontmatter block`);

	const meta: Record<string, string> = {};
	for (const line of match[1].split('\n')) {
		if (!line.trim()) continue;
		const sep = line.indexOf(':');
		if (sep === -1) throw new Error(`${file}: frontmatter line is not "key: value": ${line}`);
		meta[line.slice(0, sep).trim()] = line.slice(sep + 1).trim();
	}
	return { meta, body: source.slice(match[0].length) };
}

/** `0.10.0` sorts above `0.9.0`; a string compare would get that backwards. */
function compareVersionsDesc(a: string, b: string): number {
	const pa = a.split('.').map(Number);
	const pb = b.split('.').map(Number);
	for (let i = 0; i < 3; i++) {
		if (pa[i] !== pb[i]) return pb[i] - pa[i];
	}
	return 0;
}

export function loadReleaseNotes(): ReleaseNote[] {
	const notes: ReleaseNote[] = [];

	for (const [path, source] of Object.entries(FILES)) {
		const name = path.slice(path.lastIndexOf('/') + 1, -'.md'.length);
		if (name.startsWith('_')) continue;

		const { meta, body } = parseFrontmatter(source, path);
		for (const key of ['version', 'date', 'summary', 'latest']) {
			if (!(key in meta)) throw new Error(`${path}: frontmatter is missing "${key}"`);
		}
		if (meta.version !== name) {
			throw new Error(`${path}: frontmatter version "${meta.version}" does not match the file name`);
		}
		if (!/^\d+\.\d+\.\d+$/.test(meta.version)) {
			throw new Error(`${path}: "${meta.version}" is not a MAJOR.MINOR.PATCH version`);
		}
		if (!/^\d{4}-\d{2}-\d{2}$/.test(meta.date)) {
			throw new Error(`${path}: "${meta.date}" is not an ISO date`);
		}

		notes.push({
			version: meta.version,
			date: meta.date,
			summary: meta.summary,
			latest: meta.latest === 'true',
			html: marked.parse(body.trim(), { async: false })
		});
	}

	notes.sort((a, b) => compareVersionsDesc(a.version, b.version));

	const latest = notes.filter((n) => n.latest);
	if (latest.length !== 1) {
		throw new Error(`expected exactly one note with "latest: true", found ${latest.length}`);
	}
	if (latest[0].version !== notes[0].version) {
		throw new Error(
			`"latest: true" is on ${latest[0].version} but ${notes[0].version} is the highest version`
		);
	}

	return notes;
}

const MONTHS = [
	'januari', 'februari', 'maart', 'april', 'mei', 'juni',
	'juli', 'augustus', 'september', 'oktober', 'november', 'december'
];

/** `2026-09-09` → `9 september 2026`. */
export function formatDutchDate(iso: string): string {
	const [year, month, day] = iso.split('-').map(Number);
	return `${day} ${MONTHS[month - 1]} ${year}`;
}
