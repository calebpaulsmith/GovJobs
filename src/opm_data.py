"""File-based OPM workforce importer.

OPM workforce datasets arrive as downloaded files rather than a USAJOBS-style
REST API. This module normalizes common FedScope/data.opm.gov column names into
the app's intentionally small `opm_workforce_records` table.
"""
from __future__ import annotations

import csv
import re
import sqlite3
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pandas as pd

from config import Config
from src.database import (
    complete_manifest,
    record_raw_response,
    replace_opm_workforce_records,
    start_manifest,
)


SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".txt", ".xlsx", ".xls", ".zip"}
STATE_NAMES = {
    "ALABAMA": "AL",
    "ALASKA": "AK",
    "ARIZONA": "AZ",
    "ARKANSAS": "AR",
    "CALIFORNIA": "CA",
    "COLORADO": "CO",
    "CONNECTICUT": "CT",
    "DELAWARE": "DE",
    "DISTRICT OF COLUMBIA": "DC",
    "FLORIDA": "FL",
    "GEORGIA": "GA",
    "HAWAII": "HI",
    "IDAHO": "ID",
    "ILLINOIS": "IL",
    "INDIANA": "IN",
    "IOWA": "IA",
    "KANSAS": "KS",
    "KENTUCKY": "KY",
    "LOUISIANA": "LA",
    "MAINE": "ME",
    "MARYLAND": "MD",
    "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI",
    "MINNESOTA": "MN",
    "MISSISSIPPI": "MS",
    "MISSOURI": "MO",
    "MONTANA": "MT",
    "NEBRASKA": "NE",
    "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM",
    "NEW YORK": "NY",
    "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND",
    "OHIO": "OH",
    "OKLAHOMA": "OK",
    "OREGON": "OR",
    "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN",
    "TEXAS": "TX",
    "UTAH": "UT",
    "VERMONT": "VT",
    "VIRGINIA": "VA",
    "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI",
    "WYOMING": "WY",
}


@dataclass(frozen=True)
class OpmImportResult:
    dataset: str
    records_imported: int
    manifest_id: int
    source_path: Path


def import_opm_file(
    conn: sqlite3.Connection,
    cfg: Config,
    source_path: str | Path,
    *,
    dataset: str,
    max_rows: int | None = None,
    clear_existing: bool = False,
) -> OpmImportResult:
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported OPM file type: {path.suffix}")

    manifest_id = start_manifest(
        conn,
        source="opm",
        endpoint=str(path),
        download_mode="STAGED_DOWNLOAD",
        filters={"dataset": dataset, "max_rows": max_rows, "clear_existing": clear_existing},
        notes="OPM file import started.",
    )
    try:
        imported = 0
        first_batch = True
        for rows in _iter_normalized_rows(path, dataset=dataset, max_rows=max_rows):
            imported += replace_opm_workforce_records(
                conn,
                dataset=dataset,
                rows=rows,
                clear_existing=clear_existing and first_batch,
            )
            first_batch = False
        record_raw_response(
            conn,
            source="opm",
            endpoint=str(path),
            query_params={"dataset": dataset},
            response_path=_display_path(path, cfg),
            status_code=200,
            record_count=imported,
            page_number=1,
        )
        complete_manifest(
            conn,
            manifest_id,
            actual_records=imported,
            notes=f"Imported {imported} OPM workforce row(s) from {path.name}.",
        )
        return OpmImportResult(
            dataset=dataset,
            records_imported=imported,
            manifest_id=manifest_id,
            source_path=path,
        )
    except Exception as exc:
        complete_manifest(conn, manifest_id, status="failed", actual_records=0, notes=str(exc))
        raise


def _iter_normalized_rows(
    path: Path,
    *,
    dataset: str,
    max_rows: int | None,
) -> Iterable[list[dict[str, Any]]]:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        with TemporaryDirectory() as tmp:
            extracted = _extract_first_data_file(path, Path(tmp))
            yield from _iter_normalized_rows(extracted, dataset=dataset, max_rows=max_rows)
        return

    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path, nrows=max_rows)
        yield [_normalize_row(row, dataset=dataset, source_path=path, row_number=idx + 2) for idx, row in df.iterrows()]
        return

    sep = "\t" if suffix == ".tsv" else _sniff_delimiter(path)
    remaining = max_rows
    for chunk in pd.read_csv(path, sep=sep, dtype=str, chunksize=5_000, nrows=max_rows):
        if remaining is not None:
            chunk = chunk.head(remaining)
            remaining -= len(chunk)
        yield [
            _normalize_row(row, dataset=dataset, source_path=path, row_number=int(idx) + 2)
            for idx, row in chunk.iterrows()
        ]
        if remaining is not None and remaining <= 0:
            break


