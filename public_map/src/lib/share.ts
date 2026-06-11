// D.5.29 / ADR-0033 — short-link hashing for shareable view URLs.
//
// Pure helpers shared by the `/api/share` Pages Function (which writes the
// param string to KV under the hash) and the `/s/[hash]` resolver. Kept free
// of Cloudflare and DOM globals so the logic is unit-testable under vitest and
// identical on both ends of the contract.
//
// The hash is a deterministic base32 truncation of SHA-256(paramString): the
// same view always produces the same short link, so re-sharing an identical
// view is idempotent in KV (one key, refreshed TTL) rather than minting a new
// hash every time.

/** KV entry lifetime: 90 days (matches ADR-0033 / invariant #28). */
export const SHARE_KV_TTL_SECONDS = 7_776_000;

/** Short-hash length. 7 base32 chars ≈ 35 bits ≈ 34 billion values. */
export const SHARE_HASH_LENGTH = 7;

/** Crockford-free RFC 4648 base32 lower-cased, minus padding. URL-safe. */
const BASE32_ALPHABET = 'abcdefghijklmnopqrstuvwxyz234567';

/** Max param-string length we'll stash. Guards KV (25 MiB cap) and abuse. */
export const SHARE_PARAMS_MAX_LENGTH = 4_096;

/**
 * Encode bytes as lower-case base32 (no padding), returning at most `length`
 * characters. Used to turn a SHA-256 digest into a compact URL token.
 */
export function base32Encode(bytes: Uint8Array, length = SHARE_HASH_LENGTH): string {
	let bits = 0;
	let value = 0;
	let out = '';
	for (let i = 0; i < bytes.length && out.length < length; i++) {
		value = (value << 8) | bytes[i];
		bits += 8;
		while (bits >= 5 && out.length < length) {
			out += BASE32_ALPHABET[(value >>> (bits - 5)) & 31];
			bits -= 5;
		}
	}
	// Flush remaining bits (only matters for very short inputs).
	if (bits > 0 && out.length < length) {
		out += BASE32_ALPHABET[(value << (5 - bits)) & 31];
	}
	return out;
}

/**
 * Deterministic short hash for a canonical param string. Uses Web Crypto
 * (`crypto.subtle`), available in Workers, modern browsers, and Node ≥ 20.
 */
export async function shareHash(
	paramString: string,
	cryptoImpl: Crypto | undefined = globalThis.crypto
): Promise<string> {
	if (!cryptoImpl?.subtle) {
		throw new Error('Web Crypto unavailable; cannot hash share params');
	}
	const data = new TextEncoder().encode(paramString);
	const digest = await cryptoImpl.subtle.digest('SHA-256', data);
	return base32Encode(new Uint8Array(digest), SHARE_HASH_LENGTH);
}

/** A hash is well-formed iff it's the right length and all base32 chars. */
export function isValidShareHash(hash: unknown): hash is string {
	return (
		typeof hash === 'string' &&
		hash.length === SHARE_HASH_LENGTH &&
		[...hash].every((c) => BASE32_ALPHABET.includes(c))
	);
}

/** A param string is shareable iff non-empty and within the size cap. */
export function isShareableParams(params: unknown): params is string {
	return typeof params === 'string' && params.length > 0 && params.length <= SHARE_PARAMS_MAX_LENGTH;
}
