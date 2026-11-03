"""Deploy bundle: everything the website needs, in one small file, for hosts without the raw data.

The website normally builds Yala from the survey DEMs (1.6 GB, git-ignored) and reads the ICIMOD station files
(redistribution not allowed). A host such as Hugging Face Spaces has neither, so this file stores what the site
actually uses:

* the prepared 50 m model glacier (``SiteData``: bed, surface, thickness, outline, survey surfaces at 50 m),
* the 1981 -> today replay (``HistoryRun``) and the climate record it was run with,
* the station checks as **statistics only** (model-minus-thermometer means), never station data.

The DEM owner allowed publishing these derived 50 m grids (owner decision, 3 Nov 2026).

Build it:   python -m web.bundle            (writes web/data/yala_bundle.pkl.gz, ~4 MB)
Use it:     HIMSIM_WEB_BUNDLE=web/data/yala_bundle.pkl.gz python -m web
"""

from __future__ import annotations

import argparse
import gzip
import logging
import pickle
from pathlib import Path

from himsim.store import code_fingerprint

FORMAT_VERSION = 1
DEFAULT_PATH = Path(__file__).with_name("data") / "yala_bundle.pkl.gz"
log = logging.getLogger("himsim.web")


def save(model, path: Path = DEFAULT_PATH) -> Path:
    """Write a ``web.api.Model`` to ``path`` (gzip-compressed pickle)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"format": FORMAT_VERSION, "code": code_fingerprint(), "model": model}
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wb", compresslevel=9) as f:
        pickle.dump(payload, f, protocol=4)  # protocol 4: readable by every Python 3.8+
    tmp.replace(path)
    return path


def load(path: Path):
    """Read a bundle written by :func:`save`. Only load bundles you built yourself: pickle can run code."""
    with gzip.open(Path(path), "rb") as f:
        payload = pickle.load(f)
    if payload.get("format") != FORMAT_VERSION:
        raise RuntimeError(f"{path} is a format-{payload.get('format')} bundle; this code reads format "
                           f"{FORMAT_VERSION}. Rebuild it with: python -m web.bundle")
    if payload["code"] != code_fingerprint():
        # line endings can differ after copying the code to a host, so warn instead of refusing
        log.warning("Bundle %s was built from different himsim code (%s, running %s). Rebuild it with "
                    "`python -m web.bundle` if the physics changed.", path, payload["code"], code_fingerprint())
    return payload["model"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the HimSim website's deploy bundle (needs the Yala DEMs).")
    parser.add_argument("--out", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    from web.api import build_model  # needs the DEMs; the station files are optional

    model = build_model(with_station_summary=True)
    path = save(model, args.out)
    stations = "with" if model.stations else "WITHOUT (station files not found)"
    print(f"Wrote {path} ({path.stat().st_size / 1e6:.1f} MB), {stations} station statistics.")


if __name__ == "__main__":
    main()
