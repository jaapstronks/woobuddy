/**
 * Recent Woo articles — tiny client-side LRU persisted in localStorage.
 *
 * Used by the manual text-redaction form (#06) to pin the reviewer's most
 * recently used articles at the top of the dropdown. This is ergonomic
 * sugar only; nothing about the decision itself is stored client-side.
 */

import type { WooArticleCode } from '$lib/types';

const STORAGE_KEY = 'woobuddy.recentArticles';
const MAX_RECENT = 5;

export function getRecentArticles(): WooArticleCode[] {
	if (typeof window === 'undefined') return [];
	try {
		const raw = window.localStorage.getItem(STORAGE_KEY);
		if (!raw) return [];
		const parsed = JSON.parse(raw);
		return Array.isArray(parsed) ? (parsed as WooArticleCode[]).slice(0, MAX_RECENT) : [];
	} catch {
		return [];
	}
}

export function recordRecentArticle(code: WooArticleCode): void {
	if (typeof window === 'undefined') return;
	try {
		const current = getRecentArticles().filter((c) => c !== code);
		const next = [code, ...current].slice(0, MAX_RECENT);
		window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
	} catch {
		// localStorage unavailable (private mode, disabled) — just skip.
	}
}
