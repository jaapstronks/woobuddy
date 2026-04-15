import { redirect } from '@sveltejs/kit';

// /try was folded into the landing page — the hero now hosts the upload
// drop zone directly. Keep a permanent redirect so existing share links and
// the old og:url keep resolving.
export function load() {
	throw redirect(308, '/#try');
}
