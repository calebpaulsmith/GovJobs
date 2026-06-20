"""Ingest State Dept DSSR overseas allowances (post/COLA, hardship, danger pay).

US federal jobs posted abroad keep GS base pay (USD) but get **no US locality
pay**. Their real compensation adds State Department allowances published under
the Department of State Standardized Regulations (DSSR):

* Post (Hardship) Differential — DSSR 500 — % of basic compensation (base pay).
* Danger Pay — DSSR 650 — % of basic compensation.
* Post (Cost of Living) Allowance — DSSR 220 — % of **spendable income** (NOT
  base pay). Converting it to dollars needs the Spendable Income Table (annual
  spendable income by salary band x family size).

This is a NEW pay path, kept entirely separate from ``pay_scales`` (which stays
GS-table-shaped per the hard rules). It fills two tables: ``overseas_post_allowances``
and ``spendable_income``.

Source (verified 2026-06-20): https://allowances.state.gov (aoprals.state.gov
302-redirects here). The site publishes HTML tables only — no CSV/XML — so the
operator chose live HTML fetch as the canonical refresh. Per ADR-0027 the script
is still self-bootstrapping: when the live fetch fails (offline, site-format
drift, ToS block) it falls back to the checked-in seed CSVs captured from the
live tables, so a clean checkout always builds:

    data/external/dssr/post_allowances_2026-06-14.csv   (792 posts)
    data/external/dssr/spendable_income_2023-01-01.csv  (22 salary bands x 6)

Run:
    python scripts/ingest_dssr_allowances.py            # live, seed on failure
    python scripts/ingest_dssr_allowances.py --offline  # force the seed
    python scripts/ingest_dssr_allowances.py --input my_allowances.csv
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import logging
import re
import sqlite3
import sys
import zipfile
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import load_config  # noqa: E402
from src.database import normalize_country, utc_now  # noqa: E402
from src.ingest_common import emit_summary, run_ingest  # noqa: E402

logger = logging.getLogger(__name__)

SOURCE_KEY = "dssr_allowances"
DISPLAY_NAME = "State Dept DSSR overseas allowances"
CATEGORY = "pay"

BASE = "https://allowances.state.gov"
HARDSHIP_URL = f"{BASE}/Web920/hardship.asp"
DANGER_URL = f"{BASE}/Web920/danger_pay_all.asp"
COLA_URL = f"{BASE}/Web920/cola.asp"
SPENDABLE_URL = (
    f"{BASE}/Content/Documents/Annual Spendable Income by Salary and "
    "Family Size       effective  January 1, 2023.docx"
)

SEED_ALLOWANCES = REPO / "data" / "external" / "dssr" / "post_allowances_2026-06-14.csv"
SEED_SPENDABLE = REPO / "data" / "external" / "dssr" / "spendable_income_2023-01-01.csv"

# Fallback effective date when a page omits a per-row "Rates Effective" line.
DEFAULT_EFFECTIVE = "2026-06-14"


# ---------------------------------------------------------------------------
# Pure parse helpers (no network; unit-tested against small fixtures)
# ---------------------------------------------------------------------------
def parse_effective_date(html_text: str) -> str | None:
    """Pull "Rates Effective: MM/DD/YYYY" off a table page -> ISO YYYY-MM-DD."""
    m = re.search(r"Rates Effective:\s*(\d{2})/(\d{2})/(\d{4})", html_text)
    if not m:
        return None
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"


def parse_allowance_table(html_text: str, value_title: str) -> list[dict[str, Any]]:
    """Parse a Web920 allowance table into rows.

    The tables share a cell structure keyed by ``title=`` attributes::

        <td title='Country Name'><a id='ITALY'>ITALY</a></td>
        <td title='Post Name'>Rome</td>
        <td title='<value_title>' ...>30%&nbsp;</td>
        <td title='Effective Date' ...>05/19/2024</td>   (danger pay only)

    ``value_title`` is "Rate" for hardship/danger and "Post Allowance" for COLA.
    Returns dicts: ``{country, post, pct, effective_date}`` (effective_date may
    be None for tables without a per-row date column).
    """
    rows: list[dict[str, Any]] = []
    for chunk in re.split(r"<tr\b", html_text):
        country = re.search(r"title='Country Name'>(?:<a[^>]*>)?([^<]+)", chunk)
        post = re.search(r"title='Post Name'>([^<]+)", chunk)
        value = re.search(
            rf"title='{re.escape(value_title)}'[^>]*>\s*(-?\d+)%", chunk
        )
        if not (country and post and value):
            continue
        eff = re.search(r"title='Effective Date'[^>]*>\s*(\d{2}/\d{2}/\d{4})", chunk)
        eff_iso = None
        if eff:
            mm, dd, yyyy = eff.group(1).split("/")
            eff_iso = f"{yyyy}-{mm}-{dd}"
        rows.append(
            {
                "country": html.unescape(country.group(1)).strip(),
                "post": html.unescape(post.group(1)).strip(),
                "pct": int(value.group(1)),
                "effective_date": eff_iso,
            }
        )
    return rows


def merge_allowance_tables(
    hardship: list[dict[str, Any]],
    danger: list[dict[str, Any]],
    cola: list[dict[str, Any]],
    *,
    default_effective: str,
    source_url: str = BASE + "/Web920/",
) -> list[dict[str, Any]]:
    """Merge the three per-table row lists into one row per (country, post)."""
    merged: dict[tuple[str, str], dict[str, Any]] = {}

    def slot(country: str, post: str) -> dict[str, Any]:
        key = (country, post)
        if key not in merged:
            merged[key] = {
                "country_name": country,
                "country_iso": normalize_country(country) or country.upper(),
                "post_name": post,
                "post_differential_pct": None,
                "danger_pay_pct": None,
                "cola_pct_spendable_income": None,
                "effective_date": default_effective,
                "source_url": source_url,
            }
        return merged[key]

    for r in hardship:
        slot(r["country"], r["post"])["post_differential_pct"] = float(r["pct"])
    for r in danger:
        row = slot(r["country"], r["post"])
        row["danger_pay_pct"] = float(r["pct"])
        if r.get("effective_date"):
            row["effective_date"] = r["effective_date"]
    for r in cola:
        slot(r["country"], r["post"])["cola_pct_spendable_income"] = float(r["pct"])

    return sorted(merged.values(), key=lambda d: (d["country_name"], d["post_name"]))


def extract_docx_cells(docx_bytes: bytes) -> list[str]:
    """Flatten a .docx table to a list of non-empty cell text runs."""
    xml = zipfile.ZipFile(io.BytesIO(docx_bytes)).read("word/document.xml")
    text = xml.decode("utf-8", "replace")
    cells = [html.unescape(t).strip() for t in re.findall(r"<w:t[^>]*>([^<]*)</w:t>", text)]
    return [c for c in cells if c]


def _parse_band(text: str) -> tuple[int, int | None] | None:
    """Parse a salary band label -> (min, max | None for 'and over')."""
    b = text.replace(",", "").strip()
    m = re.match(r"^(\d+)\s*and over$", b)
    if m:
        return int(m.group(1)), None
    m = re.match(r"^(\d+)\s*-\s*(\d+)$", b)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"^(\d+)\s*and under$", b)
    if m:
        return 0, int(m.group(1))
    return None


def parse_spendable_cells(
    cells: list[str],
    *,
    effective_date: str = "2023-01-01",
    source_url: str = SPENDABLE_URL,
) -> list[dict[str, Any]]:
    """Parse the flattened Spendable Income Table cells into rows.

    Layout: a header ending in family-size columns ``1 2 3 4 5 6``, then groups
    of 7 cells: ``[salary_band, fam1, fam2, ..., fam6]``. Stops at the first
    group that isn't a valid band + six numbers.
    """
    if "6" not in cells:
        return []
    seq = cells[cells.index("6") + 1 :]
    rows: list[dict[str, Any]] = []
    j = 0
    while j + 6 < len(seq) + 1:
        band = _parse_band(seq[j]) if j < len(seq) else None
        vals = seq[j + 1 : j + 7]
        if band is None or len(vals) < 6 or not all(re.match(r"^[\d,]+$", v) for v in vals):
            break
        for fam, v in enumerate(vals, start=1):
            rows.append(
                {
                    "salary_min": band[0],
                    "salary_max": band[1],
                    "family_size": fam,
                    "annual_spendable_income": int(v.replace(",", "")),
                    "effective_date": effective_date,
                    "source_url": source_url,
                }
            )
        j += 7
    return rows


# ---------------------------------------------------------------------------
# Seed loaders (CSV) — the offline floor
# ---------------------------------------------------------------------------
def load_allowance_seed(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = []
        for r in csv.DictReader(handle):
            rows.append(
                {
                    "country_name": r["country_name"],
                    "country_iso": r.get("country_iso")
                    or normalize_country(r["country_name"])
                    or r["country_name"].upper(),
                    "post_name": r["post_name"],
                    "post_differential_pct": _opt_float(r.get("post_differential_pct")),
                    "danger_pay_pct": _opt_float(r.get("danger_pay_pct")),
                    "cola_pct_spendable_income": _opt_float(
                        r.get("cola_pct_spendable_income")
                    ),
                    "effective_date": r.get("effective_date") or DEFAULT_EFFECTIVE,
                    "source_url": r.get("source_url") or (BASE + "/Web920/"),
                }
            )
    return rows


def load_spendable_seed(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = []
        for r in csv.DictReader(handle):
            rows.append(
                {
                    "salary_min": int(r["salary_min"]),
                    "salary_max": int(r["salary_max"]) if r.get("salary_max") else None,
                    "family_size": int(r["family_size"]),
                    "annual_spendable_income": int(r["annual_spendable_income"]),
                    "effective_date": r.get("effective_date") or "2023-01-01",
                    "source_url": r.get("source_url") or SPENDABLE_URL,
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Live fetch (network) — the canonical refresh; falls back to seed on failure
# ---------------------------------------------------------------------------
def _http_get(url: str, *, binary: bool = False, timeout: int = 30) -> Any:
    import requests

    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content if binary else response.text


def fetch_live(fetch: Callable[..., Any] | None = None) -> tuple[list[dict], list[dict]]:
    """Fetch + parse the three allowance tables and the spendable-income docx.

    ``fetch(url, binary=False)`` is injectable so tests never hit the network.
    Raises on any failure so the caller can fall back to the seed.
    """
    get = fetch or _http_get
    hardship_html = get(HARDSHIP_URL)
    danger_html = get(DANGER_URL)
    cola_html = get(COLA_URL)
    effective = parse_effective_date(hardship_html) or DEFAULT_EFFECTIVE
    allowances = merge_allowance_tables(
        parse_allowance_table(hardship_html, "Rate"),
        parse_allowance_table(danger_html, "Rate"),
        parse_allowance_table(cola_html, "Post Allowance"),
        default_effective=effective,
    )
    if not allowances:
        raise ValueError("live allowance tables parsed to zero rows")
    spendable = parse_spendable_cells(extract_docx_cells(get(SPENDABLE_URL, binary=True)))
    if not spendable:
        raise ValueError("live spendable-income table parsed to zero rows")
    return allowances, spendable


# ---------------------------------------------------------------------------
# Upsert (replace-all snapshot)
# ---------------------------------------------------------------------------
def import_dssr(
    conn: sqlite3.Connection,
    *,
    allowances: list[dict[str, Any]],
    spendable: list[dict[str, Any]],
) -> int:
    now = utc_now()
    conn.execute("DELETE FROM overseas_post_allowances")
    conn.execute("DELETE FROM spendable_income")
    for r in allowances:
        conn.execute(
            """
            INSERT INTO overseas_post_allowances (
                country_iso, country_name, post_name,
                post_differential_pct, danger_pay_pct, cola_pct_spendable_income,
                effective_date, source_url, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(country_iso, post_name) DO UPDATE SET
                country_name=excluded.country_name,
                post_differential_pct=excluded.post_differential_pct,
                danger_pay_pct=excluded.danger_pay_pct,
                cola_pct_spendable_income=excluded.cola_pct_spendable_income,
                effective_date=excluded.effective_date,
                source_url=excluded.source_url,
                imported_at=excluded.imported_at
            """,
            (
                r["country_iso"], r["country_name"], r["post_name"],
                r["post_differential_pct"], r["danger_pay_pct"],
                r["cola_pct_spendable_income"], r["effective_date"],
                r["source_url"], now,
            ),
        )
    for r in spendable:
        conn.execute(
            """
            INSERT INTO spendable_income (
                salary_min, salary_max, family_size, annual_spendable_income,
                effective_date, source_url, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(salary_min, family_size) DO UPDATE SET
                salary_max=excluded.salary_max,
                annual_spendable_income=excluded.annual_spendable_income,
                effective_date=excluded.effective_date,
                source_url=excluded.source_url,
                imported_at=excluded.imported_at
            """,
            (
                r["salary_min"], r["salary_max"], r["family_size"],
                r["annual_spendable_income"], r["effective_date"],
                r["source_url"], now,
            ),
        )
    conn.commit()
    return len(allowances) + len(spendable)


def gather_rows(
    *,
    use_live: bool,
    allowance_input: Path | None = None,
    spendable_input: Path | None = None,
    fetch: Callable[..., Any] | None = None,
) -> tuple[list[dict], list[dict], str]:
    """Return (allowances, spendable, source_label) honoring overrides.

    Priority: explicit --input files > live fetch > checked-in seed. The seed is
    the offline floor so a clean checkout always builds (ADR-0027).
    """
    if allowance_input or spendable_input:
        allow = load_allowance_seed(allowance_input or SEED_ALLOWANCES)
        spend = load_spendable_seed(spendable_input or SEED_SPENDABLE)
        return allow, spend, "input"
    if use_live:
        try:
            allow, spend = fetch_live(fetch)
            return allow, spend, "live"
        except Exception as exc:  # noqa: BLE001 - any failure degrades to seed
            logger.warning("live DSSR fetch failed (%s); falling back to seed", exc)
    return load_allowance_seed(SEED_ALLOWANCES), load_spendable_seed(SEED_SPENDABLE), "seed"


def run(
    database_path: Path,
    *,
    use_live: bool = True,
    allowance_input: Path | None = None,
    spendable_input: Path | None = None,
    fetch: Callable[..., Any] | None = None,
) -> int:
    allow, spend, label = gather_rows(
        use_live=use_live,
        allowance_input=allowance_input,
        spendable_input=spendable_input,
        fetch=fetch,
    )

    def work(conn: sqlite3.Connection) -> int:
        return import_dssr(conn, allowances=allow, spendable=spend)

    count = run_ingest(
        source_key=SOURCE_KEY,
        display_name=DISPLAY_NAME,
        category=CATEGORY,
        work=work,
        database_path=database_path,
        notes=f"source={label}; {len(allow)} posts, {len(spend)} spendable rows",
    )
    emit_summary(SOURCE_KEY, count, notes=f"source={label}")
    return count


def _opt_float(value: str | None) -> float | None:
    text = (value or "").strip()
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=None, help="Allowance CSV override.")
    parser.add_argument("--spendable", type=Path, default=None, help="Spendable-income CSV override.")
    parser.add_argument(
        "--offline", action="store_true",
        help="Skip the live fetch and use the checked-in seed CSVs.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args()
    cfg = load_config()
    run(
        cfg.database_path,
        use_live=not args.offline,
        allowance_input=args.input,
        spendable_input=args.spendable,
    )


if __name__ == "__main__":
    main()