def _normalize_row(
    row: Mapping[str, Any],
    *,
    dataset: str,
    source_path: Path,
    row_number: int,
) -> dict[str, Any]:
    values = {_key(key): _clean(value) for key, value in dict(row).items()}
    count = _first(values, "count", "total", "headcount", "employment", "employmentcount", "employees")
    dataset_key = _key(dataset)
    return {
        "period_year": _year(values),
        "period_quarter": _quarter(values),
        "agency": _first(values, "agency", "agencyname", "department", "departmentagency"),
        "sub_agency": _first(values, "subagency", "subelement", "subelementname", "bureau"),
        "occupation_series": _series(_first(values, "occupationseries", "occupationalseries", "series", "occseries", "occupation")),
        "grade": _grade(_first(values, "grade", "gradelevel", "paygrade")),
        "pay_plan": _first(values, "payplan", "payplancode", "paypln"),
        "location_state": _state(_first(values, "state", "statecode", "locationstate", "workstate", "dutyshirestate")),
        "location_metro": _first(values, "metro", "msa", "cbsa", "locationmetro", "dutystation"),
        "employment_count": _count_for_dataset(dataset_key, "employment", count, values),
        "accessions_count": _count_for_dataset(dataset_key, "accession", count, values),
        "separations_count": _count_for_dataset(dataset_key, "separation", count, values),
        "salary_avg": _number(_first(values, "salaryavg", "averagesalary", "avg_salary", "salary")),
        "raw_row_path": f"{source_path}#{row_number}",
    }


def _extract_first_data_file(zip_path: Path, target_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path) as archive:
        names = [
            name
            for name in archive.namelist()
            if Path(name).suffix.lower() in SUPPORTED_EXTENSIONS - {".zip"}
            and not Path(name).name.startswith(".")
        ]
        if not names:
            raise ValueError(f"No supported data file found in {zip_path}")
        first = names[0]
        archive.extract(first, target_dir)
    return target_dir / first


def _sniff_delimiter(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
        sample = handle.read(4096)
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t|").delimiter
    except csv.Error:
        return ","


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _first(values: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = values.get(_key(key))
        if value not in (None, ""):
            return str(value)
    return None


def _year(values: Mapping[str, Any]) -> int | None:
    direct = _first(values, "year", "fiscalyear", "fiscalyr", "periodyear", "reportingyear")
    if direct:
        match = re.search(r"(19|20)\d{2}", direct)
        if match:
            return int(match.group(0))
    period = _first(values, "period", "quarter", "reportingperiod")
    if period:
        match = re.search(r"(19|20)\d{2}", period)
        if match:
            return int(match.group(0))
    return None


def _quarter(values: Mapping[str, Any]) -> int | None:
    direct = _first(values, "quarter", "qtr", "periodquarter")
    if direct:
        match = re.search(r"[Qq]?\s*([1-4])", direct)
        if match:
            return int(match.group(1))
    period = _first(values, "period", "reportingperiod")
    if period:
        match = re.search(r"[Qq]\s*([1-4])", period)
        if match:
            return int(match.group(1))
    return None


def _series(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"\d{1,4}", value)
    return match.group(0).zfill(4) if match else value.strip()


def _grade(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"\d{1,2}", value)
    return str(int(match.group(0))) if match else value.strip()


def _state(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().upper()
    if len(text) == 2 and text.isalpha():
        return text
    return STATE_NAMES.get(text)


def _count_for_dataset(
    dataset_key: str,
    target: str,
    count: str | None,
    values: Mapping[str, Any],
) -> int | None:
    specific = _first(values, f"{target}count", target)
    if specific is not None:
        return _integer(specific)
    if target in dataset_key:
        return _integer(count)
    if target == "employment" and not any(word in dataset_key for word in ("accession", "separation")):
        return _integer(count)
    return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except ValueError:
        return None


def _clean(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def _display_path(path: Path, cfg: Config) -> str:
    try:
        return str(path.relative_to(cfg.raw_data_path.parent))
    except ValueError:
        return str(path)
