// Locality rollup math for the D.5.27 Localities screen (per ADR-0032).
// Pure + unit-tested so the screen component stays a thin renderer. The
// centerpiece is a sortable table with one row per locality; the headline is
// the posting count under the current filters (a count, so it works for every
// pay plan — NOT a GS-anchored metric). Geography is the *variable* on this
// screen, so geography/radius chips are dropped from the filter set here.
import type { JobDetails, FeatureCollection } from './data';
import type { JobFilters } from './filters';
import { matchesJobFeature } from './filters';
import { localityPrimaryState, type StateRpp } from './compensation';

// GS-family pay plans (per CLAUDE.md invariant #10) — used only to report GS
// coverage honestly ("~70% of federal postings are GS"), never to anchor the
// headline pay metric.
const GS_FAMILY = new Set(['GS', 'GM', 'GL', 'GP', 'GR']);

export interface LocalityMeta {
	code: string;
	name: string;
	rppOverall: number | null;
	rppApproximate: boolean;
	gs13Step1: number | null;
	adjustmentPct: number | null;
}

export interface PayPlanShare {
	plan: string;
	count: number;
	pct: number; // 0..100, rounded
}

export interface LocalityRollupRow {
	code: string;
	name: string;
	postings: number;
	salaryMin: number | null;
	salaryMax: number | null;
	payPlanMix: PayPlanShare[]; // top plans + an "other" bucket, desc by count
	gsCount: number;
	gsCoveragePct: number; // gsCount / postings * 100, rounded
	rppOverall: number | null;
	rppApproximate: boolean; // true when falling back to the primary state's RPP
	rppState: string | null; // the state whose RPP was used on fallback
}

export type SortKey = 'name' | 'postings' | 'pay' | 'rpp';
export type SortDir = 'asc' | 'desc';

// Parse localities.geojson into a code → meta map. Defensive about missing
// properties; an unknown code still yields a usable (sparse) meta row.
export function localityMetaFromGeoJson(fc: FeatureCollection | null | undefined): Map<string, LocalityMeta> {
	const map = new Map<string, LocalityMeta>();
	for (const f of fc?.features ?? []) {
		const p = (f.properties ?? {}) as Record<string, unknown>;
		const code = String(p.code ?? '').toUpperCase();
		if (!code) continue;
		map.set(code, {
			code,
			name: String(p.name ?? code),
			rppOverall: p.rpp_overall == null ? null : Number(p.rpp_overall),
			rppApproximate: Boolean(p.rpp_overall_approximate),
			gs13Step1: p.gs13_step1_locality == null ? null : Number(p.gs13_step1_locality),
			adjustmentPct: p.adjustment_pct == null ? null : Number(p.adjustment_pct)
		});
	}
	return map;
}

// One matched posting within a locality (deduped by posting id). Pay fields are
// pulled from jobs.geojson feature properties (which carry locality_code), with
// jobs_detail as a backstop — jobs_detail.json itself has no locality_code.
interface PostingRec {
	payPlan: string;
	salaryMin: number | null;
	salaryMax: number | null;
}

function payPlanMix(recs: PostingRec[]): { mix: PayPlanShare[]; gsCount: number } {
	const counts = new Map<string, number>();
	let gsCount = 0;
	for (const r of recs) {
		const plan = r.payPlan || 'Other';
		counts.set(plan, (counts.get(plan) ?? 0) + 1);
		if (GS_FAMILY.has(plan)) gsCount += 1;
	}
	const total = recs.length || 1;
	const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
	// Keep the top 3 named plans; fold the rest into one "other" bucket so the
	// inline breakdown stays short (e.g. "GS 65% · WG 20% · other 15%").
	const TOP = 3;
	const top = sorted.slice(0, TOP);
	const rest = sorted.slice(TOP);
	const mix: PayPlanShare[] = top.map(([plan, count]) => ({
		plan,
		count,
		pct: Math.round((count / total) * 100)
	}));
	if (rest.length > 0) {
		const restCount = rest.reduce((s, [, c]) => s + c, 0);
		mix.push({ plan: 'other', count: restCount, pct: Math.round((restCount / total) * 100) });
	}
	return { mix, gsCount };
}

// Resolve the cost-of-living (BEA RPP) figure for a locality: prefer the
// locality's own RPP; fall back to its primary state's RPP, flagged
// approximate (per ADR-0032 §6 / D.5.10 honesty rule).
function resolveRpp(
	meta: LocalityMeta,
	stateRpp: Record<string, StateRpp>
): { rppOverall: number | null; rppApproximate: boolean; rppState: string | null } {
	if (meta.rppOverall != null) {
		return { rppOverall: meta.rppOverall, rppApproximate: meta.rppApproximate, rppState: null };
	}
	const state = localityPrimaryState(meta.code, meta.name);
	const sr = state ? stateRpp[state] : undefined;
	if (sr && sr.rpp_overall != null) {
		return { rppOverall: sr.rpp_overall, rppApproximate: true, rppState: state };
	}
	return { rppOverall: null, rppApproximate: false, rppState: null };
}

