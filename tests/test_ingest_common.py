"""Tests for the self-bootstrapping ingest helpers (ADR-0027).

Covers:
- ``resolve_or_download`` priority: --input > cache > seed CSV > download.
- ``shapefile_zip_to_geojson`` round-trips a synthetic shapefile to GeoJSON.
- ``ensure_geojson_input`` detects ZIP suffix and converts; passes GeoJSON
  inputs through unchanged.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from src.ingest_common import (
    ensure_geojson_input,
    resolve_or_download,
    shapefile_zip_to_geojson,
    write_geojson,
)


# ---------- resolve_or_download --------------------------------------------


def test_resolve_or_download_prefers_user_input(tmp_path: Path) -> None:
    user_path = tmp_path / "explicit.geojson"
    user_path.write_text("{}", encoding="utf-8")
    resolved = resolve_or_download(
        source_key="example",
        default_url="https://example.com/should-not-fetch.zip",
        cache_dir=tmp_path / "cache",
        user_input=user_path,
    )
    assert resolved == user_path


def test_resolve_or_download_uses_cache_hit(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cached = cache_dir / "thing.zip"
    cached.write_bytes(b"\x00\x01\x02")
    resolved = resolve_or_download(
        source_key="example",
        default_url="https://example.com/thing.zip",
        cache_dir=cache_dir,
    )
    assert resolved == cached


def test_resolve_or_download_copies_seed_when_no_cache(tmp_path: Path) -> None:
    seed = tmp_path / "seed.csv"
    seed.write_text("a,b\n1,2\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    resolved = resolve_or_download(
        source_key="example",
        default_url=None,
        cache_dir=cache_dir,
        seed_path=seed,
    )
    assert resolved.parent == cache_dir
    assert resolved.read_text(encoding="utf-8") == "a,b\n1,2\n"


def test_resolve_or_download_raises_when_user_input_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.geojson"
    with pytest.raises(FileNotFoundError):
        resolve_or_download(
            source_key="example",
            default_url="https://example.com/x.zip",
            cache_dir=tmp_path / "cache",
            user_input=missing,
        )


def test_resolve_or_download_raises_when_no_paths_available(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        resolve_or_download(
            source_key="example",
            default_url=None,
            cache_dir=tmp_path / "cache",
            filename="thing.zip",
        )


# ---------- shapefile_zip_to_geojson ---------------------------------------


def _build_synthetic_state_shapefile_zip(target: Path) -> Path:
    """Create a minimal one-feature shapefile ZIP for testing.

    Uses pyshp to write a polygon with STUSPS / NAME attributes, then bundles
    the .shp/.shx/.dbf into a ZIP at ``target``. No .prj is included; pyshp
    can read shapefiles without one and we treat the data as WGS84 anyway.
    """
    import shapefile  # pyshp

    shp_buf = io.BytesIO()
    shx_buf = io.BytesIO()
    dbf_buf = io.BytesIO()
    writer = shapefile.Writer(
        shp=shp_buf, shx=shx_buf, dbf=dbf_buf, shapeType=shapefile.POLYGON
    )
    writer.field("STUSPS", "C", size=2)
    writer.field("NAME", "C", size=64)
    writer.field("STATEFP", "C", size=2)
    # Counter-clockwise polygon for an arbitrary square.
    writer.poly([[
        [-87.0, 41.0], [-87.0, 42.0], [-86.0, 42.0], [-86.0, 41.0], [-87.0, 41.0]
    ]])
    writer.record("IL", "Illinois", "17")
    writer.close()

    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w") as zf:
        zf.writestr("test.shp", shp_buf.getvalue())
        zf.writestr("test.shx", shx_buf.getvalue())
        zf.writestr("test.dbf", dbf_buf.getvalue())
    return target


def test_shapefile_zip_to_geojson_round_trip(tmp_path: Path) -> None:
    zip_path = _build_synthetic_state_shapefile_zip(tmp_path / "states.zip")
    payload = shapefile_zip_to_geojson(zip_path)

    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) == 1
    feature = payload["features"][0]
    assert feature["properties"]["STUSPS"] == "IL"
    assert feature["properties"]["NAME"] == "Illinois"
    geometry = feature["geometry"]
    assert geometry["type"] in {"Polygon", "MultiPolygon"}


def test_shapefile_zip_to_geojson_filters_properties(tmp_path: Path) -> None:
    zip_path = _build_synthetic_state_shapefile_zip(tmp_path / "states.zip")
    payload = shapefile_zip_to_geojson(zip_path, properties_to_keep={"STUSPS"})
    props = payload["features"][0]["properties"]
    assert props == {"STUSPS": "IL"}


# ---------- ensure_geojson_input -------------------------------------------


def test_ensure_geojson_input_passes_geojson_through(tmp_path: Path) -> None:
    geojson = tmp_path / "states.geojson"
    write_geojson(
        {"type": "FeatureCollection", "features": []},
        geojson,
    )
    resolved = ensure_geojson_input(
        source_key="example",
        default_url="https://example.com/states.geojson",
        user_input=geojson,
    )
    assert resolved == geojson


def test_ensure_geojson_input_converts_zip(tmp_path: Path) -> None:
    zip_path = _build_synthetic_state_shapefile_zip(tmp_path / "states.zip")
    resolved = ensure_geojson_input(
        source_key="example",
        default_url="https://example.com/states.zip",
        user_input=zip_path,
        properties_to_keep={"STUSPS", "NAME"},
    )
    assert resolved.suffix == ".geojson"
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    assert payload["features"][0]["properties"]["STUSPS"] == "IL"
    # Second call should reuse the cached GeoJSON without reconverting.
    again = ensure_geojson_input(
        source_key="example",
        default_url="https://example.com/states.zip",
        user_input=zip_path,
    )
    assert again == resolved
