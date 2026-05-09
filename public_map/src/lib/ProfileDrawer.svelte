<!--
	D.5.19 — Local profile drawer: Saved Jobs / Hidden Jobs / Viewed Closed.
	Opened via the profile button in the masthead. All data is localStorage-only.
-->
<script lang="ts">
	import { mapState } from './store.svelte';
	import { jobProfile } from './jobProfile.svelte';
	import { loadJobDetailsIndex } from './data';

	type Tab = 'saved' | 'hidden' | 'viewed-closed';
	let activeTab = $state<Tab>('saved');
	let details = $state<Record<string, { title?: string; close_date?: string | null; url?: string | null; agency?: string }>>({});

	$effect(() => {
		if (!mapState.profileOpen) return;
		loadJobDetailsIndex().then((idx) => {
			details = idx as Record<string, { title?: string; close_date?: string | null; url?: string | null; agency?: string }>;
		});
	});

	function close() {
		mapState.profileOpen = false;
	}

	function pickSavedJob(id: string) {
		mapState.profileOpen = false;
		// Open the job card by faking a selectedFeature with just an id.
		mapState.selectedFeature = {
			source: 'profile',
			label: 'Job card',
			properties: { id }
		};
	}

	function unhide(id: string) {
		jobProfile.unhideJob(id);
		// Reactively update mapState hidden set so the map re-renders.
		mapState.hiddenJobIds = jobProfile.hiddenIds;
	}

	const savedJobs = $derived(jobProfile.savedJobs);
	const hiddenJobs = $derived(jobProfile.hiddenJobs);
	const viewedClosed = $derived(jobProfile.viewedClosedJobs(details));
</script>

