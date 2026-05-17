/**
 * Single source of truth for public-map UI panel positioning (CLAUDE.md
 * "Public Map V1.5 invariants" rule #12). Each panel reads its position from
 * CSS variables emitted by `layoutCssBlock()`; the matching `LAYOUT_RECTS`
 * data structure is what the breakpoint overlap test consumes.
 *
 * Add a new panel by:
 *   1. Adding its slot name to `LayoutSlot`.
 *   2. Filling in its rect at every breakpoint in `LAYOUT_RECTS`.
 *   3. Listing it in `COEXISTING_SLOTS` for any breakpoint where it shares
 *      the screen with other slots.
 *   4. In the component CSS, drive `top` / `left` / `right` / `bottom` /
 *      `width` from the matching `--slot-<name>-*` CSS variables.
 *
 * No ad-hoc absolute positioning is allowed; the test in `layout.test.ts`
 * fails loudly if two coexisting slots overlap at any of the three reference
 * viewports.
 */

export type LayoutSlot =
	| 'masthead'
	| 'chip-strip'
	| 'search'
	| 'saved-search'
	| 'filters'
	| 'feature'
	| 'metric'
	| 'freshness'
	| 'map-controls'
	| 'scoped-window'
	| 'theme-toggle';

export const LAYOUT_SLOTS: Record<LayoutSlot, LayoutSlot> = {
	masthead: 'masthead',
	'chip-strip': 'chip-strip',
	search: 'search',
	'saved-search': 'saved-search',
	filters: 'filters',
	feature: 'feature',
	metric: 'metric',
	freshness: 'freshness',
	'map-controls': 'map-controls',
	'scoped-window': 'scoped-window',
	'theme-toggle': 'theme-toggle'
};

export const slotAttr = (slot: LayoutSlot): string => slot;

// ─────────────────────────────────────────────────────────────────────────────
// Breakpoints
// ─────────────────────────────────────────────────────────────────────────────

export type Breakpoint = 'desktop' | 'tablet' | 'mobile';

/**
 * Lower bound (inclusive) for each breakpoint, in CSS pixels.
 * desktop: ≥1280, tablet: 720–1279, mobile: <720.
 */
export const BREAKPOINT_MIN_WIDTH: Record<Breakpoint, number> = {
	desktop: 1280,
	tablet: 720,
	mobile: 0
};

/** Reference viewports used by the overlap test. */
export const REFERENCE_VIEWPORTS: Record<Breakpoint, { width: number; height: number }> = {
	desktop: { width: 1440, height: 900 },
	tablet: { width: 1024, height: 768 },
	mobile: { width: 720, height: 1280 }
};

export function pickBreakpoint(viewportWidth: number): Breakpoint {
	if (viewportWidth >= BREAKPOINT_MIN_WIDTH.desktop) return 'desktop';
	if (viewportWidth >= BREAKPOINT_MIN_WIDTH.tablet) return 'tablet';
	return 'mobile';
}

// ─────────────────────────────────────────────────────────────────────────────
// Rect spec
// ─────────────────────────────────────────────────────────────────────────────

/**
 * A panel's position and size at one breakpoint. All values are CSS strings
 * (e.g. `'1rem'`, `'min(24rem, calc(100vw - 2rem))'`). At least one of
 * `(left, right, width)` and one of `(top, bottom, height)` must be set.
 *
 * `intrinsicHeight` and `intrinsicWidth` are content-driven fallbacks the
 * overlap test uses when CSS does not pin the dimension (panels usually grow
 * with content); they are not emitted as CSS variables.
 */
export type Rect = {
	top?: string;
	right?: string;
	bottom?: string;
	left?: string;
	width?: string;
	height?: string;
	maxWidth?: string;
	transform?: string;
	intrinsicHeight?: string;
	intrinsicWidth?: string;
};

/**
 * `null` at a breakpoint = the slot is hidden by default at that width
 * (controlled by component-level `display: none` or runtime state).
 */
export type SlotRects = Record<Breakpoint, Rect | null>;

const PANEL_WIDTH = 'min(24rem, calc(100vw - 2rem))';
const PANEL_INTRINSIC_HEIGHT = '14rem'; // shared content-height assumption for the overlap test

