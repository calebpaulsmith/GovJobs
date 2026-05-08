export type LayoutSlot =
	| 'masthead'
	| 'search'
	| 'filters'
	| 'feature'
	| 'metric'
	| 'freshness'
	| 'map-controls';

export const LAYOUT_SLOTS: Record<LayoutSlot, LayoutSlot> = {
	masthead: 'masthead',
	search: 'search',
	filters: 'filters',
	feature: 'feature',
	metric: 'metric',
	freshness: 'freshness',
	'map-controls': 'map-controls'
};

export const slotAttr = (slot: LayoutSlot): string => slot;
