import { describe, expect, it } from 'vitest';
import {
	BREAKPOINT_MIN_WIDTH,
	COEXISTING_SLOTS,
	LAYOUT_RECTS,
	REFERENCE_VIEWPORTS,
	computeRectPx,
	layoutCssBlock,
	parseLength,
	pickBreakpoint,
	rectsOverlap,
	slotCssVarName
} from './layout';
import type { Breakpoint, LayoutSlot, Rect } from './layout';

describe('parseLength', () => {
	const vp = { width: 1440, height: 900 };

	it('handles bare units', () => {
		expect(parseLength('1rem', vp, 'x')).toBe(16);
		expect(parseLength('5.15rem', vp, 'x')).toBeCloseTo(82.4);
		expect(parseLength('100px', vp, 'x')).toBe(100);
		expect(parseLength('50%', vp, 'x')).toBe(720);
		expect(parseLength('100vw', vp, 'x')).toBe(1440);
		expect(parseLength('100vh', vp, 'y')).toBe(900);
	});

	it('handles min() and max()', () => {
		expect(parseLength('min(24rem, calc(100vw - 2rem))', vp, 'x')).toBe(384);
		// 72rem = 1152, calc(100vw - 2rem) = 1408 → min = 1152.
		expect(parseLength('min(72rem, calc(100vw - 2rem))', vp, 'x')).toBe(1152);
		expect(parseLength('max(10rem, 20rem)', vp, 'x')).toBe(320);
	});

	it('handles calc() with subtraction', () => {
		expect(parseLength('calc(100vw - 2rem)', vp, 'x')).toBe(1408);
		expect(parseLength('calc(100vh - 7.5rem)', vp, 'y')).toBe(780);
	});

	it('handles initial / auto / none as zero', () => {
		expect(parseLength('initial', vp, 'x')).toBe(0);
		expect(parseLength('auto', vp, 'x')).toBe(0);
	});

	it('throws on unsupported expressions', () => {
		expect(() => parseLength('hsl(0,0,0)', vp, 'x')).toThrow();
	});
});

describe('pickBreakpoint', () => {
	it('selects the right breakpoint for each width', () => {
		expect(pickBreakpoint(1920)).toBe('desktop');
		expect(pickBreakpoint(BREAKPOINT_MIN_WIDTH.desktop)).toBe('desktop');
		expect(pickBreakpoint(BREAKPOINT_MIN_WIDTH.desktop - 1)).toBe('tablet');
		expect(pickBreakpoint(BREAKPOINT_MIN_WIDTH.tablet)).toBe('tablet');
		expect(pickBreakpoint(BREAKPOINT_MIN_WIDTH.tablet - 1)).toBe('mobile');
		expect(pickBreakpoint(0)).toBe('mobile');
	});
});

describe('computeRectPx', () => {
	const vp = { width: 1440, height: 900 };

	it('handles top-left + width', () => {
		const r = computeRectPx(
			{ top: '5.15rem', left: '1rem', width: '24rem', intrinsicHeight: '14rem' },
			vp
		);
		expect(r.x).toBe(16);
		expect(r.y).toBeCloseTo(82.4);
		expect(r.w).toBe(384);
	});

	it('handles top-right + width (right anchor)', () => {
		const r = computeRectPx(
			{ top: '5.25rem', right: '1rem', width: '24rem', intrinsicHeight: '14rem' },
			vp
		);
		expect(r.w).toBe(384);
		expect(r.x).toBe(1440 - 16 - 384);
	});

	it('handles bottom-left + width', () => {
		const r = computeRectPx({ bottom: '0.4rem', right: '0.6rem', intrinsicWidth: '20rem', intrinsicHeight: '1.5rem' }, vp);
		expect(r.h).toBeCloseTo(24);
		expect(r.y).toBeCloseTo(900 - 6.4 - 24);
	});

	it('handles transform: translateX(-50%) for centered slots', () => {
		const r = computeRectPx(
			{ top: '1rem', left: '50%', transform: 'translateX(-50%)', intrinsicWidth: '32rem', intrinsicHeight: '2.5rem' },
			vp
		);
		expect(r.w).toBe(512);
		expect(r.x).toBe(720 - 256);
	});

	it('handles left+right (computed width)', () => {
		const r = computeRectPx({ top: '0.5rem', left: '0.5rem', right: '0.5rem', intrinsicHeight: '4.5rem' }, vp);
		expect(r.x).toBe(8);
		expect(r.w).toBe(1440 - 16);
	});

	it('throws when neither left nor right is set', () => {
		expect(() => computeRectPx({ top: '1rem', intrinsicHeight: '1rem' }, vp)).toThrow();
	});
});

