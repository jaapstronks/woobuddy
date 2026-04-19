/**
 * Site mode — distinguishes the hosted woobuddy.nl deployment from
 * any self-hosted fork.
 *
 * The hosted tier ships a marketing-heavy landing page (headline,
 * demo video, "how it works", lead-capture form) plus static pages
 * that are specific to woobuddy.nl (legal, roadmap). A self-hosted
 * fork inherits the same codebase but almost certainly wants a
 * neutral landing that drops the reviewer straight into the upload
 * flow and doesn't advertise someone else's service or publish
 * someone else's legal pages under their own domain.
 *
 * Set `PUBLIC_SITE_MODE=hosted` in the environment that runs
 * woobuddy.nl. Everything else — dev, self-host, forks — leaves it
 * unset and gets the neutral default.
 */
import { env } from '$env/dynamic/public';

export type SiteMode = 'hosted' | 'selfhost';

export function siteMode(): SiteMode {
	return env.PUBLIC_SITE_MODE === 'hosted' ? 'hosted' : 'selfhost';
}

export function isHosted(): boolean {
	return siteMode() === 'hosted';
}
