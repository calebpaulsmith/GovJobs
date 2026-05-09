// D.5.17 — Personal compensation / cost-of-living comparator (per ADR-0028).
//
// Pure helpers, no Svelte deps. The comparator takes either:
//   (a) GS grade + step + OPM locality, or
//   (b) a custom annual wage in a given U.S. state,
// and returns the COL-adjusted equivalent in a target state, with source
// citations and approximation flags. RPP comes from cost_of_living.json
// (BEA Regional Price Parities, state-level). Locality RPP is not yet
// populated in the bundle, so locality comparisons fall back to the locality's
// primary state RPP and the result is flagged approximate.

import type { FeatureCollection, PayTables } from './data';

export type CompMode = 'gs' | 'custom';

export interface LocalityInfo {
	code: string;
	name: string;
	adjustment_pct: number;
	primary_state: string | null;
}

export interface StateRpp {
	rpp_overall: number | null;
	year: number | null;
	source: string;
}

export interface CompInputs {
	mode: CompMode;
	year: number;
	// GS mode
	grade?: string;
	step?: string;
	localityCode?: string;
	// Custom mode
	customAnnual?: number;
	customStateCode?: string;
	// Comparison
	targetStateCode?: string;
	// Data
	payTables: PayTables;
	localities: LocalityInfo[];
	stateRpp: Record<string, StateRpp>;
}

export interface CompBreakdown {
	method: 'gs' | 'custom';
	gs_base?: number;
	locality_adjustment_pct?: number;
	locality_code?: string;
	locality_name?: string;
}

export interface CompResult {
	annual_pay: number | null;
	breakdown: CompBreakdown;
	source_state: string | null;
	source_state_rpp: number | null;
	source_state_rpp_year: number | null;
	source_state_rpp_approximate: boolean;
	target_state: string | null;
	target_state_rpp: number | null;
	target_state_rpp_year: number | null;
	target_state_rpp_approximate: boolean;
	equivalent_pay: number | null;
	notes: string[];
	sources: string[];
}

const STATE_POSTAL = new Set([
	'AL','AK','AZ','AR','CA','CO','CT','DE','DC','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA',
	'ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR',
	'PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','PR','VI','GU','AS','MP'
]);

// OPM locality code → primary state postal. Two-letter codes (AK, HI) are the
// state itself. Multi-area codes like "CHI" or "DCB" are mapped by parsing
// the state-list suffix in the locality name (e.g. "Chicago-Naperville
// IL-IN-WI" → "IL"). Special-case codes that don't follow that pattern.
const LOCALITY_PRIMARY_STATE_OVERRIDES: Record<string, string> = {
	DCB: 'DC', // Washington-Baltimore-Arlington DC-MD-VA-WV-PA
	NYC: 'NY',
	BOS: 'MA',
	LOS: 'CA',
	SFO: 'CA',
	SAC: 'CA',
	SAN: 'CA',
	SDC: 'CA', // San Diego-Chula Vista-Carlsbad
	CHI: 'IL',
	PHI: 'PA',
	DAL: 'TX',
	HOU: 'TX',
	AUS: 'TX',
	DEN: 'CO',
	SEA: 'WA',
	POR: 'OR',
	PHX: 'AZ',
	ATL: 'GA',
	MIA: 'FL',
	ORL: 'FL',
	TPA: 'FL',
	DTW: 'MI',
	MSP: 'MN',
	STL: 'MO',
	KCY: 'MO',
	IND: 'IN',
	CIN: 'OH',
	CLE: 'OH',
	COL: 'OH',
	PIT: 'PA',
	NSH: 'TN',
	CHA: 'NC',
	RAL: 'NC',
	RIC: 'VA',
	LVG: 'NV',
	SLC: 'UT'
};

export function localityPrimaryState(code: string, name: string): string | null {
	if (STATE_POSTAL.has(code)) return code;
	const override = LOCALITY_PRIMARY_STATE_OVERRIDES[code];
	if (override) return override;
	// Fallback: parse first 2-letter postal token in the trailing state list.
	const match = name.match(/\b([A-Z]{2})(?:[-,]|\b)/g);
	if (match) {
		for (const tok of match) {
			const candidate = tok.replace(/[-,]/g, '').trim();
			if (STATE_POSTAL.has(candidate)) return candidate;
		}
	}
	return null;
}

export function localitiesFromGeoJson(fc: FeatureCollection | null | undefined): LocalityInfo[] {
	const features = fc?.features ?? [];
	const out: LocalityInfo[] = [];
	for (const f of features) {
		const p = f.properties ?? {};
		const code = String(p.code ?? '').trim();
		const name = String(p.name ?? '').trim();
		const adj = Number(p.adjustment_pct);
		if (!code || !name || !Number.isFinite(adj)) continue;
		out.push({
			code,
			name,
			adjustment_pct: adj,
			primary_state: localityPrimaryState(code, name)
		});
	}
	out.sort((a, b) => a.name.localeCompare(b.name));
	return out;
}

export function stateRppFromCol(
	col: { by_state?: Record<string, { rpp_overall?: number | null; year?: number | null; source?: string }> } | null | undefined
): Record<string, StateRpp> {
	const by = col?.by_state ?? {};
	const out: Record<string, StateRpp> = {};
	for (const [state, row] of Object.entries(by)) {
		out[state] = {
			rpp_overall:
				row && typeof row.rpp_overall === 'number' && Number.isFinite(row.rpp_overall)
					? row.rpp_overall
					: null,
			year: row && typeof row.year === 'number' ? row.year : null,
			source: (row && typeof row.source === 'string' && row.source) || 'bea:rpp'
		};
	}
	return out;
}

