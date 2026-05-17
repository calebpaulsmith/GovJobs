"""Tests for the public-map bundle splitting helpers."""
from __future__ import annotations

import json

import pytest

from scripts.bundle_split import (
    SPLIT_THRESHOLD_BYTES,
    part_filename,
    split_payload,
    write_split_json,
)


def _big_feature_collection(features: int) -> dict:
    """A FeatureCollection whose serialized form exceeds the split threshold."""
    # Each feature carries a chunky description so the payload crosses 20 MiB.
    blob = "x" * 512
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(i), float(-i)]},
                "properties": {"id": i, "blob": blob},
            }
            for i in range(features)
        ],
    }


def _big_dict(entries: int) -> dict:
    blob = "y" * 512
    return {str(i): {"id": i, "blob": blob} for i in range(entries)}


def test_part_filename_inserts_index_before_extension() -> None:
    assert part_filename("jobs.geojson", 1) == "jobs.geojson"
    assert part_filename("jobs.geojson", 2) == "jobs.2.geojson"
    assert part_filename("jobs.geojson", 3) == "jobs.3.geojson"
    assert part_filename("jobs_detail.json", 2) == "jobs_detail.2.json"
    # No extension -> append the index.
    assert part_filename("noext", 2) == "noext.2"


def test_part_filename_rejects_bad_index() -> None:
    with pytest.raises(ValueError):
        part_filename("jobs.geojson", 0)


def test_small_payload_is_not_split() -> None:
    payload = {"type": "FeatureCollection", "features": [{"a": 1}]}
    parts = split_payload(payload)
    assert len(parts) == 1
    assert parts[0] == payload

    small_dict = {"1": {"id": 1}, "2": {"id": 2}}
    assert split_payload(small_dict) == [small_dict]


def test_large_feature_collection_splits_and_round_trips() -> None:
    # ~60k * ~560 bytes serialized comfortably exceeds the 20 MiB threshold.
    payload = _big_feature_collection(60_000)
    serialized_size = len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    assert serialized_size > SPLIT_THRESHOLD_BYTES

    parts = split_payload(payload)
    assert len(parts) >= 2

    for part in parts:
        assert part["type"] == "FeatureCollection"
        part_size = len(json.dumps(part, separators=(",", ":")).encode("utf-8"))
        assert part_size <= SPLIT_THRESHOLD_BYTES

    # Reassembling the parts' features yields the original collection.
    merged = [f for part in parts for f in part["features"]]
    assert merged == payload["features"]


def test_large_dict_splits_and_round_trips() -> None:
    payload = _big_dict(60_000)
    serialized_size = len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    assert serialized_size > SPLIT_THRESHOLD_BYTES

    parts = split_payload(payload)
    assert len(parts) >= 2

    merged: dict = {}
    for part in parts:
        assert isinstance(part, dict)
        merged.update(part)
    assert merged == payload


def test_write_split_json_small_payload_single_file(tmp_path) -> None:
    payload = {"type": "FeatureCollection", "features": [{"a": 1}]}
    paths, count = write_split_json(tmp_path, "jobs.geojson", payload)
    assert count == 1
    assert [p.name for p in paths] == ["jobs.geojson"]
    assert json.loads(paths[0].read_text()) == payload


def test_write_split_json_large_payload_numbered_parts(tmp_path) -> None:
    payload = _big_feature_collection(60_000)
    paths, count = write_split_json(tmp_path, "jobs.geojson", payload)
    assert count >= 2
    assert paths[0].name == "jobs.geojson"
    assert paths[1].name == "jobs.2.geojson"

    # Every written part is under Cloudflare's 25 MiB hard limit.
    for path in paths:
        assert path.stat().st_size < 25 * 1024 * 1024

    # Round-trip: concatenating the parts reproduces the original payload.
    merged_features: list = []
    for path in paths:
        part = json.loads(path.read_text())
        assert part["type"] == "FeatureCollection"
        merged_features.extend(part["features"])
    assert merged_features == payload["features"]
