"""One-off sampler for USAJOBS + OPM data — run before the importer exists.

Pulls a small FEMA-focused sample from each USAJOBS endpoint and HEAD-probes
OPM landing pages. Saves raw JSON to data/raw/{source}/{YYYYMMDD}/...

Run: python scripts/sample_data.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import load_config  # noqa: E402

cfg = load_config()
if not cfg.has_usajobs_credentials:
    print("ERROR: USAJOBS credentials missing from .env. Aborting.")
    sys.exit(1)

HEADERS = {
    "Host": "data.usajobs.gov",
    "User-Agent": cfg.usajobs_user_agent,
    "Authorization-Key": cfg.usajobs_authorization_key,
}

DAY = datetime.now(timezone.utc).strftime("%Y%m%d")
RAW = REPO / "data" / "raw"


def save(source: str, name: str, payload: dict, status: int, params: dict, url: str) -> Path:
    out = RAW / source / DAY / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    wrapped = {
        "_meta": {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "params": params,
            "status_code": status,
        },
        "data": payload,
    }
    out.write_text(json.dumps(wrapped, indent=2), encoding="utf-8")
    return out


def fetch(label: str, url: str, params: dict, sleep: float = 1.0) -> tuple[dict, int]:
    print(f"\n--- {label} ---")
    print(f"GET {url}")
    print(f"   params: {params}")
    r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    print(f"   HTTP {r.status_code}  ({len(r.content):,} bytes)")
    if r.status_code != 200:
        snippet = r.text[:400].replace("\n", " ")
        print(f"   BODY: {snippet}")
        time.sleep(sleep)
        return {}, r.status_code
    time.sleep(sleep)
    try:
        return r.json(), 200
    except Exception as e:
        print(f"   JSON parse error: {e}")
        return {"_raw_text": r.text[:2000]}, 200


def first_path(d: dict, paths: list[list[str]]):
    """Try to fetch the first key chain that exists. Returns (value, path_used)."""
    for p in paths:
        cur = d
        ok = True
        for k in p:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if ok:
            return cur, ".".join(p)
    return None, None


def find_control_number(hist_payload: dict) -> str | None:
    """HistoricJoa returns a list of records; look for the unique announcement key."""
    for path in [["data"], ["Data"], ["SearchResult", "SearchResultItems"]]:
        cur = hist_payload
        for k in path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                cur = None
                break
        if isinstance(cur, list) and cur:
            sample = cur[0]
            for k in (
                "usajobsControlNumber",
                "UsajobsControlNumber",
                "controlNumber",
                "ControlNumber",
                "announcementNumber",
                "AnnouncementNumber",
            ):
                if k in sample:
                    return str(sample[k])
    return None


# ---------------------------------------------------------------------------
# 1. Search — FEMA
# Try OrganizationCodes=HSBC first; fallback to Keyword=FEMA.

search_payload, status = fetch(
    "USAJOBS Search (FEMA via OrganizationCodes=HSBC)",
    "https://data.usajobs.gov/api/Search",
    {"OrganizationCodes": "HSBC", "ResultsPerPage": 25, "Page": 1},
)
sr = search_payload.get("SearchResult", {}) if isinstance(search_payload, dict) else {}
count = sr.get("SearchResultCountAll") or sr.get("SearchResultCount")
items = sr.get("SearchResultItems", [])
print(f"   SearchResultCount(All): {count} | items returned: {len(items)}")

if not items:
    print("   No results from HSBC; retrying with Keyword=FEMA")
    search_payload, status = fetch(
        "USAJOBS Search (FEMA via Keyword)",
        "https://data.usajobs.gov/api/Search",
        {"Keyword": "FEMA", "ResultsPerPage": 25, "Page": 1},
    )
    sr = search_payload.get("SearchResult", {}) if isinstance(search_payload, dict) else {}
    count = sr.get("SearchResultCountAll") or sr.get("SearchResultCount")
    items = sr.get("SearchResultItems", [])
    print(f"   SearchResultCount(All): {count} | items returned: {len(items)}")

save("usajobs_current", "search_fema", search_payload, status,
     params={"OrganizationCodes": "HSBC or Keyword=FEMA", "ResultsPerPage": 25}, url="/api/Search")


# ---------------------------------------------------------------------------
# 2. HistoricJoa — FEMA, 2024
# Try several plausible param names since the docs phrasing varies.

hist_payload = {}
hist_status = 0
hist_attempts = [
    ("HiringAgencyCodes=HSCB,2024", {
        "HiringAgencyCodes": "HSCB",
        "StartPositionOpenDate": "2024-01-01",
        "EndPositionOpenDate": "2024-12-31",
    }),
    ("HiringAgencyCodes=HSCB lowercase dates,2024", {
        "HiringAgencyCodes": "HSCB",
        "startPositionOpenDate": "2024-01-01",
        "endPositionOpenDate": "2024-12-31",
    }),
    ("HiringDepartmentCodes=HS,2024 (DHS-wide)", {
        "HiringDepartmentCodes": "HS",
        "StartPositionOpenDate": "2024-01-01",
        "EndPositionOpenDate": "2024-01-31",  # narrower since DHS-wide
    }),
    ("just date range 2024-01", {
        "StartPositionOpenDate": "2024-01-01",
        "EndPositionOpenDate": "2024-01-07",
    }),
]

for label, params in hist_attempts:
    payload, status = fetch(
        f"USAJOBS HistoricJoa ({label})",
        "https://data.usajobs.gov/api/historicjoa",
        params,
    )
    hist_status = status
    if status == 200:
        hist_payload = payload
        # Check if we got actual data
        for path in [["data"], ["Data"], ["SearchResult", "SearchResultItems"]]:
            cur = payload
            for k in path:
                if isinstance(cur, dict) and k in cur:
                    cur = cur[k]
                else:
                    cur = None
                    break
            if isinstance(cur, list) and cur:
                print(f"   Got {len(cur)} records via path={'.'.join(path)}")
                break
        break

save("usajobs_historic", "fema_2024", hist_payload, hist_status,
     params={"see _meta in saved blocks": True}, url="/api/historicjoa")


# ---------------------------------------------------------------------------
# 3. AnnouncementText — one record from the historic results

control_no = find_control_number(hist_payload)
print(f"\nUsing control number: {control_no!r}")

text_payload = {}
text_status = 0
if control_no:
    text_attempts = [
        {"USAJOBSControlNumbers": control_no},
        {"UsajobsControlNumbers": control_no},
        {"usajobsControlNumbers": control_no},
    ]
    for params in text_attempts:
        text_payload, text_status = fetch(
            "USAJOBS AnnouncementText",
            "https://data.usajobs.gov/api/historicjoa/announcementtext",
            params,
        )
        if text_status == 200 and text_payload:
            break

    save("usajobs_announcement_text", f"text_{control_no}",
         text_payload, text_status,
         params={"control_no": control_no}, url="/api/historicjoa/announcementtext")
else:
    print("   No control number available — skipping AnnouncementText sample.")


# ---------------------------------------------------------------------------
# 4. OPM probe — HEAD only (workforce data is bulk files, no API)

print("\n--- OPM probe (HEAD only — no download) ---")
opm_targets = [
    "https://www.opm.gov/data/datasets/",
    "https://www.fedscope.opm.gov/",
    "https://www.opm.gov/policy-data-oversight/data-analysis-documentation/federal-employment-reports/",
    "https://data.opm.gov/explore-data/data/data-downloads/",
]
opm_results = []
for url in opm_targets:
    try:
        r = requests.head(url, timeout=15, allow_redirects=True,
                          headers={"User-Agent": cfg.usajobs_user_agent})
        opm_results.append({
            "url": url,
            "status": r.status_code,
            "final_url": r.url,
            "content_type": r.headers.get("Content-Type"),
            "content_length": r.headers.get("Content-Length"),
        })
        print(f"   HEAD {url}  →  {r.status_code}  ct={r.headers.get('Content-Type')}  len={r.headers.get('Content-Length','?')}")
    except Exception as e:
        opm_results.append({"url": url, "error": str(e)})
        print(f"   HEAD {url}  →  ERROR: {e}")

opm_out = RAW / "opm_workforce" / DAY / "head_probes.json"
opm_out.parent.mkdir(parents=True, exist_ok=True)
opm_out.write_text(json.dumps({"probes": opm_results,
                               "fetched_at": datetime.now(timezone.utc).isoformat()},
                              indent=2), encoding="utf-8")
print(f"   Saved OPM probe results → {opm_out}")

print("\nDone. Inspect data/raw/ for samples.")
