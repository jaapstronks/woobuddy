import { describe, it, expect, vi } from 'vitest';

vi.mock('$env/static/public', () => ({ PUBLIC_API_URL: 'http://test.invalid' }));

import { messageFromErrorBody } from './client';

describe('messageFromErrorBody (#68)', () => {
	it('uses the Dutch FastAPI detail when present', () => {
		expect(
			messageFromErrorBody(502, '{"detail":"Kon het verzenden niet voltooien. Probeer het later opnieuw."}')
		).toBe('Kon het verzenden niet voltooien. Probeer het later opnieuw.');
		expect(messageFromErrorBody(400, '{"detail":"Ongeldig e-mailadres."}')).toBe('Ongeldig e-mailadres.');
	});

	it('never shows a raw body for 500/502/503', () => {
		const cases: Array<[number, string]> = [
			[500, '{"detail":"Internal Server Error"}'],
			[500, ''],
			[502, '<html><body><h1>502 Bad Gateway</h1></body></html>'],
			[503, '<html>Service Unavailable</html>'],
			[503, 'upstream connect error']
		];
		for (const [status, body] of cases) {
			const msg = messageFromErrorBody(status, body);
			expect(msg).not.toContain('<');
			expect(msg).not.toContain('{');
			expect(msg).not.toMatch(/Internal Server Error|Bad Gateway|Service Unavailable|upstream/);
			expect(msg).toMatch(/opnieuw/);
		}
	});

	it('falls back to Dutch copy for a 422 validation array', () => {
		const msg = messageFromErrorBody(422, '{"detail":[{"loc":["body","email"],"msg":"value is not a valid email"}]}');
		expect(msg).not.toContain('valid email');
		expect(msg).toMatch(/gegevens/);
	});
});
