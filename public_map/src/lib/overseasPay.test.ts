import { describe, it, expect } from 'vitest';
import { overseasPayDisplay } from './overseasPay';
import type { OverseasPay } from './data';

const rome: OverseasPay = {
	base_salary: 100000,
	matched_post: { country_name: 'ITALY', post_name: 'Rome', match: 'post' },
	lines: [
		{ label: 'Post (hardship) differential', dssr: 'DSSR 500', pct: 0, basis: '% of base pay',
		  amount: 0, estimated: false, source_url: 'https://allowances.state.gov/Web920/hardship.asp', effective_date: '2026-06-14' },
		{ label: 'Post (COLA) allowance', dssr: 'DSSR 220', pct: 30, basis: '% of spendable income',
		  amount: 11160, estimated: true, assumption: 'family size 1',
		  source_url: 'https://allowances.state.gov/Web920/cola.asp', effective_date: '2026-06-14' }
	],
	estimated_total: 111160,
	notes: [],
	family_size: 1
};

describe('overseasPayDisplay', () => {
	it('formats base, exact lines, and a flagged COLA estimate', () => {
		const d = overseasPayDisplay(rome);
		expect(d.baseAmount).toBe('$100,000');
		expect(d.totalAmount).toBe('$111,160');
		expect(d.matchLabel).toBe('Rome, ITALY · exact post');
		const hardship = d.lines[0];
		expect(hardship.rate).toBe('0% % of base pay');
		expect(hardship.amount).toBe('$0');
		const cola = d.lines[1];
		expect(cola.amount).toBe('est. $11,160'); // estimate flagged inline
		expect(cola.estimated).toBe(true);
		expect(cola.withheld).toBe(false);
	});

	it('marks a country-level (non-exact) match as approximate', () => {
		const d = overseasPayDisplay({ ...rome, matched_post: { country_name: 'ITALY', post_name: 'Other', match: 'country' } });
		expect(d.matchLabel).toBe('Other, ITALY · country-level (approx)');
	});

	it('shows "withheld" (not $0) when a non-zero allowance has no dollar value', () => {
		const d = overseasPayDisplay({
			...rome,
			lines: [{ label: 'Post (COLA) allowance', dssr: 'DSSR 220', pct: 30, basis: '% of spendable income',
				amount: null, estimated: true, source_url: 'x' }],
			notes: ['Post (COLA) allowance dollar estimate withheld: salary outside the table.']
		});
		expect(d.lines[0].withheld).toBe(true);
		expect(d.lines[0].amount).toBe('withheld');
		expect(d.notes.length).toBe(1);
	});

	it('handles a missing matched post (no label)', () => {
		const d = overseasPayDisplay({ ...rome, matched_post: null });
		expect(d.matchLabel).toBeNull();
	});
});
