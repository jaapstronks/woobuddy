/**
 * DOM-side effects for the PDF overlay layer.
 *
 * Extracted from PdfViewer.svelte so the animation/scroll plumbing can
 * be reused across callers (undo flash, sidebar-selection pulse) and
 * tested as pure DOM helpers.
 *
 * Both helpers target elements stamped with `data-detection-id="<id>"`
 * inside the provided overlay root. The helpers are idempotent — a
 * second call on an already-animating element restarts the animation.
 */

/**
 * Briefly apply a CSS class to all overlays matching a detection id,
 * forcing a reflow in between so the keyframe restarts if the class
 * was already present. The class is removed on `animationend`.
 */
export function pulseOverlay(
	root: HTMLElement,
	detectionId: string,
	className: string
): void {
	const els = root.querySelectorAll<HTMLElement>(
		`[data-detection-id="${CSS.escape(detectionId)}"]`
	);
	for (const el of els) {
		el.classList.remove(className);
		// Force a reflow so a re-add re-plays the keyframe.
		void el.offsetWidth;
		el.classList.add(className);
		el.addEventListener('animationend', () => el.classList.remove(className), {
			once: true
		});
	}
}

/**
 * Center a detection's overlay in its scroll ancestor and pulse it.
 * No-op when the overlay for that id is not currently rendered — e.g.
 * when the detection lives on a page other than the one being shown.
 */
export function scrollDetectionIntoView(
	root: HTMLElement,
	detectionId: string,
	pulseClass: string
): void {
	const el = root.querySelector<HTMLElement>(
		`[data-detection-id="${CSS.escape(detectionId)}"]`
	);
	if (!el) return;
	el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
	el.classList.remove(pulseClass);
	void el.offsetWidth;
	el.classList.add(pulseClass);
	el.addEventListener('animationend', () => el.classList.remove(pulseClass), {
		once: true
	});
}

/**
 * Flash the overlays for a list of detection ids. Convenience wrapper
 * over `pulseOverlay` used by the undo/redo affordance.
 */
export function flashOverlays(
	root: HTMLElement,
	detectionIds: readonly string[],
	className: string
): void {
	for (const id of detectionIds) pulseOverlay(root, id, className);
}
