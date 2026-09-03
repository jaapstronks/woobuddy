import { describe, it, expect, vi } from 'vitest';
import { renderTextLayer } from './pdf-page-render';

// pdf.js 6 drives the whole text layer through CSS custom properties: the
// container sizes itself with
// `round(down, var(--total-scale-factor) * <page>px, var(--scale-round-x))`
// and every span is positioned in percent of that box. Miss one of those
// vars and the declaration is invalid at computed-value time, the container
// collapses to 0px, and the spans stack on the left edge (#82). None of that
// throws, so only a test that reads the container back catches a regression.
//
// vitest runs under `environment: 'node'`, so there is no real DOM. The
// function under test only touches `innerHTML` and `style.setProperty`, so
// stubbing that surface is enough — no JSDOM needed.

vi.mock('pdfjs-dist', () => ({
	TextLayer: class {
		render() {
			return Promise.resolve();
		}
		cancel() {}
	}
}));

function fakeContainer() {
	const props = new Map<string, string>();
	return {
		innerHTML: 'stale',
		style: {
			width: '',
			height: '',
			setProperty(name: string, value: string) {
				props.set(name, value);
			}
		},
		props
	};
}

function fakePage() {
	return { getTextContent: () => Promise.resolve({ items: [], styles: {} }) };
}

const viewport = { width: 864, height: 1222, rawDims: { pageWidth: 595, pageHeight: 842 } };

describe('renderTextLayer', () => {
	it('sets the CSS vars pdf.js 6 needs to size the container', async () => {
		const container = fakeContainer();

		await renderTextLayer(
			fakePage(),
			viewport,
			container as unknown as HTMLDivElement,
			1.4521008403361344,
			null
		);

		// The pdf.js 6 name. Without it the container computes to 0px wide.
		expect(container.props.get('--total-scale-factor')).toBe('1.4521008403361344');
		// The rounding steps in the same calc — equally required.
		expect(container.props.get('--scale-round-x')).toBe('1px');
		expect(container.props.get('--scale-round-y')).toBe('1px');
		// The pdf.js 5 name stays alongside for anything still reading it.
		expect(container.props.get('--scale-factor')).toBe('1.4521008403361344');
	});

	it('clears the previous render before starting a new one', async () => {
		const container = fakeContainer();
		const cancel = vi.fn();

		await renderTextLayer(fakePage(), viewport, container as unknown as HTMLDivElement, 1, {
			cancel
		});

		expect(cancel).toHaveBeenCalledOnce();
		expect(container.innerHTML).toBe('');
	});

	it('returns null when there is no container to render into', async () => {
		await expect(renderTextLayer(fakePage(), viewport, null, 1, null)).resolves.toBeNull();
	});
});
