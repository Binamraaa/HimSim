"""Disk cache for expensive, deterministic results (prepared sites, history replays).

Building a site from the raw DEMs (~1.7 GB) and replaying 1981-today takes seconds to
minutes; the results are a few MB. ``cached`` stores them in ``data/cache`` keyed by the
inputs *and* a fingerprint of the himalsim source code and data files, so any code
change automatically invalidates old results. A prepared site therefore works without
the raw DEMs, which is what makes the app quick to start and easy to host.
"""

from __future__ import annotations

import hashlib
import pickle
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

PACKAGE_DIR = Path(__file__).resolve().parent
CACHE_DIR = PACKAGE_DIR.parent / "data" / "cache"

T = TypeVar("T")


@lru_cache(maxsize=1)
def code_fingerprint() -> str:
    """Hash of every source and data file in the package (not caches)."""
    h = hashlib.sha1()
    for path in sorted(PACKAGE_DIR.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".csv", ".geojson"}:
            h.update(path.relative_to(PACKAGE_DIR).as_posix().encode())
            h.update(path.read_bytes())
    return h.hexdigest()[:12]


def cached(kind: str, key: object, compute: Callable[[], T]) -> T:
    """Return ``compute()``, loading it from disk if an identical call was cached before.

    ``key`` must have a deterministic ``repr`` (dataclasses, numbers, strings, tuples).
    """
    fingerprint = code_fingerprint()
    digest = hashlib.sha1(repr(key).encode()).hexdigest()[:16]
    path = CACHE_DIR / f"{kind}_{fingerprint}_{digest}.pkl"
    if path.exists():
        try:
            with path.open("rb") as f:
                return pickle.load(f)
        except Exception:  # corrupt or written by an incompatible version: rebuild
            path.unlink(missing_ok=True)
    value = compute()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for stale in CACHE_DIR.glob(f"{kind}_*.pkl"):  # results from older code are never valid again
        if not stale.name.startswith(f"{kind}_{fingerprint}_"):
            stale.unlink(missing_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("wb") as f:
        pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(path)
    return value
