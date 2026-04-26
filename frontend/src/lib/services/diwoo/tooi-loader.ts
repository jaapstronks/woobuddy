/**
 * Tiny browser-side cache for the vendored TOOI value-list metadata
 * (#52). The dialog and the bundle assembler both want the schema
 * version; fetching it twice from the same origin would be silly.
 */

interface VersionPayload {
	diwoo_metadata_schema_version: string;
	diwoo_metadata_schema_url: string;
	informatiecategorieen_lijst_uri: string;
	formatlijst_lijst_uri: string;
	last_bumped_at: string;
}

let cached: VersionPayload | null = null;
let inflight: Promise<VersionPayload> | null = null;

export async function loadTooiVersion(): Promise<VersionPayload> {
	if (cached) return cached;
	if (inflight) return inflight;
	inflight = fetch('/diwoo-tooi-lists/version.json')
		.then((res) => {
			if (!res.ok) throw new Error(`TOOI version load failed: ${res.status}`);
			return res.json() as Promise<VersionPayload>;
		})
		.then((payload) => {
			cached = payload;
			return payload;
		})
		.finally(() => {
			inflight = null;
		});
	return inflight;
}

export function getCachedTooiVersion(): VersionPayload | null {
	return cached;
}
