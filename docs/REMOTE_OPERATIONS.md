# REMOTE_OPERATIONS.md

How to keep the public map fresh without sitting at your laptop.

---

## TL;DR

1. The map auto-refreshes **daily at 09:00 UTC** via GitHub Actions.
2. You can trigger an extra refresh from your phone in three taps via the GitHub mobile app.
3. Cowork (Claude on phone) is the right tool for ad-hoc work like fixing bugs or trying new features remotely; routine refreshes should stay on GitHub Actions.

---

## One-time setup (do this from your phone before traveling)

### Add USAJOBS credentials as repo secrets

1. Open your phone browser to `https://github.com/calebpaulsmith/GovJobs/settings/secrets/actions`
2. Tap **New repository secret** twice and add:
   - **Name:** `USAJOBS_USER_AGENT` · **Value:** `calebpaulsmith@gmail.com` (your email)
   - **Name:** `USAJOBS_AUTHORIZATION_KEY` · **Value:** your USAJOBS API key (the same one in your local `.env`)
3. The values are encrypted; even you can't read them back, only update or delete.

That's it for setup. The workflow file is already committed at `.github/workflows/refresh-public-map.yml`.

---

## How the auto-refresh works

| Step | What happens | Where it runs |
|---|---|---|
| 1 | GitHub fires the cron at 09:00 UTC | GitHub Actions runner (Ubuntu) |
| 2 | Reference data refreshes (states, counties, locality pay, BEA RPP, agency codes) | Runner |
| 3 | Federal-wide USAJOBS Search import (up to 50 pages = 25,000 postings) | Runner → USAJOBS API |
| 4 | Bundle re-exported to `public_map/static/data/` | Runner |
| 5 | Bundle committed + pushed to `master` (only if changed) | Runner → GitHub |
| 6 | Cloudflare Pages detects the push and rebuilds the live site | Cloudflare |

Total runtime: 5–15 minutes per cycle. Free GitHub Actions tier allows ~2,000 minutes/month for private repos and unlimited for public — well within budget.

---

## Triggering a manual refresh from your phone

### Option A — GitHub mobile app (easiest, 4 taps)

1. Open the **GitHub** app
2. Navigate to your repo → **Actions** tab
3. Tap **Refresh public map** in the workflow list
4. Tap **Run workflow** → optionally adjust `max_pages` → **Run workflow**

The job runs in 5–15 minutes. You can watch the live log in the same screen.

### Option B — Phone browser (works from any phone)

1. Open `https://github.com/calebpaulsmith/GovJobs/actions/workflows/refresh-public-map.yml`
2. Tap **Run workflow**
3. Pick the branch (master) and tap **Run workflow**

### Option C — Cowork (Claude on phone)

When you have ad-hoc work — "the map looks wrong, fix the COL formula", "ship a new metric", "investigate why it failed last night" — open a Cowork session and tell Claude. From the Cowork session Claude can:

- Trigger the workflow: `gh workflow run refresh-public-map.yml -f max_pages=100`
- Watch progress: `gh run watch`
- Read the latest run: `gh run view --log`
- Edit code, commit, push (which triggers the next cron + an immediate Cloudflare rebuild)

For Cowork to call `gh`, the session needs a `GH_TOKEN` in its environment or a logged-in `gh auth` state. Set this up the first time you start a Cowork session for this repo and it persists.

USAJOBS credentials: Cowork doesn't need them as long as you're triggering the GitHub Action (the secrets stay in GitHub). If you ever want Cowork to run `python scripts/refresh_postings.py` directly, you'd need to paste your `.env` into the Cowork environment — which is fine but extra work, so prefer the workflow-trigger path.

---

## Watching the live site

The custom domain `map.thegrandpipeline.com` is the production URL (the app serves at the subdomain root; `/` redirects to `/browse`). Cloudflare Pages gives every deploy its own permanent URL like `9202521b.govjobs-map.pages.dev` — those URLs **never update**, they snapshot one specific deploy. Always check the production URL to see "the latest live map."

To find the latest preview/deploy URL, open `https://dash.cloudflare.com/?to=/:account/pages/view/govjobs-map` from your phone.

---

## What if something breaks while you're away

### Live map shows stale data

- **First check:** is the workflow failing? `https://github.com/calebpaulsmith/GovJobs/actions` — red ❌ next to recent runs means the cron crashed.
- **Common causes:**
  - USAJOBS rate-limited (workflow retries automatically; will succeed on the next cron)
  - USAJOBS API outage (wait it out)
  - Cloudflare Pages deploy failed (check Cloudflare dashboard; usually caused by a file > 25 MiB — the slimmed export keeps `jobs.geojson` at ~18 MB so this is unlikely, but keep an eye on it as the corpus grows)

### "I need to ship a code fix from my phone"

Open Cowork. Tell Claude what's wrong and what you want changed. Claude commits to a feature branch, opens a PR, you approve in the GitHub mobile app, merge → cron picks up the next run.

### "I need to roll back a bad deploy"

In the GitHub mobile app: navigate to **Code → Commits**, find the last good commit, tap **\<>** (browse files at this commit), then use Cloudflare Pages dashboard to redeploy that commit. Or just push a `git revert` from a Cowork session.

---

## Tuning the cron

To change the schedule, edit `.github/workflows/refresh-public-map.yml`, line `- cron: '0 9 * * *'`:

| Cron | Cadence |
|---|---|
| `'0 9 * * *'` | daily at 09:00 UTC (default) |
| `'0 9,21 * * *'` | twice daily, 09:00 and 21:00 UTC |
| `'0 */6 * * *'` | every 6 hours |
| `'0 9 * * 1-5'` | weekdays only at 09:00 UTC |

Validate at <https://crontab.guru>.

---

## What this does NOT cover

- HistoricJoa bulk imports (per ADR-0029, those are now on-demand via the Cloudflare Pages Function — no scheduled refresh needed for historic data).
- OPM workforce file ingestion (still manual; OPM publishes files quarterly and they require operator review).
- Pay table updates (per ADR-0018, pay scales need the manual diff-review step in `pages/11_Public_Map_Admin.py` before going live, not auto-commit).
