// Unit tests for the share Pages Functions with a mocked KV namespace. The
// Function files live under functions/ (Cloudflare Pages), but their handlers
// are plain async functions, so we import and drive them directly here.
import { describe, it, expect } from 'vitest';
import { onRequestPost } from '../../functions/api/share';
import { onRequestGet } from '../../functions/s/[hash]';
import { shareHash } from './share';

function fakeKV() {
	const store = new Map<string, string>();
	return {
		store,
		get: async (k: string) => store.get(k) ?? null,
		put: async (k: string, v: string) => void store.set(k, v)
	};
}

function postReq(body: unknown): Request {
	return new Request('https://map.test/api/share', {
		method: 'POST',
		body: typeof body === 'string' ? body : JSON.stringify(body)
	});
}

describe('POST /api/share', () => {
	it('stores the params under a deterministic hash and returns the short URL', async () => {
		const kv = fakeKV();
		const params = 'q=analyst&center=-87.6,41.8&zoom=10';
		const res = await onRequestPost({ request: postReq({ params }), env: { fedfinder_share: kv } });
		expect(res.status).toBe(200);
		const body = (await res.json()) as { hash: string; url: string; path: string };
		const expectedHash = await shareHash(params);
		expect(body.hash).toBe(expectedHash);
		expect(body.path).toBe(`/s/${expectedHash}`);
		expect(body.url).toBe(`https://map.test/s/${expectedHash}`);
		expect(kv.store.get(expectedHash)).toBe(params);
	});

	it('is idempotent — the same view reuses the same key', async () => {
		const kv = fakeKV();
		const params = 'agency=HSCB';
		const a = await (await onRequestPost({ request: postReq({ params }), env: { fedfinder_share: kv } })).json();
		const b = await (await onRequestPost({ request: postReq({ params }), env: { fedfinder_share: kv } })).json();
		expect((a as { hash: string }).hash).toBe((b as { hash: string }).hash);
		expect(kv.store.size).toBe(1);
	});

	it('returns 503 when no KV binding is present (client falls back to long URL)', async () => {
		const res = await onRequestPost({ request: postReq({ params: 'q=x' }), env: {} });
		expect(res.status).toBe(503);
	});

	it('rejects empty params with 400', async () => {
		const kv = fakeKV();
		const res = await onRequestPost({ request: postReq({ params: '' }), env: { fedfinder_share: kv } });
		expect(res.status).toBe(400);
	});

	it('rejects invalid JSON with 400', async () => {
		const kv = fakeKV();
		const res = await onRequestPost({ request: postReq('{not json'), env: { fedfinder_share: kv } });
		expect(res.status).toBe(400);
	});
});

describe('GET /s/[hash]', () => {
	it('302-redirects to /browse?<params> on a KV hit', async () => {
		const kv = fakeKV();
		const params = 'q=nurse&metric=workforce';
		const hash = await shareHash(params);
		kv.store.set(hash, params);
		const res = await onRequestGet({
			request: new Request(`https://map.test/s/${hash}`),
			params: { hash },
			env: { fedfinder_share: kv }
		});
		expect(res.status).toBe(302);
		expect(res.headers.get('location')).toBe(`https://map.test/browse?${params}`);
	});

	it('renders the friendly expired page on a KV miss (never 404)', async () => {
		const kv = fakeKV();
		const hash = 'abc2345';
		const res = await onRequestGet({
			request: new Request(`https://map.test/s/${hash}`),
			params: { hash },
			env: { fedfinder_share: kv }
		});
		expect(res.status).toBe(200);
		expect(res.headers.get('content-type')).toContain('text/html');
		expect(await res.text()).toContain('expired');
	});

	it('renders the friendly page for a malformed hash', async () => {
		const res = await onRequestGet({
			request: new Request('https://map.test/s/BAD!'),
			params: { hash: 'BAD!' },
			env: { fedfinder_share: fakeKV() }
		});
		expect(res.status).toBe(200);
		expect(await res.text()).toContain('expired');
	});

	it('renders the friendly page when no KV binding is present', async () => {
		const res = await onRequestGet({
			request: new Request('https://map.test/s/abc2345'),
			params: { hash: 'abc2345' },
			env: {}
		});
		expect(res.status).toBe(200);
	});
});
