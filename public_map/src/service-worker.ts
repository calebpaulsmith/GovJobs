/// <reference types="@sveltejs/kit" />
/// <reference lib="webworker" />

// FedFinder service worker — makes the map installable (PWA) and usable
// offline after a first visit. Strategy:
//   • Precache the app shell (hashed build assets + prerendered HTML + small
//     static files). The data bundle under /data/ is intentionally NOT
//     precached — it's tens of MB; we cache it on demand instead.
//   • Navigations: network-first, falling back to a cached shell offline (the
//     app is a client-rendered SPA, so any shell boots it).
//   • Hashed build assets: cache-first (immutable, content-hashed names).
//   • /data/ bundle: network-first so fresh postings win, cache as fallback.
//   • Cross-origin (Mapbox tiles, the job-history API): left untouched.

import { build, files, prerendered, version } from '$service-worker';

const sw = self as unknown as ServiceWorkerGlobalScope;
const CACHE = `fedfinder-${version}`;

// App shell: everything except the heavy data bundle.
const SHELL = [...build, ...prerendered, ...files.filter((f) => !f.startsWith('/data/'))];

sw.addEventListener('install', (event) => {
	event.waitUntil(
		caches
			.open(CACHE)
			.then((cache) => cache.addAll(SHELL))
			.then(() => sw.skipWaiting())
	);
});

sw.addEventListener('activate', (event) => {
	event.waitUntil(
		(async () => {
			for (const key of await caches.keys()) {
				if (key !== CACHE) await caches.delete(key);
			}
			await sw.clients.claim();
		})()
	);
});

sw.addEventListener('fetch', (event) => {
	const req = event.request;
	if (req.method !== 'GET') return;

	const url = new URL(req.url);
	if (url.origin !== sw.location.origin) return; // Mapbox / API / fonts: leave alone.

	if (req.mode === 'navigate') {
		event.respondWith(navigateThenShell(req));
		return;
	}
	if (build.includes(url.pathname)) {
		event.respondWith(cacheFirst(req));
		return;
	}
	if (url.pathname.startsWith('/data/')) {
		event.respondWith(networkFirst(req));
		return;
	}
	event.respondWith(cacheFirst(req)); // icons, manifest, favicon, og-image…
});

async function navigateThenShell(req: Request): Promise<Response> {
	try {
		return await fetch(req);
	} catch {
		const cache = await caches.open(CACHE);
		return (
			(await cache.match(new URL(req.url).pathname)) ??
			(await cache.match('/browse')) ??
			(await cache.match('/')) ??
			Response.error()
		);
	}
}

async function cacheFirst(req: Request): Promise<Response> {
	const cached = await caches.match(req);
	if (cached) return cached;
	const res = await fetch(req);
	if (res.ok) (await caches.open(CACHE)).put(req, res.clone());
	return res;
}

async function networkFirst(req: Request): Promise<Response> {
	try {
		const res = await fetch(req);
		if (res.ok) (await caches.open(CACHE)).put(req, res.clone());
		return res;
	} catch (err) {
		const cached = await caches.match(req);
		if (cached) return cached;
		throw err;
	}
}
