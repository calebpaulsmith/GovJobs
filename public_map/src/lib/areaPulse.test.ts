import { describe, it, expect } from 'vitest';
import { computeAreaPulse, MIN_BASELINE_OPENINGS } from './areaPulse';
import type { Feature, JobDetails } from './data';

const NOW = new Date('2026-06-12T12:00:00Z');
const AREA = { scope: 'state', code: 'IL', label: 'Illinois' };

function job(overrides: Partial<JobDetails> = {}): JobDetails {
	return {
		id: Math.floor(Math.random() * 1e9),
		title: 'Analyst',
		agency: 'FEMA',
		open_date: '2026-06-10',
		close_date: '2026-06-30',
		...overrides
	} as JobDetails;
}

function closedFeature(id: string, openDate: string | null): Feature {
	return {
		type: 'Feature',
		geometry: { type: 'Point', coordinates: [-87, 41] },
		properties: { id, open_date: openDate, status: 'closed' }
	} as unknown as Feature;
}

/** N closed postings opened weekly through the baseline window. */
function baselineClosed(n: number): Feature[] {
	const out: Feature[] = [];
	for (let i = 0; i < n; i++) {
		const daysAgo = 10 + ((i * 5) % 70); // spread across [now-80, now-10]
		const d = new Date(NOW.getTime() - daysAgo * 86_400_000);
		out.push(closedFeature(`c${i}`, d.toISOString().slice(0, 10)));
	}
	return out;
}

describe('computeAreaPulse', () => {
	it('counts the four headline numbers from open postings', () => {
		const jobs = [
			job({ open_date: '2026-06-11', close_date: '2026-06-13' }), // new + closing soon
			job({ open_date: '2026-05-01', close_date: '2026-06-14' }), // closing soon
			job({ open_date: '2026-05-01', close_date: '2026-07-30' }),
			job({ open_date: '2026-06-08', close_date: '2026-07-08' }) // new
		];
		const pulse = computeAreaPulse(jobs, [], AREA, NOW);
		expect(pulse.openPostings).toBe(4);
		expect(pulse.newLast7d).toBe(2);
		expect(pulse.closingSoon3d).toBe(2);
		expect(pulse.scope).toBe('state');
		expect(pulse.code).toBe('IL');
	});

	it('computes the median posting window in days', () => {
		const jobs = [
			job({ open_date: '2026-06-01', close_date: '2026-06-11' }), // 10
			job({ open_date: '2026-06-01', close_date: '2026-06-21' }), // 20
			job({ open_date: '2026-06-01', close_date: '2026-07-31' }) // 60
		];
		expect(computeAreaPulse(jobs, [], AREA, NOW).medianWindowDays).toBe(20);
		// Even count -> mean of middle two: (10+20)/2 = 15.
		expect(computeAreaPulse(jobs.slice(0, 2), [], AREA, NOW).medianWindowDays).toBe(15);
	});

	it('skips invalid or inverted date pairs from the median', () => {
		const jobs = [
			job({ open_date: '2026-06-01', close_date: '2026-05-01' }), // inverted
			job({ open_date: null as unknown as string, close_date: '2026-06-20' }),
			job({ open_date: '2026-06-01', close_date: 'garbage' })
		];
		expect(computeAreaPulse(jobs, [], AREA, NOW).medianWindowDays).toBeNull();
	});

	it('emits no delta or annotation when the baseline is too thin', () => {
		const pulse = computeAreaPulse(
			[job()],
			baselineClosed(MIN_BASELINE_OPENINGS - 1),
			AREA,
			NOW
		);
		expect(pulse.deltas).toBeUndefined();
		expect(pulse.annotation).toBeNull();
	});

	it('emits a delta + annotation once the baseline is thick enough', () => {
		const jobs = [
			job({ open_date: '2026-06-11' }),
			job({ open_date: '2026-06-10' }),
			job({ open_date: '2026-06-09' })
		];
		const pulse = computeAreaPulse(jobs, baselineClosed(12), AREA, NOW);
		// weeklyAvg = 12 / (83/7) ≈ 1.012; (3 - 1.012)/1.012 ≈ +196%.
		expect(pulse.deltas?.newLast7d).toBe(196);
		expect(pulse.annotation).toContain('above the trailing-90-day weekly average for Illinois');
	});

	it('dedupes multi-location closed features by posting id', () => {
		// 8 distinct postings each appearing twice — baseline must count 8, not 16.
		const doubled = [...baselineClosed(8), ...baselineClosed(8)];
		const pulse = computeAreaPulse([job({ open_date: '2026-06-11' })], doubled, AREA, NOW);
		// weeklyAvg = 8 / (83/7) ≈ 0.675; delta = (1-0.675)/0.675 ≈ +48%.
		expect(pulse.deltas?.newLast7d).toBe(48);
	});

	it('open postings opened in the baseline window count toward the baseline', () => {
		// 8 open postings opened 30 days ago + 1 opened this week.
		const old = Array.from({ length: 8 }, (_, i) =>
			job({ open_date: '2026-05-13', close_date: '2026-07-30', id: i })
		);
		const pulse = computeAreaPulse([...old, job({ open_date: '2026-06-11' })], [], AREA, NOW);
		expect(pulse.deltas?.newLast7d).toBeDefined();
	});

	it('uses a below-average annotation when this week is slow', () => {
		const pulse = computeAreaPulse(
			[job({ open_date: '2026-01-01', close_date: '2026-08-01' })],
			baselineClosed(20),
			AREA,
			NOW
		);
		expect(pulse.deltas?.newLast7d).toBeLessThan(0);
		expect(pulse.annotation).toContain('below the trailing-90-day weekly average');
	});

	it('says "nationwide" instead of "for Nationwide" at national scope', () => {
		const pulse = computeAreaPulse(
			[job({ open_date: '2026-06-11' })],
			baselineClosed(12),
			{ scope: 'nationwide', code: '', label: 'Nationwide' },
			NOW
		);
		expect(pulse.annotation).toContain('weekly average nationwide');
	});

	it('handles empty inputs without claims', () => {
		const pulse = computeAreaPulse([], [], AREA, NOW);
		expect(pulse).toMatchObject({
			openPostings: 0,
			newLast7d: 0,
			closingSoon3d: 0,
			medianWindowDays: null,
			annotation: null
		});
		expect(pulse.deltas).toBeUndefined();
	});
});
