// WebKit (iOS Safari engine) test for the Browse Postings pager on mobile:
// 50 rows per page, a compact top pager beside the count (so paging never
// depends on reaching the bottom pager, which iPhone can clip after the
// keyboard closes), Enter in "Search within results" dismisses the keyboard,
// and both pagers jump the list back to the top.
//
// Usage: `npm run dev` in another terminal, then
//   node tests/list-pager-webkit.spec.mjs

import { webkit, devices } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const out = (...a) => console.log('[wk-pager]', ...a);
let failures = 0;
const check = (cond, msg) => {
	out(`${cond ? 'PASS' : 'FAIL'} — ${msg}`);
	if (!cond) failures++;
};

const browser = await webkit.launch();
const ctx = await browser.newContext({ ...devices['iPhone 13'] });
await ctx.route(/events\.mapbox\.com/, (route) => route.fulfill({ status: 204, body: '' }));
const page = await ctx.newPage();
await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(2000);
await page.locator('.grabber').click();
await page.waitForTimeout(800);

const st = () =>
	page.evaluate(() => {
		const q = (s) => document.querySelector('.sheet ' + s);
		return {
			rows: document.querySelectorAll('.sheet .postings-host li').length,
			mini: q('.mini-pager .page-indicator')?.textContent ?? null,
			bottom: q('nav.pager .page-indicator')?.textContent ?? null,
			scrollTop: q('.postings')?.scrollTop ?? null
		};
	});

let s = await st();
out('start', JSON.stringify(s));
check(s.rows === 50, `first page shows 50 rows (got ${s.rows})`);
check(s.mini === '1–50', `top pager shows 1–50 (got ${s.mini})`);

const box = page.locator('.sheet input[placeholder^="Search within"]');
await box.tap();
await box.fill('engineer');
await page.keyboard.press('Enter');
await page.waitForTimeout(700);
s = await st();
const focused = await page.evaluate(() => document.activeElement?.tagName ?? null);
out('after search', JSON.stringify(s), 'focused:', focused);
check(focused !== 'INPUT', 'Enter in the search box blurs it (dismisses the keyboard)');
check(s.mini !== null && s.bottom !== null, 'both pagers still present after an in-list search');

if (s.bottom && /of [2-9]|of \d\d/.test(s.bottom)) {
	await page.locator('.sheet .mini-pager button[aria-label="Next page"]').tap();
	await page.waitForTimeout(400);
	s = await st();
	check(s.mini === '51–100', `top pager Next advances a page (got ${s.mini})`);

	await page.evaluate(() => {
		const sc = document.querySelector('.sheet .postings');
		sc.scrollTop = sc.scrollHeight;
	});
	await page.locator('.sheet nav.pager button[aria-label="Next page"]').tap();
	await page.waitForTimeout(400);
	s = await st();
	check(s.mini === '101–150', `bottom pager Next advances a page (got ${s.mini})`);
	check(s.scrollTop === 0, `page change scrolls the list back to the top (scrollTop ${s.scrollTop})`);
} else {
	out('SKIP multi-page checks — search matched ≤ 1 page in this bundle');
}

await browser.close();
out(failures ? `${failures} CHECK(S) FAILED` : 'ALL CHECKS PASSED');
process.exit(failures ? 1 : 0);
