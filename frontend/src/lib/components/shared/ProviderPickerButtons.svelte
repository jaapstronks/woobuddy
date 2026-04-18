<script lang="ts">
	/**
	 * Three-button strip for the SharePoint / OneDrive and Google Drive
	 * pickers (#51). Lives below the drop zone so the primary path
	 * (drag-drop of a local PDF) stays visually dominant, while
	 * reviewers whose documents live in M365 or Drive get a first-
	 * class ingestion path.
	 *
	 * The component handles its own progress UI during
	 * auth → pick → download because the flow is meaningfully
	 * different from a drag-drop (network round-trips, an OAuth
	 * popup, a transfer bar). On success it calls the shared
	 * `onfile` callback, which is the same entry point the drop
	 * zone uses — the parent doesn't care where the file came from.
	 */
	import '@shoelace-style/shoelace/dist/components/progress-bar/progress-bar.js';
	import {
		anyPickerEnabled,
		isPickerEnabled,
		type PickerProvider
	} from '$lib/config/file-picker';
	import { pickFromProvider, PickerError, trackPicker } from '$lib/services/file-picker';

	let {
		onfile,
		disabled = false
	}: {
		onfile: (file: File) => void;
		disabled?: boolean;
	} = $props();

	type PhaseKind = 'idle' | 'auth' | 'downloading' | 'consent-blocked' | 'error';

	interface Phase {
		kind: PhaseKind;
		provider: PickerProvider | null;
		loadedBytes: number;
		totalBytes: number | null;
		message: string | null;
	}

	let phase = $state<Phase>({
		kind: 'idle',
		provider: null,
		loadedBytes: 0,
		totalBytes: null,
		message: null
	});

	const msEnabled = isPickerEnabled('microsoft');
	const googleEnabled = isPickerEnabled('google');
	const anyEnabled = anyPickerEnabled();

	function resetPhase() {
		phase = {
			kind: 'idle',
			provider: null,
			loadedBytes: 0,
			totalBytes: null,
			message: null
		};
	}

	async function handlePick(provider: PickerProvider) {
		if (disabled || phase.kind !== 'idle') return;
		phase = {
			kind: 'auth',
			provider,
			loadedBytes: 0,
			totalBytes: null,
			message: null
		};
		trackPicker('picker.launched', provider);

		try {
			const file = await pickFromProvider(provider, {
				onDownloadStart: () => {
					phase = { ...phase, kind: 'downloading' };
				},
				onDownloadProgress: (loaded, total) => {
					phase = { ...phase, loadedBytes: loaded, totalBytes: total };
				}
			});
			trackPicker('picker.completed', provider);
			resetPhase();
			onfile(file);
		} catch (e) {
			if (e instanceof PickerError && e.kind === 'cancelled') {
				trackPicker('picker.cancelled', provider);
				resetPhase();
				return;
			}
			if (e instanceof PickerError && e.kind === 'consent') {
				phase = {
					kind: 'consent-blocked',
					provider,
					loadedBytes: 0,
					totalBytes: null,
					message: e.message
				};
				return;
			}
			phase = {
				kind: 'error',
				provider,
				loadedBytes: 0,
				totalBytes: null,
				message:
					e instanceof PickerError
						? e.message
						: 'Er ging iets mis bij het ophalen van het bestand.'
			};
		}
	}

	function formatBytes(n: number): string {
		if (n < 1024) return `${n} B`;
		if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
		return `${(n / 1024 / 1024).toFixed(1)} MB`;
	}
</script>

