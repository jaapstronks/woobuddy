import { describe, it, expect, beforeEach, vi } from 'vitest';

// ---------------------------------------------------------------------------
// detectionStore mock
//
// undo.svelte.ts talks to the detections store for every command's forward
// and reverse. We replace it with a spy-backed stub so tests can assert
// exactly which payloads the Tier 2 card commands dispatch, without running
// the real Svelte 5 runes state machine or any network requests.
// ---------------------------------------------------------------------------

// `vi.mock` is hoisted above the file; use `vi.hoisted` so the shared spy
// is constructed before the mock factory references it.
const { reviewMock } = vi.hoisted(() => ({
	reviewMock: vi.fn(async () => {})
}));

vi.mock('$lib/stores/detections.svelte', () => ({
	detectionStore: {
		review: reviewMock,
		createManual: vi.fn(async () => null),
		adjustBoundary: vi.fn(async () => null),
		remove: vi.fn(async () => {})
	}
}));

// #17 — the undo store imports referenceNamesStore which in turn imports the
// API client and `$env/static/public`. Those aren't available in the test
// environment, so short-circuit the chain with a stub exporting just the
// handful of methods the commands call.
vi.mock('$lib/stores/reference-names.svelte', () => ({
	referenceNamesStore: {
		add: vi.fn(async () => null),
		remove: vi.fn(async () => false)
	}
}));

// list-commands.ts also imports customTermsStore (for AddCustomTermCommand /
// RemoveCustomTermCommand). Same story as reference-names: the real module
// pulls in `$lib/api/client.ts` → `$env/static/public`, which vitest can't
// resolve. Short-circuit with the two methods the commands actually call.
vi.mock('$lib/stores/custom-terms.svelte', () => ({
	customTermsStore: {
		add: vi.fn(async () => null),
		remove: vi.fn(async () => false)
	}
}));

import {
	ChangeArticleCommand,
	SetSubjectRoleCommand,
	SweepBlockCommand,
	SameNameSweepCommand
} from './undo.svelte';

beforeEach(() => {
	reviewMock.mockClear();
});

describe('ChangeArticleCommand', () => {
	it('forward sends the new article only', async () => {
		const cmd = new ChangeArticleCommand('det-1', '5.1.2e', '5.1.1d');
		await cmd.forward();
		expect(reviewMock).toHaveBeenCalledWith('det-1', { woo_article: '5.1.1d' });
	});

	it('reverse restores the previous article', async () => {
		const cmd = new ChangeArticleCommand('det-1', '5.1.2e', '5.1.1d');
		await cmd.reverse();
		expect(reviewMock).toHaveBeenCalledWith('det-1', { woo_article: '5.1.2e' });
	});

	it('reverse is a no-op when there was no previous article', async () => {
		const cmd = new ChangeArticleCommand('det-1', null, '5.1.1d');
		await cmd.reverse();
		expect(reviewMock).not.toHaveBeenCalled();
	});
});

describe('SetSubjectRoleCommand', () => {
	it('burger chip sends the role and does NOT touch review_status', async () => {
		const cmd = new SetSubjectRoleCommand('det-1', null, 'burger', 'pending');
		await cmd.forward();
		expect(reviewMock).toHaveBeenCalledWith('det-1', { subject_role: 'burger' });
	});

	it('ambtenaar chip sends the role and does NOT touch review_status', async () => {
		const cmd = new SetSubjectRoleCommand('det-1', 'burger', 'ambtenaar', 'accepted');
		await cmd.forward();
		expect(reviewMock).toHaveBeenCalledWith('det-1', { subject_role: 'ambtenaar' });
	});

	it('publiek_functionaris click records the role without touching review_status', async () => {
		const cmd = new SetSubjectRoleCommand('det-1', null, 'publiek_functionaris', 'pending');
		await cmd.forward();
		expect(reviewMock).toHaveBeenCalledWith('det-1', {
			subject_role: 'publiek_functionaris'
		});
	});

	it('reverse after publiek_functionaris only restores the previous role', async () => {
		const cmd = new SetSubjectRoleCommand('det-1', 'burger', 'publiek_functionaris', 'accepted');
		await cmd.reverse();
		expect(reviewMock).toHaveBeenCalledWith('det-1', {
			subject_role: 'burger'
		});
	});

	it('reverse of a first-time chip click clears subject_role explicitly', async () => {
		const cmd = new SetSubjectRoleCommand('det-1', null, 'burger', 'pending');
		await cmd.reverse();
		expect(reviewMock).toHaveBeenCalledWith('det-1', { clear_subject_role: true });
	});
});