export const LAYOUT_RECTS: Record<LayoutSlot, SlotRects> = {
	masthead: {
		// Width capped to the gap between the two 24rem side columns so the
		// brand + manifest + action buttons can never bleed into the address
		// search or saved-searches dropdown. The pill content wraps inside
		// (white-space allowed) when the cap forces it.
		desktop: {
			top: '1rem',
			left: '50%',
			transform: 'translateX(-50%)',
			maxWidth: 'calc(100vw - 52rem)',
			intrinsicHeight: '2.5rem'
		},
		tablet: {
			top: '1rem',
			left: '50%',
			transform: 'translateX(-50%)',
			maxWidth: 'calc(100vw - 52rem)',
			intrinsicHeight: '2.5rem'
		},
		mobile: {
			top: '0.5rem',
			left: '0.5rem',
			right: '0.5rem',
			intrinsicHeight: '4.5rem'
		}
	},
	'chip-strip': {
		// Width is capped to the gap between the two 24rem side columns
		// (each column = 1rem inset + 24rem width; we leave a 1rem gap on
		// each side, so the chip strip can span at most 100vw - 54rem).
		desktop: {
			top: '4.4rem',
			left: '50%',
			transform: 'translateX(-50%)',
			maxWidth: 'calc(100vw - 54rem)',
			intrinsicHeight: '2rem'
		},
		tablet: {
			top: '4.4rem',
			left: '50%',
			transform: 'translateX(-50%)',
			maxWidth: 'calc(100vw - 54rem)',
			intrinsicHeight: '2rem'
		},
		// At mobile the chip strip docks above the metric switcher (matching
		// the existing UX). It is kept out of COEXISTING_SLOTS.mobile since
		// it is conditionally visible (only when filters are active) and
		// FeaturePanel may take the same bottom-anchored space when open.
		mobile: {
			bottom: '5.5rem',
			left: '0.5rem',
			right: '0.5rem',
			intrinsicHeight: '2rem'
		}
	},
	search: {
		// Side column starts at the same top as the masthead — the centered
		// masthead leaves the top-LEFT free, so search/saved-search/filters
		// can stack vertically along the left edge without leaving an empty
		// 5rem gap at the top of the column.
		desktop: {
			top: '1rem',
			left: '1rem',
			width: PANEL_WIDTH,
			intrinsicHeight: '3rem'
		},
		tablet: {
			top: '1rem',
			left: '1rem',
			width: PANEL_WIDTH,
			intrinsicHeight: '3rem'
		},
		// On mobile the address search docks just under the wrapped masthead.
		// Excluded from COEXISTING_SLOTS.mobile because the toggle keeps it
		// closed by default and the input opens as a transient dropdown.
		mobile: {
			top: '5.7rem',
			left: '0.5rem',
			width: 'min(24rem, calc(100vw - 1rem))',
			intrinsicHeight: '3rem'
		}
	},
	'saved-search': {
		desktop: {
			top: '4.7rem',
			left: '1rem',
			width: PANEL_WIDTH,
			intrinsicHeight: '2.5rem'
		},
		tablet: {
			top: '4.7rem',
			left: '1rem',
			width: PANEL_WIDTH,
			intrinsicHeight: '2.5rem'
		},
		mobile: {
			top: '9.4rem',
			left: '0.5rem',
			width: 'min(24rem, calc(100vw - 1rem))',
			intrinsicHeight: '2.5rem'
		}
	},
	filters: {
		desktop: {
			top: '8.3rem',
			left: '1rem',
			width: PANEL_WIDTH,
			intrinsicHeight: PANEL_INTRINSIC_HEIGHT
		},
		tablet: {
			top: '8.3rem',
			left: '1rem',
			width: PANEL_WIDTH,
			intrinsicHeight: PANEL_INTRINSIC_HEIGHT
		},
		// On mobile the FilterPanel docks at the bottom; runtime auto-collapse
		// (existing 2026-05-08 partial D.5.0 work) ensures it doesn't coexist
		// with FeaturePanel, so it is excluded from COEXISTING_SLOTS.mobile.
		mobile: {
			bottom: '6.5rem',
			left: '0.5rem',
			width: 'min(24rem, calc(100vw - 1rem))',
			intrinsicHeight: '3rem'
		}
	},
	feature: {
		desktop: {
			top: '5.25rem',
			right: '1rem',
			width: PANEL_WIDTH,
			intrinsicHeight: PANEL_INTRINSIC_HEIGHT
		},
		tablet: {
			top: '5.25rem',
			right: '1rem',
			width: PANEL_WIDTH,
			intrinsicHeight: PANEL_INTRINSIC_HEIGHT
		},
		// On mobile the FeaturePanel docks at the bottom and the FilterPanel
		// auto-collapses (runtime mutual exclusion). Stays clear of the metric
		// switcher (which sits at bottom: 1rem with height ~4rem).
		mobile: {
			bottom: '6.5rem',
			left: '0.5rem',
			right: '0.5rem',
			intrinsicHeight: '12rem'
		}
	},
	metric: {
		desktop: {
			bottom: '1rem',
			left: '50%',
			transform: 'translateX(-50%)',
			width: 'min(26rem, calc(100vw - 2rem))',
			intrinsicHeight: '4rem'
		},
		tablet: {
			bottom: '1rem',
			left: '50%',
			transform: 'translateX(-50%)',
			width: 'min(26rem, calc(100vw - 2rem))',
			intrinsicHeight: '4rem'
		},
		mobile: {
			bottom: '1rem',
			left: '0.5rem',
			right: '0.5rem',
			intrinsicHeight: '4rem'
		}
	},
	freshness: {
		desktop: {
			bottom: '0.4rem',
			right: '0.6rem',
			intrinsicWidth: '20rem',
			intrinsicHeight: '1.5rem'
		},
		tablet: {
			bottom: '0.4rem',
			right: '0.6rem',
			intrinsicWidth: '18rem',
			intrinsicHeight: '1.5rem'
		},
		mobile: null
	},
	'map-controls': {
		// Native Mapbox controls; we don't position them ourselves but track
		// the slot so future overlap rules can include them if needed.
		desktop: null,
		tablet: null,
		mobile: null
	},
	'scoped-window': {
		// Lives inside FeaturePanel's content; no independent fixed position.
		desktop: null,
		tablet: null,
		mobile: null
	},
	'theme-toggle': {
		// Lives inside the masthead; no independent fixed position.
		desktop: null,
		tablet: null,
		mobile: null
	}
};