export interface RollupOptions {
	stateRpp?: Record<string, StateRpp>;
}

function numOrNull(v: unknown): number | null {
	if (v == null) return null;
	const n = Number(v);
	return Number.isFinite(n) ? n : null;
}

// Build the locality rollup. Source is jobs.geojson FEATURES (which carry
// locality_code, pay_plan, and salary on their properties — jobs_detail.json
// does NOT carry locality_code), filtered by the current NON-geographic filters
// via matchesJobFeature (geography/radius chips dropped — geography is the
// variable here). A posting with several duty stations appears as several
// features; it is deduped per locality by posting id, so it counts once in each
// locality where it has a duty station. Localities with no matching postings are
// omitted. `details` backs the keyword filter and is a pay backstop.
export function computeLocalityRollup(
	jobs: FeatureCollection | null | undefined,
	details: Record<string, JobDetails> | null | undefined,
	meta: Map<string, LocalityMeta>,
	filters: JobFilters,
	opts: RollupOptions = {}
): LocalityRollupRow[] {
	if (!jobs) return [];
	const detailIndex = details ?? {};
	const nonGeo: JobFilters = { ...filters, geographies: [], radii: [] };
	// locality_code → (posting id → PostingRec), deduping multi-feature postings.
	const groups = new Map<string, Map<string, PostingRec>>();
	for (const f of jobs.features) {
		if (!matchesJobFeature(f, nonGeo, detailIndex)) continue;
		const props = (f.properties ?? {}) as Record<string, unknown>;
		const code = String(props.locality_code ?? '').toUpperCase().trim();
		if (!code) continue; // a duty station with no locality can't roll up
		const id = String(props.id ?? '');
		if (!id) continue;
		let g = groups.get(code);
		if (!g) {
			g = new Map();
			groups.set(code, g);
		}
		if (g.has(id)) continue;
		const detail = detailIndex[id];
		g.set(id, {
			payPlan: String(props.pay_plan ?? detail?.pay_plan ?? '').toUpperCase().trim() || 'Other',
			salaryMin: numOrNull(props.salary_min ?? detail?.salary_min),
			salaryMax: numOrNull(props.salary_max ?? detail?.salary_max)
		});
	}
	const stateRpp = opts.stateRpp ?? {};
	const rows: LocalityRollupRow[] = [];
	for (const [code, recMap] of groups) {
		const recs = [...recMap.values()];
		const m = meta.get(code) ?? {
			code,
			name: code,
			rppOverall: null,
			rppApproximate: false,
			gs13Step1: null,
			adjustmentPct: null
		};
		let salaryMin: number | null = null;
		let salaryMax: number | null = null;
		for (const r of recs) {
			if (r.salaryMin != null && (salaryMin == null || r.salaryMin < salaryMin)) salaryMin = r.salaryMin;
			if (r.salaryMax != null && (salaryMax == null || r.salaryMax > salaryMax)) salaryMax = r.salaryMax;
		}
		const { mix, gsCount } = payPlanMix(recs);
		const rpp = resolveRpp(m, stateRpp);
		rows.push({
			code,
			name: m.name,
			postings: recs.length,
			salaryMin,
			salaryMax,
			payPlanMix: mix,
			gsCount,
			gsCoveragePct: Math.round((gsCount / recs.length) * 100),
			rppOverall: rpp.rppOverall,
			rppApproximate: rpp.rppApproximate,
			rppState: rpp.rppState
		});
	}
	return rows;
}

// Sort a rollup in place-safe fashion (returns a new array). Posting-count
// descending is the default per ADR-0032 §2. Nulls sort last regardless of dir.
export function sortRollup(rows: LocalityRollupRow[], key: SortKey, dir: SortDir): LocalityRollupRow[] {
	const sign = dir === 'asc' ? 1 : -1;
	const val = (r: LocalityRollupRow): number | string | null => {
		switch (key) {
			case 'name':
				return r.name.toLowerCase();
			case 'postings':
				return r.postings;
			case 'pay':
				return r.salaryMax ?? r.salaryMin; // rank by top of range
			case 'rpp':
				return r.rppOverall;
		}
	};
	return [...rows].sort((a, b) => {
		const va = val(a);
		const vb = val(b);
		// Nulls always last.
		if (va == null && vb == null) return 0;
		if (va == null) return 1;
		if (vb == null) return -1;
		if (typeof va === 'string' && typeof vb === 'string') return sign * va.localeCompare(vb);
		return sign * ((va as number) - (vb as number));
	});
}

// Total postings across the rollup (for the "Show N jobs in M localities" CTA
// when all rows are implicitly in scope) and for the screen's summary line.
export function rollupTotals(rows: LocalityRollupRow[]): { postings: number; localities: number } {
	return { postings: rows.reduce((s, r) => s + r.postings, 0), localities: rows.length };
}

// Format a pay-plan mix as an inline string, e.g. "GS 65% · WG 20% · other 15%".
export function formatPayPlanMix(mix: PayPlanShare[]): string {
	return mix.map((s) => `${s.plan} ${s.pct}%`).join(' · ');
}
