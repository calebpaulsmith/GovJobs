<!--
	QuickAdd — wraps any displayed value with a + button on hover/focus.
	Clicking + appends the value to the corresponding mapState.filters key.
	Single write path: always sets mapState.filters = { ...mapState.filters, ... }.
-->
<script lang="ts">
	import { mapState } from './store.svelte';

	export type QuickAddType = 'agency' | 'series' | 'grade' | 'payPlan' | 'hiringPath' | 'geography';

	let {
		type,
		value,
		label
	}: { type: QuickAddType; value: string; label?: string } = $props();

	const display = $derived(label ?? value);

	const active = $derived.by(() => {
		if (!value) return false;
		const f = mapState.filters;
		switch (type) {
			case 'agency':
				return f.agencies.includes(value.toUpperCase());
			case 'series':
				return f.series.some((s) => s.trim().toLowerCase() === value.trim().toLowerCase());
			case 'grade':
				return f.gradeMin === value;
			case 'payPlan':
				return f.payPlans.some((p) => p.trim().toUpperCase() === value.trim().toUpperCase());
			case 'hiringPath':
				return f.hiringPaths.some((h) => h.trim().toLowerCase() === value.trim().toLowerCase());
			case 'geography':
				return f.geographies.includes(value);
			default:
				return false;
		}
	});

	function add() {
		if (!value) return;
		const f = mapState.filters;
		switch (type) {
			case 'agency': {
				const code = value.toUpperCase();
				if (!f.agencies.includes(code)) {
					mapState.filters = { ...f, agencies: [...f.agencies, code] };
				}
				break;
			}
			case 'series': {
				const s = value.trim();
				if (s && !f.series.includes(s)) mapState.filters = { ...f, series: [...f.series, s] };
				break;
			}
			case 'grade':
				if (!f.gradeMin) mapState.filters = { ...f, gradeMin: value };
				break;
			case 'payPlan': {
				const plan = value.trim().toUpperCase();
				if (plan && !f.payPlans.includes(plan)) mapState.filters = { ...f, payPlans: [...f.payPlans, plan] };
				break;
			}
			case 'hiringPath': {
				const path = value.trim().toLowerCase();
				if (path && !f.hiringPaths.includes(path)) mapState.filters = { ...f, hiringPaths: [...f.hiringPaths, path] };
				break;
			}
			case 'geography':
				if (!f.geographies.includes(value)) {
					mapState.filters = { ...f, geographies: [...f.geographies, value] };
				}
				break;
		}
	}
</script>

<span class="qa" class:active>
	<span class="val">{display}</span>
	{#if !active && value}
		<button
			type="button"
			class="plus"
			onclick={add}
			title="Add {display} to filters"
			aria-label="Add {display} to filters"
		>+</button>
	{/if}
</span>

<style>
	.qa {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
	}
	.plus {
		display: none;
		appearance: none;
		background: var(--c-accent-bg, rgba(123, 208, 242, 0.12));
		border: 1px solid var(--c-accent, #7bd0f2);
		color: var(--c-accent, #7bd0f2);
		border-radius: 999px;
		width: 15px;
		height: 15px;
		font-size: 13px;
		line-height: 1;
		cursor: pointer;
		padding: 0;
		flex-shrink: 0;
		align-items: center;
		justify-content: center;
		transition: background 100ms ease, color 100ms ease;
	}
	.plus:hover {
		background: var(--c-accent, #7bd0f2);
		color: var(--c-apply-text, #06111f);
	}
	.plus:focus-visible {
		outline: 2px solid var(--c-accent, #7bd0f2);
		outline-offset: 2px;
	}
	.qa:hover .plus,
	.qa:focus-within .plus {
		display: flex;
	}
	.active .val {
		text-decoration: underline dotted var(--c-accent, #7bd0f2);
		text-underline-offset: 2px;
	}
</style>