/**
 * Pairs of slots that are simultaneously visible at each breakpoint.
 * The overlap test asserts no two of these intersect at the breakpoint's
 * reference viewport.
 *
 * Excludes:
 *   - `feature` and `filters` together at any breakpoint where filters
 *     auto-collapse when feature opens (today: all of them, but desktop
 *     happens to leave room).
 *   - `map-controls`, `scoped-window`, `theme-toggle` (no independent rect).
 */
export const COEXISTING_SLOTS: Record<Breakpoint, LayoutSlot[]> = {
	desktop: ['masthead', 'chip-strip', 'search', 'saved-search', 'filters', 'feature', 'metric', 'freshness'],
	tablet: ['masthead', 'chip-strip', 'search', 'saved-search', 'filters', 'feature', 'metric', 'freshness'],
	// At mobile, FilterPanel auto-collapses when FeaturePanel opens, and
	// ActiveFilterStrip is conditionally visible (only when filters are
	// active). The mutual-exclusion runtime keeps these from coexisting.
	mobile: ['masthead', 'feature', 'metric']
};

// ─────────────────────────────────────────────────────────────────────────────
// CSS variable emission
// ─────────────────────────────────────────────────────────────────────────────

const RECT_PROPS: Array<keyof Rect> = [
	'top',
	'right',
	'bottom',
	'left',
	'width',
	'height',
	'maxWidth',
	'transform'
];

const PROP_TO_VAR: Record<string, string> = {
	top: 'top',
	right: 'right',
	bottom: 'bottom',
	left: 'left',
	width: 'width',
	height: 'height',
	maxWidth: 'max-width',
	transform: 'transform'
};

export function slotCssVarName(slot: LayoutSlot, prop: keyof Rect): string {
	const suffix = PROP_TO_VAR[prop as string] ?? (prop as string);
	return `--slot-${slot}-${suffix}`;
}

function rectToVarBlock(slot: LayoutSlot, rect: Rect | null): string {
	if (!rect) {
		// Slot has no opinion at this breakpoint. Emit `initial` for every
		// position prop so values from a previous breakpoint don't leak in,
		// but leave display untouched — components decide visibility via
		// their own runtime state (mutual-exclusion drawer logic, etc.).
		let out = '';
		for (const prop of RECT_PROPS) {
			out += `\t${slotCssVarName(slot, prop)}: initial;\n`;
		}
		return out;
	}
	let out = '';
	for (const prop of RECT_PROPS) {
		const value = rect[prop];
		if (value !== undefined) {
			out += `\t${slotCssVarName(slot, prop)}: ${value};\n`;
		} else {
			// Reset stale values from a previous breakpoint.
			out += `\t${slotCssVarName(slot, prop)}: initial;\n`;
		}
	}
	return out;
}

