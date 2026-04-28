/**
 * Tagged-PDF support for the onderbouwingsrapport (#65).
 *
 * pdf-lib does not ship a high-level structure-tree API, but it exposes
 * every primitive we need to build one: the `BMC` / `BDC` / `EMC`
 * marked-content operators on `PDFPage.pushOperators`, indirect-object
 * registration on `PDFContext`, and direct catalog access on
 * `PDFDocument.catalog`. This module is the wrapper that turns those
 * primitives into a small, opinionated tagging API for the report
 * renderer.
 *
 * Why we need it: WCAG 2.1 / EN 301 549 / PDF/UA-1 require a logical
 * structure tree (`/StructTreeRoot`) so screen readers can announce
 * headings as headings, table cells as cells with their column
 * headers, and lists as lists. Without it, AT users get a flat
 * geometric reading of the visual stream — passable for short
 * single-column documents but below the bar Dutch government
 * recipients expect for a Woo-besluit bijlage.
 *
 * What this module does NOT cover (callers must handle):
 *
 * - Pagination decisions. Pagination must happen *before* a marked-
 *   content sequence is opened, never inside one. Marked-content
 *   sequences cannot span pages — each line of wrapped text gets its
 *   own MCID.
 * - The catalog `/Lang` and `/MarkInfo` entries are managed by the
 *   caller; we only mount `/StructTreeRoot` and per-page
 *   `/StructParents`.
 * - Outlines (`/Outlines`) are a separate concern handled by
 *   `mountOutline`.
 *
 * Performance: the report has ~hundreds to ~few-thousand MCIDs in
 * total. All bookkeeping is in-memory; nothing is hot enough to
 * matter.
 */

import {
	PDFArray,
	PDFDict,
	PDFName,
	PDFNumber,
	PDFOperator,
	PDFOperatorNames as Op,
	PDFRef,
	PDFString,
	type PDFContext,
	type PDFDocument,
	type PDFPage
} from 'pdf-lib';

// ---------------------------------------------------------------------------
// Roles
// ---------------------------------------------------------------------------

/**
 * Structure roles we use. All map directly onto the standard PDF
 * structure types defined in ISO 32000-1 §14.8.4 — no custom roles,
 * so we don't need a `/RoleMap`. Keep the union narrow on purpose:
 * adding a new role should be a deliberate decision, not a typo.
 */
export type StructRole =
	| 'Document'
	| 'Sect'
	| 'H1'
	| 'H2'
	| 'H3'
	| 'P'
	| 'Span'
	| 'Table'
	| 'TR'
	| 'TH'
	| 'TD'
	| 'Caption';

// ---------------------------------------------------------------------------
// Internal model
// ---------------------------------------------------------------------------

/** Either a child element or a leaf marked-content reference. */
type StructChild =
	| { readonly kind: 'element'; readonly id: number }
	| { readonly kind: 'mcid'; readonly pageIndex: number; readonly mcid: number };

interface StructElement {
	role: StructRole;
	id: number;
	parentId: number | null;
	children: StructChild[];
	title?: string;
	alt?: string;
}

// ---------------------------------------------------------------------------
// Outline (bookmarks)
// ---------------------------------------------------------------------------

export interface OutlineEntry {
	/** Display title shown in the bookmarks pane. */
	title: string;
	/** 0-based page index the bookmark jumps to. */
	pageIndex: number;
}

// ---------------------------------------------------------------------------
// StructureBuilder
// ---------------------------------------------------------------------------

/**
 * Lifecycle:
 *
 * ```
 * const sb = new StructureBuilder();
 *
 * sb.beginElement('Sect');
 *   sb.beginElement('H1');
 *     sb.tag(page, 0, () => page.drawText('Hello', { ... }));
 *   sb.endElement();
 *   sb.beginElement('P');
 *     sb.tag(page, 0, () => page.drawText('Body line 1', { ... }));
 *     sb.tag(page, 0, () => page.drawText('Body line 2', { ... }));
 *   sb.endElement();
 * sb.endElement();
 *
 * sb.finalize(doc);
 * ```
 *
 * Decorative content (footers, divider lines, page numbers) goes
 * through `artifact()`, which wraps the drawing in a `BMC /Artifact ...
 * EMC` sequence so it's invisible to assistive tech. PDF/UA-1
 * (Matterhorn check 14-001) requires every content-stream operation
 * to be either tagged or marked as artifact.
 */