{#if mapState.profileOpen}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="overlay" onclick={close}></div>
	<aside class="drawer" aria-label="Your job profile">
		<div class="header">
			<h2>My Jobs</h2>
			<button type="button" class="close" onclick={close} aria-label="Close profile">✕</button>
		</div>
		<div class="tabs" role="tablist">
			<button type="button" role="tab" aria-selected={activeTab === 'saved'} class="tab" class:active={activeTab === 'saved'} onclick={() => (activeTab = 'saved')}>
				Saved {#if savedJobs.length > 0}<span class="count">{savedJobs.length}</span>{/if}
			</button>
			<button type="button" role="tab" aria-selected={activeTab === 'hidden'} class="tab" class:active={activeTab === 'hidden'} onclick={() => (activeTab = 'hidden')}>
				Hidden {#if hiddenJobs.length > 0}<span class="count">{hiddenJobs.length}</span>{/if}
			</button>
			<button type="button" role="tab" aria-selected={activeTab === 'viewed-closed'} class="tab" class:active={activeTab === 'viewed-closed'} onclick={() => (activeTab = 'viewed-closed')}>
				Viewed Closed {#if viewedClosed.length > 0}<span class="count">{viewedClosed.length}</span>{/if}
			</button>
		</div>

		<div class="body">
			{#if activeTab === 'saved'}
				{#if savedJobs.length === 0}
					<p class="empty">No saved jobs yet. Click "Save" on any job card.</p>
				{:else}
					<ul>
						{#each savedJobs as job (job.id)}
							<li>
								<button type="button" class="job-row" onclick={() => pickSavedJob(job.id)}>
									<div class="job-title">{job.title}</div>
									<div class="job-meta">{job.agency || '—'} · closes {job.close_date ?? '—'}</div>
								</button>
								<div class="actions">
									{#if job.url}
										<a href={job.url} target="_blank" rel="noreferrer noopener" class="action-btn">Apply ↗</a>
									{/if}
									<button type="button" class="action-btn danger" onclick={() => jobProfile.unsaveJob(job.id)}>
										Unsave
									</button>
								</div>
							</li>
						{/each}
					</ul>
				{/if}
			{:else if activeTab === 'hidden'}
				{#if hiddenJobs.length === 0}
					<p class="empty">No hidden jobs. Use the "Hide" button on any job card to remove it from the map.</p>
				{:else}
					<p class="note">Hidden jobs are excluded from the map, heat layer, and job lists by default.</p>
					<ul>
						{#each hiddenJobs as job (job.id)}
							{@const d = details[job.id]}
							<li>
								<div class="job-row static">
									<div class="job-title">{d?.title ?? job.id}</div>
									<div class="job-meta">closes {d?.close_date ?? '—'}</div>
								</div>
								<div class="actions">
									<button type="button" class="action-btn" onclick={() => unhide(job.id)}>
										Unhide
									</button>
								</div>
							</li>
						{/each}
					</ul>
				{/if}
			{:else}
				{#if viewedClosed.length === 0}
					<p class="empty">No viewed jobs have closed yet.</p>
				{:else}
					<ul>
						{#each viewedClosed as job (job.id)}
							<li>
								<div class="job-row static">
									<div class="job-title">{job.title}</div>
									<div class="job-meta">Closed {job.close_date}</div>
								</div>
							</li>
						{/each}
					</ul>
				{/if}
			{/if}
		</div>
	</aside>
{/if}

<style>
	.overlay {
		position: fixed;
		inset: 0;
		z-index: 19;
		background: rgba(0, 0, 0, 0.35);
	}
	.drawer {
		position: fixed;
		top: 0;
		right: 0;
		bottom: 0;
		width: min(360px, 90vw);
		z-index: 20;
		background: #0e1726;
		border-left: 1px solid #2a3a52;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 1rem 1rem 0.6rem;
		border-bottom: 1px solid #2a3a52;
	}
	h2 {
		margin: 0;
		font-size: 16px;
		font-weight: 600;
	}
	.close {
		appearance: none;
		border: none;
		background: none;
		color: #94a3b8;
		font-size: 16px;
		cursor: pointer;
		padding: 0.2rem 0.4rem;
		border-radius: 4px;
	}
	.close:hover { color: #e5edf5; background: rgba(255,255,255,0.07); }
	.tabs {
		display: flex;
		border-bottom: 1px solid #2a3a52;
		padding: 0 0.5rem;
	}
	.tab {
		appearance: none;
		border: none;
		background: none;
		color: #94a3b8;
		font-size: 12px;
		padding: 0.55rem 0.65rem;
		cursor: pointer;
		border-bottom: 2px solid transparent;
		display: flex;
		align-items: center;
		gap: 0.35rem;
		white-space: nowrap;
		transition: color 120ms ease, border-color 120ms ease;
	}
	.tab:hover { color: #e5edf5; }
	.tab.active { color: #7bd0f2; border-bottom-color: #7bd0f2; }
	.count {
		background: #4979b3;
		color: #fff;
		font-size: 10px;
		padding: 0.05rem 0.4rem;
		border-radius: 999px;
		font-weight: 700;
	}
	.body {
		flex: 1;
		overflow-y: auto;
		padding: 0.75rem 0.75rem;
	}
	.empty, .note {
		margin: 0.5rem 0;
		font-size: 12px;
		color: #94a3b8;
		line-height: 1.5;
	}
	ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}
	li {
		border: 1px solid #22344c;
		border-radius: 6px;
		padding: 0.5rem 0.65rem;
		background: rgba(20, 32, 50, 0.55);
	}
	.job-row {
		display: block;
		width: 100%;
		text-align: left;
		appearance: none;
		background: none;
		border: none;
		padding: 0;
		color: inherit;
		cursor: pointer;
	}
	.job-row.static { cursor: default; }
	.job-title {
		font-weight: 600;
		font-size: 12.5px;
		color: #e5edf5;
		line-height: 1.3;
	}
	.job-meta {
		margin-top: 0.2rem;
		font-size: 11px;
		color: #94a3b8;
	}
	.actions {
		display: flex;
		gap: 0.4rem;
		margin-top: 0.4rem;
		flex-wrap: wrap;
	}
	.action-btn {
		appearance: none;
		border: 1px solid #2c4870;
		background: rgba(28, 42, 64, 0.4);
		color: #cfd9e6;
		padding: 0.2rem 0.55rem;
		border-radius: 999px;
		font-size: 11px;
		cursor: pointer;
		text-decoration: none;
		display: inline-block;
		transition: border-color 120ms ease, color 120ms ease;
	}
	.action-btn:hover { border-color: #7bd0f2; color: #7bd0f2; }
	.action-btn.danger { border-color: #6b2020; color: #f7a0a0; }
	.action-btn.danger:hover { border-color: #dc5050; }
</style>
