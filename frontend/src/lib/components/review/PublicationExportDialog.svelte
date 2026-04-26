<script lang="ts">
	/**
	 * Publication-export dialog (#52).
	 *
	 * Collects the DiWoo / GPP-Woo metadata required to build the
	 * publication bundle, then hands the values off to the parent which
	 * runs the export flow. The dialog itself doesn't fetch the
	 * redacted PDF — that part stays in the existing review-export
	 * store so the busy/error UX is consistent with the plain PDF
	 * export.
	 *
	 * Required fields drive button state:
	 *   - officieleTitel
	 *   - identifier
	 *   - informatiecategorieen (1+)
	 *   - opsteller
	 * Other DiWoo fields default off the document context (creatiedatum
	 * = upload time, language = nld, format = application/pdf).
	 */
	import '@shoelace-style/shoelace/dist/components/dialog/dialog.js';
	import '@shoelace-style/shoelace/dist/components/input/input.js';
	import '@shoelace-style/shoelace/dist/components/select/select.js';
	import '@shoelace-style/shoelace/dist/components/option/option.js';
	import '@shoelace-style/shoelace/dist/components/textarea/textarea.js';
	import '@shoelace-style/shoelace/dist/components/button/button.js';
	import '@shoelace-style/shoelace/dist/components/alert/alert.js';
	import '@shoelace-style/shoelace/dist/components/tag/tag.js';
	import '@shoelace-style/shoelace/dist/components/spinner/spinner.js';

	import { onMount } from 'svelte';
	import type { Document } from '$lib/types';
	import type {
		InformatiecategorieRef,
		PublicationMetadataInput
	} from '$lib/services/diwoo';
	import { validateMetadataInput } from '$lib/services/diwoo';

	interface ListItem {
		uri: string;
		label: string;
	}

	interface Props {
		open: boolean;
		document: Document | null;
		busy: boolean;
		onCancel: () => void;
		onSubmit: (input: PublicationMetadataInput) => Promise<void> | void;
	}

	let { open, document: doc, busy, onCancel, onSubmit }: Props = $props();

	// Form state. We seed once on first open so reopening the dialog
	// after a successful export resets to the doc-derived defaults
	// rather than holding the previous reviewer's values.
	let officieleTitel = $state('');
	let identifier = $state('');
	let chosenCategorieUri = $state('');
	let opsteller = $state('');
	let omschrijving = $state('');
	let language = $state('nld');

	let categorieen = $state<ListItem[]>([]);
	let listsError = $state<string | null>(null);
	let initialized = $state(false);

	const creatiedatum = $derived(deriveCreated(doc));

	// Lazy-load TOOI lists once the dialog opens. The fetch is small
	// (~3 KB JSON) so we don't bother caching it across mounts.
	$effect(() => {
		if (!open) return;
		if (categorieen.length > 0 || listsError) return;
		void loadLists();
	});

	// Seed defaults from the document the first time the dialog opens
	// for it. Only fires when `open` flips to true *and* we haven't
	// initialized yet for this document — otherwise typing in the
	// dialog would get clobbered every render.
	$effect(() => {
		if (!open || initialized) return;
		officieleTitel = stripExtension(doc?.filename ?? '');
		identifier = '';
		chosenCategorieUri = '';
		opsteller = '';
		omschrijving = '';
		language = 'nld';
		initialized = true;
	});

	// Reset the "initialized" flag once the dialog closes so the next
	// open picks up fresh defaults (e.g. after navigating to another
	// document).
	$effect(() => {
		if (!open) initialized = false;
	});

	async function loadLists() {
		try {
			const res = await fetch('/diwoo-tooi-lists/informatiecategorieen.json');
			if (!res.ok) throw new Error(`status ${res.status}`);
			const payload = (await res.json()) as { items: ListItem[] };
			categorieen = payload.items;
		} catch (err) {
			listsError = err instanceof Error ? err.message : 'onbekende fout';
		}
	}

	function stripExtension(filename: string): string {
		return filename.replace(/\.[a-z0-9]{1,5}$/i, '');
	}

	function deriveCreated(d: Document | null): string {
		if (d?.document_date) return d.document_date.slice(0, 10);
		if (d?.created_at) return d.created_at.slice(0, 10);
		return new Date().toISOString().slice(0, 10);
	}

	const chosenCategorie = $derived(
		categorieen.find((c) => c.uri === chosenCategorieUri) ?? null
	);

	const draftInput = $derived<Partial<PublicationMetadataInput>>({
		officieleTitel: officieleTitel.trim(),
		identifier: identifier.trim(),
		informatiecategorieen: chosenCategorie ? [chosenCategorie] : [],
		opsteller: opsteller.trim(),
		creatiedatum,
		laatstGewijzigdDatum: new Date().toISOString(),
		language,
		bestandsformaat: 'application/pdf',
		bestandsnaam: `gelakt_${doc?.filename ?? 'document.pdf'}`,
		omschrijving: omschrijving.trim() || undefined
	});

	const missing = $derived(validateMetadataInput(draftInput));
	const canSubmit = $derived(missing.length === 0 && !busy && !listsError);

	async function handleSubmit() {
		if (!canSubmit) return;
		const input: PublicationMetadataInput = {
			officieleTitel: officieleTitel.trim(),
			identifier: identifier.trim(),
			informatiecategorieen: chosenCategorie ? [chosenCategorie as InformatiecategorieRef] : [],
			opsteller: opsteller.trim(),
			verantwoordelijke: opsteller.trim(),
			creatiedatum,
			laatstGewijzigdDatum: new Date().toISOString(),
			language,
			bestandsformaat: 'application/pdf',
			bestandsnaam: `gelakt_${doc?.filename ?? 'document.pdf'}`,
			handelingen: [{ type: 'anonimiseren', atTime: new Date().toISOString() }],
			omschrijving: omschrijving.trim() || undefined
		};
		await onSubmit(input);
	}

	onMount(() => {
		// no-op; keeps the import surface explicit even when the dialog
		// is rendered conditionally by the parent
	});
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<sl-dialog
	label="Exporteer met publicatiemetadata"
	open={open}
	onsl-request-close={(e: Event) => {
		// Block dismissal while the export is running so the user
		// doesn't half-cancel an in-flight zip.
		if (busy) {
			e.preventDefault();
			return;
		}
		onCancel();
	}}
