// D.5.17 — Compensation/COL comparator tests.

import { describe, expect, it } from 'vitest';
import {
	compute,
	gsBasePay,
	applyLocality,
	localityPrimaryState,
	localitiesFromGeoJson,
	stateRppFromCol,
	type LocalityInfo,
	type StateRpp
} from './compensation';
import type { PayTables } from './data';

const PAY_TABLES_2025: PayTables = {
	GS: {
		'2025': {
			BASE: {
				'01': { '1': 22886, '5': 25906, '10': 28590 },
				'13': { '1': 92216, '2': 95289, '10': 119881 },
				'15': { '1': 128183, '10': 166640 }
			}
		}
	}
};

const LOCALITIES: LocalityInfo[] = [
	{ code: 'CHI', name: 'Chicago-Naperville IL-IN-WI', adjustment_pct: 32.45, primary_state: 'IL' },
	{ code: 'DEN', name: 'Denver-Aurora CO', adjustment_pct: 30.52, primary_state: 'CO' },
	{ code: 'AK', name: 'State of Alaska', adjustment_pct: 30.27, primary_state: 'AK' }
];

const STATE_RPP: Record<string, StateRpp> = {
	IL: { rpp_overall: 99.4, year: 2023, source: 'bea:rpp' },
	CO: { rpp_overall: 102.7, year: 2023, source: 'bea:rpp' },
	AK: { rpp_overall: 105.6, year: 2023, source: 'bea:rpp' },
	MS: { rpp_overall: 86.1, year: 2023, source: 'bea:rpp' }
};

describe('gsBasePay', () => {
	it('returns the base for a valid grade/step/year', () => {
		expect(gsBasePay(PAY_TABLES_2025, 2025, '13', '1')).toBe(92216);
		expect(gsBasePay(PAY_TABLES_2025, 2025, '15', '10')).toBe(166640);
	});

	it('handles single-digit grade input by zero-padding', () => {
		expect(gsBasePay(PAY_TABLES_2025, 2025, '1', '5')).toBe(25906);
	});

	it('returns null for unknown year/grade/step', () => {
		expect(gsBasePay(PAY_TABLES_2025, 2099, '13', '1')).toBeNull();
		expect(gsBasePay(PAY_TABLES_2025, 2025, '99', '1')).toBeNull();
		expect(gsBasePay(PAY_TABLES_2025, 2025, '13', '99')).toBeNull();
	});
});

describe('applyLocality', () => {
	it('applies a locality percent rounded to whole dollars', () => {
		expect(applyLocality(100000, 32.45)).toBe(132450);
		expect(applyLocality(92216, 32.45)).toBe(122140);
	});
});

describe('localityPrimaryState', () => {
	it('returns the code for two-letter state codes', () => {
		expect(localityPrimaryState('AK', 'State of Alaska')).toBe('AK');
		expect(localityPrimaryState('HI', 'State of Hawaii')).toBe('HI');
	});

	it('returns the override for known multi-state localities', () => {
		expect(localityPrimaryState('CHI', 'Chicago-Naperville IL-IN-WI')).toBe('IL');
		expect(localityPrimaryState('DCB', 'Washington DC-MD-VA-WV-PA')).toBe('DC');
	});

	it('parses a state-list suffix when no override exists', () => {
		expect(localityPrimaryState('XYZ', 'Made-up Metro NM')).toBe('NM');
	});

	it('returns null when no postal token can be found', () => {
		expect(localityPrimaryState('XYZ', 'no state token here')).toBeNull();
	});
});

describe('localitiesFromGeoJson', () => {
	it('parses a feature collection into LocalityInfo[]', () => {
		const fc = {
			type: 'FeatureCollection' as const,
			features: [
				{
					type: 'Feature' as const,
					geometry: null,
					properties: { code: 'CHI', name: 'Chicago-Naperville IL-IN-WI', adjustment_pct: 32.45 }
				},
				{
					type: 'Feature' as const,
					geometry: null,
					properties: { code: 'AK', name: 'State of Alaska', adjustment_pct: 30.27 }
				}
			]
		};
		const out = localitiesFromGeoJson(fc);
		expect(out).toHaveLength(2);
		const chi = out.find((l) => l.code === 'CHI')!;
		expect(chi.primary_state).toBe('IL');
		expect(chi.adjustment_pct).toBe(32.45);
	});

	it('skips features missing required fields', () => {
		const fc = {
			type: 'FeatureCollection' as const,
			features: [
				{ type: 'Feature' as const, geometry: null, properties: { code: '', name: 'x', adjustment_pct: 1 } },
				{ type: 'Feature' as const, geometry: null, properties: { code: 'X', name: '', adjustment_pct: 1 } },
				{ type: 'Feature' as const, geometry: null, properties: { code: 'X', name: 'x' } }
			]
		};
		expect(localitiesFromGeoJson(fc)).toHaveLength(0);
	});
});

