/**
 * The one join rule that turns pdf.js / tesseract text items into page text.
 *
 * KEEP IN SYNC WITH `backend/eval/pdfjs_extract.mjs` and
 * `backend/eval/pdfio.py`. The evaluation harness only measures something
 * real if the text it feeds the pipeline is byte-for-byte what the browser
 * would have sent, and `test_pdfjs_extract.py` pins the Node and Python twins
 * against each other.
 *
 * Three separators, and each one exists for a reason:
 *
 * - **nothing** between items that touch on the same line. pdf.js splits long
 *   tokens (URLs, IBANs, phone numbers) across several text items; a blind
 *   `' '` join inserts a phantom space that breaks both regexes and NER.
 * - **a space** between items that share a line but stand apart.
 * - **a newline** when the next item starts a new line. The backend treats a
 *   line as a unit of meaning: the structure engine cuts e-mail headers,
 *   salutations and signature blocks on line boundaries, and a dozen rules in
 *   `ner_engine` use `[^\n]` or `rfind("\n")` to stay on "the same line". Join
 *   lines with a space and every one of those windows silently becomes "the
 *   last 40 to 60 characters", which is how a letterhead `Postbus` ended up
 *   vouching for a resident's postcode seventeen lines further down.
 *
 * Every separator is exactly one character, so a caller can rebuild
 * `full_text` after reordering items without any offset arithmetic, and
 * `start_char`/`end_char` mean the same thing whichever separator was chosen.
 */

/** Cross-line jitter, in points, that still counts as the same line. */
export const SAME_LINE_TOLERANCE = 2;
/** Gap, in points, under which two items on a line are one word. */
export const ADJACENT_X_TOLERANCE = 1.5;

/**
 * Minimal box shape the join needs. These must be *layout* (unrotated) boxes:
 * on a /Rotate 90 page a line runs top-to-bottom in viewer space and every
 * same-line test below would fail.
 */
export interface JoinBox {
	x0: number;
	y0: number;
	x1: number;
	y1: number;
}

/** The separator that belongs between two consecutive text items. */
export function separatorBetween(prev: JoinBox, box: JoinBox): '' | ' ' | '\n' {
	if (Math.abs(box.y0 - prev.y0) >= SAME_LINE_TOLERANCE) return '\n';
	return box.x0 - prev.x1 < ADJACENT_X_TOLERANCE ? '' : ' ';
}

/** Build a page's full text from its items, in the order they are given. */
export function joinTextItems(texts: string[], boxes: JoinBox[]): string {
	return texts.reduce(
		(acc, text, idx) =>
			idx === 0 ? text : acc + separatorBetween(boxes[idx - 1], boxes[idx]) + text,
		''
	);
}
