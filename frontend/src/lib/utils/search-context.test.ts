import { describe, it, expect } from 'vitest';
import { highlightedContext } from './search-context';

describe('highlightedContext', () => {
	it('splits context around an exact-case match', () => {
		expect(highlightedContext('de heer Jan de Vries woont', 'Jan')).toEqual({
			before: 'de heer ',
			match: 'Jan',
			after: ' de Vries woont'
		});
	});

	it('matches case-insensitively but preserves original casing', () => {
		expect(highlightedContext('...Voornaam ACHTERNAAM bij...', 'achternaam')).toEqual({
			before: '...Voornaam ',
			match: 'ACHTERNAAM',
			after: ' bij...'
		});
	});

	it('returns the whole context as `before` when the match is missing', () => {
		expect(highlightedContext('nothing to see here', 'missing')).toEqual({
			before: 'nothing to see here',
			match: '',
			after: ''
		});
	});

	it('handles a match at the very start', () => {
		expect(highlightedContext('Amsterdam ligt in Noord-Holland', 'Amsterdam')).toEqual({
			before: '',
			match: 'Amsterdam',
			after: ' ligt in Noord-Holland'
		});
	});

	it('handles a match at the very end', () => {
		expect(highlightedContext('woonplaats: Utrecht', 'Utrecht')).toEqual({
			before: 'woonplaats: ',
			match: 'Utrecht',
			after: ''
		});
	});
});
