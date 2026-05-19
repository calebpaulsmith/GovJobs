"""Splitting helpers for the public-map static data bundle.

Cloudflare Pages rejects any single file larger than 25 MiB. Oversized
bundle files are written as numbered parts, each safely under a 20 MiB
threshold, and reassembled client-side (see ``public_map/src/lib/data.ts``).

Naming scheme: a file ``jobs.geojson`` split into N parts is written as
``jobs.geojson`` (part 1), ``jobs.2.geojson``, ``jobs.3.geojson``, ...
The part number is inserted before the final extension. ``jobs_detail.json``
splits to ``jobs_detail.json``, ``jobs_detail.2.json``, ...

``manifest.json`` carries a ``"split"`` object listing only files with more
than one part, e.g. ``{"jobs.geojson": 2}``. Files absent from that map are
single-file (the default).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

# 20 MiB threshold leaves a safe margin under Cloudflare's 25 MiB limit.
SPLIT_THRESHOLD_BYTES = 20 * 1024 * 1024

_SEPARATORS = (",", ":")


def part_filename(name: str, index: int) -> str:
    """Return the filename for part ``index`` (1-based) of ``name``.

    Part 1 keeps the original name. Later parts insert the part number
    before the final extension: ``jobs.geojson`` -> ``jobs.2.geojson``.
    """
    if index < 1:
        raise ValueError(f"part index must be >= 1, got {index}")
    if index == 1:
        return name
    dot = name.rfind(".")
    if dot == -1:
        return f"{name}.{index}"
    return f"{name[:dot]}.{index}{name[dot:]}"


def _serialize(payload: Any) -> str:
    return json.dumps(payload, separators=_SEPARATORS)


def _chunk_count(byte_size: int) -> int:
    """Number of parts needed so each part is under the threshold."""
    if byte_size <= SPLIT_THRESHOLD_BYTES:
        return 1
    return max(2, math.ceil(byte_size / SPLIT_THRESHOLD_BYTES))


def _split_list(items: list[Any], parts: int) -> list[list[Any]]:
    """Divide ``items`` into ``parts`` roughly-equal contiguous chunks."""
    if parts <= 1:
        return [items]
    size = math.ceil(len(items) / parts)
    chunks = [items[i : i + size] for i in range(0, len(items), size)]
    # Pad with empties if rounding produced fewer chunks than requested.
    while len(chunks) < parts:
        chunks.append([])
    return chunks


def split_payload(payload: Any) -> list[Any]:
    """Split ``payload`` into part-payloads if its serialized form is large.

    A GeoJSON ``FeatureCollection`` is chunked by its ``features`` list;
    each part is a complete ``{"type": "FeatureCollection", "features": ...}``.
    A plain dict is chunked by its entries; each part is a ``{...}`` object.

    Returns a list of one or more payloads. A single-element list means the
    payload was small enough to write as one file.
    """
    serialized = _serialize(payload)
    parts = _chunk_count(len(serialized.encode("utf-8")))
    if parts == 1:
        return [payload]

    if (
        isinstance(payload, dict)
        and payload.get("type") == "FeatureCollection"
        and isinstance(payload.get("features"), list)
    ):
        feature_chunks = _split_list(list(payload["features"]), parts)
        return [
            {"type": "FeatureCollection", "features": chunk}
            for chunk in feature_chunks
        ]

    if isinstance(payload, dict):
        entry_chunks = _split_list(list(payload.items()), parts)
        return [dict(chunk) for chunk in entry_chunks]

    # Unsupported payload shape (e.g. a list) — do not split.
    return [payload]


def write_split_json(directory: Path, name: str, payload: Any) -> tuple[list[Path], int]:
    """Write ``payload`` to ``directory/name``, splitting into parts if large.

    Returns ``(paths, part_count)`` where ``paths`` is every file written and
    ``part_count`` is the number of parts (1 = unsplit).
    """
    directory.mkdir(parents=True, exist_ok=True)
    chunks = split_payload(payload)
    written: list[Path] = []
    for index, chunk in enumerate(chunks, start=1):
        path = directory / part_filename(name, index)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(chunk, handle, separators=_SEPARATORS)
        written.append(path)
    return written, len(chunks)
