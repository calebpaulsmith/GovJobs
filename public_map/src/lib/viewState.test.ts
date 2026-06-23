import { describe, it, expect } from 'vitest';
import {
	readViewFromParams,
	writeViewToParams,
	viewToParamString,
	shareUrlFromView,
	type ShareableView
} from './viewState';
import { DEFAULT_FILTERS, type JobFilters } from './filters';
import { DEFAULT_LIST_TOOLBAR, type ListToolbarState } from './jobListFacets';

function filters(overrides: Partial<JobFilters> = {}): JobFilters {
	return { ...DEFAULT_FILTERS, agencies: [], geographies: [], radii: [], ...overrides };
}

function view(overrides: Partial<ShareableView> = {}): ShareableView {
	return {
		filters: filters(),
		metric: 'postings',
		viewport: null,
		theme: null,
		selectedJobId: null,
		scroll: null,
		list: { ...DEFAULT_LIST_TOOLBAR, facets: [] },
		...overrides
	};
}

function toolbar(overrides: Partial<ListToolbarState> = {}): ListToolbarState {
	return { ...DEFAULT_LIST_TOOLBAR, facets: [], ...overrides };
}

function roundTrip(v: ShareableView): ShareableView {
	return readViewFromParams(new URLSearchParams(viewToParamString(v)));
}

describe('viewState round-trip', () => {
	it('round-trips filters, metric, viewport, theme, selected, scroll', () => {
		const v = view({
			filters: filters({ keyword: 'analyst', agencies: ['HSCB'], gradeMin: '12' }),
			metric: 'workforce',
			viewport: { center: [-87.63, 41.88], zoom: 10.5 },
			theme: 'light',
			selectedJobId: '4815',
			scroll: 0.42
		});
		const out = roundTrip(v);
		expect(out.filters.keyword).toBe('analyst');
		expect(out.filters.agencies).toEqual(['HSCB']);
		expect(out.filters.gradeMin).toBe('12');
		expect(out.metric).toBe('workforce');
		expect(out.viewport).toEqual({ center: [-87.63, 41.88], zoom: 10.5 });
		expect(out.theme).toBe('light');
		expect(out.selectedJobId).toBe('4815');
		expect(out.scroll).toBeCloseTo(0.42, 3);
	});

	it('round-trips the country scope filter', () => {
		const out = roundTrip(view({ filters: filters({ countries: ['IT', 'JP'] }) }));
		expect(out.filters.countries).toEqual(['IT', 'JP']);
	});

	it('omits defaults — default metric, dark theme, and empty extras stay out of the URL', () => {
		const qs = viewToParamString(view({ metric: 'postings', theme: 'dark' }));
		expect(qs).not.toContain('metric=');
		expect(qs).not.toContain('theme=');
		expect(qs).not.toContain('selected=');
		expect(qs).not.toContain('scroll=');
		expect(qs).not.toContain('center=');
	});

	it('falls back to defaults when params are missing or malformed', () => {
		const out = readViewFromParams(new URLSearchParams('metric=bogus&center=foo&zoom=bar&scroll=9'));
		expect(out.metric).toBe('postings');
		expect(out.viewport).toBeNull();
		expect(out.selectedJobId).toBeNull();
		expect(out.scroll).toBe(1); // 9 clamps to 1
	});

	it('drops a viewport with only one of center/zoom', () => {
		expect(readViewFromParams(new URLSearchParams('center=-87.6,41.8')).viewport).toBeNull();
		expect(readViewFromParams(new URLSearchParams('zoom=10')).viewport).toBeNull();
	});

	it('rejects out-of-range center coordinates', () => {
		expect(readViewFromParams(new URLSearchParams('center=-999,41.8&zoom=10')).viewport).toBeNull();
	});

	it('clamps scroll into 0..1', () => {
		expect(readViewFromParams(new URLSearchParams('scroll=-0.5')).scroll).toBe(0);
		expect(readViewFromParams(new URLSearchParams('scroll=2')).scroll).toBe(1);
	});

	it('is idempotent — rewriting a populated URLSearchParams does not duplicate keys', () => {
		const params = new URLSearchParams('q=old&metric=workforce&center=-70,40&zoom=5');
		const v = view({ filters: filters({ keyword: 'new' }), metric: 'accessions' });
		writeViewToParams(params, v);
		writeViewToParams(params, v);
		expect(params.getAll('metric')).toEqual(['accessions']);
		expect(params.getAll('q')).toEqual(['new']);
	});

	it('preserves radius chips through the view codec (delegates to filters)', () => {
		const v = view({
			filters: filters({
				radii: [{ center: [-74.006, 40.7128], miles: 50, label: 'NYC', includeRemote: true }]
			})
		});
		const out = roundTrip(v);
		expect(out.filters.radii).toHaveLength(1);
		expect(out.filters.radii[0].miles).toBe(50);
	});
});

describe('shareUrlFromView', () => {
	it('builds an absolute /browse URL with the encoded view', () => {
		const url = shareUrlFromView(view({ filters: filters({ keyword: 'nurse' }) }), {
			origin: 'https://map.thegrandpipeline.com'
		});
		expect(url).toBe('https://map.thegrandpipeline.com/browse?q=nurse');
	});
	it('honors a custom path and omits the query when the view is empty', () => {
		const url = shareUrlFromView(view(), { origin: 'https://x.test', path: '/map' });
		expect(url).toBe('https://x.test/map');
	});
});

describe('in-list toolbar codec (D.5.28)', () => {
	it('round-trips search, sort, and facets', () => {
		const v = view({
			list: toolbar({ search: 'analyst chicago', sort: 'salary_high', facets: ['gs_family', 'closing_7d'] })
		});
		const qs = viewToParamString(v);
		expect(qs).toContain('lq=analyst+chicago');
		expect(qs).toContain('lsort=salary_high');
		expect(qs.match(/lf=/g)?.length).toBe(2);
		expect(roundTrip(v).list).toEqual({
			search: 'analyst chicago',
			sort: 'salary_high',
			facets: ['gs_family', 'closing_7d']
		});
	});

	it('omits the resting toolbar from the URL entirely', () => {
		const qs = viewToParamString(view());
		expect(qs).not.toContain('lq=');
		expect(qs).not.toContain('lsort=');
		expect(qs).not.toContain('lf=');
	});

	it('drops unknown sort keys and facet keys on decode', () => {
		const params = new URLSearchParams('lsort=bogus&lf=nope&lf=remote_eligible');
		const decoded = readViewFromParams(params);
		expect(decoded.list.sort).toBe('closing_soon');
		expect(decoded.list.facets).toEqual(['remote_eligible']);
	});

	it('facet order in the URL does not matter — FACETS order wins', () => {
		const params = new URLSearchParams('lf=closing_7d&lf=gs_family&lf=gs_family');
		const decoded = readViewFromParams(params);
		expect(decoded.list.facets).toEqual(['gs_family', 'closing_7d']);
	});

	it('rewriting a URL that already carries toolbar keys is idempotent', () => {
		const params = new URLSearchParams('lq=old&lsort=title&lf=gs_family');
		writeViewToParams(params, view({ list: toolbar({ search: 'new' }) }));
		expect(params.get('lq')).toBe('new');
		expect(params.get('lsort')).toBeNull();
		expect(params.getAll('lf')).toEqual([]);
	});
});
