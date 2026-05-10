"""Resolve a merge that conflicts only in `public_map/static/data/*`.

Why this exists. The GitHub Actions scheduler at
`.github/workflows/refresh-public-map.yml` regenerates the public-map
bundle on a daily cron and pushes it to master. If the operator has
unpushed local commits that also touched the bundle (typically as a side
effect of running `scripts/export_public_map.py` after corpus growth),
`git pull` produces a merge with every bundle file in conflict. The
content of those files is deterministic — it is whatever
`export_public_map.py` produces from the current local SQLite — so the
right resolution is always "regenerate, take ours, finish the merge."
This script automates that.

What it does, in order:

    1. Refuse to run unless there is an active merge or rebase in
       progress. This is a safety brake; the script is destructive in
       the narrow sense that it overwrites the bundle on disk.
    2. Confirm that every conflicted path lives under
       `public_map/static/data/`. If anything else is in conflict, we
       abort and let the operator handle it manually.
    3. Run `python scripts/export_public_map.py` to regenerate the
       bundle from the current SQLite snapshot.
    4. `git add` the regenerated bundle paths.
    5. Continue the merge or rebase.

The script is intentionally read-only against any path outside
`public_map/static/data/`. If anything looks off, it bails with a
descriptive message rather than guessing.

Usage:

    python scripts/resolve_bundle_conflicts.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUNDLE_DIR = REPO / "public_map" / "static" / "data"
BUNDLE_PREFIX = "public_map/static/data/"


def _run(cmd: list[str], *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=REPO,
        check=check,
        text=True,
        capture_output=capture,
    )


def _git_dir() -> Path:
    out = _run(["git", "rev-parse", "--git-dir"], capture=True).stdout.strip()
    return (REPO / out).resolve()


def _is_merging(git_dir: Path) -> bool:
    return (git_dir / "MERGE_HEAD").exists()


def _is_rebasing(git_dir: Path) -> bool:
    return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()


def _conflicted_paths() -> list[str]:
    out = _run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        capture=True,
    ).stdout.strip()
    return [line for line in out.splitlines() if line]


def main() -> int:
    git_dir = _git_dir()
    merging = _is_merging(git_dir)
    rebasing = _is_rebasing(git_dir)
    if not (merging or rebasing):
        print(
            "No merge or rebase in progress. Run `git pull` (or `git rebase`) first; "
            "this script only resolves an existing conflict."
        )
        return 1

    conflicts = _conflicted_paths()
    if not conflicts:
        print(
            "No conflicted paths reported by git. The merge state may already be resolved; "
            "if so, run `git commit` (merge) or `git rebase --continue` (rebase) to finalize."
        )
        return 1

    non_bundle = [p for p in conflicts if not p.startswith(BUNDLE_PREFIX)]
    if non_bundle:
        print(
            "Conflicts outside the auto-generated bundle path "
            f"({BUNDLE_PREFIX}); resolve these manually first:"
        )
        for p in non_bundle:
            print(f"  {p}")
        return 2

    print(f"All {len(conflicts)} conflicted paths are under {BUNDLE_PREFIX}. Regenerating bundle.")
    for p in conflicts:
        print(f"  conflict: {p}")

    # Re-run the exporter against the current DB. The script writes into
    # public_map/static/data/ and overwrites whatever the merge left
    # there (including conflict markers).
    _run([sys.executable, "scripts/export_public_map.py"])

    # Stage every regenerated bundle path. We add the whole directory
    # rather than just the conflicted subset so newly-emitted files (e.g.
    # a layer added since the merge target) also land in the merge.
    _run(["git", "add", str(BUNDLE_DIR)])

    if rebasing:
        print("Continuing rebase…")
        _run(["git", "rebase", "--continue"])
        print("Rebase resolved.")
    else:
        # Plain merge. Don't auto-commit — let the operator review the
        # merge commit message before finalizing.
        print(
            "Bundle conflicts resolved and staged. Review the staged diff, then run "
            "`git commit` to finalize the merge with the auto-generated message."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