describe('stateRppFromCol', () => {
	it('keeps numeric rpp_overall and discards everything else', () => {
		const out = stateRppFromCol({
			by_state: {
				IL: { rpp_overall: 99.4, year: 2023, source: 'bea:rpp' },
				ZZ: { rpp_overall: null, year: null, source: 'bea:rpp' }
			}
		});
		expect(out.IL.rpp_overall).toBe(99.4);
		expect(out.ZZ.rpp_overall).toBeNull();
	});
});

describe('compute (GS mode)', () => {
	it('calculates locality-adjusted pay and the COL equivalent', () => {
		const result = compute({
			mode: 'gs',
			year: 2025,
			grade: '13',
			step: '1',
			localityCode: 'DEN',
			targetStateCode: 'IL',
			payTables: PAY_TABLES_2025,
			localities: LOCALITIES,
			stateRpp: STATE_RPP
		});
		expect(result.breakdown.method).toBe('gs');
		expect(result.breakdown.gs_base).toBe(92216);
		expect(result.breakdown.locality_adjustment_pct).toBe(30.52);
		// 92216 * 1.3052 = 120360.3232 → 120360
		expect(result.annual_pay).toBe(120360);
		expect(result.source_state).toBe('CO');
		expect(result.source_state_rpp).toBe(102.7);
		expect(result.target_state_rpp).toBe(99.4);
		expect(result.equivalent_pay).toBe(Math.round(120360 * (99.4 / 102.7)));
		expect(result.source_state_rpp_approximate).toBe(true);
	});

	it('flags AK source as not approximate (locality code is the state)', () => {
		const result = compute({
			mode: 'gs',
			year: 2025,
			grade: '13',
			step: '1',
			localityCode: 'AK',
			targetStateCode: 'MS',
			payTables: PAY_TABLES_2025,
			localities: LOCALITIES,
			stateRpp: STATE_RPP
		});
		expect(result.source_state).toBe('AK');
		expect(result.source_state_rpp_approximate).toBe(false);
	});

	it('returns notes when required GS fields are missing', () => {
		const result = compute({
			mode: 'gs',
			year: 2025,
			payTables: PAY_TABLES_2025,
			localities: LOCALITIES,
			stateRpp: STATE_RPP
		});
		expect(result.annual_pay).toBeNull();
		expect(result.notes.length).toBeGreaterThan(0);
	});

	it('returns a clear note when the GS base table is missing the row', () => {
		const result = compute({
			mode: 'gs',
			year: 2099,
			grade: '13',
			step: '1',
			localityCode: 'DEN',
			payTables: PAY_TABLES_2025,
			localities: LOCALITIES,
			stateRpp: STATE_RPP
		});
		expect(result.annual_pay).toBeNull();
		expect(result.notes.some((n) => /No GS base rate/.test(n))).toBe(true);
	});

	it('omits equivalent_pay when target RPP is missing', () => {
		const result = compute({
			mode: 'gs',
			year: 2025,
			grade: '13',
			step: '1',
			localityCode: 'CHI',
			targetStateCode: 'WY', // not in STATE_RPP
			payTables: PAY_TABLES_2025,
			localities: LOCALITIES,
			stateRpp: STATE_RPP
		});
		expect(result.annual_pay).not.toBeNull();
		expect(result.equivalent_pay).toBeNull();
		expect(result.notes.some((n) => /No RPP available for target state/.test(n))).toBe(true);
	});
});

describe('compute (custom mode)', () => {
	it('uses the custom amount and source state RPP', () => {
		const result = compute({
			mode: 'custom',
			year: 2025,
			customAnnual: 100000,
			customStateCode: 'IL',
			targetStateCode: 'MS',
			payTables: PAY_TABLES_2025,
			localities: LOCALITIES,
			stateRpp: STATE_RPP
		});
		expect(result.annual_pay).toBe(100000);
		expect(result.source_state).toBe('IL');
		// 100000 * (86.1/99.4) = 86619.7 → 86620
		expect(result.equivalent_pay).toBe(Math.round(100000 * (86.1 / 99.4)));
		expect(result.source_state_rpp_approximate).toBe(false);
	});

	it('rejects negative or zero wages', () => {
		const result = compute({
			mode: 'custom',
			year: 2025,
			customAnnual: 0,
			customStateCode: 'IL',
			payTables: PAY_TABLES_2025,
			localities: LOCALITIES,
			stateRpp: STATE_RPP
		});
		expect(result.annual_pay).toBeNull();
		expect(result.notes[0]).toMatch(/positive annual wage/);
	});
});
