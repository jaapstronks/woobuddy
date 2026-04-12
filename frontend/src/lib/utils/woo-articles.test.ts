import { describe, it, expect } from 'vitest';
import {
	WOO_ARTICLES,
	getArticleLabel,
	isAbsoluteGround,
	isRelativeGround
} from './woo-articles';
import type { WooArticleCode } from '$lib/types';

describe('WOO_ARTICLES', () => {
	it('contains all 12 article codes', () => {
		const codes: WooArticleCode[] = [
			'5.1.1c',
			'5.1.1d',
			'5.1.1e',
			'5.1.2a',
			'5.1.2c',
			'5.1.2d',
			'5.1.2e',
			'5.1.2f',
			'5.1.2h',
			'5.1.2i',
			'5.2',
			'5.1.5'
		];
		for (const code of codes) {
			expect(WOO_ARTICLES[code]).toBeDefined();
			expect(WOO_ARTICLES[code].code).toBe(code);
		}
	});

	it('each article has code, ground, description, type, and tier', () => {
		for (const article of Object.values(WOO_ARTICLES)) {
			expect(article.code).toBeTruthy();
			expect(article.ground).toBeTruthy();
			expect(article.description).toBeTruthy();
			expect(['absolute', 'relative', 'special', 'residual']).toContain(article.type);
			expect(['1', '2', '3']).toContain(article.tier);
		}
	});
});

describe('getArticleLabel', () => {
	it('returns formatted label for each article', () => {
		expect(getArticleLabel('5.1.1e')).toBe('Art. 5.1.1e — Identificatienummers');
		expect(getArticleLabel('5.1.2e')).toBe('Art. 5.1.2e — Persoonlijke levenssfeer');
		expect(getArticleLabel('5.2')).toBe('Art. 5.2 — Persoonlijke beleidsopvattingen');
	});
});

describe('isAbsoluteGround', () => {
	it('returns true for absolute grounds', () => {
		expect(isAbsoluteGround('5.1.1c')).toBe(true);
		expect(isAbsoluteGround('5.1.1d')).toBe(true);
		expect(isAbsoluteGround('5.1.1e')).toBe(true);
	});

	it('returns false for relative grounds', () => {
		expect(isAbsoluteGround('5.1.2a')).toBe(false);
		expect(isAbsoluteGround('5.1.2e')).toBe(false);
		expect(isAbsoluteGround('5.1.2f')).toBe(false);
	});

	it('returns false for special and residual grounds', () => {
		expect(isAbsoluteGround('5.2')).toBe(false);
		expect(isAbsoluteGround('5.1.5')).toBe(false);
	});
});

describe('isRelativeGround', () => {
	it('returns true for relative grounds', () => {
		expect(isRelativeGround('5.1.2a')).toBe(true);
		expect(isRelativeGround('5.1.2c')).toBe(true);
		expect(isRelativeGround('5.1.2d')).toBe(true);
		expect(isRelativeGround('5.1.2e')).toBe(true);
		expect(isRelativeGround('5.1.2f')).toBe(true);
		expect(isRelativeGround('5.1.2h')).toBe(true);
		expect(isRelativeGround('5.1.2i')).toBe(true);
	});

	it('returns false for absolute grounds', () => {
		expect(isRelativeGround('5.1.1c')).toBe(false);
		expect(isRelativeGround('5.1.1d')).toBe(false);
		expect(isRelativeGround('5.1.1e')).toBe(false);
	});

	it('returns false for special and residual grounds', () => {
		expect(isRelativeGround('5.2')).toBe(false);
		expect(isRelativeGround('5.1.5')).toBe(false);
	});
});

describe('tier assignments', () => {
	it('Tier 1 articles are absolute identification grounds', () => {
		const tier1Articles = Object.values(WOO_ARTICLES).filter((a) => a.tier === '1');
		expect(tier1Articles.length).toBeGreaterThan(0);
		for (const article of tier1Articles) {
			expect(article.type).toBe('absolute');
		}
	});

	it('5.1.2e (persoonlijke levenssfeer) is Tier 2', () => {
		expect(WOO_ARTICLES['5.1.2e'].tier).toBe('2');
	});

	it('5.2 (persoonlijke beleidsopvattingen) is Tier 3', () => {
		expect(WOO_ARTICLES['5.2'].tier).toBe('3');
	});

	it('residual ground 5.1.5 is Tier 3', () => {
		expect(WOO_ARTICLES['5.1.5'].tier).toBe('3');
		expect(WOO_ARTICLES['5.1.5'].type).toBe('residual');
	});
});
