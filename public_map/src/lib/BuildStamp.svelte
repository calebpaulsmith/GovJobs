<!--
	Thin status strip under the masthead: which build/version is deployed and
	when the USAJOBS postings were last imported.

	• Version comes from Vite `define` (CF_PAGES_* at build time). On a PR preview
	  deploy the branch is the PR's head branch; on production it's `master`. The
	  7-char commit SHA is the unambiguous identifier — `title` carries the full
	  branch + SHA + build time on hover/long-press.
	• "USAJOBS data" is the last current-search import completion time from the
	  bundle manifest (posting_coverage.last_current_import_completed_at), falling
	  back to the bundle generated_at. Honest about provenance: this is when the
	  postings were pulled, not merely when the page loaded.
-->
<script lang="ts">
	import { mapState } from './store.svelte';

	const sha = __BUILD_SHA__;
	const branch = __BUILD_BRANCH__;
	const buildTime = __BUILD_TIME__;

	const version =
		branch === 'master' ? 'prod' : branch === 'local' ? 'dev' : branch.replace(/^claude\//, '');

	function fmtDate(iso: string | null | undefined): string {
		if (!iso) return 'unknown';
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return 'unknown';
		return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
	}

	const usajobsUpdated = $derived(
		mapState.manifest?.posting_coverage?.last_current_import_completed_at ??
			mapState.manifest?.generated_at ??
			null
	);

	const title = $derived(
		`Build: ${branch} @ ${sha}\n` +
			`Built: ${new Date(buildTime).toLocaleString()}\n` +
			`USAJOBS postings last imported: ${usajobsUpdated ? new Date(usajobsUpdated).toLocaleString() : 'unknown'}`
	);
</script>

<div class="build-stamp" {title}>
	<span class="ver">{version} · {sha}</span>
	<span class="data">USAJOBS data: {fmtDate(usajobsUpdated)}</span>
</div>

<style>
	.build-stamp {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.2rem 0.75rem;
		background: var(--c-bg, #06111f);
		border-bottom: 1px solid var(--c-border-subtle, #22344c);
		font-size: 10px;
		font-weight: 600;
		color: var(--c-muted, #94a3b8);
		white-space: nowrap;
		overflow: hidden;
	}
	.ver {
		color: var(--c-accent, #7bd0f2);
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.data {
		flex-shrink: 0;
	}
</style>
