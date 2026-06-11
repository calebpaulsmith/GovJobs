// D.5.29 / ADR-0033 — short-link resolver.
//
//   GET /s/<hash>
//   → 302 redirect to /browse?<params>  (KV hit)
//   → 200 friendly "link expired" page   (KV miss / bad hash / no binding)
//
// Never 404s (invariant #28): a missing or expired hash renders a small page
// that links to the unfiltered /browse, rather than a hard error. The selected
// job possibly having closed is handled downstream on /browse (a banner), not
// here — we only resolve the param string.
//
// Binding: same `fedfinder_share` KV namespace as /api/share.

import { isValidShareHash } from '../../src/lib/share';

interface KVNamespace {
	get(key: string): Promise<string | null>;
}

interface PagesContext {
	request: Request;
	params: { hash?: string | string[] };
	env?: { fedfinder_share?: KVNamespace };
}

function expiredPage(origin: string): Response {
	const browse = `${origin}/browse`;
	const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Share link expired · The Grand Pipeline map</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #06111f; color: #e5edf5;
         font: 15px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
  .card { max-width: 30rem; padding: 2rem 1.5rem; text-align: center; }
  h1 { font-size: 18px; margin: 0 0 0.75rem; }
  p { color: #94a3b8; margin: 0 0 1.25rem; }
  a.btn { display: inline-block; padding: 0.6rem 1.1rem; border-radius: 8px;
          background: #7bd0f2; color: #06111f; text-decoration: none; font-weight: 600; }
</style>
</head>
<body>
  <div class="card">
    <h1>This share link has expired</h1>
    <p>Shared map views are kept for 90 days. This one is no longer available, but you can start a fresh search.</p>
    <a class="btn" href="${browse}">Open the map</a>
  </div>
</body>
</html>`;
	return new Response(html, {
		// 200, not 404 — this is a friendly fallback, not an error.
		status: 200,
		headers: { 'content-type': 'text/html; charset=utf-8' }
	});
}

export async function onRequestGet(context: PagesContext): Promise<Response> {
	const origin = new URL(context.request.url).origin;
	const raw = context.params?.hash;
	const hash = Array.isArray(raw) ? raw[0] : raw;

	if (!isValidShareHash(hash)) return expiredPage(origin);

	const kv = context.env?.fedfinder_share;
	if (!kv) return expiredPage(origin);

	let params: string | null = null;
	try {
		params = await kv.get(hash);
	} catch {
		params = null;
	}
	if (!params) return expiredPage(origin);

	const target = `${origin}/browse?${params}`;
	return new Response(null, { status: 302, headers: { location: target } });
}
