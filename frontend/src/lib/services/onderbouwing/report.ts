/**
 * Onderbouwingsrapport PDF builder (#64).
 *
 * Renders a defensible Dutch-language attachment for the Woo-besluit,
 * fully client-side via pdf-lib. Nothing in this file talks to the
 * server; nothing in this file reads `entity_text`. The recipient
 * already has the redacted PDF — the report explains why each black
 * bar exists.
 *
 * Lazy-loaded by the review-export store so the ~250KB pdf-lib
 * payload never hits the landing page bundle.
 */

import {
	PDFBool,
	PDFDocument,
	PDFName,
	StandardFonts,
	rgb,
	type PDFFont,
	type PDFPage,
	type RGB
} from 'pdf-lib';
import { WOO_ARTICLES } from '$lib/utils/woo-articles';
import {
	buildReportRows,
	buildReportSummary,
	articlesForToelichting,
	type ReportRow
} from './summary';
import { StructureBuilder, mountOutline, type OutlineEntry } from './structure';
import type { OnderbouwingInput } from './types';

// ---------------------------------------------------------------------------
// Layout constants (A4 portrait, in PDF points)
// ---------------------------------------------------------------------------

const PAGE_WIDTH = 595.28;
const PAGE_HEIGHT = 841.89;
const MARGIN_X = 56;
const MARGIN_TOP = 64;
const MARGIN_BOTTOM = 64;
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN_X * 2;
const FOOTER_OFFSET = 32;

// Colour palette is WCAG 1.4.3 AA compliant against white (≥ 4.5:1) for
// every shade actually used as text. INK ≈ 14:1, INK_SOFT ≈ 7:1, INK_MUTE
// ≈ 5.8:1 — INK_MUTE is the small-print threshold (footer 8pt, summary
// placeholders); going any lighter would fall below AA for body text.
const COLOR_INK: RGB = rgb(0.12, 0.14, 0.17);
const COLOR_INK_SOFT: RGB = rgb(0.32, 0.36, 0.42);
const COLOR_INK_MUTE: RGB = rgb(0.36, 0.4, 0.46);
const COLOR_DIVIDER: RGB = rgb(0.85, 0.87, 0.9);
const COLOR_TABLE_HEADER_BG: RGB = rgb(0.96, 0.97, 0.98);
const COLOR_TABLE_ROW_ALT: RGB = rgb(0.985, 0.99, 0.995);
const COLOR_BOX_BG: RGB = rgb(0.97, 0.98, 0.99);

// Per-redactie tabel column layout. Widths sum to CONTENT_WIDTH
// (~483 pt). Columns are tuned for an A4 page; long motivation text
// wraps within the last column.
const TABLE_COLUMNS = [
	{ key: 'number', label: '#', width: 26, align: 'right' as const },
	{ key: 'page', label: 'Pagina', width: 46, align: 'right' as const },
	{ key: 'entity', label: 'Type', width: 78, align: 'left' as const },
	{ key: 'tier', label: 'Trap', width: 32, align: 'right' as const },
	{ key: 'article', label: 'Woo-artikel', width: 64, align: 'left' as const },
	{ key: 'source', label: 'Bron', width: 56, align: 'left' as const },
	{ key: 'motivation', label: 'Motivering', width: -1, align: 'left' as const }
];

// ---------------------------------------------------------------------------
// Layout cursor — a tiny abstraction over "draw text then advance Y"
// ---------------------------------------------------------------------------

interface Fonts {
	regular: PDFFont;
	bold: PDFFont;
}

interface Layout {
	doc: PDFDocument;
	pages: PDFPage[];
	page: PDFPage;
	pageIndex: number;
	cursorY: number;
	fonts: Fonts;
	footerText: string;
	structure: StructureBuilder;
	/**
	 * Captured page indices for top-level outline entries
	 * (Voorblad, Samenvatting, Tabel, Bijlage A). Filled as each
	 * section starts so /Outlines points at the right page.
	 */
	outline: OutlineEntry[];
}

function newPage(layout: Layout): void {
	const page = layout.doc.addPage([PAGE_WIDTH, PAGE_HEIGHT]);
	layout.pages.push(page);
	layout.page = page;
	layout.pageIndex = layout.pages.length - 1;
	layout.cursorY = PAGE_HEIGHT - MARGIN_TOP;
}

function ensureSpace(layout: Layout, needed: number): void {
	if (layout.cursorY - needed < MARGIN_BOTTOM) {
		newPage(layout);
	}
}

function moveDown(layout: Layout, dy: number): void {
	layout.cursorY -= dy;
}

