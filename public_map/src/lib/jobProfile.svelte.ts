// Local browser profile for viewed, saved, and hidden jobs.
// Stored in localStorage under key STORAGE_KEY, never sent to any server.
// Reactive via Svelte $state so components re-render on mutations.

const STORAGE_KEY = 'tgp.public_map.job_profile.v1';

interface SavedJob {
	ts: number;
	title: string;
	agency: string;
	close_date: string | null;
	url: string | null;
}

interface ProfileData {
	// id -> unix-ms timestamp of last view
	viewed: Record<string, number>;
	// id -> saved job metadata
	saved: Record<string, SavedJob>;
	// id -> unix-ms timestamp when hidden
	hidden: Record<string, number>;
}

function emptyProfile(): ProfileData {
	return { viewed: {}, saved: {}, hidden: {} };
}

function loadFromStorage(): ProfileData {
	if (typeof localStorage === 'undefined') return emptyProfile();
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (!raw) return emptyProfile();
		const parsed = JSON.parse(raw) as Partial<ProfileData>;
		return {
			viewed: parsed.viewed ?? {},
			saved: parsed.saved ?? {},
			hidden: parsed.hidden ?? {}
		};
	} catch {
		return emptyProfile();
	}
}

function saveToStorage(data: ProfileData): void {
	if (typeof localStorage === 'undefined') return;
	try {
		localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
	} catch {
		// quota exceeded or private browsing — silently degrade
	}
}

class JobProfile {
	private data = $state<ProfileData>(loadFromStorage());

	// --- Viewed ---

	markViewed(id: string): void {
		if (!id) return;
		this.data.viewed[id] = Date.now();
		saveToStorage(this.data);
	}

	isViewed(id: string): boolean {
		return id in this.data.viewed;
	}

	get viewedIds(): Set<string> {
		return new Set(Object.keys(this.data.viewed));
	}

	// --- Saved ---

	saveJob(id: string, meta: { title: string; agency: string; close_date: string | null; url: string | null }): void {
		if (!id) return;
		this.data.saved[id] = { ts: Date.now(), ...meta };
		saveToStorage(this.data);
	}

	unsaveJob(id: string): void {
		delete this.data.saved[id];
		saveToStorage(this.data);
	}

	isSaved(id: string): boolean {
		return id in this.data.saved;
	}

	get savedJobs(): Array<{ id: string } & SavedJob> {
		return Object.entries(this.data.saved)
			.map(([id, meta]) => ({ id, ...meta }))
			.sort((a, b) => b.ts - a.ts);
	}

	// --- Hidden ---

	hideJob(id: string): void {
		if (!id) return;
		this.data.hidden[id] = Date.now();
		saveToStorage(this.data);
	}

	unhideJob(id: string): void {
		delete this.data.hidden[id];
		saveToStorage(this.data);
	}

	isHidden(id: string): boolean {
		return id in this.data.hidden;
	}

	get hiddenIds(): Set<string> {
		return new Set(Object.keys(this.data.hidden));
	}

	get hiddenJobs(): Array<{ id: string; ts: number }> {
		return Object.entries(this.data.hidden)
			.map(([id, ts]) => ({ id, ts }))
			.sort((a, b) => b.ts - a.ts);
	}

	// Jobs that were viewed and are now closed (status 'closed' or close_date in the past).
	// Takes a detail index so the caller can cross-reference.
	viewedClosedJobs(details: Record<string, { title?: string; close_date?: string | null; url?: string | null; agency?: string }>): Array<{ id: string; title: string; close_date: string | null }> {
		const today = new Date();
		today.setHours(0, 0, 0, 0);
		return Object.keys(this.data.viewed)
			.map((id) => {
				const d = details[id];
				if (!d) return null;
				const cd = d.close_date ?? null;
				if (!cd) return null;
				const close = new Date(cd);
				close.setHours(0, 0, 0, 0);
				if (close >= today) return null;
				return { id, title: d.title ?? id, close_date: cd };
			})
			.filter((x): x is { id: string; title: string; close_date: string } => x !== null)
			.sort((a, b) => new Date(b.close_date!).getTime() - new Date(a.close_date!).getTime());
	}

	clear(): void {
		this.data = emptyProfile();
		saveToStorage(this.data);
	}
}

export const jobProfile = new JobProfile();
