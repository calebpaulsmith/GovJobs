"""One-time re-split of the committed public-map data bundle.

Cloudflare Pages rejects any single file over 25 MiB. When an already-committed
bundle file (e.g. ``public_map/static/data/jobs.geojson``) exceeds the 20 MiB
split threshold, this script re-splits it on disk into numbered parts using the
same scheme as the exporter (see ``scripts/bundle_split.py``) and updates the
committed ``manifest.json``'s ``"split"`` map accordingly. It also removes any
stale split parts from a previous (possibly buggy) run.

Run from the repo root::

    python scripts/resplit_committed_bundle.py
    python scripts/resplit_committed_bundle.py --dry-run

Idempotent: re-running it after the bundle is already correctly split is a
no-op apart from confirming sizes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.bundle_split import (  # noqa: E402
    SPLIT_THRESHOLD_BYTES,
    part_filename,
    split_payload,
    write_split_json,
)

BUNDLE_DIR = REPO / "public_map" / "static" / "data"

# Files the bundle ships. Anything that may grow past the threshold is a
# candidate for splitting; small files stay single and never appear in `split`.
SPLITTABLE_FILES = ("jobs.geojson", "jobs_detail.json")


def _stale_part_paths(directory: Path, name: str) -> list[Path]:
    """Return existing files that look like split parts of ``name``.

    Matches both the correct scheme (``jobs.2.geojson``) and the buggy
    dot-dropped variant (``jobs.2geojson``) so stale artifacts are cleaned up.
    """
    dot = name.rfind(".")
    if dot == -1:
        stem, ext = name, ""
    else:
        stem, ext = name[:dot], name[dot:]
    # e.g. stem='jobs', ext='.geojson' -> matches 'jobs.2.geojson' or 'jobs.2geojson'
    pattern = re.compile(
        rf"^{re.escape(stem)}\.\d+{re.escape(ext)}$|^{re.escape(stem)}\.\d+{re.escape(ext.lstrip('.'))}$"
    )
    return sorted(p for p in directory.glob(f"{stem}.*") if pattern.match(p.name))


def resplit_file(directory: Path, name: str, *, dry_run: bool = False) -> int:
    """Re-split ``directory/name`` into parts if it exceeds the threshold.

    Returns the resulting part count (1 = single file). Removes any stale
    split parts from a previous run before writing.
    """
    path = directory / name
    if not path.exists():
        print(f"  {name}: missing — skipped")
        return 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    chunks = split_payload(payload)
    part_count = len(chunks)

    stale = [p for p in _stale_part_paths(directory, name) if p != path]
    if dry_run:
        size = path.stat().st_size
        verdict = "over" if size > SPLIT_THRESHOLD_BYTES else "under"
        print(f"  {name}: {size:,} bytes ({verdict} threshold) -> {part_count} part(s)")
        for p in stale:
            print(f"    would remove stale part {p.name}")
        return part_count

    for p in stale:
        p.unlink()
        print(f"    removed stale part {p.name}")

    paths, written_count = write_split_json(directory, name, payload)
    for index, p in enumerate(paths, start=1):
        print(f"    wrote {p.name} ({p.stat().st_size:,} bytes)")
    return written_count


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change; do not write files.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    directory = BUNDLE_DIR
    manifest_path = directory / "manifest.json"

    print(f"Re-splitting committed bundle in {directory}")
    split_map: dict[str, int] = {}
    for name in SPLITTABLE_FILES:
        part_count = resplit_file(directory, name, dry_run=args.dry_run)
        if part_count > 1:
            split_map[name] = part_count

    if not manifest_path.exists():
        print("  manifest.json: missing — cannot update split map")
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if split_map:
        manifest["split"] = split_map
    else:
        manifest.pop("split", None)

    if args.dry_run:
        print(f"  manifest.json: split map would be {split_map or '{} (key removed)'}")
        return 0

    manifest_path.write_text(
        json.dumps(manifest, separators=(",", ":")), encoding="utf-8"
    )
    print(f"  manifest.json: split map set to {split_map or '{} (key removed)'}")

    # Sanity: confirm every bundle file is under Cloudflare's 25 MiB limit.
    limit = 25 * 1024 * 1024
    oversized = [
        p for p in directory.iterdir() if p.is_file() and p.stat().st_size > limit
    ]
    if oversized:
        for p in oversized:
            print(f"  ERROR: {p.name} is {p.stat().st_size:,} bytes (> 25 MiB)")
        return 1
    print("All bundle files are under the 25 MiB Cloudflare Pages limit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
