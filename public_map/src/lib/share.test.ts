import { describe, it, expect } from 'vitest';
import {
	base32Encode,
	shareHash,
	isValidShareHash,
	isShareableParams,
	SHARE_HASH_LENGTH,
	SHARE_PARAMS_MAX_LENGTH
} from './share';

describe('base32Encode', () => {
	it('emits only lower-case base32 chars and respects the length cap', () => {
		const bytes = new Uint8Array([0xff, 0x00, 0xa5, 0x5a, 0x12, 0x34]);
		const out = base32Encode(bytes, 7);
		expect(out).toHaveLength(7);
		expect(out).toMatch(/^[a-z2-7]{7}$/);
	});
	it('is deterministic for identical input', () => {
		const bytes = new Uint8Array([1, 2, 3, 4, 5]);
		expect(base32Encode(bytes, 7)).toBe(base32Encode(bytes, 7));
	});
});

describe('shareHash', () => {
	it('produces a 7-char base32 hash', async () => {
		const h = await shareHash('q=analyst&center=-87.6,41.8&zoom=10');
		expect(h).toHaveLength(SHARE_HASH_LENGTH);
		expect(isValidShareHash(h)).toBe(true);
	});
	it('is deterministic — the same view yields the same hash', async () => {
		const params = 'agency=HSCB&metric=workforce';
		expect(await shareHash(params)).toBe(await shareHash(params));
	});
	it('differs for different views', async () => {
		expect(await shareHash('a=1')).not.toBe(await shareHash('a=2'));
	});
});

describe('isValidShareHash', () => {
	it('accepts a well-formed hash', () => {
		expect(isValidShareHash('abc2345')).toBe(true);
	});
	it('rejects wrong length, bad chars, and non-strings', () => {
		expect(isValidShareHash('abc234')).toBe(false); // too short
		expect(isValidShareHash('abc23456')).toBe(false); // too long
		expect(isValidShareHash('abc2341')).toBe(false); // '1' not in base32
		expect(isValidShareHash('ABC2345')).toBe(false); // upper-case
		expect(isValidShareHash(null)).toBe(false);
		expect(isValidShareHash(42)).toBe(false);
	});
});

describe('isShareableParams', () => {
	it('accepts a non-empty in-bounds string', () => {
		expect(isShareableParams('q=x')).toBe(true);
	});
	it('rejects empty, oversized, and non-strings', () => {
		expect(isShareableParams('')).toBe(false);
		expect(isShareableParams('x'.repeat(SHARE_PARAMS_MAX_LENGTH + 1))).toBe(false);
		expect(isShareableParams(undefined)).toBe(false);
		expect(isShareableParams({})).toBe(false);
	});
});
