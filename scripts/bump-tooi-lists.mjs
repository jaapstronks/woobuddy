#!/usr/bin/env node
/**
 * Refresh the vendored TOOI value lists used by the DiWoo publication
 * export (#52). Pulls the current state of the SCW waardelijsten from
 * standaarden.overheid.nl and writes them to
 * `frontend/static/diwoo-tooi-lists/`.
 *
 * Run annually, or whenever the DiWoo metadata schema bumps a minor
 * version. The Dutch Woo informatiecategorieen list is stable
 * (statutory enumeration), so updates are mostly editorial; the format
 * list grows slowly. The full organisations register is intentionally
 * not fetched here — see `organisaties.json` for the rationale.
 *
 * Usage:
 *   node scripts/bump-tooi-lists.mjs
 *   node scripts/bump-tooi-lists.mjs --check   # exit 1 if vendored copy is stale
 *
 * The script uses only built-in Node 18+ (global fetch). No deps.
 */

import { writeFile, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const ROOT = join(dirname(__filename), '..');
const OUT_DIR = join(ROOT, 'frontend', 'static', 'diwoo-tooi-lists');

const SOURCES = {
	informatiecategorieen: {
		lijstUri: 'https://identifier.overheid.nl/tooi/set/scw_woo_informatiecategorieen/3',
		page:
			'https://standaarden.overheid.nl/tooi/waardelijsten/expression?lijst_uri=https://identifier.overheid.nl/tooi/set/scw_woo_informatiecategorieen/3',
		out: 'informatiecategorieen.json'
	},
	formatlijst: {
		lijstUri: 'https://identifier.overheid.nl/tooi/set/scw_formats/1',
		page: 'https://standaarden.overheid.nl/tooi/waardelijsten/expression?lijst_uri=https://identifier.overheid.nl/tooi/set/scw_formats/1',
		out: 'formatlijst.json'
	}
};

const SCHEMA_DOC = 'https://standaarden.overheid.nl/diwoo/metadata/doc/0.9.8';

const args = new Set(process.argv.slice(2));
const checkOnly = args.has('--check');

async function fetchHtml(url) {
	const res = await fetch(url, { headers: { Accept: 'text/html' } });
	if (!res.ok) throw new Error(`Fetch ${url} → ${res.status}`);
	return await res.text();
}

/**
 * Quick-and-dirty extraction: the SCW expression page renders a table
 * with `<a href=".../tooi/def/thes/kern/c_XXXX">label</a>` for each
 * concept. We don't depend on Atom/JSON-LD output because the resolver
 * surface has changed historically — the HTML table is the most stable
 * thing on offer.
 */
function parseConceptList(html) {
	const out = [];
	const seen = new Set();
	const re =
		/href="(https:\/\/identifier\.overheid\.nl\/tooi\/def\/thes\/kern\/c_[0-9a-f]+)"[^>]*>([^<]+)</g;
	let m;
	while ((m = re.exec(html))) {
		const uri = m[1];
		const label = m[2].replace(/\s+/g, ' ').trim();
		if (seen.has(uri)) continue;
		seen.add(uri);
		out.push({ uri, label });
	}
	return out;
}

async function bumpOne(key) {
	const src = SOURCES[key];
	const html = await fetchHtml(src.page);
	const items = parseConceptList(html);
	if (items.length === 0) {
		throw new Error(`No items extracted for ${key} — page format may have changed.`);
	}
	const payload = {
		$schema: SCHEMA_DOC,
		lijst_uri: src.lijstUri,
		items
	};
	const path = join(OUT_DIR, src.out);
	const next = JSON.stringify(payload, null, '\t') + '\n';

	if (checkOnly) {
		const current = await readFile(path, 'utf8').catch(() => '');
		if (current.trim() !== next.trim()) {
			console.error(`[stale] ${src.out} differs from upstream`);
			process.exitCode = 1;
		} else {
			console.log(`[ok]    ${src.out} matches upstream`);
		}
		return;
	}

	await writeFile(path, next, 'utf8');
	console.log(`[wrote] ${src.out} (${items.length} items)`);
}

async function bumpVersion() {
	if (checkOnly) return;
	const payload = {
		diwoo_metadata_schema_version: '0.9.8',
		diwoo_metadata_schema_url: SCHEMA_DOC,
		informatiecategorieen_lijst_uri: SOURCES.informatiecategorieen.lijstUri,
		formatlijst_lijst_uri: SOURCES.formatlijst.lijstUri,
		last_bumped_at: new Date().toISOString().slice(0, 10),
		bumped_by: 'scripts/bump-tooi-lists.mjs'
	};
	await writeFile(join(OUT_DIR, 'version.json'), JSON.stringify(payload, null, '\t') + '\n', 'utf8');
	console.log('[wrote] version.json');
}

for (const key of Object.keys(SOURCES)) {
	await bumpOne(key);
}
await bumpVersion();
