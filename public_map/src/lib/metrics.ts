// Choropleth metric definitions for the state-fill layer.
//
// Properties on a state feature (per src/public_map_export.py::states_geojson):
//   postings, workforce, accessions, separations, gs13_step1_locality,
//   rpp_overall, pay_vs_col
//
// `remote_share` is NOT pre-computed by the export — it's derived client-side
// from jobs.geojson aggregated by state and stamped onto each state feature
// before the layer renders. See lib/Map.svelte::deriveRemoteShare.

export type MetricKey =
	| 'postings'
	| 'workforce'
	| 'accessions'
	| 'separations'
	| 'remote_share'
	| 'pay_vs_col';

export type MetricFormat = 'count' | 'percent' | 'index';
export type MetricStatus = 'ready' | 'wip' | 'under-construction';

export interface MetricDef {
	key: MetricKey;
	label: string;
	short: string;
	description: string;
	source: string;
	property: string;
	format: MetricFormat;
	// [breakpoint, hex] pairs in ascending order. Mapbox `interpolate ['linear']`
	// renders values between stops smoothly; values below the first / above the
	// last clamp to the endpoints.
	colorStops: [number, string][];
	// Color used when the property is null/missing.
	nullColor: string;
	// Declared status. Auto-demotion in Map.svelte can downgrade to 'wip' at
	// runtime when ≥ 50% of state features are null for this metric.
	status: MetricStatus;
	// Shown in the metric switcher when status is 'wip'.
	wipNote?: string;
}

const SEQ_BLUE: [number, string][] = [
	[0, '#13202e'],
	[1, '#1f3a5f'],
	[100, '#2c5b8a'],
	[400, '#3f86b8'],
	[1200, '#65b1da'],
	[3000, '#a8d8f0']
];

const SEQ_PURPLE: [number, string][] = [
	[0, '#1a1a2e'],
	[1000, '#312865'],
	[10000, '#5d3a99'],
	[50000, '#8a5dc6'],
	[150000, '#b88dde'],
	[400000, '#dcc1f0']
];

const SEQ_GREEN: [number, string][] = [
	[0, '#10241a'],
	[100, '#1d4a30'],
	[1000, '#2c7849'],
	[5000, '#3da664'],
	[15000, '#6cd09a'],
	[40000, '#a8e8c5']
];

const DIVERGING_PAY_COL: [number, string][] = [
	// pay_vs_col: 100 = national average. >100 = pay outpaces COL.
	[60, '#9b3a3a'],
	[85, '#c87c7c'],
	[100, '#d8d8d8'],
	[115, '#7bb29b'],
	[140, '#3d8a6a']
];

const SEQ_REMOTE: [number, string][] = [
	// remote_share is a fraction in [0, 1].
	[0, '#1a2030'],
	[0.05, '#2c4870'],
	[0.15, '#4979b3'],
	[0.3, '#7bb6e0'],
	[0.55, '#bce2f5']
];

export const METRICS: Record<MetricKey, MetricDef> = {
	postings: {
		key: 'postings',
		label: 'Open postings',
		short: 'Postings',
		description: 'Open USAJOBS announcements today.',
		source: 'USAJOBS',
		property: 'postings',
		format: 'count',
		colorStops: SEQ_BLUE,
		nullColor: '#13202e',
		status: 'ready'
	},
	workforce: {
		key: 'workforce',
		label: 'Federal workforce',
		short: 'Workforce',
		description: 'Federal civilian employees by duty-station state. Workforce, not postings.',
		source: 'OPM FedScope',
		property: 'workforce',
		format: 'count',
		colorStops: SEQ_PURPLE,
		nullColor: '#1a1a2e',
		status: 'ready',
		wipNote: 'OPM workforce data not yet loaded — run the OPM import in Data Admin.'
	},
	accessions: {
		key: 'accessions',
		label: 'Accessions',
		short: 'Hires',
		description: 'New hires reported by OPM (FedScope) in the most recent year.',
		source: 'OPM FedScope',
		property: 'accessions',
		format: 'count',
		colorStops: SEQ_GREEN,
		nullColor: '#10241a',
		status: 'ready',
		wipNote: 'OPM accessions data not yet loaded — run the OPM import in Data Admin.'
	},
	separations: {
		key: 'separations',
		label: 'Separations',
		short: 'Separations',
		description: 'Departures reported by OPM (FedScope) in the most recent year.',
		source: 'OPM FedScope',
		property: 'separations',
		format: 'count',
		colorStops: SEQ_GREEN,
		nullColor: '#10241a',
		status: 'ready',
		wipNote: 'OPM separations data not yet loaded — run the OPM import in Data Admin.'
	},
	remote_share: {
		key: 'remote_share',
		label: 'Remote share',
		short: 'Remote',
		description: 'Share of open postings flagged as fully remote by USAJOBS.',
		source: 'USAJOBS (derived)',
		property: 'remote_share',
		format: 'percent',
		colorStops: SEQ_REMOTE,
		nullColor: '#1a2030',
		status: 'ready',
		wipNote: 'Remote share requires at least one open posting per state.'
	},
	pay_vs_col: {
		key: 'pay_vs_col',
		label: 'Pay vs cost of living',
		short: 'Pay/COL',
		description:
			'Illustrative GS-13 step 1 locality pay ÷ BEA Regional Price Parity × 100. 100 = national average purchasing power.',
		source: 'OPM + BEA',
		property: 'pay_vs_col',
		format: 'index',
		colorStops: DIVERGING_PAY_COL,
		nullColor: '#1c1c1c',
		status: 'ready',
		wipNote: 'Pay/COL requires both OPM locality pay and BEA RPP data.'
	}
};

export const METRIC_ORDER: MetricKey[] = [
	'postings',
	'workforce',
	'accessions',
	'separations',
	'remote_share',
	'pay_vs_col'
];

export const DEFAULT_METRIC: MetricKey = 'postings';

export function formatMetricValue(metric: MetricDef, value: number | null | undefined): string {
	if (value === null || value === undefined || Number.isNaN(value)) return '—';
	switch (metric.format) {
		case 'count':
			return Math.round(value).toLocaleString();
		case 'percent':
			return `${(value * 100).toFixed(1)}%`;
		case 'index':
			return value.toFixed(0);
		default:
			return String(value);
	}
}

/**
 * Build a Mapbox `interpolate` expression that maps the metric's numeric
 * property to a color. Null/missing values fall through to `nullColor` via
 * `coalesce`.
 */
export function fillColorExpression(metric: MetricDef): unknown[] {
	const stops = metric.colorStops.flatMap(([breakpoint, color]) => [breakpoint, color]);
	return [
		'case',
		['==', ['get', metric.property], null],
		metric.nullColor,
		['interpolate', ['linear'], ['to-number', ['get', metric.property], 0], ...stops]
	];
}
