// D.5.29 / ADR-0033 — short-link minting endpoint.
//
//   POST /api/share   body: { "params": "<query string, no leading ?>" }
//   → 200 { hash, path: "/s/<hash>", url: "<origin>/s/<hash>" }
//
// The full view is encoded client-side (viewState.ts) into a query string; we
// stash that string in Workers KV under a deterministic 7-char base32 hash of
// it (so re-sharing an identical view reuses the same key and just refreshes
// the 90-day TTL). The resolver at /s/[hash] reads it back and 302s to
// /browse?<params>.
//
// Binding: the Cloudflare Pages project must bind the `fedfinder_share` KV
// namespace to the variable `fedfinder_share` (Settings → Functions → KV
// namespace bindings). When the binding is absent (e.g. a preview deploy
// without KV), we return 503 so the client falls back to the long URL — the
// clipboard copy must always succeed (invariant #28).
//
// Pure hashing/validation lives in ../../src/lib/share.ts so it is unit-tested
// and identical to what the resolver expects.

import {
	shareHash,
	isShareableParams,
	SHARE_KV_TTL_SECONDS,
	SHARE_PARAMS_MAX_LENGTH
} from '../../src/lib/share';

interface KVNamespace {
	get(key: string): Promise<string | null>;
	put(key: string, value: string, options?: { expirationTtl?: number }): Promise<void>;
}

interface PagesContext {
	request: Request;
	env?: { fedfinder_share?: KVNamespace };
}

const JSON_HEADERS = { 'content-type': 'application/json; charset=utf-8' } as const;

function json(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });
}

export async function onRequestPost(context: PagesContext): Promise<Response> {
	const kv = context.env?.fedfinder_share;
	if (!kv) {
		// No KV bound — tell the client to use the long URL.
		return json({ error: 'short_links_unavailable' }, 503);
	}

	let params: unknown;
	try {
		const body = (await context.request.json()) as { params?: unknown };
		params = body?.params;
	} catch {
		return json({ error: 'invalid_json' }, 400);
	}

	if (!isShareableParams(params)) {
		return json({ error: 'invalid_params', max: SHARE_PARAMS_MAX_LENGTH }, 400);
	}

	let hash: string;
	try {
		hash = await shareHash(params);
		await kv.put(hash, params, { expirationTtl: SHARE_KV_TTL_SECONDS });
	} catch {
		return json({ error: 'kv_write_failed' }, 502);
	}

	const origin = new URL(context.request.url).origin;
	return json({ hash, path: `/s/${hash}`, url: `${origin}/s/${hash}` });
}
