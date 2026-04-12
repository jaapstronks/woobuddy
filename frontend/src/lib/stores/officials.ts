/**
 * Public officials store — manages the per-dossier reference list of
 * names that should NOT be redacted.
 */

import { getOfficials, uploadOfficials } from '$lib/api/client';
import type { PublicOfficial } from '$lib/types';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let officials = $state<PublicOfficial[]>([]);
let loading = $state(false);
let error = $state<string | null>(null);

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function load(dossierId: string) {
	loading = true;
	error = null;
	try {
		officials = await getOfficials(dossierId);
	} catch (e) {
		error = e instanceof Error ? e.message : 'Laden mislukt';
	} finally {
		loading = false;
	}
}

async function upload(dossierId: string, file: File) {
	loading = true;
	error = null;
	try {
		const newOfficials = await uploadOfficials(dossierId, file);
		officials = [...officials, ...newOfficials];
	} catch (e) {
		error = e instanceof Error ? e.message : 'Upload mislukt';
	} finally {
		loading = false;
	}
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export const officialsStore = {
	get all() {
		return officials;
	},
	get loading() {
		return loading;
	},
	get error() {
		return error;
	},
	load,
	upload
};