export function gsBasePay(
	payTables: PayTables,
	year: number,
	grade: string,
	step: string
): number | null {
	const padGrade = String(grade).padStart(2, '0');
	const stepKey = String(Number(step));
	const base = payTables?.GS?.[String(year)]?.BASE?.[padGrade]?.[stepKey];
	return typeof base === 'number' && Number.isFinite(base) ? base : null;
}

export function applyLocality(base: number, adjustmentPct: number): number {
	return Math.round(base * (1 + adjustmentPct / 100));
}

export function compute(inputs: CompInputs): CompResult {
	const notes: string[] = [];
	const sources: string[] = [];
	const breakdown: CompBreakdown = { method: inputs.mode };

	let annual: number | null = null;
	let sourceState: string | null = null;

	if (inputs.mode === 'gs') {
		const { grade, step, localityCode } = inputs;
		if (!grade || !step || !localityCode) {
			return emptyResult(breakdown, [], ['Pick grade, step, and locality.']);
		}
		const locality = inputs.localities.find((l) => l.code === localityCode);
		if (!locality) {
			return emptyResult(breakdown, [], [`Unknown locality: ${localityCode}`]);
		}
		const base = gsBasePay(inputs.payTables, inputs.year, grade, step);
		if (base === null) {
			return emptyResult(breakdown, [], [
				`No GS base rate for grade ${grade} step ${step} in ${inputs.year}.`
			]);
		}
		annual = applyLocality(base, locality.adjustment_pct);
		breakdown.gs_base = base;
		breakdown.locality_adjustment_pct = locality.adjustment_pct;
		breakdown.locality_code = locality.code;
		breakdown.locality_name = locality.name;
		sourceState = locality.primary_state;
		sources.push(`OPM ${inputs.year} GS base rates`);
		sources.push(`OPM ${inputs.year} locality pay (${locality.code} +${locality.adjustment_pct}%)`);
		if (!sourceState) {
			notes.push(`Could not infer a primary state for locality ${locality.code}; pick a comparison state to compute COL.`);
		}
	} else {
		// custom mode
		const amount = Number(inputs.customAnnual);
		if (!Number.isFinite(amount) || amount <= 0) {
			return emptyResult(breakdown, [], ['Enter a positive annual wage.']);
		}
		annual = Math.round(amount);
		sourceState = inputs.customStateCode ?? null;
		if (!sourceState) {
			notes.push('Pick the state where you currently earn this wage.');
		}
	}

	const sourceRow = sourceState ? inputs.stateRpp[sourceState] ?? null : null;
	const targetRow = inputs.targetStateCode ? inputs.stateRpp[inputs.targetStateCode] ?? null : null;

	let equivalent: number | null = null;
	if (
		annual !== null &&
		sourceRow?.rpp_overall &&
		targetRow?.rpp_overall &&
		sourceRow.rpp_overall > 0
	) {
		equivalent = Math.round(annual * (targetRow.rpp_overall / sourceRow.rpp_overall));
		sources.push(
			`BEA Regional Price Parities (${sourceRow.year ?? '?'}): source ${sourceState}=${sourceRow.rpp_overall}, target ${inputs.targetStateCode}=${targetRow.rpp_overall}`
		);
	} else if (annual !== null && inputs.targetStateCode) {
		if (!sourceRow?.rpp_overall) notes.push(`No RPP available for source state ${sourceState ?? '(unset)'}.`);
		if (!targetRow?.rpp_overall) notes.push(`No RPP available for target state ${inputs.targetStateCode}.`);
	}

	// Locality-derived source state means RPP is "approximate" because OPM
	// localities can span multiple states. The state RPP is the primary state.
	const sourceApprox =
		inputs.mode === 'gs' &&
		!!breakdown.locality_code &&
		!!sourceState &&
		!STATE_POSTAL.has(breakdown.locality_code);

	return {
		annual_pay: annual,
		breakdown,
		source_state: sourceState,
		source_state_rpp: sourceRow?.rpp_overall ?? null,
		source_state_rpp_year: sourceRow?.year ?? null,
		source_state_rpp_approximate: sourceApprox,
		target_state: inputs.targetStateCode ?? null,
		target_state_rpp: targetRow?.rpp_overall ?? null,
		target_state_rpp_year: targetRow?.year ?? null,
		target_state_rpp_approximate: false,
		equivalent_pay: equivalent,
		notes,
		sources
	};
}

function emptyResult(
	breakdown: CompBreakdown,
	sources: string[],
	notes: string[]
): CompResult {
	return {
		annual_pay: null,
		breakdown,
		source_state: null,
		source_state_rpp: null,
		source_state_rpp_year: null,
		source_state_rpp_approximate: false,
		target_state: null,
		target_state_rpp: null,
		target_state_rpp_year: null,
		target_state_rpp_approximate: false,
		equivalent_pay: null,
		notes,
		sources
	};
}

export const STATE_NAMES: Record<string, string> = {
	AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California',
	CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', DC: 'District of Columbia',
	FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois',
	IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana',
	ME: 'Maine', MD: 'Maryland', MA: 'Massachusetts', MI: 'Michigan',
	MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri', MT: 'Montana',
	NE: 'Nebraska', NV: 'Nevada', NH: 'New Hampshire', NJ: 'New Jersey',
	NM: 'New Mexico', NY: 'New York', NC: 'North Carolina', ND: 'North Dakota',
	OH: 'Ohio', OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania',
	RI: 'Rhode Island', SC: 'South Carolina', SD: 'South Dakota', TN: 'Tennessee',
	TX: 'Texas', UT: 'Utah', VT: 'Vermont', VA: 'Virginia', WA: 'Washington',
	WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming', PR: 'Puerto Rico',
	VI: 'U.S. Virgin Islands', GU: 'Guam', AS: 'American Samoa',
	MP: 'Northern Mariana Islands'
};
