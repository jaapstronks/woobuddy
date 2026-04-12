<script lang="ts">
	interface SentenceClassification {
		type: string;
		sentence: string;
		explanation: string;
	}

	interface Props {
		classifications: SentenceClassification[];
	}

	let { classifications }: Props = $props();

	const typeLabels: Record<string, string> = {
		fact: 'Feit',
		opinion: 'Mening',
		prognosis: 'Prognose',
		policy_alternative: 'Beleidsalternatief',
		mixed: 'Gemengd'
	};

	const typeColors: Record<string, string> = {
		fact: 'bg-blue-100 text-blue-700',
		opinion: 'bg-warning/20 text-warning',
		prognosis: 'bg-green-100 text-green-700',
		policy_alternative: 'bg-teal-100 text-teal-700',
		mixed: 'bg-purple-100 text-purple-700'
	};
</script>

{#if classifications.length > 0}
	<div class="space-y-1.5">
		<h4 class="text-xs font-semibold uppercase text-neutral">Feit-mening analyse (art. 5.2)</h4>
		{#each classifications as sc}
			<div class="flex items-start gap-2 rounded bg-white p-2 text-xs border border-gray-100">
				<span class="mt-0.5 shrink-0 rounded px-1.5 py-0.5 font-medium {typeColors[sc.type] ?? 'bg-gray-100 text-gray-600'}">
					{typeLabels[sc.type] ?? sc.type}
				</span>
				<div class="min-w-0">
					<p class="text-gray-700 break-words">{sc.sentence}</p>
					<p class="mt-0.5 text-neutral">{sc.explanation}</p>
				</div>
			</div>
		{/each}

		<p class="text-xs italic text-neutral">
			Let op: feiten, prognoses en beleidsalternatieven mogen NIET gelakt worden onder art. 5.2.
		</p>
	</div>
{/if}
