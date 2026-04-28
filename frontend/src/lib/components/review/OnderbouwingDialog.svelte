<script lang="ts">
	/**
	 * Onderbouwingsrapport dialog (#64).
	 *
	 * Collects the optional reviewer-supplied metadata (zaaknummer,
	 * naam, opmerkingen) and the "ook CSV erbij" toggle before the
	 * review-export store generates the report. All inputs are
	 * stored only in memory — they end up in the PDF the reviewer
	 * downloads, not on any server.
	 *
	 * The dialog itself doesn't import pdf-lib or the report
	 * generator: the parent's `onConfirm` handler does the lazy
	 * import so this component stays cheap to render.
	 */
	import '@shoelace-style/shoelace/dist/components/dialog/dialog.js';
	import '@shoelace-style/shoelace/dist/components/input/input.js';
	import '@shoelace-style/shoelace/dist/components/textarea/textarea.js';
	import '@shoelace-style/shoelace/dist/components/checkbox/checkbox.js';
	import '@shoelace-style/shoelace/dist/components/button/button.js';
	import '@shoelace-style/shoelace/dist/components/spinner/spinner.js';

	import type { ReviewerInput } from '$lib/services/onderbouwing';
	import { Download } from 'lucide-svelte';

	interface Props {
		open: boolean;
		busy: boolean;
		acceptedCount: number;
		hasRedactedHash: boolean;
		onCancel: () => void;
		onConfirm: (input: ReviewerInput) => Promise<void> | void;
	}

	let { open, busy, acceptedCount, hasRedactedHash, onCancel, onConfirm }: Props =
		$props();

	let zaaknummer = $state('');
	let reviewerName = $state('');
	let opmerkingen = $state('');
	let includeCsv = $state(false);
	let initialized = $state(false);

	$effect(() => {
		if (open && !initialized) {
			zaaknummer = '';
			reviewerName = '';
			opmerkingen = '';
			includeCsv = false;
			initialized = true;
		}
		if (!open) initialized = false;
	});

	async function handleSubmit() {
		if (busy) return;
		await onConfirm({
			zaaknummer: zaaknummer.trim(),
			reviewerName: reviewerName.trim(),
			opmerkingen: opmerkingen.trim(),
			includeCsv
		});
	}
</script>

<sl-dialog
	label="Onderbouwingsrapport genereren"
	open={open || undefined}
	onsl-request-close={(e: Event) => {
		if (busy) {
			e.preventDefault();
			return;
		}
		onCancel();
	}}
>
	<p class="mb-3 text-sm text-ink-soft">
		Een PDF-bijlage bij het Woo-besluit met per gelakte passage de juridische grond
		en motivering. Het rapport bevat geen documenttekst &mdash; alleen positie,
		Woo-artikel en SHA-256 hashes ter verificatie.
	</p>
	<p class="mb-4 text-xs text-ink-mute">
		<strong>{acceptedCount}</strong> geaccepteerde redactie{acceptedCount === 1 ? '' : 's'} worden
		opgenomen.
		{#if !hasRedactedHash}
			De hash van de gelakte PDF ontbreekt &mdash; exporteer eerst de gelakte PDF
			om die ook in het rapport te krijgen.
		{/if}
	</p>

	<div class="flex flex-col gap-3">
		<sl-input
			label="Zaaknummer (optioneel)"
			help-text="Komt op het voorblad. Wordt niet opgeslagen."
			placeholder="Bijv. 2026-0123"
			value={zaaknummer}
			onsl-input={(e: Event) => {
				zaaknummer = (e.target as HTMLInputElement).value;
			}}
			maxlength="80"
			disabled={busy || undefined}
		></sl-input>
		<sl-input
			label="Beoordelaar (optioneel)"
			help-text="Naam van de Woo-co\u00f6rdinator of jurist."
			placeholder="Bijv. J. de Vries"
			value={reviewerName}
			onsl-input={(e: Event) => {
				reviewerName = (e.target as HTMLInputElement).value;
			}}
			maxlength="120"
			disabled={busy || undefined}
		></sl-input>
		<sl-textarea
			label="Opmerkingen (optioneel)"
			help-text="Korte toelichting bij dit besluit, bijvoorbeeld de afhandelingsstrategie."
			rows="3"
			value={opmerkingen}
			onsl-input={(e: Event) => {
				opmerkingen = (e.target as HTMLTextAreaElement).value;
			}}
			maxlength="1000"
			disabled={busy || undefined}
		></sl-textarea>
		<sl-checkbox
			checked={includeCsv || undefined}
			onsl-change={(e: Event) => {
				includeCsv = (e.target as HTMLInputElement).checked;
			}}
			disabled={busy || undefined}
		>
			Ook een CSV-versie toevoegen (PDF + CSV in een zip)
		</sl-checkbox>
	</div>

	<div slot="footer" class="flex justify-end gap-2">
		<sl-button variant="text" onclick={onCancel} disabled={busy || undefined}>
			Annuleren
		</sl-button>
		<sl-button
			variant="primary"
			onclick={handleSubmit}
			disabled={busy || undefined}
		>
			{#if busy}
				<sl-spinner slot="prefix" style="font-size: 1rem; --indicator-color: white;"></sl-spinner>
				Genereren...
			{:else}
				<span slot="prefix"><Download size={14} /></span>
				Genereer rapport
			{/if}
		</sl-button>
	</div>
</sl-dialog>