/**
 * Returns the full CSS text that pins every slot's position to the values in
 * `LAYOUT_RECTS`. Inject once into `+layout.svelte` via `<svelte:head>`.
 */
export function layoutCssBlock(): string {
	const slots = Object.keys(LAYOUT_RECTS) as LayoutSlot[];

	const desktop = slots.map((s) => rectToVarBlock(s, LAYOUT_RECTS[s].desktop)).join('');
	const tablet = slots.map((s) => rectToVarBlock(s, LAYOUT_RECTS[s].tablet)).join('');
	const mobile = slots.map((s) => rectToVarBlock(s, LAYOUT_RECTS[s].mobile)).join('');

	return [
		`/* Generated by public_map/src/lib/layout.ts — do not hand-edit. */`,
		`:root {`,
		desktop,
		`}`,
		`@media (max-width: ${BREAKPOINT_MIN_WIDTH.desktop - 1}px) {`,
		`:root {`,
		tablet,
		`}`,
		`}`,
		`@media (max-width: ${BREAKPOINT_MIN_WIDTH.tablet - 1}px) {`,
		`:root {`,
		mobile,
		`}`,
		`}`
	].join('\n');
}

// ─────────────────────────────────────────────────────────────────────────────
// Pixel-rect math (for tests)
// ─────────────────────────────────────────────────────────────────────────────

const REM_PX = 16;

export type Viewport = { width: number; height: number };
export type PixelRect = { x: number; y: number; w: number; h: number };

/**
 * Parses a CSS length expression in the limited subset we use:
 *   `<n>rem`, `<n>px`, `<n>%`, `<n>vw`, `<n>vh`,
 *   `min(a, b, ...)`, `max(a, b, ...)`,
 *   `calc(a + b)`, `calc(a - b)`, `calc(a * b)`, `calc(a / b)`.
 *
 * `axis` selects whether `100%` resolves to viewport.width or viewport.height.
 * Throws on anything outside the subset so the test fails loudly when CSS
 * starts using a new shape that isn't accounted for.
 */
export function parseLength(value: string, viewport: Viewport, axis: 'x' | 'y'): number {
	const v = value.trim();
	if (v === '') return 0;
	if (v === 'initial' || v === 'auto' || v === 'none') return 0;

	// Function calls.
	for (const fn of ['min', 'max'] as const) {
		const prefix = `${fn}(`;
		if (v.startsWith(prefix) && v.endsWith(')')) {
			const inner = v.slice(prefix.length, -1);
			const parts = splitTopLevel(inner, ',');
			const nums = parts.map((p) => parseLength(p, viewport, axis));
			return fn === 'min' ? Math.min(...nums) : Math.max(...nums);
		}
	}
	if (v.startsWith('calc(') && v.endsWith(')')) {
		return evalCalc(v.slice(5, -1), viewport, axis);
	}

	// Bare numeric units.
	const m = v.match(/^(-?\d+(?:\.\d+)?)(rem|px|vw|vh|%)?$/);
	if (m) {
		const n = parseFloat(m[1]);
		const unit = m[2] ?? 'px';
		switch (unit) {
			case 'rem':
				return n * REM_PX;
			case 'px':
				return n;
			case 'vw':
				return (n / 100) * viewport.width;
			case 'vh':
				return (n / 100) * viewport.height;
			case '%':
				return (n / 100) * (axis === 'x' ? viewport.width : viewport.height);
		}
	}
	throw new Error(`layout.parseLength: unsupported expression ${JSON.stringify(value)}`);
}

function splitTopLevel(s: string, sep: string): string[] {
	const out: string[] = [];
	let depth = 0;
	let buf = '';
	for (const ch of s) {
		if (ch === '(') depth++;
		else if (ch === ')') depth--;
		if (ch === sep && depth === 0) {
			out.push(buf);
			buf = '';
			continue;
		}
		buf += ch;
	}
	if (buf.length > 0) out.push(buf);
	return out.map((p) => p.trim());
}

