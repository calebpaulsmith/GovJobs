// Display formatting for the overseas (DSSR) pay breakdown that the exporter
// precomputes into jobs_detail.json. Pure + unit-tested so JobCard stays a thin
// renderer and the honesty rules (sources, flags, withheld values) live in one
// place. No math here — the dollar amounts are computed once at export time by
// src/reference_data.overseas_compensation; we only format them.
import type { OverseasPay } from './data';

export interface OverseasPayDisplayLine {
	label: string; // "Post (hardship) differential (DSSR 500)"
	rate: string; // "35% of base pay" or "—"
	amount: string; // "$35,000", "est. $11,160", or "withheld"
	sourceUrl: string;
	withheld: boolean;
	estimated: boolean;
}

export interface OverseasPayDisplay {
	baseAmount: string; // "$100,000" | "—"
	lines: OverseasPayDisplayLine[];
	totalAmount: string; // "$170,000" | "—"
	matchLabel: string | null; // "Rome, ITALY · exact post" | "ITALY · country-level (approx)"
	notes: string[];
}

function money(value: number | null | undefined): string {
	if (value === null || value === undefined) return '—';
	return `$${Math.round(value).toLocaleString('en-US')}`;
}

function matchLabel(op: OverseasPay): string | null {
	const m = op.matched_post;
	if (!m) return null;
	const place = [m.post_name, m.country_name].filter(Boolean).join(', ');
	const precision = m.match === 'post' ? 'exact post' : 'country-level (approx)';
	return place ? `${place} · ${precision}` : precision;
}

export function overseasPayDisplay(op: OverseasPay): OverseasPayDisplay {
	const lines: OverseasPayDisplayLine[] = op.lines.map((line) => {
		const withheld = line.amount === null && line.pct !== null && line.pct !== 0;
		let amount: string;
		if (withheld) amount = 'withheld';
		else if (line.estimated && line.amount) amount = `est. ${money(line.amount)}`;
		else amount = money(line.amount);
		const rate = line.pct === null ? '—' : `${line.pct}% ${line.basis}`;
		return {
			label: `${line.label} (${line.dssr})`,
			rate,
			amount,
			sourceUrl: line.source_url,
			withheld,
			estimated: line.estimated
		};
	});
	return {
		baseAmount: money(op.base_salary),
		lines,
		totalAmount: money(op.estimated_total),
		matchLabel: matchLabel(op),
		notes: op.notes ?? []
	};
}
