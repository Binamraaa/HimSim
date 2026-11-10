/* HimSim student site. Plain JavaScript, no build step. All numbers and charts come from web/core.py, via the server
   (web/api.py) or in the browser (pyworker.js); transport.js picks. */
(() => {
  "use strict";

  // ------------------------------------------------------------ helpers
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
  const FONT = '"Inter", "Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif';
  const MAX_KEPT = 7;
  const CONFIG = {
    displaylogo: false, responsive: true,
    modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines", "hoverCompareCartesian", "hoverClosestCartesian"],
    toImageButtonOptions: { format: "png", scale: 2, filename: "himsim" },
  };

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // the API writes **bold** and *italic* like the Streamlit lab; escape first, then format
  const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\*(.+?)\*/g, "<em>$1</em>");
  // guide.js listens to these: it only shows numbers the API sent
  const emit = (name, detail) => document.dispatchEvent(new CustomEvent(`himsim:${name}`, { detail }));
  const signed = (v, digits, unit) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(digits)}${unit}`;

  // transport.js: a web request to the server, or the model running in this browser on the static site
  const api = (path, options) => window.himsim.request(path, options);
  const post = (path, body) => window.himsim.post(path, body);

  let toastTimer;
  function toast(text) {
    const el = $("#toast");
    el.textContent = text;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 5000);
  }
  const failed = (what) => (err) => {
    console.error(what, err);
    toast(window.himsim.isStatic() ? `Couldn't load ${what}. Try reloading the page.` : `Couldn't load ${what}. Is the HimSim server still running?`);
  };

  const plotlyReady = new Promise((resolve) => {
    if (window.Plotly) resolve();
    else window.addEventListener("load", resolve, { once: true });
  });

  function styled(layout, extra) {
    const l = { ...(layout || {}) };
    l.font = { ...(l.font || {}), family: FONT, color: "#4a5868" };
    l.paper_bgcolor = "rgba(0,0,0,0)";
    l.plot_bgcolor = "rgba(0,0,0,0)";
    l.hoverlabel = { font: { family: FONT }, bordercolor: "#dde5ee" };
    l.autosize = true;
    delete l.width;
    if (l.title) {
      const title = typeof l.title === "string" ? { text: l.title } : { ...l.title };
      if (title.text) l.title = { ...title, font: { size: 15, color: "#1e2a38", family: FONT }, x: 0.01, xanchor: "left" };
    }
    return Object.assign(l, extra || {});
  }

  async function plot(id, fig, extra) {
    await plotlyReady;
    const el = document.getElementById(id);
    if (!el || !fig) return;
    $(".skeleton", el)?.remove();
    const figure = { data: fig.data, layout: styled(fig.layout, extra), config: CONFIG };
    if (fig.frames && fig.frames.length) {
      Plotly.purge(el); // animated 3D views: start clean so old frames don't linger
      figure.frames = fig.frames;
      // room for the Play / Pause buttons left of the time slider
      if (figure.layout.sliders) figure.layout.sliders = figure.layout.sliders.map((s) => ({ ...s, x: 0.26, len: 0.74 }));
      await Plotly.newPlot(el, figure);
    } else {
      await Plotly.react(el, figure);
    }
    emit("plotted", { id, el });
  }

  function resizePlots(container) {
    if (!window.Plotly) return;
    $$(".js-plotly-plot", container).forEach((el) => { if (el.offsetParent !== null) Plotly.Plots.resize(el); });
  }

  function setFill(input) {
    const pct = (100 * (input.value - input.min)) / (input.max - input.min || 1);
    input.style.setProperty("--fill", `${pct}%`);
  }

  function renderStats(container, stats) {
    container.innerHTML = stats.map((s) => `
      <div class="stat ${esc(s.tone)}">
        <div class="stat-label">${esc(s.label)}${s.help ? `<button type="button" class="info" aria-label="More about ${esc(s.label)}">?<span class="tip" role="tooltip">${esc(s.help)}</span></button>` : ""}</div>
        <div class="stat-value">${esc(s.value)}</div>
        ${s.delta ? `<div class="stat-delta">${esc(s.delta)}</div>` : ""}
      </div>`).join("");
  }

  function selectTab(buttons, attr, value) {
    buttons.forEach((b) => b.setAttribute("aria-selected", String(b.dataset[attr] === value)));
  }

  // ------------------------------------------------------------ shared overview (hero numbers, today's year)
  let overviewPromise;
  const overview = () => (overviewPromise ||= api("/api/overview").then((o) => { emit("overview", o); return o; }));

  // ------------------------------------------------------------ 1 · Meet Yala
  let meetLoaded = false;
  function loadMeet() {
    if (meetLoaded) return;
    meetLoaded = true;
    overview().then((o) => {
      const s = o.site;
      $("#hero-place").textContent = s.place;
      $("#hero-lede").innerHTML = `A small glacier high in the Himalaya, between about <strong>${s.z_min.toLocaleString("en")} m and ${s.z_max.toLocaleString("en")} m</strong> above sea level. Scientists have measured it for over 40 years. Replay its real history, then choose the climate and see what happens.`;
      $("#hero-badges").innerHTML = [
        `${s.z_min.toLocaleString("en")}–${s.z_max.toLocaleString("en")} m`,
        `Surveys ${s.surveys.join(" · ")}`,
        `Weather from ${s.village}`,
      ].map((t) => `<span class="badge">${esc(t)}</span>`).join("");
      $("#hero-lost").textContent = `${o.lost_pct} %`;
      $("#hero-since").textContent = `${s.start_year} → ${s.today}`;
      $("#past-3d-title").textContent = `Watch ${s.today - s.start_year} years go by`;
      $$(".today").forEach((el) => { el.textContent = s.today; });
      renderStats($("#meet-stats"), o.stats);
      $("#how-know").innerHTML = `Scientists mapped the glacier's surface in <strong>${s.surveys.join(", ")}</strong>. The model starts from the ${s.start_year} map and is fed the <strong>weather of every year</strong> since, as reconstructed for ${esc(s.village)} village (see <a href="#learn">Learn more</a>).`;
      $("#radar-note").innerHTML = o.radar.map((r) => `Green diamond: the ice volume measured with radar in ${r.year} (${r.measured_million_m3} million m³). The model never saw it; its own value for ${r.year} is ${r.model_million_m3} million m³.`).join(" ");
      return plot("past-volume", o.volume_figure, { height: 400 });
    }).catch(failed("the glacier"));
    api("/api/past-3d").then((fig) => plot("past-3d", fig, { height: 540, margin: { l: 0, r: 0, t: 40, b: 0 } }))
      .catch(failed("the 3D view"));
  }

  // ------------------------------------------------------------ 2 · Change the climate
  const fut = {
    warming: 2.0, precip_pct: 0, gradual: true, end_year: 2100, preset: null,
    presets: [], kept: [], view: "compare", last: null, reqId: 0, figs3d: new Map(), mapIndex: null,
  };
  const scenario = () => ({ warming: Math.round(fut.warming * 10) / 10, precip_pct: fut.precip_pct, gradual: fut.gradual, end_year: fut.end_year });
  const keyOf = (s) => `${s.warming.toFixed(1)}|${s.precip_pct}|${s.gradual}|${s.end_year}`;
  const query = (s, extra = {}) => new URLSearchParams({ ...s, ...extra }).toString();

  function syncControls() {
    $("#warming").value = fut.warming;
    $("#precip").value = fut.precip_pct;
    $("#end-year").value = fut.end_year;
    $("#warming-out").textContent = signed(fut.warming, 1, " °C");
    $("#precip-out").textContent = signed(fut.precip_pct, 0, " %");
    $("#end-year-out").textContent = fut.end_year;
    ["#precip", "#end-year"].forEach((s) => setFill($(s)));
    $$(".segmented button").forEach((b) => b.setAttribute("aria-checked", String((b.dataset.gradual === "true") === fut.gradual)));
    $$(".chip", $("#presets")).forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.name === fut.preset)));
    const p = fut.presets.find((x) => x.name === fut.preset);
    $("#preset-note").textContent = p ? p.notes : "";
  }

  let debounce;
  function schedule(ms = 220) {
    clearTimeout(debounce);
    debounce = setTimeout(runFuture, ms);
  }

  function choosePreset(name) {
    const p = fut.presets.find((x) => x.name === name);
    if (!p) return;
    Object.assign(fut, { preset: name, warming: p.warming, precip_pct: p.precip_pct, gradual: p.gradual });
    syncControls();
    schedule(0);
  }

  let futureLoaded = false;
  function loadFuture() {
    if (futureLoaded) { resizePlots($("#page-future")); return; }
    futureLoaded = true;
    overview().then((o) => {
      const s = o.site;
      $("#warming-hint").textContent = `Compared with today's climate (the ${s.today - 9}–${s.today} average). For scale: ${s.village} warmed ${signed(s.recent_warming, 1, " °C")} between ${s.start_year}–${s.period_end} and ${s.today - 9}–${s.today}.`;
    }).catch(() => {});
    api("/api/presets").then((d) => {
      fut.presets = d.presets;
      $("#presets").innerHTML = d.presets.map((p) => `<button type="button" class="chip" data-name="${esc(p.name)}" aria-pressed="false">${esc(p.name)}</button>`).join("");
      choosePreset(d.default);
    }).catch(failed("the climate ideas"));

    $("#presets").addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (chip) choosePreset(chip.dataset.name);
    });
    const onSlide = (field, parse) => (e) => {
      fut[field] = parse(e.target.value);
      fut.preset = null; // moving a slider means "set your own"
      syncControls();
      schedule();
    };
    $("#warming").addEventListener("input", onSlide("warming", parseFloat));
    $("#precip").addEventListener("input", onSlide("precip_pct", (v) => parseInt(v, 10)));
    $("#end-year").addEventListener("input", (e) => { fut.end_year = parseInt(e.target.value, 10); syncControls(); schedule(); });
    $$(".segmented button").forEach((b) => b.addEventListener("click", () => {
      fut.gradual = b.dataset.gradual === "true";
      fut.preset = null;
      syncControls();
      schedule(0);
    }));

    $$("#results .tabs button[data-view]").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
    $("#keep-btn").addEventListener("click", () => {
      if (!fut.last || fut.last.is_baseline || fut.kept.length >= MAX_KEPT) return;
      const s = scenario();
      if (!fut.kept.some((k) => keyOf(k) === keyOf(s))) fut.kept.push(s);
      runFuture();
    });
    $("#clear-btn").addEventListener("click", () => { fut.kept = []; runFuture(); });
    $("#csv-btn").addEventListener("click", downloadCsv);
    $("#map-year").addEventListener("input", (e) => {
      fut.mapIndex = parseInt(e.target.value, 10);
      setFill(e.target);
      $("#map-year-out").textContent = fut.last ? fut.last.snapshot_years[fut.mapIndex] : "";
      clearTimeout(fut.mapTimer);
      fut.mapTimer = setTimeout(loadMaps, 200);
    });
  }

  async function runFuture() {
    const id = ++fut.reqId;
    const s = scenario();
    $("#results").classList.add("busy");
    try {
      const d = await post("/api/future", { scenario: s, kept: fut.kept });
      if (id !== fut.reqId) return; // a newer request is on its way
      fut.last = { ...d, scenario: s };
      renderFuture(d);
    } catch (err) {
      if (id === fut.reqId) failed("the model results")(err);
    } finally {
      if (id === fut.reqId) $("#results").classList.remove("busy");
    }
  }

  function renderFuture(d) {
    $("#headline").innerHTML = md(d.headline);
    $("#comparison").innerHTML = d.comparison ? md(d.comparison) : "";
    renderStats($("#future-stats"), d.stats);
    const s = fut.last.scenario;
    const keptAlready = fut.kept.some((k) => keyOf(k) === keyOf(s));
    $("#keep-btn").disabled = d.is_baseline || keptAlready || fut.kept.length >= MAX_KEPT;
    $("#keep-btn").textContent = keptAlready ? "Kept ✓" : "Keep this result to compare";
    $("#clear-btn").disabled = fut.kept.length === 0;
    renderTable(d);
    if (fut.view === "compare") plot("future-volume", d.volume_figure, { height: 420 });
    if (fut.view === "why") plot("future-smb", d.smb_figure, { height: 480 });
    if (fut.view === "3d") load3d();
    if (fut.view === "maps") setupMaps(true);
    emit("future", { s, d });
  }

  function renderTable(d) {
    const end = d.table.length ? d.table[0].end_year : "";
    $("#future-table").innerHTML = `
      <thead><tr><th>Scenario</th><th>Ice left in ${end}</th><th>Area</th><th>Snowline rise</th><th>Gone by</th></tr></thead>
      <tbody>${d.table.map((r) => `
        <tr>
          <td><span class="swatch ${r.scenario === "Today's climate continues" ? "dashed" : ""}" style="background:${esc(r.color || "#52514e")}"></span>${esc(r.scenario)}</td>
          <td class="num">${r.ice_left_pct} %</td>
          <td class="num">${r.area_km2.toFixed(2)} km²</td>
          <td class="num">${signed(r.snowline_rise_m, 0, " m")}</td>
          <td class="num">${r.gone_by ?? "still there"}</td>
        </tr>`).join("")}</tbody>`;
  }

  function showView(view) {
    fut.view = view;
    selectTab($$("#results .tabs button[data-view]"), "view", view);
    $$("#results .view").forEach((v) => { v.hidden = v.dataset.view !== view; });
    const d = fut.last;
    if (!d) return;
    if (view === "compare") plot("future-volume", d.volume_figure, { height: 420 }).then(() => resizePlots($("#results")));
    if (view === "why") plot("future-smb", d.smb_figure, { height: 480 });
    if (view === "3d") load3d();
    if (view === "maps") setupMaps(false);
    emit("view", view);
  }

  async function load3d() {
    const s = scenario();
    const key = keyOf(s);
    try {
      if (!fut.figs3d.has(key)) {
        if (fut.figs3d.size > 12) fut.figs3d.clear();
        fut.figs3d.set(key, api(`/api/future-3d?${query(s)}`));
      }
      const fig = await fut.figs3d.get(key);
      if (keyOf(scenario()) === key && fut.view === "3d") await plot("future-3d", fig, { height: 540, margin: { l: 0, r: 0, t: 40, b: 0 } });
    } catch (err) {
      fut.figs3d.delete(key);
      failed("the 3D view")(err);
    }
  }

  function setupMaps(scenarioChanged) {
    const years = fut.last.snapshot_years;
    const input = $("#map-year");
    input.max = years.length - 1;
    if (fut.mapIndex === null || fut.mapIndex > years.length - 1 || (scenarioChanged && fut.mapIndex === null)) fut.mapIndex = years.length - 1;
    input.value = fut.mapIndex;
    setFill(input);
    $("#map-year-out").textContent = years[fut.mapIndex];
    loadMaps();
  }

  async function loadMaps() {
    if (!fut.last) return;
    const s = scenario();
    const year = fut.last.snapshot_years[fut.mapIndex];
    try {
      const d = await api(`/api/future-maps?${query(s, { year })}`);
      if (keyOf(scenario()) !== keyOf(s)) return;
      await Promise.all([plot("map-thickness", d.thickness_figure, { height: 420 }), plot("map-change", d.change_figure, { height: 420 })]);
    } catch (err) { failed("the maps")(err); }
  }

  function downloadCsv() {
    if (!fut.last) return;
    const rows = [["scenario", "year", "ice_million_m3", "area_km2", "snowline_m"]];
    fut.last.series.forEach((s) => s.year.forEach((y, i) => rows.push([s.name, y, s.volume_million_m3[i], s.area_km2[i], s.snowline_m[i]])));
    const csv = rows.map((r) => r.map((v) => (/[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : v)).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "yala_scenarios.csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // ------------------------------------------------------------ 3 · Can we trust it?
  const GRADE = {
    matches: ["Matches", "Within the measurement's stated uncertainty, or within 10 %."],
    close: ["Close", "Within 25 % of the measured value."],
    off: ["Off", "More than 25 % away from the measured value."],
  };
  let trustLoaded = false;
  function loadTrust() {
    if (trustLoaded) { resizePlots($("#page-trust")); return; }
    trustLoaded = true;
    api("/api/reality").then((d) => {
      $("#trust-intro").innerHTML = md(d.intro);
      $("#trust-score").innerHTML = Object.entries(GRADE).map(([g, [t, desc]]) => `
        <div class="score-tile ${g}"><span class="n">${d.counts[g]}</span><span><span class="t">${t}</span><br><span class="d">${desc}</span></span></div>`).join("");
      $("#trust-table").innerHTML = `
        <thead><tr><th>What was measured</th><th>Measured</th><th>Model</th><th>Result</th></tr></thead>
        <tbody>${d.rows.map((r) => `
          <tr><td>${esc(r.question)}<span class="src">${esc(r.source)}</span></td><td class="num">${esc(r.measured)}</td>
          <td class="num">${esc(r.model)}</td><td><span class="pill ${esc(r.grade)}">${GRADE[r.grade][0]}</span></td></tr>`).join("")}</tbody>`;
      $("#trust-struggles").innerHTML = d.struggles.length ? `
        <div class="struggles"><h3>Where the model struggles, and why</h3>
        <ul>${d.struggles.map((s) => `<li><em>${esc(s.question)}</em> ${md(s.why)}</li>`).join("")}</ul></div>` : "";
      if (d.yearly) {
        $("#trust-yearly-text").innerHTML = md(d.yearly.text);
        plot("trust-yearly", d.yearly.figure, { height: 380 });
      } else {
        $("#trust-yearly-card").hidden = true;
      }
      plot("trust-bands", d.bands_figure, { height: 420, title: null });
      $("#trust-weather").innerHTML = d.weather.map((p) => `<p>${md(p)}</p>`).join("");
      if (d.station_figure) plot("trust-stations", d.station_figure, { height: 380 });
      else $("#trust-stations").hidden = true;
      const m = d.method;
      $("#trust-method").innerHTML = `
        <p><strong>Grading:</strong> ${md(m.grading)}</p>
        <p><strong>Tuning:</strong> ${md(m.tuning)}</p>
        <p><strong>Sources:</strong></p><ul>${m.sources.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>
        <p><strong>How the model glacier was built:</strong></p><ul>${m.notes.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>`;
      emit("reality", d);
    }).catch(failed("the reality check"));
  }

  // ------------------------------------------------------------ Learn more
  let learnData;
  let learnLoaded = false;
  function showLearn(tab) {
    selectTab($$("#page-learn .tabs button"), "learn", tab);
    $$("#page-learn [data-learn]:not(button)").forEach((el) => { el.hidden = el.dataset.learn !== tab; });
    if (tab === "climate" && learnData) {
      plot("climate-annual", learnData.climate.annual_figure, { height: 540 });
      plot("climate-monthly", learnData.climate.monthly_figure, { height: 340 });
    }
  }
  function loadLearn() {
    if (learnLoaded) { resizePlots($("#page-learn")); return; }
    learnLoaded = true;
    $$("#page-learn .tabs button").forEach((b) => b.addEventListener("click", () => showLearn(b.dataset.learn)));
    api("/api/learn").then((d) => {
      learnData = d;
      $("#learn-how").innerHTML = d.explainer_html; // our own Markdown file, rendered by the server
      const c = d.climate;
      $("#climate-intro").innerHTML = md(c.intro);
      renderStats($("#climate-stats"), c.stats);
      $("#climate-sources").innerHTML = `<ul>${c.sources.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>`;
      const current = $("#page-learn .tabs button[aria-selected='true']").dataset.learn;
      showLearn(current);
    }).catch(failed("the explainer"));
  }

  // ------------------------------------------------------------ router
  const LOADERS = { meet: loadMeet, future: loadFuture, trust: loadTrust, learn: loadLearn };
  function route() {
    const name = location.hash.slice(1);
    const page = LOADERS[name] ? name : "meet";
    $$(".page").forEach((p) => { p.hidden = p.dataset.page !== page; });
    $$(".steps a").forEach((a) => {
      if (a.dataset.page === page) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    window.scrollTo({ top: 0 });
    emit("page", page);
    LOADERS[page]();
    requestAnimationFrame(() => resizePlots($(`#page-${page}`)));
  }
  window.addEventListener("hashchange", route);
  route();
})();
