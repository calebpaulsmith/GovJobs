// D.5.29 / ADR-0033 — bridge between the live store and the pure view codec.
//
// `readCurrentView` snapshots mapState into a ShareableView (used by the share
// button and the address-bar sync). `applySharedView` pushes a decoded view
// back into mapState when hydrating a shared `/browse?…` link. Both are called
// from lifecycle hooks / event handlers — never from inside a `$effect` — so
// the writes here don't need `untrack` (the deferred selection resolution,
// which DOES run in an effect, lives in the page and wraps its writes).

import { mapState } from './store.svelte';
import { normalizeListToolbar } from './jobListFacets';
import type { ShareableView } from './viewState';

/** True when the current selection is an actual job card (not a polygon). */
function selectedJobId(): string | null {
	const sel = mapState.selectedFeature;
	if (!sel || sel.label !== 'Job card') return null;
	const id = sel.properties?.id;
	return id != null && id !== '' ? String(id) : null;
}

/** Snapshot the current view from the store. */
export function readCurrentView(): ShareableView {
	const vp = mapState.viewport;
	const viewport =
		vp && Array.isArray(vp.center) && Number.isFinite(vp.zoom)
			? { center: [Number(vp.center[0]), Number(vp.center[1])] as [number, number], zoom: Number(vp.zoom) }
			: null;
	return {
		filters: mapState.filters,
		metric: mapState.metric,
		viewport,
		theme: mapState.theme,
		selectedJobId: selectedJobId(),
		scroll: mapState.listScroll > 0 ? mapState.listScroll : null,
		list: mapState.list
	};
}

/**
 * Push a decoded view into the store when hydrating a shared link. The map
 * viewport and list scroll restore through their `pending*` channels; the
 * selected job is deferred (jobs_detail may not be loaded yet) via
 * `pendingSelectedJobId`, resolved by the page once details arrive.
 */
export function applySharedView(view: ShareableView): void {
	mapState.filters = view.filters;
	mapState.metric = view.metric;
	mapState.list = normalizeListToolbar(view.list);
	if (view.theme) mapState.theme = view.theme;
	if (view.viewport) {
		mapState.pendingViewport = { center: view.viewport.center, zoom: view.viewport.zoom };
	}
	if (view.scroll != null) mapState.pendingListScroll = view.scroll;
	if (view.selectedJobId) mapState.pendingSelectedJobId = view.selectedJobId;
}
