import { describe, it, expect } from 'vitest';
import { TIERS, confidenceToLevel } from './tiers';

describe('TIERS', () => {
	it('defines all three tiers', () => {
		expect(TIERS['1']).toBeDefined();
		expect(TIERS['2']).toBeDefined();
		expect(TIERS['3']).toBeDefined();
	});

	it('Tier 1 is hard identifiers (auto-redacted)', () => {
		expect(TIERS['1'].label).toBe('Harde identifiers');
		expect(TIERS['1'].defaultState).toContain('Automatisch');
	});

	it('Tier 2 is contextual personal data (user decision)', () => {
		expect(TIERS['2'].label).toContain('Contextafhankelijk');
		expect(TIERS['2'].userAction).toContain('Bevestigen');
	});

	it('Tier 3 is content judgment (human review)', () => {
		expect(TIERS['3'].label).toContain('Inhoudelijke');
		expect(TIERS['3'].userAction).toContain('Beoordelen');
	});

	it('each tier has required fields', () => {
		for (const tier of Object.values(TIERS)) {
			expect(tier.label).toBeTruthy();
			expect(tier.description).toBeTruthy();
			expect(tier.defaultState).toBeTruthy();
			expect(tier.userAction).toBeTruthy();
			expect(tier.color).toBeTruthy();
		}
	});
});

describe('confidenceToLevel', () => {
	it('returns "high" for confidence >= 0.85', () => {
		expect(confidenceToLevel(0.85)).toBe('high');
		expect(confidenceToLevel(0.90)).toBe('high');
		expect(confidenceToLevel(0.95)).toBe('high');
		expect(confidenceToLevel(1.0)).toBe('high');
	});

	it('returns "medium" for confidence >= 0.6 and < 0.85', () => {
		expect(confidenceToLevel(0.6)).toBe('medium');
		expect(confidenceToLevel(0.7)).toBe('medium');
		expect(confidenceToLevel(0.84)).toBe('medium');
	});

	it('returns "low" for confidence < 0.6', () => {
		expect(confidenceToLevel(0.59)).toBe('low');
		expect(confidenceToLevel(0.5)).toBe('low');
		expect(confidenceToLevel(0.1)).toBe('low');
		expect(confidenceToLevel(0.0)).toBe('low');
	});

	it('handles boundary values exactly', () => {
		// 0.85 is the threshold for high — should be high
		expect(confidenceToLevel(0.85)).toBe('high');
		// 0.6 is the threshold for medium — should be medium
		expect(confidenceToLevel(0.6)).toBe('medium');
		// Just below thresholds
		expect(confidenceToLevel(0.8499)).toBe('medium');
		expect(confidenceToLevel(0.5999)).toBe('low');
	});
});
