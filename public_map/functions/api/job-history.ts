// D.5.24 / ADR-0029 — On-demand Posting Intelligence proxy.
//
// Cloudflare Pages Function that proxies USAJOBS HistoricJoa for the public
// map's "Posting Intelligence" tab on JobCard. ADR-0029 contract:
//
//   GET /api/job-history?
//     position_id=…&agency_code=…&series=…&grade=…&state=…&window=…
//
// HistoricJoa is a public, key-less endpoint per CLAUDE.md, so we may call it
// directly from the edge. Long-text fields are stripped before the response
// crosses back so payload stays small. The Function is wrapped in a 24-hour
// edge cache keyed by the canonical query — first hit ≈ 1–3 s round-trip;
// every later hit globally is served from cache.
//
// Failure mode (network blip, HistoricJoa downtime, schema drift): the body
// becomes `{status: 'unavailable', retry_after: 3600, ...}` and the
// JobCard renders an explanatory message. We never fabricate history rows.
//
// The pure helpers (window→date range, query builder, record trimmer,
// monthly bucketing) live in `../../src/lib/jobHistory.ts` so the worker
// and the Svelte client share the same contract — see that file for the
// shape definitions referenced below.

import {
	bucketByMonth,
	buildHistoricJoaParams,
	cacheKey,
	normalizeWindow,
	postFilter,
	trimRecord,
	windowToDateRange,
	type HistoryPayload,
	type PostingHistoryQuery,
	type TrimmedRecord
} from '../../src/lib/jobHistory';

// `EventContext` ships with @cloudflare/workers-types in production. We
// declare a minimal shape so this file type-checks under the local SvelteKit
// tsconfig too — Pages will still load it as a Function at deploy time.
interface PagesContext {
	request: Request;
	waitUntil(promise: Promise<unknown>): void;
}

const HISTORICJOA_HOST = 'https://data.usajobs.gov';
const HISTORICJOA_PATH = '/api/historicjoa';

// USAJOBS requires the User-Agent to identify the developer (per their public
// API docs at https://developer.usajobs.gov/general-information/). The
// canonical form is the project owner's email so they can reach us if our
// traffic causes problems.
const UPSTREAM_USER_AGENT = 'thegrandpipeline-map (calebpaulsmith@gmail.com)';

// Hard upstream cap. HistoricJoa returns 500 records per page; 5 pages ≈
// 2,500 records is plenty for filtered slice timelines (the 10yr window for
// a busy agency is the worst case, and even then we surface the truncation
// flag in the response so the UI can warn the user).
const MAX_PAGES = 5;
const PAGE_SIZE_HINT = 500;
const RECORD_CAP = MAX_PAGES * PAGE_SIZE_HINT;
const EDGE_TTL_SECONDS = 24 * 60 * 60;
const UPSTREAM_TIMEOUT_MS = 20_000;

export async function onRequestGet(context: PagesContext): Promise<Response> {
	const url = new URL(context.request.url);
	const query: PostingHistoryQuery = {
		agencyCode: url.searchParams.get('agency_code') ?? undefined,
		series: url.searchParams.get('series') ?? undefined,
		grade: url.searchParams.get('grade') ?? undefined,
		state: url.searchParams.get('state') ?? undefined,
		controlNumber: url.searchParams.get('position_id') ?? undefined
	};
	const window = normalizeWindow(url.searchParams.get('window'));

	// Build a stable cache key URL so equivalent queries (different param
	// order, mixed case) collapse to the same edge cache entry.
	const canonical = `${url.origin}${url.pathname}?${cacheKey(query, window)}`;
	const cacheRequest = new Request(canonical, { method: 'GET' });

	const edgeCache = (globalThis as unknown as { caches?: { default: Cache } }).caches?.default;
	if (edgeCache) {
		const hit = await edgeCache.match(cacheRequest);
		if (hit) return hit;
	}

	const asOf = new Date();
	let payload: HistoryPayload;
	try {
		payload = await fetchHistoryPayload(query, window, asOf);
	} catch (err) {
		const message = err instanceof Error ? err.message : 'unknown error';
		const failure: HistoryPayload = {
			status: 'unavailable',
			window,
			as_of: asOf.toISOString(),
			...windowDateRange(window, asOf),
			total: 0,
			truncated: false,
			page_cap: MAX_PAGES,
			monthly: [],
			records: [],
			source: 'usajobs:historicjoa',
			retry_after: 3600,
			error: message
		};
		// Cache failures briefly so a HistoricJoa outage doesn't melt the
		// upstream when many users open the same JobCard. 5 minutes is the
		// retry-after the client honors; longer would mask recovery.
		const failureResponse = jsonResponse(failure, 300);
		if (edgeCache) {
			context.waitUntil(edgeCache.put(cacheRequest, failureResponse.clone()));
		}
		return failureResponse;
	}

	const response = jsonResponse(payload, EDGE_TTL_SECONDS);
	if (edgeCache) {
		context.waitUntil(edgeCache.put(cacheRequest, response.clone()));
	}
	return response;
}

