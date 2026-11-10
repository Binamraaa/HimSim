"""Build the student website as a static site in dist/static-site/ (git-ignored): no server needed.

    python scripts/build_static.py                 # rebuild the deploy bundle from the DEMs, then the site
    python scripts/build_static.py --keep-bundle   # reuse web/data/yala_bundle.pkl.gz
    python -m http.server 8700 -d dist/static-site # try it at http://127.0.0.1:8700

The page is the normal website (web/static) with ``window.HIMSIM_STATIC = true``: every /api/... call then runs
``web/core.py`` inside the student's browser with Pyodide (see web/static/pyworker.js). Any static host serves the
folder (GitHub Pages, Cloudflare Pages, a Hugging Face Static Space, a school computer).

The folder holds the himsim package, web/core.py + web/browser.py, the student explainer, the deploy bundle
(50 m model grids + station *statistics*; see web/bundle.py), pinned wheels for plotly and markdown, and Plotly.js.
No raw DEMs, no ICIMOD station files. Python, numpy, scipy and pandas come from the Pyodide CDN (jsDelivr).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import plotly

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "static-site"
BUNDLE = ROOT / "web" / "data" / "yala_bundle.pkl.gz"
# Pure-Python wheels installed in the browser. Same versions as the server (build_space.py) so the charts match
# the Plotly.js copied below.
WHEELS = ("plotly==5.24.1", "markdown==3.4.1")
WEB_MODULES = ("__init__.py", "core.py", "browser.py", "bundle.py")
FLAG = "<script>window.HIMSIM_STATIC = true;</script>"
# Parts of the plotly wheel the browser never uses (19 MB -> ~8 MB): the JupyterLab extension (stored twice), a
# second copy of Plotly.js (the page loads vendor/plotly.min.js), sample datasets and the matplotlib converter.
WHEEL_DROP = ("jupyterlab_plotly/", "plotly/package_data/plotly.min.js", "plotly/package_data/datasets/",
              "plotly/matplotlylib/")


def slim_wheel(path: Path) -> None:
    """Rewrite a wheel without the WHEEL_DROP files (RECORD updated to match, so the installer stays happy)."""
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as dst:
        def dropped(name: str) -> bool:
            return name.startswith(WHEEL_DROP) or name.split("/", 1)[0].endswith(".data")  # .data/: Jupyter files
        for info in src.infolist():
            name = info.filename
            if dropped(name):
                continue
            data = src.read(name)
            if name.endswith(".dist-info/RECORD"):
                kept = [line for line in data.decode().splitlines() if line and not dropped(line.split(",", 1)[0])]
                data = ("\n".join(kept) + "\n").encode()
            dst.writestr(name, data)
    tmp.replace(path)


def code_zip(dest: Path) -> None:
    """himsim + the server-free part of web/ + explainer + bundle, as the worker unpacks them."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted((ROOT / "himsim").rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".tmp"):
                z.write(p, p.relative_to(ROOT).as_posix())
        for name in WEB_MODULES:
            z.write(ROOT / "web" / name, f"web/{name}")
        z.write(BUNDLE, f"web/data/{BUNDLE.name}")
        z.write(ROOT / "app" / "how_it_works.md", "app/how_it_works.md")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep-bundle", action="store_true", help="reuse the existing deploy bundle")
    args = parser.parse_args()

    if not args.keep_bundle or not BUNDLE.exists():
        subprocess.run([sys.executable, "-m", "web.bundle", "--out", str(BUNDLE)], cwd=ROOT, check=True)

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "web" / "static", OUT)
    (OUT / "vendor").mkdir()
    shutil.copy2(Path(plotly.__file__).parent / "package_data" / "plotly.min.js", OUT / "vendor" / "plotly.min.js")

    py = OUT / "py"
    py.mkdir()
    subprocess.run([sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary", ":all:", "-q", "-d", str(py),
                    *WHEELS], check=True)
    wheels = sorted(p.name for p in py.glob("*.whl"))
    for w in py.glob("plotly-*.whl"):
        slim_wheel(w)
    tmp = py / "code.zip"
    code_zip(tmp)
    code = f"himsim-{hashlib.sha256(tmp.read_bytes()).hexdigest()[:12]}.zip"  # new name per build: no stale caches
    tmp.rename(py / code)
    (py / "manifest.json").write_text(json.dumps({"code": code, "wheels": wheels}, indent=1), encoding="utf-8")

    index = OUT / "index.html"
    html = index.read_text(encoding="utf-8")
    assert html.count("</head>") == 1
    index.write_text(html.replace("</head>", f"  {FLAG}\n</head>"), encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")  # GitHub Pages: serve files as they are
    shutil.copy2(ROOT / "LICENSE", OUT / "LICENSE.txt")

    files = [p for p in OUT.rglob("*") if p.is_file()]
    size = sum(p.stat().st_size for p in files) / 1e6
    print(f"Static site ready in {OUT}: {len(files)} files, {size:.1f} MB "
          f"(+ Pyodide, numpy, scipy, pandas from the CDN)\n  try: python -m http.server 8700 -d {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
