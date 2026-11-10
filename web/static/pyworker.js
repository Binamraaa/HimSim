/* Runs the HimSim model inside the student's browser (static site only; see transport.js).
   Pyodide = Python compiled to WebAssembly. The first visit downloads Python, numpy, scipy and pandas from the
   jsDelivr CDN plus HimSim itself (py/); the browser caches them, so later visits start much faster.
   Versions are pinned so every student runs exactly the same code.
   First visit, measured 10 Nov 2026 (compressed): 42 MB = CDN 27.9 MB (scipy 13.9, pandas 4.2, Python 5.9, numpy 2.9)
   + HimSim 14.1 MB (plotly wheel 12.1, code + glacier 0.6, Plotly.js 1.3). Ready after ~19 s on a fast line, ~13 s
   with a warm cache. Update the banner text below if these change. */
// A module worker (transport.js starts it with type: "module"): classic importScripts() of the CDN script fails in
// current Chrome, while an ES-module import of pyodide.mjs works.
import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.6/full/pyodide.mjs";

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.6/full/";

const progress = (text, done = false) => postMessage({ type: "progress", text, done });

async function start() {
  progress("Starting the glacier model in your browser (first visit: a one-time download of about 42 MB)…");
  const py = await loadPyodide({ indexURL: PYODIDE });
  progress("Loading the maths libraries (numpy, scipy, pandas)…");
  await py.loadPackage(["numpy", "scipy", "pandas", "micropip"]);
  progress("Loading the chart library…");
  const manifest = await (await fetch("py/manifest.json")).json();
  const micropip = py.pyimport("micropip");
  await micropip.install(manifest.wheels.map((w) => new URL("py/" + w, self.location.href).href));
  progress("Loading Yala Glacier…");
  const zip = await (await fetch("py/" + manifest.code)).arrayBuffer();
  py.unpackArchive(zip, "zip", { extractDir: "/home/pyodide/himsim-app" });
  py.runPython(`
import os, sys
sys.path.insert(0, "/home/pyodide/himsim-app")
os.environ["HIMSIM_WEB_BUNDLE"] = "/home/pyodide/himsim-app/web/data/yala_bundle.pkl.gz"
from web import core
core.model()
`);
  progress("", true);
  return py.pyimport("web.browser");
}

const ready = start();
ready.catch((err) => progress("The glacier model could not start: " + err.message));

// one request at a time: Python here is single-threaded, so requests queue in order
let queue = Promise.resolve();
self.onmessage = (e) => {
  const { id, path, body } = e.data;
  queue = queue.then(async () => {
    try {
      const browser = await ready;
      postMessage({ id, result: browser.handle(path, body) });
    } catch (err) {
      postMessage({ id, error: String(err && err.message ? err.message : err) });
    }
  });
};
