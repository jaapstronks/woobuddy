<script lang="ts">
	import { Mail, CheckCircle2, AlertCircle, Loader2 } from 'lucide-svelte';
	import { submitLead, type LeadSource } from '$lib/api/client';
	import { track } from '$lib/analytics/plausible';

	interface Props {
		/** Where the form is being submitted from — telemetry signal only. */
		source: LeadSource;
		/** Compact variant for the post-export moment (fewer fields, tighter spacing). */
		compact?: boolean;
	}

	const { source, compact = false }: Props = $props();

	// Plain HTML inputs rather than Shoelace: the landing page is SSR and
	// cannot load Shoelace at all (see CLAUDE.md — `/review/*` disables SSR
	// exactly because Shoelace needs browser APIs). Using native inputs
	// keeps the form identical across both placements and avoids hydration
	// mismatch headaches.

	let email = $state('');
	let name = $state('');
	let organization = $state('');
	let message = $state('');
	let newsletterOptIn = $state(false);

	type Status = 'idle' | 'submitting' | 'success' | 'error';
	let status = $state<Status>('idle');
	let errorMessage = $state<string | null>(null);

	// Basic client-side email check. The real validation is on the server —
	// this just catches the obviously-wrong cases before a round-trip.
	const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
	const emailLooksValid = $derived(EMAIL_RE.test(email.trim()));
	const canSubmit = $derived(status !== 'submitting' && emailLooksValid);

	async function handleSubmit(event: Event) {
		event.preventDefault();
		if (!canSubmit) return;

		status = 'submitting';
		errorMessage = null;
		try {
			await submitLead({
				email: email.trim(),
				name: name.trim() || undefined,
				organization: organization.trim() || undefined,
				message: message.trim() || undefined,
				source,
				newsletterOptIn
			});
			track('lead_captured', { source, newsletter_opt_in: newsletterOptIn });
			status = 'success';
		} catch (err) {
			status = 'error';
			errorMessage =
				err instanceof Error && err.message
					? err.message
					: 'Er ging iets mis. Probeer het later opnieuw.';
		}
	}
</script>

{#if status === 'success'}
	<div
		class="flex items-start gap-3 rounded-lg border border-success/30 bg-success/5 p-5 text-sm leading-relaxed text-ink"
		role="status"
		aria-live="polite"
	>
		<CheckCircle2 size={20} class="mt-0.5 shrink-0 text-success" />
		<div>
			<p class="font-medium text-ink">Dank je — je bericht is verstuurd.</p>
			<p class="mt-1 text-ink-soft">
				{#if newsletterOptIn}
					We nemen zo snel mogelijk contact op. Je ontvangt voortaan ook de
					nieuwsbrief — je kunt je altijd weer uitschrijven.
				{:else}
					We nemen zo snel mogelijk contact op.
				{/if}
			</p>
		</div>
	</div>
{:else}
	<form
		class="space-y-4"
		onsubmit={handleSubmit}
		aria-describedby={errorMessage ? 'lead-form-error' : undefined}
	>
		<div class={compact ? 'grid gap-3' : 'grid gap-4 sm:grid-cols-2'}>
			<label class="block">
				<span class="text-xs font-medium tracking-wide text-ink-soft uppercase">
					E-mailadres <span class="text-primary">*</span>
				</span>
				<input
					type="email"
					required
					autocomplete="email"
					bind:value={email}
					placeholder="naam@gemeente.nl"
					class="mt-1.5 w-full rounded-md border border-border bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-ink-mute focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
				/>
			</label>

			{#if !compact}
				<label class="block">
					<span class="text-xs font-medium tracking-wide text-ink-soft uppercase">
						Naam <span class="text-ink-mute">(optioneel)</span>
					</span>
					<input
						type="text"
						autocomplete="name"
						bind:value={name}
						class="mt-1.5 w-full rounded-md border border-border bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-ink-mute focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
					/>
				</label>
			{/if}
		</div>

		{#if !compact}
			<label class="block">
				<span class="text-xs font-medium tracking-wide text-ink-soft uppercase">
					Organisatie <span class="text-ink-mute">(optioneel)</span>
				</span>
				<input
					type="text"
					autocomplete="organization"
					bind:value={organization}
					placeholder="Gemeente, ministerie of anders"
					class="mt-1.5 w-full rounded-md border border-border bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-ink-mute focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
				/>
			</label>

			<label class="block">
				<span class="text-xs font-medium tracking-wide text-ink-soft uppercase">
					Bericht <span class="text-ink-mute">(optioneel)</span>
				</span>
				<textarea
					rows="3"
					bind:value={message}
					placeholder="Bijvoorbeeld: waar in je werk zou dit helpen?"
					class="mt-1.5 w-full resize-y rounded-md border border-border bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-ink-mute focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
				></textarea>
			</label>
		{/if}

		<label class="flex items-start gap-3 text-sm leading-relaxed text-ink-soft">
			<input
				type="checkbox"
				bind:checked={newsletterOptIn}
				class="mt-1 h-4 w-4 shrink-0 rounded border-border text-primary focus:ring-2 focus:ring-primary/20"
			/>
			<span>
				Meld me ook aan voor de nieuwsbrief — af en toe een bericht als er iets
				te melden is over updates of teamfuncties. Je kunt je altijd weer
				uitschrijven.
			</span>
		</label>

		{#if errorMessage}
			<div
				id="lead-form-error"
				class="flex items-start gap-2 rounded-md border border-danger/30 bg-danger/5 p-3 text-sm text-danger"
				role="alert"
				aria-live="assertive"
			>
				<AlertCircle size={16} class="mt-0.5 shrink-0" />
				<span>{errorMessage}</span>
			</div>
		{/if}

		<button
			type="submit"
			disabled={!canSubmit}
			class="group inline-flex items-center gap-2 rounded-md bg-ink px-5 py-3 text-sm font-medium text-bg transition-colors hover:bg-primary disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-ink"
		>
			{#if status === 'submitting'}
				<Loader2 size={16} class="animate-spin" />
				Bezig met versturen…
			{:else}
				<Mail size={16} />
				Verstuur bericht
			{/if}
		</button>
	</form>
{/if}
