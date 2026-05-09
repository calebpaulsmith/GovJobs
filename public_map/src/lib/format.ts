import { METRICS, formatMetricValue, type MetricKey } from './metrics';

export function propString(
	props: Record<string, unknown> | null | undefined,
	key: string,
	fallback = '—'
): string {
	const value = props?.[key];
	if (value === null || value === undefined || value === '') return fallback;
	return String(value);
}

export function propNumber(
	props: Record<string, unknown> | null | undefined,
	key: string
): number | null {
	const value = props?.[key];
	if (value === null || value === undefined || value === '') return null;
	const n = Number(value);
	return Number.isFinite(n) ? n : null;
}

export function metricValue(props: Record<string, unknown>, key: MetricKey): string {
	const metric = METRICS[key];
	return formatMetricValue(metric, propNumber(props, metric.property));
}

export function countValue(value: unknown): string {
	const n = Number(value ?? 0);
	return Number.isFinite(n) ? Math.round(n).toLocaleString() : '0';
}

export function money(value: unknown): string {
	const n = Number(value);
	if (!Number.isFinite(n)) return '—';
	return n.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}

export function percent(value: unknown, digits = 1): string {
	const n = Number(value);
	if (!Number.isFinite(n)) return '—';
	return `${n.toFixed(digits)}%`;
}

export function salaryRange(min: unknown, max: unknown, type: unknown): string {
	const lo = Number(min);
	const hi = Number(max);
	if (!Number.isFinite(lo) && !Number.isFinite(hi)) return '—';
	const suffix = String(type ?? '').toLowerCase() === 'per_hour' ? '/hr' : '/yr';
	if (Number.isFinite(lo) && Number.isFinite(hi)) return `${money(lo)}–${money(hi)}${suffix}`;
	return `${money(Number.isFinite(lo) ? lo : hi)}${suffix}`;
}

export function gradeRange(payPlan: unknown, low: unknown, high: unknown): string {
	const plan = propFromValue(payPlan);
	const lo = propFromValue(low);
	const hi = propFromValue(high);
	if (lo === '—' && hi === '—') return plan;
	if (lo !== '—' && hi !== '—' && lo !== hi) return `${plan}-${lo}/${hi}`;
	return `${plan}-${lo !== '—' ? lo : hi}`;
}

function propFromValue(value: unknown): string {
	if (value === null || value === undefined || value === '') return '—';
	return String(value);
}

export type UrgencyLevel = 'critical' | 'soon' | null;
export interface UrgencyBadge {
	text: string;
	level: UrgencyLevel;
}

export function urgencyBadge(closeDate: string | null | undefined): UrgencyBadge {
	if (!closeDate) return { text: '', level: null };
	const today = new Date();
	today.setHours(0, 0, 0, 0);
	const close = new Date(closeDate);
	close.setHours(0, 0, 0, 0);
	const days = Math.round((close.getTime() - today.getTime()) / 86400000);
	if (days < 0) return { text: '', level: null };
	if (days === 0) return { text: 'Closes today', level: 'critical' };
	if (days === 1) return { text: 'Closes tomorrow', level: 'critical' };
	if (days <= 7) return { text: `Closes in ${days} days`, level: 'soon' };
	return { text: '', level: null };
}