// ---------------------------------------------------------------------------
// Text helpers
// ---------------------------------------------------------------------------

/**
 * pdf-lib's standard-font WinAnsi encoding can't render every code
 * point a Dutch reviewer might paste (curly quotes from Word, em
 * dashes, non-breaking spaces). We sanitize aggressively to ASCII-
 * compatible substitutes so generation never throws — losing a
 * dash to a hyphen is far better than failing the export.
 */
function sanitizeForWinAnsi(input: string): string {
	return input
		.replace(/[\u2018\u2019\u201A\u201B]/g, "'")
		.replace(/[\u201C\u201D\u201E\u201F]/g, '"')
		.replace(/[\u2013\u2014\u2212]/g, '-')
		.replace(/\u2026/g, '...')
		.replace(/\u00A0/g, ' ')
		.replace(/\u2009/g, ' ')
		.replace(/\u200B/g, '')
		.replace(/[^\x09\x0A\x0D\x20-\x7E\u00A1-\u00FF\u20AC]/g, '?');
}

function widthOf(font: PDFFont, text: string, size: number): number {
	return font.widthOfTextAtSize(sanitizeForWinAnsi(text), size);
}

/**
 * Raw text drawing primitive. Does NOT wrap the operation in a
 * marked-content sequence — callers must use either {@link drawTaggedText}
 * (logical content) or {@link drawArtifact} (decorative content). PDF/UA
 * (Matterhorn 14-001) requires every content-stream op to be one or
 * the other.
 *
 * Kept separate from the wrappers so the actual `page.drawText` call
 * lives in a single, easy-to-audit place.
 */
function drawText(
	layout: Layout,
	text: string,
	options: {
		x: number;
		y: number;
		font?: PDFFont;
		size?: number;
		color?: RGB;
	}
): void {
	const font = options.font ?? layout.fonts.regular;
	const size = options.size ?? 10;
	const color = options.color ?? COLOR_INK;
	layout.page.drawText(sanitizeForWinAnsi(text), {
		x: options.x,
		y: options.y,
		font,
		size,
		color
	});
}

/**
 * Draw text inside a marked-content sequence linked to the
 * currently-open structure element. Use for headings, paragraphs,
 * table cells — anything a screen reader should announce.
 */
function drawTaggedText(
	layout: Layout,
	text: string,
	options: {
		x: number;
		y: number;
		font?: PDFFont;
		size?: number;
		color?: RGB;
	}
): void {
	layout.structure.tag(layout.page, layout.pageIndex, () => {
		drawText(layout, text, options);
	});
}

/**
 * Wrap one or more drawing operations as a PDF artifact (decorative,
 * ignored by AT). Used for footer page numbers, divider lines, table
 * row backgrounds — anything that exists for sighted layout reasons
 * only.
 */
function drawArtifact(layout: Layout, draw: () => void): void {
	layout.structure.artifact(layout.page, draw);
}

/**
 * Word-wrap `text` into lines that each fit within `maxWidth`.
 * Greedy, no hyphenation — fine for the report's body copy and
 * table cells.
 */
function wrapText(
	font: PDFFont,
	text: string,
	maxWidth: number,
	size: number
): string[] {
	const safe = sanitizeForWinAnsi(text);
	const words = safe.split(/\s+/).filter(Boolean);
	if (words.length === 0) return [''];
	const lines: string[] = [];
	let current = '';
	for (const word of words) {
		const candidate = current ? `${current} ${word}` : word;
		if (font.widthOfTextAtSize(candidate, size) <= maxWidth) {
			current = candidate;
		} else if (current) {
			lines.push(current);
			current = word;
		} else {
			lines.push(word);
			current = '';
		}
	}
	if (current) lines.push(current);
	return lines;
}

/**
 * Word-wrap and draw each resulting line as its own marked-content
 * sequence. Marked-content sequences cannot span pages, so a paragraph
 * that overflows is automatically split across pages with one MCID
 * per visible line — the parent `P` (or `TD`, etc.) structure element
 * accumulates MCID leaves on each page it touches.
 */
function drawWrapped(
	layout: Layout,
	text: string,
	options: {
		x: number;
		size?: number;
		color?: RGB;
		font?: PDFFont;
		maxWidth: number;
		lineHeight?: number;
	}
): void {
	const size = options.size ?? 10;
	const font = options.font ?? layout.fonts.regular;
	const lineHeight = options.lineHeight ?? size * 1.4;
	const lines = wrapText(font, text, options.maxWidth, size);
	for (const line of lines) {
		ensureSpace(layout, lineHeight);
		drawTaggedText(layout, line, {
			x: options.x,
			y: layout.cursorY,
			size,
			font,
			color: options.color
		});
		moveDown(layout, lineHeight);
	}
}