describe('SweepBlockCommand', () => {
	it('forward accepts every target in construction order', async () => {
		const cmd = new SweepBlockCommand('email_header', [
			{ id: 'a', previousStatus: 'pending', previousArticle: '5.1.2e', nextArticle: '5.1.2e' },
			{ id: 'b', previousStatus: 'pending', previousArticle: null, nextArticle: null }
		]);
		await cmd.forward();
		expect(reviewMock).toHaveBeenNthCalledWith(1, 'a', {
			review_status: 'accepted',
			woo_article: '5.1.2e'
		});
		expect(reviewMock).toHaveBeenNthCalledWith(2, 'b', { review_status: 'accepted' });
	});

	it('reverse restores each target in the opposite order', async () => {
		const cmd = new SweepBlockCommand('signature_block', [
			{ id: 'a', previousStatus: 'pending', previousArticle: '5.1.2e', nextArticle: '5.1.2e' },
			{ id: 'b', previousStatus: 'deferred', previousArticle: null, nextArticle: null }
		]);
		await cmd.reverse();
		// Reverse walks targets[] from the end, so `b` goes first.
		expect(reviewMock).toHaveBeenNthCalledWith(1, 'b', { review_status: 'deferred' });
		expect(reviewMock).toHaveBeenNthCalledWith(2, 'a', {
			review_status: 'pending',
			woo_article: '5.1.2e'
		});
	});

	it('label reflects block kind and target count', () => {
		const header = new SweepBlockCommand('email_header', [
			{ id: 'a', previousStatus: 'pending', previousArticle: null, nextArticle: null },
			{ id: 'b', previousStatus: 'pending', previousArticle: null, nextArticle: null }
		]);
		expect(header.label).toBe('Lak e-mailheader (2)');
		const sig = new SweepBlockCommand('signature_block', [
			{ id: 'a', previousStatus: 'pending', previousArticle: null, nextArticle: null }
		]);
		expect(sig.label).toBe('Lak handtekeningblok (1)');
	});
});

describe('SameNameSweepCommand', () => {
	it('forward applies nextStatus to every target', async () => {
		const cmd = new SameNameSweepCommand('Jan de Vries', 'accepted', [
			{ id: 'a', previousStatus: 'pending' },
			{ id: 'b', previousStatus: 'pending' }
		]);
		await cmd.forward();
		expect(reviewMock).toHaveBeenNthCalledWith(1, 'a', { review_status: 'accepted' });
		expect(reviewMock).toHaveBeenNthCalledWith(2, 'b', { review_status: 'accepted' });
	});

	it('reverse restores each target previousStatus in opposite order', async () => {
		const cmd = new SameNameSweepCommand('Jan de Vries', 'accepted', [
			{ id: 'a', previousStatus: 'pending' },
			{ id: 'b', previousStatus: 'deferred' }
		]);
		await cmd.reverse();
		expect(reviewMock).toHaveBeenNthCalledWith(1, 'b', { review_status: 'deferred' });
		expect(reviewMock).toHaveBeenNthCalledWith(2, 'a', { review_status: 'pending' });
	});

	it('label quotes the display name and includes count', () => {
		const cmd = new SameNameSweepCommand('Jan de Vries', 'accepted', [
			{ id: 'a', previousStatus: 'pending' },
			{ id: 'b', previousStatus: 'pending' },
			{ id: 'c', previousStatus: 'pending' }
		]);
		expect(cmd.label).toBe("Lak 'Jan de Vries' (3)");
	});
});