{#if anyEnabled}
	<div class="picker-strip flex flex-col gap-3" aria-live="polite">
		{#if phase.kind === 'idle'}
			<div class="flex items-center gap-3">
				<span class="h-px flex-1 bg-border" aria-hidden="true"></span>
				<span class="text-xs font-medium tracking-wide text-ink-mute uppercase">
					of direct uit de cloud
				</span>
				<span class="h-px flex-1 bg-border" aria-hidden="true"></span>
			</div>

			<div class="flex flex-col gap-2 sm:flex-row">
				{#if msEnabled}
					<button
						type="button"
						{disabled}
						onclick={() => handlePick('microsoft')}
						class="picker-btn group flex flex-1 items-center justify-center gap-2.5 rounded-md border border-border bg-surface px-4 py-3 text-sm font-medium text-ink transition-colors hover:border-primary/60 hover:bg-bg disabled:cursor-not-allowed disabled:opacity-60"
					>
						<!-- Microsoft 4-square logo (official quadrant colours). -->
						<svg
							width="16"
							height="16"
							viewBox="0 0 21 21"
							aria-hidden="true"
							class="shrink-0"
						>
							<rect x="1" y="1" width="9" height="9" fill="#f25022" />
							<rect x="11" y="1" width="9" height="9" fill="#7fba00" />
							<rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
							<rect x="11" y="11" width="9" height="9" fill="#ffb900" />
						</svg>
						<span>Uit SharePoint of OneDrive</span>
					</button>
				{/if}

				{#if googleEnabled}
					<button
						type="button"
						{disabled}
						onclick={() => handlePick('google')}
						class="picker-btn group flex flex-1 items-center justify-center gap-2.5 rounded-md border border-border bg-surface px-4 py-3 text-sm font-medium text-ink transition-colors hover:border-primary/60 hover:bg-bg disabled:cursor-not-allowed disabled:opacity-60"
					>
						<!-- Google "G" — simplified two-tone rendering that avoids
						     shipping a multi-gradient asset for a small button. -->
						<svg
							width="16"
							height="16"
							viewBox="0 0 48 48"
							aria-hidden="true"
							class="shrink-0"
						>
							<path
								fill="#4285F4"
								d="M43.6 20.5H42V20H24v8h11.3A12 12 0 1 1 24 12c3.1 0 5.9 1.2 8 3.1l5.7-5.7A20 20 0 1 0 44 24c0-1.2-.1-2.3-.4-3.5z"
							/>
							<path fill="#34A853" d="M6.3 14.7l6.6 4.8A12 12 0 0 1 24 12c3.1 0 5.9 1.2 8 3.1l5.7-5.7A20 20 0 0 0 6.3 14.7z" />
							<path fill="#FBBC05" d="M24 44c5.3 0 9.8-1.8 13.1-4.9l-6-5A12 12 0 0 1 12.7 28.5l-6.6 5.1A20 20 0 0 0 24 44z" />
							<path fill="#EA4335" d="M43.6 20.5H42V20H24v8h11.3a12 12 0 0 1-4.2 6.1l6 5C40.9 35.9 44 30.4 44 24c0-1.2-.1-2.3-.4-3.5z" />
						</svg>
						<span>Uit Google Drive</span>
					</button>
				{/if}
			</div>

			<!-- The reassurance lives under the buttons: the picker is the
			     one feature most likely to trigger the "wait, does this
			     upload my document?" reflex, because the user just signed
			     into a third-party app. Answering the question in the
			     same glance as the button is the lowest-friction reply. -->
			<p class="text-center text-[11px] text-ink-mute">
				Uw bestand wordt rechtstreeks vanuit Microsoft of Google in uw browser geladen —
				het passeert onze servers niet.
			</p>
		{:else if phase.kind === 'consent-blocked'}
			<div class="rounded-md border border-warning/40 bg-warning/10 p-4 text-sm">
				<p class="font-medium text-ink">
					Uw organisatie staat externe apps nog niet toe.
				</p>
				<p class="mt-1 text-ink-soft">
					Vraag uw ICT-beheerder om WOO Buddy toe te voegen, of download het bestand
					eerst handmatig uit
					{phase.provider === 'microsoft' ? 'SharePoint/OneDrive' : 'Google Drive'}
					en sleep het hier naartoe.
				</p>
				<button
					type="button"
					onclick={resetPhase}
					class="mt-3 text-xs font-medium text-primary underline"
				>
					Sluiten
				</button>
			</div>
		{:else if phase.kind === 'error'}
			<div class="rounded-md border border-danger/30 bg-danger/5 p-4 text-sm">
				<p class="text-danger">{phase.message}</p>
				<button
					type="button"
					onclick={resetPhase}
					class="mt-2 text-xs font-medium text-primary underline"
				>
					Opnieuw proberen
				</button>
			</div>
		{:else}
			<!-- auth / downloading -->
			<div class="rounded-md border border-border bg-surface px-4 py-4">
				<p class="text-sm font-medium text-ink">
					{#if phase.kind === 'auth'}
						Aanmelden bij
						{phase.provider === 'microsoft' ? 'Microsoft' : 'Google'}…
					{:else}
						Uw bestand wordt direct uit
						{phase.provider === 'microsoft' ? 'SharePoint/OneDrive' : 'Google Drive'}
						naar uw browser gehaald.
					{/if}
				</p>
				<div class="mt-2">
					{#if phase.kind === 'downloading' && phase.totalBytes}
						<sl-progress-bar
							value={Math.min(100, Math.round((phase.loadedBytes / phase.totalBytes) * 100))}
							style="--height: 4px;"
						></sl-progress-bar>
						<p class="mt-1 text-xs text-ink-mute">
							{formatBytes(phase.loadedBytes)} van {formatBytes(phase.totalBytes)} · passeert onze
							servers niet
						</p>
					{:else}
						<sl-progress-bar indeterminate style="--height: 4px;"></sl-progress-bar>
						<p class="mt-1 text-xs text-ink-mute">
							{#if phase.kind === 'downloading'}
								{formatBytes(phase.loadedBytes)} ontvangen · passeert onze servers niet
							{:else}
								Een pop-up opent bij uw provider
							{/if}
						</p>
					{/if}
				</div>
			</div>
		{/if}
	</div>
{/if}