function drawDivider(layout: Layout): void {
	ensureSpace(layout, 8);
	moveDown(layout, 4);
	drawArtifact(layout, () => {
		layout.page.drawLine({
			start: { x: MARGIN_X, y: layout.cursorY },
			end: { x: MARGIN_X + CONTENT_WIDTH, y: layout.cursorY },
			thickness: 0.5,
			color: COLOR_DIVIDER
		});
	});
	moveDown(layout, 8);
}

// ---------------------------------------------------------------------------
// Section renderers
// ---------------------------------------------------------------------------

function formatTimestamp(date: Date): { utc: string; ams: string } {
	const utc = date.toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, ' UTC');
	const ams = new Intl.DateTimeFormat('nl-NL', {
		year: 'numeric',
		month: '2-digit',
		day: '2-digit',
		hour: '2-digit',
		minute: '2-digit',
		timeZone: 'Europe/Amsterdam'
	}).format(date);
	return { utc, ams: `${ams} (Europe/Amsterdam)` };
}

function drawCoverSection(
	layout: Layout,
	input: OnderbouwingInput,
	rowCount: number,
	pageCount: number,
	stamps: { utc: string; ams: string }
): void {
	layout.structure.beginElement('H1');
	drawTaggedText(layout, 'Onderbouwing van redacties', {
		x: MARGIN_X,
		y: layout.cursorY,
		size: 22,
		font: layout.fonts.bold,
		color: COLOR_INK
	});
	layout.structure.endElement();
	moveDown(layout, 28);

	layout.structure.beginElement('P');
	drawTaggedText(
		layout,
		'Bijlage bij het Woo-besluit. Per gelakte passage de juridische grond en motivering.',
		{
			x: MARGIN_X,
			y: layout.cursorY,
			size: 11,
			color: COLOR_INK_SOFT
		}
	);
	layout.structure.endElement();
	moveDown(layout, 22);

	const rows: Array<[string, string]> = [
		['Bestandsnaam', input.filename],
		['Aantal pagina\u2019s', String(pageCount)],
		['Aantal redacties', String(rowCount)],
		['Gegenereerd op', stamps.ams],
		['UTC-tijdstempel', stamps.utc]
	];

	if (input.reviewer.zaaknummer.trim()) {
		rows.push(['Zaaknummer', input.reviewer.zaaknummer.trim()]);
	}
	if (input.reviewer.reviewerName.trim()) {
		rows.push(['Beoordelaar', input.reviewer.reviewerName.trim()]);
	}

	drawKeyValueTable(layout, rows, { keyWidth: 130, lineGap: 6 });
}

/**
 * Draw a label/value list as a structured `Table` so screen readers
 * announce each row as "label: value" instead of two disconnected
 * sentences. The visual layout is unchanged — this only affects the
 * structure tree.
 */
function drawKeyValueTable(
	layout: Layout,
	rows: Array<[string, string]>,
	options: { keyWidth: number; lineGap: number }
): void {
	const valueX = MARGIN_X + options.keyWidth + 8;
	const valueWidth = CONTENT_WIDTH - options.keyWidth - 8;
	layout.structure.beginElement('Table');
	for (const [key, value] of rows) {
		const valueLines = wrapText(layout.fonts.regular, value, valueWidth, 10);
		const blockHeight = Math.max(1, valueLines.length) * 14 + options.lineGap;
		ensureSpace(layout, blockHeight);
		layout.structure.beginElement('TR');

		layout.structure.beginElement('TH');
		drawTaggedText(layout, key, {
			x: MARGIN_X,
			y: layout.cursorY,
			size: 10,
			font: layout.fonts.bold,
			color: COLOR_INK
		});
		layout.structure.endElement();

		layout.structure.beginElement('TD');
		valueLines.forEach((line, i) => {
			drawTaggedText(layout, line, {
				x: valueX,
				y: layout.cursorY - i * 14,
				size: 10,
				color: COLOR_INK_SOFT
			});
		});
		layout.structure.endElement();

		layout.structure.endElement();
		moveDown(layout, valueLines.length * 14 + options.lineGap);
	}
	layout.structure.endElement();
}

