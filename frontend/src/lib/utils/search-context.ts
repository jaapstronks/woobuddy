/**
 * Slice a context string around a match so the renderer can wrap the
 * matching segment in a `<mark>`.
 *
 * The `context` already carries ellipses and collapsed whitespace (built
 * by the search-redact service). The original casing inside `context`
 * may differ from `matchText` — "Jan" may appear as "jan" in the
 * lowercased snippet used for window alignment — so we match
 * case-insensitively and return the slice from the original string.
 *
 * If the match isn't found (shouldn't happen under normal flow, but
 * guards against weird diacritic/casing edge cases), we return the full
 * context as `before` with empty `match`/`after`. The UI still renders
 * the context correctly, just without a highlight.
 */
export interface HighlightedContext {
	before: string;
	match: string;
	after: string;
}

export function highlightedContext(
	context: string,
	matchText: string
): HighlightedContext {
	const idx = context.toLowerCase().indexOf(matchText.toLowerCase());
	if (idx === -1) return { before: context, match: '', after: '' };
	return {
		before: context.slice(0, idx),
		match: context.slice(idx, idx + matchText.length),
		after: context.slice(idx + matchText.length)
	};
}
