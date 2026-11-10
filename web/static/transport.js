/* How the page gets its data. With the server (python -m web) every /api/... call is a normal web request.
   On the static site (scripts/build_static.py sets window.HIMSIM_STATIC) the same calls go to pyworker.js, which runs
   the model in this browser with Pyodide, so no server is needed. Both return the same JSON (web/core.py). */
(() => {
  "use strict";

  let worker = null;
  let nextId = 1;
  const waiting = new Map();
  let banner = null;

  function showStatus(text, done) {
    if (!banner) {
      banner = document.createElement("div");
      banner.className = "loading-banner";
      banner.setAttribute("role", "status");
      banner.setAttribute("aria-live", "polite");
      document.body.prepend(banner);
    }
    banner.textContent = text;
    banner.hidden = !!done;
  }

  function startWorker() {
    worker = new Worker("pyworker.js", { type: "module" });
    worker.onmessage = (e) => {
      const m = e.data;
      if (m.type === "progress") { showStatus(m.text, m.done); return; }
      const p = waiting.get(m.id);
      if (!p) return;
      waiting.delete(m.id);
      if (m.error) { p.reject(new Error(m.error)); return; }
      const out = JSON.parse(m.result);
      if (out.status === 200) p.resolve(out.data);
      else p.reject(new Error(`${out.status} ${out.error}`));
    };
    worker.onerror = (e) => {
      showStatus("The glacier model could not start in this browser. Try reloading, or use a recent Chrome, Edge or Firefox.");
      for (const p of waiting.values()) p.reject(new Error(e.message || "worker failed"));
      waiting.clear();
    };
  }

  function inBrowser(path, options) {
    if (!worker) startWorker();
    const body = options && options.body ? options.body : null;
    return new Promise((resolve, reject) => {
      const id = nextId++;
      waiting.set(id, { resolve, reject });
      worker.postMessage({ id, path, body });
    });
  }

  async function overHttp(path, options) {
    const res = await fetch(path, options);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  }

  const request = (path, options) => (window.HIMSIM_STATIC ? inBrowser : overHttp)(path, options);
  const post = (path, body) => request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

  window.himsim = { request, post, isStatic: () => !!window.HIMSIM_STATIC };
})();