function drawProvenanceSection(layout: Layout, input: OnderbouwingInput): void {
	drawSectionHeading(layout, 'Provenance');
	layout.structure.beginElement('P');
	drawWrapped(
		layout,
		'Onderstaande SHA-256 hashes laten zich onafhankelijk verifi\u00ebren tegen de PDF-bestanden in uw dossier. Zo kunt u maanden later vaststellen dat dit rapport hoort bij precies die documenten.',
		{ x: MARGIN_X, maxWidth: CONTENT_WIDTH, color: COLOR_INK_SOFT }
	);
	layout.structure.endElement();
	moveDown(layout, 6);

	layout.structure.beginElement('Table');
	drawHashRow(layout, 'Bron-PDF (origineel)', input.hashes.originalSha256);
	if (input.hashes.redactedSha256) {
		drawHashRow(layout, 'Gelakte PDF', input.hashes.redactedSha256);
	} else {
		drawHashRow(
			layout,
			'Gelakte PDF',
			'Redactie nog niet ge\u00ebxporteerd \u2014 hash niet beschikbaar.'
		);
	}
	drawHashRow(layout, 'WOO Buddy versie', `WOO Buddy (${input.buildCommit})`);
	layout.structure.endElement();
}

function drawHashRow(layout: Layout, label: string, value: string): void {
	const labelWidth = 130;
	const valueWidth = CONTENT_WIDTH - labelWidth - 8;
	const valueX = MARGIN_X + labelWidth + 8;
	const lines = wrapText(layout.fonts.regular, value, valueWidth, 9);
	const blockHeight = lines.length * 12 + 4;
	ensureSpace(layout, blockHeight);
	layout.structure.beginElement('TR');

	layout.structure.beginElement('TH');
	drawTaggedText(layout, label, {
		x: MARGIN_X,
		y: layout.cursorY,
		size: 10,
		font: layout.fonts.bold,
		color: COLOR_INK
	});
	layout.structure.endElement();

	layout.structure.beginElement('TD');
	lines.forEach((line, i) => {
		drawTaggedText(layout, line, {
			x: valueX,
			y: layout.cursorY - i * 12,
			size: 9,
			color: COLOR_INK_SOFT,
			font: layout.fonts.regular
		});
	});
	layout.structure.endElement();

	layout.structure.endElement();
	moveDown(layout, blockHeight);
}

function drawNotesSection(layout: Layout, opmerkingen: string): void {
	const text = opmerkingen.trim();
	if (!text) return;
	drawSectionHeading(layout, 'Opmerkingen');
	layout.structure.beginElement('P');
	drawWrapped(layout, text, {
		x: MARGIN_X,
		maxWidth: CONTENT_WIDTH,
		color: COLOR_INK_SOFT
	});
	layout.structure.endElement();
}

function drawSectionHeading(layout: Layout, title: string): void {
	moveDown(layout, 4);
	ensureSpace(layout, 28);
	layout.structure.beginElement('H2');
	drawTaggedText(layout, title, {
		x: MARGIN_X,
		y: layout.cursorY,
		size: 13,
		font: layout.fonts.bold,
		color: COLOR_INK
	});
	layout.structure.endElement();
	moveDown(layout, 8);
	drawArtifact(layout, () => {
		layout.page.drawLine({
			start: { x: MARGIN_X, y: layout.cursorY + 2 },
			end: { x: MARGIN_X + CONTENT_WIDTH, y: layout.cursorY + 2 },
			thickness: 0.5,
			color: COLOR_DIVIDER
		});
	});
	moveDown(layout, 10);
}