export class StructureBuilder {
	private readonly elements: StructElement[] = [];
	private readonly mcidCounters = new Map<number, number>();
	private readonly parentStack: number[] = [];
	private readonly rootId: number;

	constructor() {
		this.rootId = this.allocateElement('Document', null);
		this.parentStack.push(this.rootId);
	}

	private allocateElement(role: StructRole, parentId: number | null): number {
		const id = this.elements.length;
		this.elements.push({ role, id, parentId, children: [] });
		if (parentId !== null) {
			this.elements[parentId].children.push({ kind: 'element', id });
		}
		return id;
	}

	/** Begin a new structure element under the currently open parent. */
	beginElement(role: StructRole, opts: { title?: string; alt?: string } = {}): void {
		const parentId = this.currentParent();
		const id = this.allocateElement(role, parentId);
		if (opts.title) this.elements[id].title = opts.title;
		if (opts.alt) this.elements[id].alt = opts.alt;
		this.parentStack.push(id);
	}

	/** Close the most recently opened element. */
	endElement(): void {
		if (this.parentStack.length <= 1) {
			throw new Error('endElement() called without matching beginElement()');
		}
		this.parentStack.pop();
	}

	/**
	 * Wrap `draw` in a `BDC /role <</MCID n>> ... EMC` sequence and
	 * record the MCID under the currently open element.
	 *
	 * MUST be called inside an `beginElement(...) ... endElement()`
	 * scope (i.e. with at least one element open above the root).
	 *
	 * Caller is responsible for ensuring the page has space *before*
	 * calling — marked-content sequences cannot span pages.
	 */
	tag(page: PDFPage, pageIndex: number, draw: () => void): void {
		const parentId = this.currentParent();
		if (parentId === this.rootId) {
			throw new Error('tag() called at the root; need at least one beginElement');
		}
		const role = this.elements[parentId].role;
		const mcid = this.allocateMcid(pageIndex);

		// pdf-lib's PDFOperatorArg union doesn't include PDFDict, so we
		// inject the inline-dict properties operand as a verbatim string.
		// `<</MCID n>>` is plain ASCII PDF syntax — `copyStringIntoBuffer`
		// emits it byte-for-byte without quoting or escaping. Validated
		// against Acrobat / PAC 2024.
		page.pushOperators(
			PDFOperator.of(Op.BeginMarkedContentSequence, [
				PDFName.of(role),
				`<</MCID ${mcid}>>`
			])
		);
		draw();
		page.pushOperators(PDFOperator.of(Op.EndMarkedContent));

		this.elements[parentId].children.push({ kind: 'mcid', pageIndex, mcid });
	}

	/**
	 * Mark `draw` as decorative artifact content. Has no MCID, no link
	 * to any structure element — exists purely to satisfy PDF/UA's
	 * "everything is tagged" rule for visually-decorative pixels like
	 * footer page numbers, divider lines, and zebra-striped row
	 * backgrounds.
	 */
	artifact(page: PDFPage, draw: () => void): void {
		page.pushOperators(
			PDFOperator.of(Op.BeginMarkedContent, [PDFName.of('Artifact')])
		);
		draw();
		page.pushOperators(PDFOperator.of(Op.EndMarkedContent));
	}

	private currentParent(): number {
		return this.parentStack[this.parentStack.length - 1];
	}

	private allocateMcid(pageIndex: number): number {
		const next = this.mcidCounters.get(pageIndex) ?? 0;
		this.mcidCounters.set(pageIndex, next + 1);
		return next;
	}

	// -------------------------------------------------------------------------
	// Finalize
	// -------------------------------------------------------------------------

