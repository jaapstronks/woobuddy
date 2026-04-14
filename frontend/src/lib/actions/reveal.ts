/**
 * Scroll-reveal action. Adds `is-visible` to the element the first time it
 * enters the viewport, then disconnects. Pair with the `.reveal` CSS class
 * (see `app.css`) to fade-and-slide-up. Optional `delay` applies a stagger
 * via inline transition-delay so consecutive items can cascade in.
 *
 * The IntersectionObserver is created lazily and only in the browser, so
 * SSR-rendered landing-page sections still hydrate cleanly. When users have
 * `prefers-reduced-motion: reduce` we short-circuit and reveal immediately
 * — the CSS rule below also no-ops the transform/opacity transitions.
 */

interface RevealOptions {
	/** Stagger delay in milliseconds. */
	delay?: number;
	/** IO root margin — defaults to a small bottom inset so reveals fire just before
	 *  the element is fully in view. */
	rootMargin?: string;
	/** Visibility threshold (0–1). */
	threshold?: number;
}

export function reveal(node: HTMLElement, options: RevealOptions = {}) {
	const { delay = 0, rootMargin = '0px 0px -10% 0px', threshold = 0.1 } = options;

	node.classList.add('reveal');
	if (delay > 0) {
		node.style.transitionDelay = `${delay}ms`;
	}

	// Honour reduced motion: skip the observer entirely and reveal at once.
	const prefersReducedMotion =
		typeof window !== 'undefined' &&
		window.matchMedia('(prefers-reduced-motion: reduce)').matches;
	if (prefersReducedMotion) {
		node.classList.add('is-visible');
		return {};
	}

	const observer = new IntersectionObserver(
		(entries) => {
			for (const entry of entries) {
				if (entry.isIntersecting) {
					node.classList.add('is-visible');
					observer.disconnect();
					break;
				}
			}
		},
		{ rootMargin, threshold }
	);
	observer.observe(node);

	return {
		destroy() {
			observer.disconnect();
		}
	};
}
