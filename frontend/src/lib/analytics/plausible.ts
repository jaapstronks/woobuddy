/**
 * Plausible Analytics wrapper — self-hosted, cookieless, SSR-safe.
 *
 * We use the `script.manual.js` variant so pageviews fire through this module
 * and can be normalized before they leave the browser. That lets us collapse
 * `/review/<uuid>` into `/review/:docId` in the dashboard, keeping the stats
 * useful and avoiding the illusion that every document is its own page.
 *
 * The wrapper is a safe no-op whenever `PUBLIC_PLAUSIBLE_DOMAIN` is unset or
 * `window.plausible` isn't loaded (SSR, dev, blocked by user's network, CSP
 * misconfiguration). Callers never need to guard their `track()` calls.
 *
 * Privacy: event names and props are enumerated in `events.ts`. Props are
 * coarse buckets only — never filenames, entity text, detection counts that
 * could fingerprint a specific document, or any user-identifying data.
 */

import { env } from '$env/dynamic/public';
import { browser } from '$app/environment';
import type { PlausibleEventName, PlausibleEventProps } from './events';

type PlausibleFn = (
	event: string,
	options?: { u?: string; props?: Record<string, string | number | boolean> }
) => void;

declare global {
	interface Window {
		plausible?: PlausibleFn & { q?: unknown[] };
	}
}

export function isEnabled(): boolean {
	return browser && !!env.PUBLIC_PLAUSIBLE_DOMAIN;
}

/**
 * Rewrite `/review/<uuid>` → `/review/:docId` so the dashboard aggregates
 * all review sessions under one row instead of one-per-document.
 */
export function normalizePath(pathname: string): string {
	if (!pathname.startsWith('/review/')) return pathname;
	const parts = pathname.split('/').filter(Boolean);
	if (parts.length < 2) return pathname;
	const rest = parts.slice(2).join('/');
	return rest ? `/review/:docId/${rest}` : '/review/:docId';
}

function absoluteUrlFromLocation(): string {
	const { origin, search } = window.location;
	return `${origin}${normalizePath(window.location.pathname)}${search}`;
}

/**
 * Fire a pageview. Called from the root layout on initial mount and on every
 * client-side navigation. No-op when analytics is disabled.
 */
export function pageview(url?: string): void {
	if (!isEnabled() || !window.plausible) return;
	window.plausible('pageview', { u: url ?? absoluteUrlFromLocation() });
}

/**
 * Fire a custom event. Call sites use the enumerated names in `events.ts`.
 * Props are passed through as-is but should stay coarse — see the privacy
 * note at the top of this file.
 */
export function track<E extends PlausibleEventName>(
	event: E,
	props?: PlausibleEventProps[E]
): void {
	if (!isEnabled() || !window.plausible) return;
	window.plausible(event, {
		u: absoluteUrlFromLocation(),
		props: props as Record<string, string | number | boolean> | undefined
	});
}
