"""Assemble the Hugging Face Space for the student website in dist/hf-space/ (git-ignored).

    python scripts/build_space.py          # rebuild the deploy bundle from the DEMs, then copy the app
    python scripts/build_space.py --keep-bundle   # reuse web/data/yala_bundle.pkl.gz

The folder holds only what the website needs: the himsim package, web/, the student explainer, the licence and
the deploy bundle (50 m model grids + station *statistics*; see web/bundle.py). No raw DEMs, no ICIMOD station
files. Upload it with:

    huggingface-cli upload <user>/<space> dist/hf-space . --repo-type space
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "hf-space"
BUNDLE = ROOT / "web" / "data" / "yala_bundle.pkl.gz"
SOURCE_URL = "https://github.com/Binamraaa/HimSim"

# Same versions as the tested local environment (Python 3.9), so the bundle unpickles exactly as built.
REQUIREMENTS = """\
numpy==1.26.4
pandas==2.2.3
scipy==1.13.1
plotly==5.24.1
rasterio==1.4.3
pyproj==3.6.1
fastapi==0.128.8
starlette==0.49.3
uvicorn==0.39.0
pydantic==2.10.3
markdown==3.4.1
"""

DOCKERFILE = """\
# HimSim student website on Hugging Face Spaces (Docker SDK). Built from the folder made by scripts/build_space.py.
FROM python:3.9-slim

# Spaces run the container as user 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .
ENV HIMSIM_WEB_BUNDLE=/home/user/app/web/data/yala_bundle.pkl.gz
EXPOSE 7860
# two processes for the two CPUs; each loads the 4 MB bundle and pre-computes the common climates
CMD ["python", "-m", "web", "--host", "0.0.0.0", "--port", "7860", "--workers", "2"]
"""

CARD = """\
---
title: HimSim · Yala Glacier
emoji: 🏔️
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: agpl-3.0
short_description: Explore a Himalayan glacier's past and possible futures
---

# HimSim · Yala Glacier

An interactive glacier model for secondary and high-school students. Replay 44 years of Yala Glacier (Langtang,
Nepal), choose a future climate, and check the model against real measurements.

* Source code, data credits and the teacher lab: {source}
* Built from commit `{commit}`.

This Space runs the website from a small deploy bundle: the 50 m model glacier derived from the Yala survey DEMs
and weather-station *statistics*. It contains no raw survey DEMs and no ICIMOD station data.
"""

GITATTRIBUTES = "*.gz filter=lfs diff=lfs merge=lfs -text\n"


def commit_id() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "himsim", "web", "app/how_it_works.md"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.strip()
        return f"{sha}{' + local changes' if dirty else ''}"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep-bundle", action="store_true", help="reuse the existing deploy bundle")
    args = parser.parse_args()

    if not args.keep_bundle or not BUNDLE.exists():
        subprocess.run([sys.executable, "-m", "web.bundle", "--out", str(BUNDLE)], cwd=ROOT, check=True)

    if OUT.exists():
        shutil.rmtree(OUT)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.tmp")
    shutil.copytree(ROOT / "himsim", OUT / "himsim", ignore=ignore)
    shutil.copytree(ROOT / "web", OUT / "web", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.tmp", "data"))
    (OUT / "web" / "data").mkdir()
    shutil.copy2(BUNDLE, OUT / "web" / "data" / BUNDLE.name)
    (OUT / "app").mkdir()
    shutil.copy2(ROOT / "app" / "how_it_works.md", OUT / "app" / "how_it_works.md")
    shutil.copy2(ROOT / "LICENSE", OUT / "LICENSE")
    for name, text in (("requirements.txt", REQUIREMENTS), ("Dockerfile", DOCKERFILE), (".gitattributes", GITATTRIBUTES),
                       ("README.md", CARD.format(source=SOURCE_URL, commit=commit_id()))):
        with open(OUT / name, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    files = [p for p in OUT.rglob("*") if p.is_file()]
    size = sum(p.stat().st_size for p in files) / 1e6
    print(f"Space ready in {OUT}: {len(files)} files, {size:.1f} MB")


if __name__ == "__main__":
    main()
