<script lang="ts">
	import '@shoelace-style/shoelace/dist/components/button/button.js';
	import '@shoelace-style/shoelace/dist/components/dialog/dialog.js';

	import { onMount, onDestroy } from 'svelte';

	interface Props {
		onAccept: () => void;
		onReject: () => void;
		onDefer: () => void;
		onNext: () => void;
		onPrev: () => void;
		onToggleMode?: () => void;
		onUndo?: () => void;
		onRedo?: () => void;
		/** Mark current page reviewed (#10). Parent decides edit-mode guard. */
		onMarkPage?: () => void;
		/** Flag current page "later terugkomen" (#10). */
		onFlagPage?: () => void;
		/**
		 * #20 — sweep the email-header block that contains the currently
		 * selected detection. Parent resolves which span to target from
		 * the selected detection's char offsets.
		 */
		onSweepHeader?: () => void;
		/**
		 * #20 — sweep the signature block that contains the currently
		 * selected detection.
		 */
		onSweepSignature?: () => void;
	}

	let {
		onAccept,
		onReject,
		onDefer,
		onNext,
		onPrev,
		onToggleMode,
		onUndo,
		onRedo,
		onMarkPage,
		onFlagPage,
		onSweepHeader,
		onSweepSignature
	}: Props = $props();

	let showHelp = $state(false);

	/**
	 * Returns true if a keydown originates from an element where the user is
	 * actively typing and shortcuts must be suppressed. The manual redaction
	 * form uses Shoelace inputs whose shadow roots expose host tag names like
	 * `SL-INPUT` / `SL-TEXTAREA` / `SL-SELECT`, which `closest()` picks up
	 * whether the event target is the host or an internal slot.
	 */
	function isTypingTarget(e: KeyboardEvent): boolean {
		const el = e.target as HTMLElement | null;
		if (!el) return false;
		const tag = el.tagName;
		if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
		if (el.isContentEditable) return true;
		if (typeof el.closest === 'function' && el.closest('sl-input, sl-textarea, sl-select')) {
			return true;
		}
		return false;
	}

	function handleKeydown(e: KeyboardEvent) {
		// Undo/redo are allowed to fire even while typing is otherwise
		// suppressed for letter keys, because they're modifier-driven and
		// users expect Ctrl+Z to work everywhere. But we still don't want
		// them to fight the browser's native undo inside a text field —
		// so bail out of undo/redo too when focus is in an input.
		const typing = isTypingTarget(e);

		// Ctrl/Cmd + Z / Shift+Z / Y → undo/redo.
		if ((e.metaKey || e.ctrlKey) && !e.altKey) {
			const k = e.key.toLowerCase();
			if (k === 'z') {
				if (typing) return;
				e.preventDefault();
				if (e.shiftKey) onRedo?.();
				else onUndo?.();
				return;
			}
			if (k === 'y' && !e.shiftKey) {
				if (typing) return;
				e.preventDefault();
				onRedo?.();
				return;
			}
		}

		if (typing) return;

		// #20 — Shift+H / Shift+S sweep the block containing the currently
		// selected detection. These fire before the letter-key branch below
		// because the lowercased key is still "h"/"s" and would otherwise
		// fall through as a no-op.
		if (e.shiftKey && !e.metaKey && !e.ctrlKey && !e.altKey) {
			const k = e.key.toLowerCase();
			if (k === 'h') {
				e.preventDefault();
				onSweepHeader?.();
				return;
			}
			if (k === 's') {
				e.preventDefault();
				onSweepSignature?.();
				return;
			}
		}

		switch (e.key.toLowerCase()) {
			case 'a':
				e.preventDefault();
				onAccept();
				break;
			case 'r':
				e.preventDefault();
				onReject();
				break;
			case 'd':
				e.preventDefault();
				onDefer();
				break;
			case 'm':
				if (e.metaKey || e.ctrlKey || e.altKey) return;
				e.preventDefault();
				onToggleMode?.();
				break;
			case 'p':
				// #10 — mark current page reviewed. Modifier-free so it
				// doesn't collide with browser Ctrl+P (print); the parent
				// enforces the edit-mode guard since that state is owned
				// by the review store.
				if (e.metaKey || e.ctrlKey || e.altKey) return;
				e.preventDefault();
				onMarkPage?.();
				break;
			case 'f':
				if (e.metaKey || e.ctrlKey || e.altKey) return;
				e.preventDefault();
				onFlagPage?.();
				break;
			case 'arrowright':
				e.preventDefault();
				onNext();
				break;
			case 'arrowleft':
				e.preventDefault();
				onPrev();
				break;
			case '?':
				e.preventDefault();
				showHelp = !showHelp;
				break;
		}
	}

	onMount(() => {
		window.addEventListener('keydown', handleKeydown);
	});

	onDestroy(() => {
		window.removeEventListener('keydown', handleKeydown);
	});
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<sl-dialog label="Sneltoetsen" open={showHelp} onsl-request-close={() => (showHelp = false)}>
	<div class="space-y-2 text-sm">
		<div class="flex justify-between">
			<span>Accepteren / Lakken</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">A</kbd>
		</div>
		<div class="flex justify-between">
			<span>Afwijzen / Niet lakken</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">R</kbd>
		</div>
		<div class="flex justify-between">
			<span>Uitstellen</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">D</kbd>
		</div>
		<div class="flex justify-between">
			<span>Volgende detectie</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">&rarr;</kbd>
		</div>
		<div class="flex justify-between">
			<span>Vorige detectie</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">&larr;</kbd>
		</div>
		<div class="flex justify-between">
			<span>Wissel modus (Beoordelen/Bewerken)</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">M</kbd>
		</div>
		<div class="flex justify-between">
			<span>Pagina beoordeeld (alleen Bewerken)</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">P</kbd>
		</div>
		<div class="flex justify-between">
			<span>Pagina markeren — later terugkomen</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">F</kbd>
		</div>
		<div class="flex justify-between">
			<span>Lak hele e-mailheader van geselecteerde detectie</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">Shift + H</kbd>
		</div>
		<div class="flex justify-between">
			<span>Lak handtekeningblok van geselecteerde detectie</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">Shift + S</kbd>
		</div>
		<div class="flex justify-between">
			<span>Ongedaan maken</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">Ctrl/Cmd + Z</kbd>
		</div>
		<div class="flex justify-between">
			<span>Opnieuw</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">Ctrl/Cmd + Shift + Z</kbd>
		</div>
		<div class="flex justify-between">
			<span>Dit venster</span>
			<kbd class="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">?</kbd>
		</div>
	</div>
	<sl-button slot="footer" variant="primary" onclick={() => (showHelp = false)}>
		Sluiten
	</sl-button>
</sl-dialog>
