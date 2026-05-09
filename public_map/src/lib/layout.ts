export type LayoutSlot =
	| 'masthead'
	| 'search'
	| 'filters'
	| 'feature'
	| 'metric'
	| 'freshness'
	| 'map-controls'
	| 'scoped-window'
	| 'theme-toggle';

export const LAYOUT_SLOTS: Record<LayoutSlot, LayoutSlot> = {
	masthead: 'masthead',
	search: 'search',
	filters: 'filters',
	feature: 'feature',
	metric: 'metric',
	freshness: 'freshness',
	'map-controls': 'map-controls',
	'scoped-window': 'scoped-window',
	'theme-toggle': 'theme-toggle'
};

export const slotAttr = (slot: LayoutSlot): string => slot;