describe('LAYOUT_RECTS structural integrity', () => {
	it('every slot defines all three breakpoints', () => {
		for (const slot of Object.keys(LAYOUT_RECTS) as LayoutSlot[]) {
			const slotRects = LAYOUT_RECTS[slot];
			expect(slotRects.desktop, `${slot}.desktop must be defined or null`).not.toBeUndefined();
			expect(slotRects.tablet).not.toBeUndefined();
			expect(slotRects.mobile).not.toBeUndefined();
		}
	});

	it('every coexisting slot has a non-null rect at its breakpoint', () => {
		for (const bp of ['desktop', 'tablet', 'mobile'] as Breakpoint[]) {
			for (const slot of COEXISTING_SLOTS[bp]) {
				expect(LAYOUT_RECTS[slot][bp], `${slot}.${bp} must not be null if it coexists`).not.toBeNull();
			}
		}
	});

	it('every non-null rect can be evaluated to pixels at its breakpoint', () => {
		for (const bp of ['desktop', 'tablet', 'mobile'] as Breakpoint[]) {
			const vp = REFERENCE_VIEWPORTS[bp];
			for (const slot of Object.keys(LAYOUT_RECTS) as LayoutSlot[]) {
				const rect = LAYOUT_RECTS[slot][bp];
				if (!rect) continue;
				const px = computeRectPx(rect, vp);
				expect(px.w).toBeGreaterThan(0);
				expect(px.h).toBeGreaterThan(0);
				// Slot must sit within the viewport (small overflow at right edge tolerated for centered max-widths).
				expect(px.y).toBeGreaterThanOrEqual(0);
			}
		}
	});
});

describe('breakpoint overlap test (D.5.0 exit criterion)', () => {
	for (const bp of ['desktop', 'tablet', 'mobile'] as Breakpoint[]) {
		it(`no two coexisting slots overlap at ${bp} (${REFERENCE_VIEWPORTS[bp].width}x${REFERENCE_VIEWPORTS[bp].height})`, () => {
			const vp = REFERENCE_VIEWPORTS[bp];
			const slots = COEXISTING_SLOTS[bp];

			const rects = new Map(
				slots.map((s) => [s, computeRectPx(LAYOUT_RECTS[s][bp] as Rect, vp)] as const)
			);

			for (let i = 0; i < slots.length; i++) {
				for (let j = i + 1; j < slots.length; j++) {
					const a = slots[i];
					const b = slots[j];
					const ra = rects.get(a)!;
					const rb = rects.get(b)!;
					if (rectsOverlap(ra, rb)) {
						throw new Error(
							`Overlap at ${bp}: ${a} ${JSON.stringify(ra)} vs ${b} ${JSON.stringify(rb)}`
						);
					}
				}
			}
		});
	}
});

describe('layoutCssBlock', () => {
	it('emits a :root block plus two media queries', () => {
		const css = layoutCssBlock();
		expect(css).toMatch(/^\/\* Generated by/);
		expect(css).toContain(':root {');
		expect(css).toContain(`@media (max-width: ${BREAKPOINT_MIN_WIDTH.desktop - 1}px)`);
		expect(css).toContain(`@media (max-width: ${BREAKPOINT_MIN_WIDTH.tablet - 1}px)`);
	});

	it('includes a CSS variable for every (slot, prop) at desktop', () => {
		const css = layoutCssBlock();
		expect(css).toContain(slotCssVarName('filters', 'top'));
		expect(css).toContain(slotCssVarName('feature', 'right'));
		expect(css).toContain(slotCssVarName('metric', 'width'));
	});
});
