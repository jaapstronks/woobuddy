/**
 * AFM-weighted character metrics for pdf.js text items.
 *
 * pdf.js hands us a text item as one string plus one box. Both directions
 * of the client-side join between characters and pixels need to know where
 * inside that box a given character sits:
 *
 * - `bbox-text-resolver.ts` goes pixels → characters: a bbox narrower than
 *   the item (the backend already narrowed it in `_narrow_bbox_to_substring`)
 *   has to be sliced back to the substring it covers.
 * - `search-redact.ts` goes characters → pixels: a search hit inside a
 *   line-wide item has to be narrowed to a box around just the match.
 *
 * Both use the same weighting, so it lives here once. A linear
 * by-character-count mapping is not good enough: "Wethouder" is full of wide
 * glyphs (W, d, u, o) and narrow ones (t, e, r), which shifts the perceived
 * boundary of the following name by more than a character.
 */

// Helvetica/Arial AFM advance widths in 1/1000 em. Mirrors the backend's
// `_GLYPH_WIDTHS` table in `span_resolver.py` so the client's x-to-character
// mapping agrees with the bbox narrowing the backend just did. Glyphs outside
// this table fall back to `DEFAULT_GLYPH_WIDTH`, matching the backend's
// behavior for non-ASCII glyphs.
const DEFAULT_GLYPH_WIDTH = 500;
const GLYPH_WIDTHS: Record<string, number> = {
	' ': 278, '!': 278, '"': 355, '#': 556, '$': 556, '%': 889, '&': 667,
	"'": 191, '(': 333, ')': 333, '*': 389, '+': 584, ',': 278, '-': 333,
	'.': 278, '/': 278,
	'0': 556, '1': 556, '2': 556, '3': 556, '4': 556, '5': 556, '6': 556,
	'7': 556, '8': 556, '9': 556,
	':': 278, ';': 278, '<': 584, '=': 584, '>': 584, '?': 556, '@': 1015,
	A: 667, B: 667, C: 722, D: 722, E: 667, F: 611, G: 778, H: 722, I: 278,
	J: 500, K: 667, L: 556, M: 833, N: 722, O: 778, P: 667, Q: 778, R: 722,
	S: 667, T: 611, U: 722, V: 667, W: 944, X: 667, Y: 667, Z: 611,
	'[': 278, '\\': 278, ']': 278, '^': 469, '_': 556, '`': 333,
	a: 556, b: 556, c: 500, d: 556, e: 556, f: 278, g: 556, h: 556, i: 222,
	j: 222, k: 500, l: 222, m: 833, n: 556, o: 556, p: 556, q: 556, r: 333,
	s: 500, t: 278, u: 556, v: 500, w: 722, x: 500, y: 500, z: 500,
	'{': 334, '|': 260, '}': 334, '~': 584
};

function glyphWidth(ch: string): number {
	return GLYPH_WIDTHS[ch] ?? DEFAULT_GLYPH_WIDTH;
}

/** Where every character of a text item sits inside the item's box. */
export interface GlyphRuler {
	/** The item's text split into characters (code points, not UTF-16 units). */
	chars: string[];
	/**
	 * `cumulative[i]` is the horizontal offset, in PDF points from the item's
	 * left edge, of the left edge of `chars[i]`. `cumulative[chars.length]`
	 * equals the item's full width.
	 */
	cumulative: number[];
	/**
	 * `utf16[i]` is the index in the original string where `chars[i]` starts;
	 * `utf16[chars.length]` is the string length. Callers holding UTF-16
	 * offsets (a page-string search hit, say) use this to find the matching
	 * character index without assuming one code unit per character.
	 */
	utf16: number[];
}

/**
 * Measure `text` across `width` points using AFM advance widths.
 *
 * Returns `null` when there is nothing to measure — empty text, a
 * non-positive width, or a total advance of zero — so callers can fall back
 * to whatever "no narrowing possible" means for them.
 */
export function measureText(text: string, width: number): GlyphRuler | null {
	if (width <= 0 || text.length === 0) return null;

	const chars = Array.from(text);
	let totalAfm = 0;
	for (const ch of chars) totalAfm += glyphWidth(ch);
	if (totalAfm <= 0) return null;
	const scale = width / totalAfm;

	const cumulative = new Array<number>(chars.length + 1);
	const utf16 = new Array<number>(chars.length + 1);
	cumulative[0] = 0;
	utf16[0] = 0;
	let acc = 0;
	let unit = 0;
	for (let i = 0; i < chars.length; i++) {
		acc += glyphWidth(chars[i]) * scale;
		unit += chars[i].length;
		cumulative[i + 1] = acc;
		utf16[i + 1] = unit;
	}
	return { chars, cumulative, utf16 };
}

/**
 * Translate a UTF-16 offset into the character index it falls on: the first
 * character that starts at or after `offset`. An offset landing inside a
 * surrogate pair rounds forward to the next character, and an offset past
 * the end returns `chars.length`.
 */
export function charIndexAtOffset(ruler: GlyphRuler, offset: number): number {
	for (let i = 0; i <= ruler.chars.length; i++) {
		if (ruler.utf16[i] >= offset) return i;
	}
	return ruler.chars.length;
}