>
	<div class="flex flex-col gap-3">
		<p class="text-sm text-ink-mute">
			Vul de DiWoo-metadata in om een publicatieklare bundel te genereren
			(gelakte PDF + metadata.xml + metadata.json + lakkenoverzicht). De bundel
			past in elk Woo-platform dat de
			<a class="underline" href="https://standaarden.overheid.nl/diwoo/metadata" target="_blank" rel="noopener">DiWoo-standaard</a>
			leest, waaronder
			<a class="underline" href="https://github.com/GPP-Woo/GPP-publicatiebank" target="_blank" rel="noopener">GPP-publicatiebank</a>.
		</p>

		{#if listsError}
			<sl-alert variant="warning" open>
				<strong>TOOI-lijst niet geladen.</strong>
				De informatiecategorieën konden niet worden opgehaald ({listsError}). Publicatie-export
				is uitgeschakeld zolang de lijst ontbreekt.
			</sl-alert>
		{/if}

		<!-- svelte-ignore a11y_label_has_associated_control -->
		<sl-input
			label="Officiële titel"
			help-text="dcterms:title — wordt overgenomen in metadata.xml"
			value={officieleTitel}
			onsl-input={(e: Event) => { officieleTitel = (e.target as HTMLInputElement).value; }}
			required
		></sl-input>

		<!-- svelte-ignore a11y_label_has_associated_control -->
		<sl-input
			label="Kenmerk / besluit-identifier"
			help-text="dcterms:identifier — bijvoorbeeld het zaaknummer of besluitnummer"
			value={identifier}
			onsl-input={(e: Event) => { identifier = (e.target as HTMLInputElement).value; }}
			required
		></sl-input>

		<!-- svelte-ignore a11y_label_has_associated_control -->
		<sl-select
			label="Informatiecategorie (TOOI)"
			help-text="diwoo:informatiecategorie — verplicht volgens DiWoo"
			value={chosenCategorieUri}
			disabled={categorieen.length === 0}
			onsl-change={(e: Event) => {
				chosenCategorieUri = (e.target as HTMLSelectElement).value;
			}}
		>
			{#each categorieen as cat}
				<sl-option value={cat.uri}>{cat.label}</sl-option>
			{/each}
		</sl-select>

		<!-- svelte-ignore a11y_label_has_associated_control -->
		<sl-input
			label="Opsteller / organisatie"
			help-text="dcterms:creator — vrij tekstveld; later koppelbaar aan TOOI-organisaties"
			value={opsteller}
			onsl-input={(e: Event) => { opsteller = (e.target as HTMLInputElement).value; }}
			required
		></sl-input>

		<!-- svelte-ignore a11y_label_has_associated_control -->
		<sl-textarea
			label="Korte omschrijving (optioneel)"
			rows="2"
			value={omschrijving}
			onsl-input={(e: Event) => { omschrijving = (e.target as HTMLTextAreaElement).value; }}
		></sl-textarea>

		<div class="rounded-md border border-border bg-surface p-3 text-xs text-ink-mute">
			<p class="mb-1 font-medium text-ink">Automatisch ingevuld</p>
			<ul class="space-y-0.5">
				<li>Creatiedatum: <span class="font-mono">{creatiedatum}</span> (uit document)</li>
				<li>Bestandsformaat: <span class="font-mono">application/pdf</span></li>
				<li>Taal: <span class="font-mono">nld</span></li>
				<li>Documenthandeling: <span class="font-mono">anonimiseren</span> (deze export)</li>
			</ul>
		</div>
	</div>

	<sl-button slot="footer" variant="text" onclick={onCancel} disabled={busy}>
		Annuleren
	</sl-button>
	<sl-button slot="footer" variant="primary" onclick={handleSubmit} disabled={!canSubmit}>
		{#if busy}
			<sl-spinner slot="prefix" style="font-size: 1rem; --indicator-color: white;"></sl-spinner>
			Bundelen...
		{:else}
			Bundel downloaden (.zip)
		{/if}
	</sl-button>
</sl-dialog>