function drawSummarySection(
	layout: Layout,
	summary: ReturnType<typeof buildReportSummary>
): void {
	drawSectionHeading(layout, 'Samenvatting');
	const tierLine = `Trap 1: ${summary.byTier['1']}   |   Trap 2: ${summary.byTier['2']}   |   Trap 3: ${summary.byTier['3']}`;
	const sourceLine = `Auto: ${summary.bySource.auto}   |   Handmatig: ${summary.bySource.handmatig}`;
	layout.structure.beginElement('P');
	drawWrapped(layout, `Totaal aantal redacties: ${summary.total}`, {
		x: MARGIN_X,
		maxWidth: CONTENT_WIDTH,
		font: layout.fonts.bold
	});
	layout.structure.endElement();
	layout.structure.beginElement('P');
	drawWrapped(layout, tierLine, { x: MARGIN_X, maxWidth: CONTENT_WIDTH, color: COLOR_INK_SOFT });
	layout.structure.endElement();
	layout.structure.beginElement('P');
	drawWrapped(layout, sourceLine, { x: MARGIN_X, maxWidth: CONTENT_WIDTH, color: COLOR_INK_SOFT });
	layout.structure.endElement();

	moveDown(layout, 4);
	drawSubHeading(layout, 'Per Woo-artikel');
	if (summary.byArticle.length === 0) {
		layout.structure.beginElement('P');
		drawWrapped(layout, '(geen artikel-gekoppelde redacties)', {
			x: MARGIN_X,
			maxWidth: CONTENT_WIDTH,
			color: COLOR_INK_MUTE
		});
		layout.structure.endElement();
	} else {
		layout.structure.beginElement('Table');
		for (const item of summary.byArticle) {
			const article = WOO_ARTICLES[item.code];
			const ground = article ? article.ground : '';
			drawTwoColumnRow(
				layout,
				`Art. ${item.code}${ground ? ` \u2014 ${ground}` : ''}`,
				String(item.count)
			);
		}
		layout.structure.endElement();
	}

	moveDown(layout, 4);
	drawSubHeading(layout, 'Per type');
	if (summary.byEntityType.length === 0) {
		layout.structure.beginElement('P');
		drawWrapped(layout, '(geen redacties)', {
			x: MARGIN_X,
			maxWidth: CONTENT_WIDTH,
			color: COLOR_INK_MUTE
		});
		layout.structure.endElement();
	} else {
		layout.structure.beginElement('Table');
		for (const item of summary.byEntityType) {
			drawTwoColumnRow(layout, item.label, String(item.count));
		}
		layout.structure.endElement();
	}
}

function drawSubHeading(layout: Layout, text: string): void {
	moveDown(layout, 4);
	ensureSpace(layout, 18);
	layout.structure.beginElement('H3');
	drawTaggedText(layout, text, {
		x: MARGIN_X,
		y: layout.cursorY,
		size: 11,
		font: layout.fonts.bold,
		color: COLOR_INK
	});
	layout.structure.endElement();
	moveDown(layout, 14);
}

/**
 * One row of the summary's labeled-count list. Caller wraps multiple
 * rows in a parent `Table` element. Each row produces one `TR` with
 * a `TH` (label) and a `TD` (count).
 */
function drawTwoColumnRow(layout: Layout, left: string, right: string): void {
	const rightWidth = 60;
	const leftWidth = CONTENT_WIDTH - rightWidth - 8;
	const lines = wrapText(layout.fonts.regular, left, leftWidth, 10);
	const blockHeight = lines.length * 13 + 2;
	ensureSpace(layout, blockHeight);
	layout.structure.beginElement('TR');

	layout.structure.beginElement('TH');
	lines.forEach((line, i) => {
		drawTaggedText(layout, line, {
			x: MARGIN_X,
			y: layout.cursorY - i * 13,
			size: 10,
			color: COLOR_INK_SOFT
		});
	});
	layout.structure.endElement();

	layout.structure.beginElement('TD');
	const rightX = MARGIN_X + CONTENT_WIDTH - widthOf(layout.fonts.bold, right, 10);
	drawTaggedText(layout, right, {
		x: rightX,
		y: layout.cursorY,
		size: 10,
		font: layout.fonts.bold,
		color: COLOR_INK
	});
	layout.structure.endElement();

	layout.structure.endElement();
	moveDown(layout, blockHeight);
}

// ---------------------------------------------------------------------------
// Per-redactie tabel
// ---------------------------------------------------------------------------

function computeColumnWidths(): number[] {
	const fixed = TABLE_COLUMNS.filter((c) => c.width > 0).reduce(
		(sum, c) => sum + c.width,
		0
	);
	const flex = CONTENT_WIDTH - fixed;
	return TABLE_COLUMNS.map((c) => (c.width > 0 ? c.width : flex));
}

/**
 * Draw the per-redactie table header. The column-header background
 * and underline are decorative (artifact); each header label is
 * tagged as a TH so screen readers can announce "Pagina, header" when
 * the cursor lands on a data cell in that column.
 *
 * Caller is responsible for the surrounding `TR` open/close.
 */