function evalCalc(expr: string, viewport: Viewport, axis: 'x' | 'y'): number {
	// Tokenize at top-level + and - only (multiplication / division stay in
	// the recursive descent). We don't use * or / today, but we'd extend
	// here if that changes.
	const tokens: Array<{ op: '+' | '-' | 'start'; term: string }> = [];
	let depth = 0;
	let buf = '';
	let pendingOp: '+' | '-' | 'start' = 'start';
	for (let i = 0; i < expr.length; i++) {
		const ch = expr[i];
		if (ch === '(') depth++;
		else if (ch === ')') depth--;
		if (depth === 0 && (ch === '+' || ch === '-') && i > 0 && /\s/.test(expr[i - 1] ?? '')) {
			tokens.push({ op: pendingOp, term: buf.trim() });
			pendingOp = ch as '+' | '-';
			buf = '';
			continue;
		}
		buf += ch;
	}
	if (buf.trim().length > 0) tokens.push({ op: pendingOp, term: buf.trim() });

	let total = 0;
	for (const { op, term } of tokens) {
		const v = parseLength(term, viewport, axis);
		if (op === '-') total -= v;
		else total += v; // 'start' or '+'
	}
	return total;
}

/**
 * Converts a `Rect` to a pixel-space bounding box at the given viewport.
 * Throws if the rect is under-specified (e.g. neither left nor right set).
 */
export function computeRectPx(rect: Rect, viewport: Viewport): PixelRect {
	const hasLeft = rect.left !== undefined;
	const hasRight = rect.right !== undefined;
	const hasWidth = rect.width !== undefined;
	const hasMaxWidth = rect.maxWidth !== undefined;
	const hasIntrinsicWidth = rect.intrinsicWidth !== undefined;
	const hasTop = rect.top !== undefined;
	const hasBottom = rect.bottom !== undefined;
	const hasHeight = rect.height !== undefined;
	const hasIntrinsicHeight = rect.intrinsicHeight !== undefined;

	let w: number;
	let widthBound: number = viewport.width;
	if (hasMaxWidth) {
		widthBound = parseLength(rect.maxWidth!, viewport, 'x');
	}
	if (hasWidth) {
		w = parseLength(rect.width!, viewport, 'x');
		if (hasMaxWidth) w = Math.min(w, widthBound);
	} else if (hasLeft && hasRight) {
		const left = parseLength(rect.left!, viewport, 'x');
		const right = parseLength(rect.right!, viewport, 'x');
		w = Math.max(0, viewport.width - left - right);
		if (hasMaxWidth) w = Math.min(w, widthBound);
	} else if (hasIntrinsicWidth) {
		w = parseLength(rect.intrinsicWidth!, viewport, 'x');
		if (hasMaxWidth) w = Math.min(w, widthBound);
	} else if (hasMaxWidth) {
		w = widthBound;
	} else {
		throw new Error(`computeRectPx: rect needs width / left+right / intrinsicWidth: ${JSON.stringify(rect)}`);
	}

	let x: number;
	if (hasLeft) {
		x = parseLength(rect.left!, viewport, 'x');
	} else if (hasRight) {
		const right = parseLength(rect.right!, viewport, 'x');
		x = viewport.width - right - w;
	} else {
		throw new Error(`computeRectPx: rect needs left or right: ${JSON.stringify(rect)}`);
	}

	if (rect.transform) {
		const t = rect.transform.trim();
		const tx = t.match(/translateX\(\s*(-?\d+(?:\.\d+)?%)\s*\)/);
		if (tx) {
			x += (parseFloat(tx[1]) / 100) * w;
		}
	}

	let h: number;
	if (hasHeight) {
		h = parseLength(rect.height!, viewport, 'y');
	} else if (hasTop && hasBottom) {
		const top = parseLength(rect.top!, viewport, 'y');
		const bottom = parseLength(rect.bottom!, viewport, 'y');
		h = Math.max(0, viewport.height - top - bottom);
	} else if (hasIntrinsicHeight) {
		h = parseLength(rect.intrinsicHeight!, viewport, 'y');
	} else {
		throw new Error(`computeRectPx: rect needs height / top+bottom / intrinsicHeight: ${JSON.stringify(rect)}`);
	}

	let y: number;
	if (hasTop) {
		y = parseLength(rect.top!, viewport, 'y');
	} else if (hasBottom) {
		const bottom = parseLength(rect.bottom!, viewport, 'y');
		y = viewport.height - bottom - h;
	} else {
		throw new Error(`computeRectPx: rect needs top or bottom: ${JSON.stringify(rect)}`);
	}

	return { x, y, w, h };
}

export function rectsOverlap(a: PixelRect, b: PixelRect): boolean {
	return !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y);
}