async function fetchHistoryPayload(
	query: PostingHistoryQuery,
	window: ReturnType<typeof normalizeWindow>,
	asOf: Date
): Promise<HistoryPayload> {
	const baseParams = buildHistoricJoaParams(query, window, asOf);
	const trimmed: TrimmedRecord[] = [];
	let pages = 0;
	let nextParams: URLSearchParams | null = baseParams;
	while (nextParams && pages < MAX_PAGES) {
		const upstreamUrl = `${HISTORICJOA_HOST}${HISTORICJOA_PATH}?${nextParams.toString()}`;
		const upstream = await fetchWithTimeout(upstreamUrl, UPSTREAM_TIMEOUT_MS);
		if (!upstream.ok) {
			// Surface the upstream body in the error message so failures are
			// debuggable from the JobCard error pill / browser console without
			// shipping the full payload back to every visitor.
			const body = await upstream.text().catch(() => '');
			throw new Error(
				`HistoricJoa returned ${upstream.status}${body ? ': ' + body.slice(0, 200) : ''}`
			);
		}
		const json = (await upstream.json()) as Record<string, unknown>;
		const records = Array.isArray(json['data']) ? (json['data'] as unknown[]) : [];
		for (const raw of records) trimmed.push(trimRecord(raw));
		pages += 1;
		if (trimmed.length >= RECORD_CAP) break;
		nextParams = nextPageParams(json, nextParams);
	}

	const filtered = postFilter(trimmed, query);
	const monthly = bucketByMonth(filtered);
	return {
		status: 'ok',
		window,
		as_of: asOf.toISOString(),
		...windowDateRange(window, asOf),
		total: filtered.length,
		truncated: trimmed.length >= RECORD_CAP,
		page_cap: MAX_PAGES,
		monthly,
		records: filtered,
		source: 'usajobs:historicjoa'
	};
}

function nextPageParams(
	payload: Record<string, unknown>,
	currentParams: URLSearchParams
): URLSearchParams | null {
	const paging = (payload['paging'] ?? payload['Paging']) as
		| Record<string, unknown>
		| undefined;
	if (!paging) return null;
	const nextUrl = paging['next'];
	if (typeof nextUrl === 'string' && nextUrl) {
		try {
			const parsed = new URL(nextUrl);
			return parsed.searchParams;
		} catch {
			// fall through to the metadata token path
		}
	}
	const metadata = paging['metadata'] as Record<string, unknown> | undefined;
	const token =
		(metadata?.['continuationToken'] as string | undefined) ??
		(metadata?.['ContinuationToken'] as string | undefined);
	if (token) {
		const next = new URLSearchParams(currentParams);
		next.set('continuationtoken', token);
		return next;
	}
	return null;
}

async function fetchWithTimeout(url: string, ms: number): Promise<Response> {
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), ms);
	try {
		return await fetch(url, {
			method: 'GET',
			headers: {
				// Per USAJOBS docs the Host header pins the API surface and the
				// User-Agent must identify the developer. Without an email-style
				// User-Agent the API rejects the request.
				Host: 'data.usajobs.gov',
				Accept: 'application/hr+json',
				'User-Agent': UPSTREAM_USER_AGENT
			},
			signal: controller.signal
		});
	} finally {
		clearTimeout(timer);
	}
}

function jsonResponse(payload: HistoryPayload, ttlSeconds: number): Response {
	return new Response(JSON.stringify(payload), {
		status: 200,
		headers: {
			'Content-Type': 'application/json; charset=utf-8',
			'Cache-Control': `public, max-age=${ttlSeconds}, s-maxage=${ttlSeconds}`,
			'Access-Control-Allow-Origin': '*'
		}
	});
}

function windowDateRange(
	window: ReturnType<typeof normalizeWindow>,
	asOf: Date
): { start_date: string; end_date: string } {
	const range = windowToDateRange(window, asOf);
	return { start_date: range.start, end_date: range.end };
}
