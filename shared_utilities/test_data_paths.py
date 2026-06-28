"""Canonical paths for regenerated test artifacts under tests/data/."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_DATA_ROOT = REPO_ROOT / "tests" / "data"


def test_output_dir(suite: str | None = None) -> Path:
    """Return (and create) a suite output folder: tests/data/{suite}_out/ or tests/data/out/."""
    if suite:
        path = TEST_DATA_ROOT / f"{suite}_out"
    else:
        path = TEST_DATA_ROOT / "out"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_review_dir() -> Path:
    """Labeled contact-sheet PNGs for visual review: tests/data/review/."""
    path = TEST_DATA_ROOT / "review"
    path.mkdir(parents=True, exist_ok=True)
    return path


def discover_suite_output_dirs() -> list[tuple[str, Path]]:
    """Return (suite_name, path) for each tests/data/*_out/ directory."""
    if not TEST_DATA_ROOT.is_dir():
        return []
    suites: list[tuple[str, Path]] = []
    generic = TEST_DATA_ROOT / "out"
    if generic.is_dir() and any(generic.rglob("*.png")):
        suites.append(("out", generic))
    for path in sorted(TEST_DATA_ROOT.glob("*_out")):
        if path.is_dir() and any(path.rglob("*.png")):
            name = path.name[: -len("_out")]
            suites.append((name, path))
    return suites