	/**
	 * Build the `/StructTreeRoot`, `/ParentTree`, and per-page
	 * `/StructParents` entries on the document. Idempotent in the sense
	 * that calling it twice produces a duplicate tree (don't do that).
	 */
	finalize(doc: PDFDocument): void {
		if (this.parentStack.length !== 1 || this.parentStack[0] !== this.rootId) {
			throw new Error('finalize() called with elements still open');
		}

		const ctx = doc.context;
		const pages = doc.getPages();

		// 1. Pre-allocate refs for every structure element. We need them
		//    upfront because element dicts cross-reference each other
		//    (parent ↔ child), and pdf-lib's two-pass `nextRef` +
		//    `assign` flow handles that cleanly.
		const elementRefs: PDFRef[] = this.elements.map(() => ctx.nextRef());

		// 2. Build the StructTreeRoot ref (also needed for /P on root
		//    children).
		const structTreeRootRef = ctx.nextRef();

		// 3. Materialize each element dict. We build via PDFDict.set
		//    instead of ctx.obj({...}) because pdf-lib's `Literal`
		//    type doesn't expose a clean way to type a Record with
		//    optional fields without a cast — set() takes plain
		//    PDFObject values and is more readable for conditional
		//    keys (T, Alt) anyway.
		for (const el of this.elements) {
			const parentRef =
				el.parentId === null ? structTreeRootRef : elementRefs[el.parentId];
			const kArray = this.buildKidsArray(ctx, el, pages, elementRefs);
			const dict = PDFDict.withContext(ctx);
			dict.set(PDFName.of('Type'), PDFName.of('StructElem'));
			dict.set(PDFName.of('S'), PDFName.of(el.role));
			dict.set(PDFName.of('P'), parentRef);
			dict.set(PDFName.of('K'), kArray);
			if (el.title) dict.set(PDFName.of('T'), PDFString.of(el.title));
			if (el.alt) dict.set(PDFName.of('Alt'), PDFString.of(el.alt));
			ctx.assign(elementRefs[el.id], dict);
		}

		// 4. Build the ParentTree. Number tree where each key is a
		//    page's /StructParents index, and each value is an array
		//    indexed by MCID giving the structure element that owns
		//    that MCID. Pages without any tagged content still need an
		//    entry (an empty array); otherwise PAC complains.
		const parentTreeNumsArray = PDFArray.withContext(ctx);
		const pageParentArrayRefs = new Map<number, PDFRef>();

		for (let pageIndex = 0; pageIndex < pages.length; pageIndex++) {
			const arr = PDFArray.withContext(ctx);
			const mcidCount = this.mcidCounters.get(pageIndex) ?? 0;
			// Indexed lookup: arr[mcid] = elementRef
			const ownerById: PDFRef[] = new Array(mcidCount);
			for (const el of this.elements) {
				for (const child of el.children) {
					if (child.kind === 'mcid' && child.pageIndex === pageIndex) {
						ownerById[child.mcid] = elementRefs[el.id];
					}
				}
			}
			for (let i = 0; i < mcidCount; i++) {
				const ref = ownerById[i];
				if (ref) arr.push(ref);
				else arr.push(elementRefs[this.rootId]);
			}
			const arrRef = ctx.register(arr);
			pageParentArrayRefs.set(pageIndex, arrRef);
			parentTreeNumsArray.push(PDFNumber.of(pageIndex));
			parentTreeNumsArray.push(arrRef);
		}

		const parentTreeDict = PDFDict.withContext(ctx);
		parentTreeDict.set(PDFName.of('Nums'), parentTreeNumsArray);
		const parentTreeRef = ctx.register(parentTreeDict);

		// 5. Wire /StructParents and /Tabs on each page.
		//
		//    /Tabs /S means "tab order follows the structure tree" — required
		//    by PDF/UA-1 (Matterhorn 09-004) on every page in a tagged
		//    document, even when the page has no form fields or annotations
		//    to traverse. Acrobat's Accessibility Check reports its absence
		//    as `Tab order — Failed`. The flag is cheap to set and harmless
		//    on form-free pages, so we set it unconditionally.
		for (let pageIndex = 0; pageIndex < pages.length; pageIndex++) {
			const pageNode = pages[pageIndex].node;
			pageNode.set(PDFName.of('StructParents'), PDFNumber.of(pageIndex));
			pageNode.set(PDFName.of('Tabs'), PDFName.of('S'));
		}

		// 6. Build the StructTreeRoot itself. /K is the root Document
		//    element. /ParentTreeNextKey is one past the last page index
		//    so future modifications can extend without colliding.
		const structTreeRootDict = PDFDict.withContext(ctx);
		structTreeRootDict.set(PDFName.of('Type'), PDFName.of('StructTreeRoot'));
		structTreeRootDict.set(PDFName.of('K'), elementRefs[this.rootId]);
		structTreeRootDict.set(PDFName.of('ParentTree'), parentTreeRef);
		structTreeRootDict.set(
			PDFName.of('ParentTreeNextKey'),
			PDFNumber.of(pages.length)
		);
		ctx.assign(structTreeRootRef, structTreeRootDict);

		// 7. Mount on catalog.
		doc.catalog.set(PDFName.of('StructTreeRoot'), structTreeRootRef);
	}

