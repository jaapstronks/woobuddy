export function formatDate(dateStr: string): string {
	return new Date(dateStr).toLocaleDateString('nl-NL', {
		day: 'numeric',
		month: 'short',
		year: 'numeric'
	});
}