function drawTableHeader(layout: Layout, widths: number[]): void {
	const headerHeight = 22;
	ensureSpace(layout, headerHeight + 6);
	drawArtifact(layout, () => {
		layout.page.drawRectangle({
			x: MARGIN_X,
			y: layout.cursorY - headerHeight + 6,
			width: CONTENT_WIDTH,
			height: headerHeight,
			color: COLOR_TABLE_HEADER_BG
		});
	});
	let x = MARGIN_X + 6;
	for (let i = 0; i < TABLE_COLUMNS.length; i++) {
		const col = TABLE_COLUMNS[i];
		const w = widths[i];
		const text = col.label;
		const textWidth = widthOf(layout.fonts.bold, text, 9);
		const textX =
			col.align === 'right' ? x + w - textWidth - 12 : x;
		layout.structure.beginElement('TH');
		drawTaggedText(layout, text, {
			x: textX,
			y: layout.cursorY - 8,
			size: 9,
			font: layout.fonts.bold,
			color: COLOR_INK
		});
		layout.structure.endElement();
		x += w;
	}
	drawArtifact(layout, () => {
		layout.page.drawLine({
			start: { x: MARGIN_X, y: layout.cursorY - headerHeight + 6 },
			end: { x: MARGIN_X + CONTENT_WIDTH, y: layout.cursorY - headerHeight + 6 },
			thickness: 0.5,
			color: COLOR_DIVIDER
		});
	});
	moveDown(layout, headerHeight);
}

function drawTableSection(layout: Layout, rows: ReportRow[]): void {
	drawSectionHeading(layout, 'Per-redactie tabel');
	if (rows.length === 0) {
		layout.structure.beginElement('P');
		drawWrapped(
			layout,
			'Geen geaccepteerde redacties \u2014 dit rapport vat een lege onderbouwing samen.',
			{ x: MARGIN_X, maxWidth: CONTENT_WIDTH, color: COLOR_INK_MUTE }
		);
		layout.structure.endElement();
		return;
	}

	const widths = computeColumnWidths();
	// The Table wraps both the header row and the data rows, so the
	// table-spanning structure is preserved across page breaks (each
	// TR becomes a child of the same Table even when split across
	// pages, with MCID leaves on whichever pages they land on).
	layout.structure.beginElement('Table');
	layout.structure.beginElement('TR');
	drawTableHeader(layout, widths);
	layout.structure.endElement();

	const cellPadX = 6;
	const cellPadY = 4;
	const fontSize = 9;
	const lineHeight = 12;

	rows.forEach((row, idx) => {
		const motivationLines = wrapText(
			layout.fonts.regular,
			row.motivation,
			widths[6] - cellPadX * 2,
			fontSize
		);
		const cellHeight = Math.max(
			lineHeight + cellPadY * 2,
			motivationLines.length * lineHeight + cellPadY * 2
		);
		if (layout.cursorY - cellHeight < MARGIN_BOTTOM) {
			newPage(layout);
			layout.structure.beginElement('TR');
			drawTableHeader(layout, widths);
			layout.structure.endElement();
		}

		if (idx % 2 === 1) {
			drawArtifact(layout, () => {
				layout.page.drawRectangle({
					x: MARGIN_X,
					y: layout.cursorY - cellHeight + cellPadY,
					width: CONTENT_WIDTH,
					height: cellHeight,
					color: COLOR_TABLE_ROW_ALT
				});
			});
		}

		const cellTopY = layout.cursorY - cellPadY - 8;
		let x = MARGIN_X + cellPadX;

		const cells: Array<{ text: string; align: 'left' | 'right' }> = [
			{ text: String(row.number), align: 'right' },
			{ text: String(row.page), align: 'right' },
			{ text: row.entityLabel, align: 'left' },
			{ text: row.tier, align: 'right' },
			{ text: row.articleCode ?? '\u2014', align: 'left' },
			{ text: row.source === 'auto' ? 'Auto' : 'Handmatig', align: 'left' }
		];

		layout.structure.beginElement('TR');

		for (let i = 0; i < cells.length; i++) {
			const w = widths[i];
			const cell = cells[i];
			const textWidth = widthOf(layout.fonts.regular, cell.text, fontSize);
			const textX =
				cell.align === 'right' ? x + w - textWidth - cellPadX * 2 : x;
			layout.structure.beginElement('TD');
			drawTaggedText(layout, cell.text, {
				x: textX,
				y: cellTopY,
				size: fontSize,
				color: COLOR_INK
			});
			layout.structure.endElement();
			x += w;
		}

		layout.structure.beginElement('TD');
		motivationLines.forEach((line, i) => {
			drawTaggedText(layout, line, {
				x: x,
				y: cellTopY - i * lineHeight,
				size: fontSize,
				color: COLOR_INK_SOFT
			});
		});
		layout.structure.endElement();

		layout.structure.endElement();

		drawArtifact(layout, () => {
			layout.page.drawLine({
				start: {
					x: MARGIN_X,
					y: layout.cursorY - cellHeight + cellPadY
				},
				end: {
					x: MARGIN_X + CONTENT_WIDTH,
					y: layout.cursorY - cellHeight + cellPadY
				},
				thickness: 0.25,
				color: COLOR_DIVIDER
			});
		});

		moveDown(layout, cellHeight);
	});
	layout.structure.endElement();
}