	private buildKidsArray(
		ctx: PDFContext,
		el: StructElement,
		pages: PDFPage[],
		elementRefs: PDFRef[]
	): PDFArray {
		const arr = PDFArray.withContext(ctx);
		for (const child of el.children) {
			if (child.kind === 'element') {
				arr.push(elementRefs[child.id]);
			} else {
				// MCID leaf: use the marked-content reference dict form
				// `<< /Type /MCR /Pg pageRef /MCID n >>`. The simpler
				// integer form (just `n`) is only valid when *every*
				// kid of the parent lives on the same page — too
				// brittle to rely on, so use the explicit MCR dict
				// everywhere.
				const pageRef = pages[child.pageIndex].ref;
				const mcr = PDFDict.withContext(ctx);
				mcr.set(PDFName.of('Type'), PDFName.of('MCR'));
				mcr.set(PDFName.of('Pg'), pageRef);
				mcr.set(PDFName.of('MCID'), PDFNumber.of(child.mcid));
				arr.push(mcr);
			}
		}
		return arr;
	}
}

// ---------------------------------------------------------------------------
// Outline (PDF bookmarks)
// ---------------------------------------------------------------------------

/**
 * Mount a flat /Outlines dictionary on the document catalog.
 *
 * Each entry becomes a top-level bookmark that jumps to the start of
 * its page (`/Fit` destination — fits the page in the viewer). pdf-lib
 * has no high-level outline API, so this is a manual catalog wire-up.
 *
 * For the onderbouwingsrapport we only need a flat list of section
 * starts (Voorblad, Samenvatting, Tabel, Bijlage A); a deeper tree
 * isn't worth the bookkeeping.
 */
export function mountOutline(doc: PDFDocument, entries: OutlineEntry[]): void {
	if (entries.length === 0) return;

	const ctx = doc.context;
	const pages = doc.getPages();
	const outlinesRef = ctx.nextRef();
	const itemRefs = entries.map(() => ctx.nextRef());

	for (let i = 0; i < entries.length; i++) {
		const entry = entries[i];
		const pageRef =
			pages[Math.min(entry.pageIndex, pages.length - 1)].ref;
		const dest = PDFArray.withContext(ctx);
		dest.push(pageRef);
		dest.push(PDFName.of('Fit'));
		const dict = PDFDict.withContext(ctx);
		dict.set(PDFName.of('Title'), PDFString.of(entry.title));
		dict.set(PDFName.of('Parent'), outlinesRef);
		dict.set(PDFName.of('Dest'), dest);
		if (i > 0) dict.set(PDFName.of('Prev'), itemRefs[i - 1]);
		if (i < entries.length - 1) dict.set(PDFName.of('Next'), itemRefs[i + 1]);
		ctx.assign(itemRefs[i], dict);
	}

	const outlinesDict = PDFDict.withContext(ctx);
	outlinesDict.set(PDFName.of('Type'), PDFName.of('Outlines'));
	outlinesDict.set(PDFName.of('First'), itemRefs[0]);
	outlinesDict.set(PDFName.of('Last'), itemRefs[itemRefs.length - 1]);
	outlinesDict.set(PDFName.of('Count'), PDFNumber.of(entries.length));
	ctx.assign(outlinesRef, outlinesDict);

	doc.catalog.set(PDFName.of('Outlines'), outlinesRef);
}
