<script lang="ts">
	/**
	 * OCR opt-in dialog (#49).
	 *
	 * Shown when `/try` detects a PDF with no selectable text — usually a
	 * scanned document. Asks the user whether to run tesseract.js in the
	 * browser (downloading ~3 MB of Dutch language data once) or to
	 * proceed to manual redaction only.
	 *
	 * Vanilla Tailwind modal rather than `<sl-dialog>`: the landing page
	 * is SSR and does not ship Shoelace (see CLAUDE.md).
	 */
	import { Lock, Languages, ScanLine } from 'lucide-svelte';

	interface Props {
		open: boolean;
		onAccept: () => void;
		onDecline: () => void;
	}

	let { open, onAccept, onDecline }: Props = $props();

	// ESC key treats the dialog as declined — dropping the reviewer into
	// manual redaction is a valid outcome, not an accidental one.
	function handleKeydown(event: KeyboardEvent) {
		if (open && event.key === 'Escape') {
			event.preventDefault();
			onDecline();
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center p-4"
		role="dialog"
		aria-modal="true"
		aria-labelledby="ocr-dialog-title"
	>
		<button
			type="button"
			class="absolute inset-0 bg-ink/50"
			aria-label="Dialoog sluiten"
			onclick={onDecline}
		></button>

		<div
			class="relative z-10 w-full max-w-lg rounded-md border border-border bg-bg p-6 shadow-xl"
		>
			<h2 id="ocr-dialog-title" class="font-serif text-xl text-ink">
				Dit lijkt een gescand document te zijn
			</h2>

			<div class="mt-4 flex flex-col gap-4 text-sm text-ink">
				<p>
					WOO Buddy vond geen selecteerbare tekst in dit PDF-bestand. Dat betekent
					meestal dat het een gescand document is — bijvoorbeeld een brief die is
					geprint en opnieuw ingescand.
				</p>
				<p>
					WOO Buddy kan de tekst in uw browser herkennen (OCR) zodat de
					detectieregels voor namen, BSN's en adressen kunnen werken. Hiervoor
					laden we éénmalig een Nederlands taalmodel van ongeveer 3 MB.
				</p>
				<ul class="flex flex-col gap-2 rounded-md border border-border bg-surface p-3">
					<li class="flex items-start gap-2">
						<Lock size={15} class="mt-0.5 shrink-0 text-primary" />
						<span>
							Alles gebeurt in uw eigen browser — er wordt niets verstuurd naar
							WOO Buddy of derde partijen.
						</span>
					</li>
					<li class="flex items-start gap-2">
						<Languages size={15} class="mt-0.5 shrink-0 text-primary" />
						<span>Het taalmodel is Nederlands en wordt lokaal gehost.</span>
					</li>
					<li class="flex items-start gap-2">
						<ScanLine size={15} class="mt-0.5 shrink-0 text-primary" />
						<span>
							OCR van een typisch document van 20 pagina's duurt 30 tot 90 seconden.
						</span>
					</li>
				</ul>
				<p class="text-xs text-ink-mute">
					Geen OCR? Dan opent het document direct in de review-modus en kunt u met
					handmatige vlakselectie gebieden onleesbaar maken.
				</p>
			</div>

			<div class="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
				<button
					type="button"
					onclick={onDecline}
					class="rounded-md border border-border bg-surface px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-bg"
				>
					Nee, alleen handmatig redigeren
				</button>
				<button
					type="button"
					onclick={onAccept}
					class="rounded-md bg-ink px-4 py-2 text-sm font-medium text-bg transition-colors hover:bg-primary"
				>
					Ja, tekst herkennen
				</button>
			</div>
		</div>
	</div>
{/if}