// ---------------------------------------------------------------------------
// Bijlage A — toelichting per Woo-grond
// ---------------------------------------------------------------------------

function drawToelichtingSection(layout: Layout, rows: ReportRow[]): void {
	const articleCodes = articlesForToelichting(rows);
	drawSectionHeading(layout, 'Bijlage A \u2014 Toelichting per Woo-grond');
	if (articleCodes.length === 0) {
		layout.structure.beginElement('P');
		drawWrapped(
			layout,
			'Er zijn geen Woo-artikelen aan deze redacties gekoppeld; deze bijlage is daarom leeg.',
			{ x: MARGIN_X, maxWidth: CONTENT_WIDTH, color: COLOR_INK_MUTE }
		);
		layout.structure.endElement();
		return;
	}
	for (const code of articleCodes) {
		const article = WOO_ARTICLES[code];
		if (!article) continue;
		ensureSpace(layout, 36);
		layout.structure.beginElement('H3');
		drawTaggedText(layout, `Art. ${article.code} \u2014 ${article.ground}`, {
			x: MARGIN_X,
			y: layout.cursorY,
			size: 11,
			font: layout.fonts.bold,
			color: COLOR_INK
		});
		layout.structure.endElement();
		moveDown(layout, 14);
		layout.structure.beginElement('P');
		drawWrapped(layout, article.description, {
			x: MARGIN_X,
			maxWidth: CONTENT_WIDTH,
			color: COLOR_INK_SOFT,
			size: 10
		});
		layout.structure.endElement();
		moveDown(layout, 6);
	}
}

// ---------------------------------------------------------------------------
// Footer pass — drawn at the very end so we know `pages.length`
// ---------------------------------------------------------------------------

/**
 * Draw the per-page footer. The wordmark text and page number are
 * intentionally artifact (not tagged) — running headers/footers and
 * page-number stamps are the canonical PDF/UA artifact case (ISO
 * 32000-1 §14.8.2.2). Including them in the structure tree would
 * have a screen reader say "Page 1 of 7. Page 2 of 7. Page 3 of 7..."
 * for every page break, which is exactly the user-hostile behaviour
 * artifact tagging exists to prevent.
 */
function drawFooters(layout: Layout): void {
	const total = layout.pages.length;
	for (let i = 0; i < total; i++) {
		const page = layout.pages[i];
		const left = layout.footerText;
		const right = `Pagina ${i + 1} / ${total}`;
		layout.structure.artifact(page, () => {
			page.drawLine({
				start: { x: MARGIN_X, y: FOOTER_OFFSET + 16 },
				end: { x: PAGE_WIDTH - MARGIN_X, y: FOOTER_OFFSET + 16 },
				thickness: 0.25,
				color: COLOR_DIVIDER
			});
			page.drawText(sanitizeForWinAnsi(left), {
				x: MARGIN_X,
				y: FOOTER_OFFSET,
				size: 8,
				font: layout.fonts.regular,
				color: COLOR_INK_MUTE
			});
			const rightWidth = layout.fonts.regular.widthOfTextAtSize(right, 8);
			page.drawText(right, {
				x: PAGE_WIDTH - MARGIN_X - rightWidth,
				y: FOOTER_OFFSET,
				size: 8,
				font: layout.fonts.regular,
				color: COLOR_INK_MUTE
			});
		});
	}
}

// ---------------------------------------------------------------------------
// Public entry point
// ---------------------------------------------------------------------------

/**
 * Build the onderbouwingsrapport as a `Uint8Array` PDF. The caller is
 * responsible for wrapping it in a Blob and triggering the download.
 *
 * Throws when pdf-lib fails (very unusual — typically a font issue
 * we sanitize against above). Errors propagate so the review-export
 * store can show the existing retry banner.
 */
