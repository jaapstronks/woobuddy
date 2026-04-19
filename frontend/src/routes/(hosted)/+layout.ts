import { error } from '@sveltejs/kit';
import { isHosted } from '$lib/config/site';

/**
 * Routes nested under `(hosted)/` are only served on the woobuddy.nl
 * hosted tier — they contain marketing copy, legal pages, and product
 * roadmap that are specific to our deployment and would be misleading
 * under a fork's own domain. Self-hosters get a 404 instead; they can
 * remove this guard (or flip `PUBLIC_SITE_MODE=hosted`) if they want
 * to reuse the pages as a starting point for their own.
 */
export function load() {
	if (!isHosted()) {
		throw error(404, 'Not found');
	}
}