export async function buildOnderbouwingPdf(input: OnderbouwingInput): Promise<Uint8Array> {
	const doc = await PDFDocument.create();
	const generatedAt = input.generatedAt ?? new Date();
	const trimmedReviewer = input.reviewer.reviewerName.trim();
	const trimmedZaak = input.reviewer.zaaknummer.trim();

	// Document metadata. setTitle({ showInWindowTitleBar }) flips
	// /ViewerPreferences /DisplayDocTitle to true so screen readers and PDF
	// viewers announce the human-readable title we set instead of falling
	// back to the filename (WCAG 2.4.2).
	doc.setTitle(`Onderbouwing van redacties \u2014 ${input.filename}`, {
		showInWindowTitleBar: true
	});
	doc.setAuthor(trimmedReviewer || 'WOO Buddy');
	doc.setSubject(
		trimmedZaak
			? `Onderbouwing bij Woo-besluit, zaaknummer ${trimmedZaak}`
			: 'Onderbouwing bij Woo-besluit'
	);
	doc.setKeywords(
		[
			'WOO Buddy',
			'Woo-besluit',
			'onderbouwing',
			'redacties',
			...(trimmedZaak ? [trimmedZaak] : [])
		].filter(Boolean)
	);
	doc.setCreator('WOO Buddy');
	doc.setProducer('WOO Buddy (#64 onderbouwingsrapport)');
	doc.setLanguage('nl-NL');
	doc.setCreationDate(generatedAt);
	doc.setModificationDate(generatedAt);

	// /MarkInfo /Marked = true declares the document carries logical
	// structure tags. We pair it with a real /StructTreeRoot below
	// (built by StructureBuilder.finalize) so the declaration is
	// honest — Acrobat / NVDA / VoiceOver will use the structure to
	// announce headings, table cells with headers, and section
	// boundaries.
	doc.catalog.set(
		PDFName.of('MarkInfo'),
		doc.context.obj({ Marked: PDFBool.True })
	);
	const fonts: Fonts = {
		regular: await doc.embedFont(StandardFonts.Helvetica),
		bold: await doc.embedFont(StandardFonts.HelveticaBold)
	};

	const layout: Layout = {
		doc,
		pages: [],
		page: undefined as unknown as PDFPage,
		pageIndex: -1,
		cursorY: 0,
		fonts,
		footerText:
			'Gegenereerd met WOO Buddy \u2014 uw PDF heeft uw browser nooit verlaten',
		structure: new StructureBuilder(),
		outline: []
	};
	newPage(layout);

	const rows = buildReportRows(input.detections);
	const summary = buildReportSummary(input.detections);
	const stamps = formatTimestamp(generatedAt);
	const documentPageCount = input.document?.page_count ?? 0;

	// Section 1 — Voorblad (cover + provenance + opmerkingen all share
	// one logical Sect because they're conceptually the document
	// front-matter).
	layout.outline.push({ title: 'Voorblad', pageIndex: layout.pageIndex });
	layout.structure.beginElement('Sect');
	drawCoverSection(layout, input, rows.length, documentPageCount, stamps);
	drawDivider(layout);
	drawProvenanceSection(layout, input);
	drawDivider(layout);
	drawNotesSection(layout, input.reviewer.opmerkingen);
	layout.structure.endElement();

	// Section 2 — Samenvatting
	newPage(layout);
	layout.outline.push({ title: 'Samenvatting', pageIndex: layout.pageIndex });
	layout.structure.beginElement('Sect');
	drawSummarySection(layout, summary);
	layout.structure.endElement();

	// Section 3 — Per-redactie tabel
	newPage(layout);
	layout.outline.push({
		title: 'Tabel met redacties',
		pageIndex: layout.pageIndex
	});
	layout.structure.beginElement('Sect');
	drawTableSection(layout, rows);
	layout.structure.endElement();

	// Section 4 — Bijlage A. Note we don't force a new page here —
	// it follows directly after the table per the original layout.
	// We capture whichever page it lands on for the outline.
	layout.outline.push({
		title: 'Bijlage A \u2014 Toelichting per Woo-grond',
		pageIndex: layout.pageIndex
	});
	layout.structure.beginElement('Sect');
	drawToelichtingSection(layout, rows);
	layout.structure.endElement();

	// Footer pass. Runs *after* all logical content so total page
	// count is known. Each footer is artifact-tagged inside
	// drawFooters, so it doesn't pollute the structure tree.
	drawFooters(layout);

	// Mount the StructTreeRoot, ParentTree, and per-page
	// /StructParents. After this point pdf-lib's serializer will
	// emit a tagged PDF.
	layout.structure.finalize(doc);
	mountOutline(doc, layout.outline);

	// `useObjectStreams: false` keeps the catalog and StructTreeRoot
	// as plain indirect objects in the body. pdf-lib's default
	// (`true`) packs them into compressed object streams, which
	// confuses some PDF/UA validators (PAC 2024 in particular has
	// historically had bugs with object-stream-packed structure
	// trees) and makes the file harder to debug. The size penalty
	// is a few kilobytes on a typical 5–10-page report.
	return doc.save({ useObjectStreams: false });
}
