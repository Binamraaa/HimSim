/* HimSim student guide: hover tips ("What am I looking at?"), the welcome tour and "Try this" missions.
   Plain JavaScript, no build step. Every number in the guide comes from the API, passed on by app.js as
   "himsim:*" events, so the guide stays true when the model changes. Text is for 14–18-year-olds. */
(() => {
  "use strict";

  // ------------------------------------------------------------ helpers
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\*(.+?)\*/g, "<em>$1</em>");
  const signed = (v, digits, unit) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(digits)}${unit}`;
  const val = (x) => (typeof x === "function" ? x() : x);
  const BASELINE = "Today's climate continues"; // same label as web/api.py

  const store = { // browser storage can be missing (private windows, blocked site data): fall back to memory
    mem: {},
    get(key, fallback) {
      try { const v = localStorage.getItem(key); if (v !== null) return JSON.parse(v); } catch (e) { /* use memory */ }
      return key in this.mem ? this.mem[key] : fallback;
    },
    set(key, value) {
      this.mem[key] = value;
      try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* memory only */ }
    },
  };
  const KEY = { tour: "himsim.tour.seen", tips: "himsim.tips", missions: "himsim.missions" };

  async function post(path, body) {
    const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  }

  // ------------------------------------------------------------ what the page currently shows (from app.js events)
  const ctx = { page: "meet", overview: null, future: null, view: "compare", reality: null };
  const site = () => ctx.overview && ctx.overview.site;
  const rowOf = (d, name) => d.table.find((r) => r.scenario === name);
  const seriesOf = (d, name) => d.series.find((s) => s.name === name);
  const outcomeOf = (r) => (r.gone_by
    ? `is gone by about <strong>${r.gone_by}</strong>`
    : `keeps <strong>${pctText(r.ice_left_pct)}</strong> of today's ice in ${r.end_year}`);
  const pctText = (p) => (p < 1 ? "less than 1 %" : `${p} %`);
  const snowlineStat = () => ctx.overview && ctx.overview.stats.find((s) => /snowline/i.test(s.label));

  function endSnowline(d) {
    const s = seriesOf(d, d.label);
    const top = site() && site().z_max;
    if (!s || !top) return null;
    const z = s.snowline_m[s.snowline_m.length - 1];
    const year = s.year[s.year.length - 1];
    const fmt = (v) => Math.round(v).toLocaleString("en");
    return z > top
      ? `In ${year} the snowline is at about <strong>${fmt(z)} m</strong>, above the top of the glacier (about ${fmt(top)} m). `
        + "Nowhere on the glacier gains snow any more, so it can only melt away, even if that takes decades."
      : `In ${year} the snowline is at about <strong>${fmt(z)} m</strong>, below the top of the glacier (about ${fmt(top)} m). `
        + "The highest part still gains snow each year, which feeds the glacier.";
  }

  // ------------------------------------------------------------ hover tips: what each part of the page shows
  const GUIDE = {
    "meet-lost": {
      title: "Ice lost so far",
      see: "How much of Yala's ice has melted since the first survey map, as the model calculates it.",
      means: () => ctx.overview && `Think of the ice Yala had in ${site().start_year} as 100 buckets. By the end of ${site().today}, `
        + `about <strong>${ctx.overview.lost_pct}</strong> of them have melted away.`,
    },
    "meet-stats": {
      title: "Key numbers",
      see: "Four numbers that sum up the glacier's story, from the first survey to today.",
      read: "The small text under a number shows the change. Hover or tap a <strong>?</strong> for more.",
      means: () => snowlineStat() && `The <strong>snowline</strong> is the height above which the glacier gains snow each year. `
        + `It has moved <strong>${esc(snowlineStat().value)}</strong> up the mountain, so less of Yala gains snow and more of it melts.`,
    },
    "meet-3d": {
      title: "The glacier in 3D",
      see: "The real shape of the mountain (grey rock) with the model's ice on top. The ice colour shows its thickness: "
        + "dark blue is thick, light blue is thin.",
      read: "Press <strong>▶ Play</strong> to watch the years go by; the year is in the title. Drag to turn the view, scroll or "
        + "pinch to zoom. The sides show distance in kilometres.",
      means: "Keep an eye on the lowest part, the <strong>tongue</strong>. It is the warmest part of the glacier, so it thins "
        + "and pulls back first.",
    },
    "meet-volume": {
      title: "How much ice is left?",
      see: "The total amount of ice in the glacier each year, as the model calculates it. One million m³ is about "
        + "400 Olympic swimming pools.",
      read: "Time runs left to right; the higher the line, the more ice. The green diamond is a radar measurement; its bar "
        + "reaches the highest amount the scientists thought possible.",
      means: () => ctx.overview && ctx.overview.radar.map((r) => `In ${r.year} the radar measured <strong>${r.measured_million_m3} `
        + `million m³</strong>; the model gives <strong>${r.model_million_m3}</strong>. The model was never shown this number, `
        + "so it's a fair test.").join(" "),
    },
    "future-presets": {
      title: "Climate ideas",
      see: "Ready-made futures. Clicking one sets the sliders for you.",
      read: "The blue idea is the one in use. Moving a slider switches to your own climate.",
      means: "Start with <strong>Today's climate continues</strong>: it shows what happens if nothing changes from now on.",
    },
    "future-warming": {
      title: "Temperature change",
      see: "How much warmer (or cooler) the air around Yala gets compared with today's climate.",
      read: "Blue end: cooler. Orange end: warmer. <em>Gradually</em> reaches this value in 2100; <em>All at once</em> starts it now.",
      means: () => site() && `This is the warming at the glacier itself, not the world average. For scale: ${esc(site().village)} `
        + `has already warmed <strong>${signed(site().recent_warming, 1, " °C")}</strong> between ${site().start_year}–`
        + `${site().period_end} and ${site().today - 9}–${site().today}.`,
    },
    "future-precip": {
      title: "Rain and snow",
      see: "How much more or less rain and snow falls each year, compared with today.",
      read: "−50 % means half as much; +50 % means one and a half times as much.",
      means: "Snow is the glacier's food. Whether it falls as snow or as rain depends on the temperature, so warming also "
        + "turns some of the snow into rain.",
    },
    "future-mode": {
      title: "How the change arrives",
      see: "<strong>Gradually</strong>: the change grows a little every year until 2100, then stays at that level. "
        + "<strong>All at once</strong>: the full change starts right now.",
      means: "\"All at once\" isn't realistic, but it shows how fast the glacier reacts to a new climate.",
    },
    "future-headline": {
      title: "Your result in one sentence",
      see: "What happens to Yala with the climate you chose. Underneath: what happens if today's climate simply continues, "
        + "for comparison.",
      read: "\"Gone\" means less than 1 % of today's glacier area is left.",
    },
    "future-stats": {
      title: "Four numbers for your climate",
      see: () => `The glacier at the end of your run, compared with the end of ${site() ? site().today : "today"}.`,
      read: "<strong>Ice left</strong>: 100 % would mean no change. <strong>Snowline</strong>: the height where a year's "
        + "snowfall and melting balance; above it the glacier gains ice, below it the glacier loses ice.",
    },
    "future-compare": {
      title: "Past and future ice",
      see: "The ice in the glacier, year by year. Thick grey line: the past, replayed by the model. Dashed line: today's "
        + "climate continues. Coloured lines: your climate and the results you kept.",
      read: "The dotted line marks today. Hover the chart to read any year. Click <strong>Keep this result</strong> to add a "
        + "line and compare climates.",
      means: () => {
        const f = ctx.future;
        const s = f && seriesOf(f.d, f.d.label);
        if (!s) return null;
        const last = s.volume_million_m3.length - 1;
        return `Your ${f.d.is_baseline ? "dashed " : ""}line ends at <strong>${s.volume_million_m3[last].toFixed(1)} million m³`
          + `</strong> in ${s.year[last]}. When a line reaches the bottom, the glacier is gone.`;
      },
    },
    "future-table": {
      title: "All your results",
      see: "One row per climate: today's climate continuing, every result you kept, and the one you're looking at.",
      read: "<strong>Snowline rise</strong>: how many metres higher the snowline is at the end than today. <strong>Gone by"
        + "</strong>: the year when less than 1 % of today's glacier area is left.",
      means: "Download the numbers (CSV) to make your own graphs in a spreadsheet.",
    },
    "future-3d": {
      title: "Your future in 3D",
      see: "The glacier from today to the end of your run, on the real shape of the mountain. Dark blue ice is thick, "
        + "light blue is thin.",
      read: "Press <strong>▶ Play</strong>. Drag to turn the view, scroll or pinch to zoom.",
      means: "Compare it with the past on the first page: does the ice thin everywhere, or mostly low down?",
    },
    "future-maps": {
      title: "Maps from above",
      see: "Left: how thick the ice is in the chosen year (darker blue = thicker). Right: how much the surface has changed "
        + "since today: red = thinner, blue = thicker, grey = no change.",
      read: "Drag the <strong>Year</strong> slider. The black line is the glacier's outline in 2000.",
      means: "Look where the red is darkest. Is it high up or low down? Low on the glacier the air is warmest.",
    },
    "future-why": {
      title: "Gain and loss at each height",
      see: "For each height on the mountain: how much ice a spot gains in a year (right of the dotted zero line) or loses "
        + "(left of it). Dark grey line: today's climate. Coloured line: your climate in the end year.",
      read: "Height goes up the page. Where a line crosses zero is the <strong>snowline</strong>. The grey band shows the "
        + "heights the glacier covers.",
      means: () => ctx.future && endSnowline(ctx.future.d),
    },
    "trust-score": {
      title: "The scorecard",
      see: "How many of the scientists' measurements the model matches.",
      read: "<strong>Matches</strong>: inside the measurement's uncertainty, or within 10 %. <strong>Close</strong>: within "
        + "25 %. <strong>Off</strong>: further away.",
      means: () => {
        const c = ctx.reality && ctx.reality.counts;
        return c && `${c.matches} match, ${c.close} are close and ${c.off} ${c.off === 1 ? "is" : "are"} off. The model was `
          + "tuned with one number only, so these measurements are a fair test.";
      },
    },
    "trust-table": {
      title: "Every measurement",
      see: "Each row is something scientists measured on Yala: their value, the model's value and the grade.",
      read: "The grey text under each question says where the measurement was published, so you can look it up.",
      means: "Read the yellow box below, too: knowing where a model struggles is as useful as knowing where it's right.",
    },
    "trust-yearly": {
      title: "Good years and bad years",
      see: "How much ice the whole glacier gained or lost each year, as a layer of water spread over the glacier. Blue dots: "
        + "measured with stakes drilled into the ice (the bars show the measurement's error). Orange squares: the model.",
      read: "Below the dotted zero line the glacier lost ice that year. If an orange square sits inside the blue bar, the "
        + "model got that year right.",
      means: "Single years are hard to get right; the long-term average is easier. That's why the model's futures are "
        + "\"what if\" experiments, not forecasts.",
    },
    "trust-bands": {
      title: "Where did the ice thin?",
      see: "How much the surface dropped between the first and the last survey map, at each height. Blue: measured by "
        + "comparing the maps. Orange: the model.",
      read: "Height goes up the page. Further left means more thinning.",
      means: () => bandGap() && `${bandGap()} Where the two lines are close, the model is right.`,
    },
    "trust-weather": {
      title: "Checking the weather",
      see: "The model's air temperature compared with real thermometers at weather stations near Yala.",
      read: "In the chart, each mark is the model minus the thermometer: above zero, the model is too warm; below, too cold. "
        + "Circles: the whole year. Squares: the monsoon, when Yala melts.",
      means: "Marks near zero mean the model's weather is right. The station on the ice reads colder, because the ice chills "
        + "the air just above it.",
    },
    "learn-annual": {
      title: "Climate, year by year",
      see: "Top: the average temperature at Kyanjin each year, with the trend as a dashed line. Bottom: how much rain and "
        + "snow fell each year.",
      read: "Hover to read a year. The legend shows how fast the temperature has risen, per ten years.",
      means: "Rain and snow jump around from year to year; the temperature climbs more steadily. Both matter for the glacier.",
    },
    "learn-monthly": {
      title: "An average year",
      see: "The climate at Kyanjin month by month. Left: temperature. Right: rain and snow.",
      means: "Most rain and snow falls in the summer monsoon, the same months the glacier melts. On Yala, summer brings both "
        + "gains (snow high up) and losses (melt low down).",
    },
  };

  function bandGap() {
    const f = ctx.reality && ctx.reality.bands_figure;
    if (!f) return null;
    const obs = f.data.find((t) => /observed/i.test(t.name));
    const mod = f.data.find((t) => /model/i.test(t.name));
    if (!obs || !mod) return null;
    let best = -1;
    obs.y.forEach((z, i) => {
      if (obs.x[i] !== null && mod.x[i] !== null && (best < 0 || Math.abs(mod.x[i] - obs.x[i]) > Math.abs(mod.x[best] - obs.x[best]))) best = i;
    });
    if (best < 0) return null;
    const lowest = Math.min(...obs.y);
    return `The biggest gap is around <strong>${Math.round(obs.y[best]).toLocaleString("en")} m</strong>: the survey maps show `
      + `${signed(obs.x[best], 0, " m")}, the model ${signed(mod.x[best], 0, " m")}.`
      + (obs.y[best] === lowest ? " That's the tongue, the lowest part of the glacier." : "");
  }

  // ------------------------------------------------------------ hover-tip popover
  const pop = document.createElement("div");
  pop.className = "guide-pop";
  pop.id = "guide-pop";
  pop.setAttribute("role", "dialog");
  pop.setAttribute("aria-label", "What am I looking at?");
  pop.hidden = true;
  document.body.appendChild(pop);

  const canHover = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  const tipsOn = () => store.get(KEY.tips, true);
  let current = null;   // element whose tip is showing
  let pending = null;   // element waiting for the hover delay
  let pinned = false;   // opened with a ? button: stays until closed
  let showTimer;
  let hideTimer;

  function resolveKey(key) {
    if (key !== "@view") return key;
    const view = $$(".view").find((v) => !v.hidden && v.offsetParent !== null);
    return view ? view.dataset.guide : null;
  }

  function showTip(el, pin) {
    const g = GUIDE[el.dataset.guide];
    if (!g) return;
    let means = null;
    try { means = val(g.means); } catch (err) { console.warn("guide", err); }
    pop.innerHTML = `
      <div class="gp-head"><span class="gp-eyebrow">What am I looking at?</span>
        <button type="button" class="gp-close" aria-label="Close">×</button></div>
      <h3>${val(g.title)}</h3>
      ${g.see ? `<p>${val(g.see)}</p>` : ""}
      ${g.read ? `<p><span class="gp-label">How to read it</span>${val(g.read)}</p>` : ""}
      ${means ? `<div class="gp-means"><span class="gp-label">What it means</span>${means}</div>` : ""}
      ${pin ? "" : `<p class="gp-foot">Too many tips? Switch them off under <strong>Guide</strong> at the top.</p>`}`;
    if (current && current !== el) current.classList.remove("guide-focus");
    current = el;
    pinned = pin;
    pending = null;
    el.classList.add("guide-focus");
    pop.hidden = false;
    pop.classList.toggle("pinned", pin);
    place(el);
    if (pin) $(".gp-close", pop).focus({ preventScroll: true });
  }

  function hideTip() {
    clearTimeout(showTimer);
    clearTimeout(hideTimer);
    pop.hidden = true;
    pinned = false;
    pending = null;
    if (current) current.classList.remove("guide-focus");
    current = null;
  }

  function place(target) {
    const r = target.getBoundingClientRect();
    const vw = document.documentElement.clientWidth;
    const vh = window.innerHeight;
    const top0 = ($(".topbar")?.getBoundingClientRect().bottom || 0) + 8;
    const gap = 12;
    pop.style.left = "8px";
    pop.style.top = `${top0}px`;
    const w = pop.offsetWidth;
    const h = pop.offsetHeight;
    const clampX = (x) => Math.max(8, Math.min(x, vw - w - 8));
    const clampY = (y) => Math.max(top0, Math.min(y, vh - h - 8));
    const sides = [ // the side with room wins, so the tip never covers what it explains
      [r.top - gap - h >= top0, () => [clampX(r.left), r.top - gap - h]],
      [r.bottom + gap + h <= vh - 8, () => [clampX(r.left), r.bottom + gap]],
      [r.right + gap + w <= vw - 8, () => [r.right + gap, clampY(r.top)]],
      [r.left - gap - w >= 8, () => [r.left - gap - w, clampY(r.top)]],
    ];
    const side = sides.find(([fits]) => fits);
    const [x, y] = side ? side[1]() : [clampX(r.right - w - 12), clampY(Math.max(r.top, top0) + 12)];
    pop.style.left = `${Math.round(x)}px`;
    pop.style.top = `${Math.round(y)}px`;
  }

  document.addEventListener("mouseover", (e) => {
    if (!canHover || !tipsOn() || pinned || tour.open || e.buttons) return;
    if (pop.contains(e.target)) { clearTimeout(hideTimer); return; }
    const el = e.target.closest("[data-guide]");
    if (el && el === current) { clearTimeout(hideTimer); return; }
    if (el && el === pending) return;
    clearTimeout(showTimer);
    pending = el;
    if (!el) { if (current) hideTimer = setTimeout(hideTip, 300); return; }
    const quick = current && !pop.hidden; // moving from one section to the next: swap fast
    showTimer = setTimeout(() => showTip(el, false), quick ? 200 : 650);
  });
  document.documentElement.addEventListener("mouseleave", () => { if (!pinned) hideTip(); });
  window.addEventListener("scroll", () => { if (pinned && current) place(current); else if (current || pending) hideTip(); }, { passive: true });
  window.addEventListener("resize", () => { if (current) place(current); });
  document.addEventListener("mousedown", (e) => { if (!pinned && current && !pop.contains(e.target)) hideTip(); }); // dragging a chart or slider

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-guide-open]");
    if (btn) {
      e.preventDefault();
      e.stopPropagation();
      const key = resolveKey(btn.dataset.guideOpen);
      const el = key && $$(`[data-guide="${key}"]`).find((x) => x.offsetParent !== null);
      if (!el) return;
      if (pinned && current === el) hideTip();
      else showTip(el, true);
      return;
    }
    if (e.target.closest(".gp-close")) { hideTip(); return; }
    if (pinned && !pop.contains(e.target)) hideTip();
  });

  // ------------------------------------------------------------ "Try this" missions
  const MISSIONS = [
    {
      id: "meet-play", page: "meet", short: "Play the history",
      title: "Watch the glacier's history",
      task: "Press <strong>▶ Play</strong> under the 3D glacier and watch it from the first survey to today. Which part of the "
        + "glacier changes most?",
      hint: "The Play button is at the bottom left of the 3D view. You can also drag the time slider next to it.",
    },
    {
      id: "meet-radar", page: "meet", short: "Find the fair test",
      title: "Find the measurement the model never saw",
      task: "In <strong>How much ice is left?</strong>, find the green diamond and hover over it (or tap it) to read its value.",
      hint: "It sits on the line, a few years before the dotted \"today\" line.",
    },
    {
      id: "f-today", page: "future", short: "No more warming",
      title: "What if the warming stopped today?",
      task: "Choose <strong>Today's climate continues</strong>. Does the glacier stop shrinking?",
      hint: "It's the first idea in the list on the left.",
    },
    {
      id: "f-memory", page: "future", short: "The long run",
      title: "Does the shrinking ever stop?",
      task: "Keep today's climate, open <strong>More options</strong> and run the model until 2200 or later. What happens "
        + "after 2100?",
      hint: "\"More options\" is at the bottom of the controls. Drag the end year to 2200.",
    },
    {
      id: "f-tipping", page: "future", short: "Tipping point",
      title: "Find the tipping point",
      task: "With the end year at 2100, find two temperatures <strong>no more than 0.5 °C apart</strong>: one where Yala "
        + "still has some ice in 2100, and one where it is gone.",
      hint: "Try the +1.5 °C idea first. Then move the temperature slider down in small steps until some ice is left in "
        + "2100. Keep both results to compare them.",
    },
    {
      id: "f-snow", page: "future", short: "Can snow save it?",
      title: "Can more snow save the glacier?",
      task: "Set at least <strong>+1.5 °C</strong> of warming, then make it <strong>30 % wetter or more</strong>. Does the "
        + "extra snow save Yala?",
      hint: "Use the \"Rain and snow\" slider. More snowfall is more food for the glacier.",
    },
    {
      id: "f-sudden", page: "future", short: "Slow or sudden?",
      title: "Slow or sudden?",
      task: "Pick a warming of at least +0.5 °C and run it both <strong>Gradually</strong> and <strong>All at once</strong>. "
        + "How much sooner does the glacier go?",
      hint: "Switch between the two buttons under \"How does the change arrive?\". Keep one result to see both lines.",
    },
    {
      id: "f-why", page: "future", short: "Why does it vanish?",
      title: "Why does the glacier vanish?",
      task: "Choose <strong>+1.5 °C or more</strong> and open the <strong>Why?</strong> tab. Where is the snowline at the end, "
        + "compared with the top of the glacier?",
      hint: "The snowline is where the coloured line crosses the dotted zero line. The grey band shows the glacier's heights.",
    },
    {
      id: "f-cool", page: "future", short: "A cooler world",
      title: "Can the glacier grow back?",
      task: "Try a <strong>cooler</strong> climate (−0.5 °C or colder). Does Yala grow?",
      hint: "Try the \"Cooler\" idea, then try the same cooling \"Gradually\".",
    },
    {
      id: "t-weak", page: "trust", short: "Weakest spot",
      title: "Find the model's weakest spot",
      task: "Look at the table. Which measurement does the model get most wrong? Think about why before you look at the answer.",
      think: true,
    },
    {
      id: "t-bands", page: "trust", short: "Where it thins",
      title: "Where does the model go wrong?",
      task: "In <strong>Where on the glacier did the ice thin?</strong>, at which height are the model and the survey maps "
        + "furthest apart?",
      think: true,
    },
    {
      id: "t-year", page: "trust", short: "Can we use it?",
      title: "Wrong years, right average",
      task: "The model gets the average right but misses most single years. Can we still use it to explore the future? "
        + "Decide what you think first.",
      think: true,
    },
  ];
  const PAGES = ["meet", "future", "trust"];
  const PAGE_NAMES = { meet: "Meet Yala", future: "Change the climate", trust: "Can we trust it?" };
  let done = store.get(KEY.missions, {});
  if (!done || typeof done !== "object") done = {};
  const selected = {};

  const THINK_ANSWERS = {
    "t-weak": () => {
      const r = ctx.reality;
      if (!r) return null;
      const off = r.rows.filter((x) => x.grade === "off");
      const pick = off.length ? off : r.rows.filter((x) => x.grade === "close").slice(0, 1);
      if (!pick.length) return "Every measurement matches. A rare result for a model!";
      return pick.map((x) => {
        const why = r.struggles.find((s) => s.question === x.question);
        return `<strong>${esc(x.question)}</strong> is graded <em>${x.grade === "off" ? "Off" : "Close"}</em>: measured `
          + `${esc(x.measured)}, model ${esc(x.model)}. ${why ? md(why.why) : ""}`;
      }).join("<br><br>") + "<br><br>Scientists use spots like this to decide what to improve next.";
    },
    "t-bands": () => bandGap() && `${bandGap()} Models are rarely right everywhere. Knowing where they struggle tells you how `
      + "much to trust each part of the result.",
    "t-year": () => "Yes, for the big picture. The model uses monthly weather from a computer reconstruction, so it can't "
      + "know about one snowy winter or one sunny summer. Over many years those ups and downs average out, and the average "
      + "is what it gets right. That's why its futures are \"what if\" experiments, not forecasts of a particular year.",
  };

  const missionsOn = (page) => MISSIONS.filter((m) => m.page === page);
  const doneCount = (list = MISSIONS) => list.filter((m) => m.id in done).length;

  function renderMissions() {
    $$("[data-missions]").forEach((box) => {
      const page = box.dataset.missions;
      const list = missionsOn(page);
      if (!list.length) return;
      const sel = list.find((m) => m.id === selected[page]) || list.find((m) => !(m.id in done)) || list[0];
      selected[page] = sel.id;
      const isDone = sel.id in done;
      box.innerHTML = `
        <header class="missions-head">
          <div class="missions-title">
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/></svg>
            <div><h2>Try this</h2><p>Small missions that show how glaciers behave.</p></div>
          </div>
          <span class="missions-count">${doneCount(list)} of ${list.length} done</span>
        </header>
        <div class="mission-tabs" role="tablist" aria-label="Missions">
          ${list.map((m, i) => `
            <button type="button" role="tab" class="mission-tab${m.id in done ? " done" : ""}" data-mission="${m.id}"
              aria-selected="${m.id === sel.id}"><span class="mt-num">${m.id in done ? "✓" : i + 1}</span>${esc(m.short)}</button>`).join("")}
        </div>
        <div class="mission-body" role="tabpanel">
          <h3>${esc(sel.title)}</h3>
          <p class="mission-task">${sel.task}</p>
          ${!isDone && sel.think ? `<button type="button" class="btn btn-primary" data-reveal="${sel.id}">I've thought about it: show the answer</button>` : ""}
          ${!isDone && sel.hint ? `<details class="mission-hint"><summary>Need a hint?</summary><p>${sel.hint}</p></details>` : ""}
          ${!isDone && !sel.think ? `<p class="mission-status"><span class="dot"></span>Waiting for you to try it…</p>` : ""}
          ${isDone ? `<div class="mission-found"><span class="gp-label">What you discovered</span>${done[sel.id]}</div>` : ""}
        </div>`;
    });
    renderMenu();
  }

  document.addEventListener("click", (e) => {
    const tab = e.target.closest(".mission-tab");
    if (tab) {
      const m = MISSIONS.find((x) => x.id === tab.dataset.mission);
      selected[m.page] = m.id;
      renderMissions();
      $(`[data-missions="${m.page}"] .mission-tab[aria-selected="true"]`)?.focus();
      return;
    }
    const reveal = e.target.closest("[data-reveal]");
    if (reveal) {
      const answer = THINK_ANSWERS[reveal.dataset.reveal]();
      if (!answer) { reveal.textContent = "Still loading the results… try again in a moment"; return; }
      complete(reveal.dataset.reveal, answer, false);
    }
  });

  function complete(id, found, popup = true) {
    if (id in done || !found) return;
    done[id] = found;
    store.set(KEY.missions, done);
    const m = MISSIONS.find((x) => x.id === id);
    selected[m.page] = id;
    renderMissions();
    if (popup) showDiscovery(m);
  }

  // the "mission complete" card
  const disc = document.createElement("aside");
  disc.className = "discovery";
  disc.setAttribute("role", "status");
  disc.hidden = true;
  document.body.appendChild(disc);

  function nextMission(m) {
    const samePage = missionsOn(m.page).find((x) => !(x.id in done)); // finish this page first
    if (samePage) return samePage;
    const order = PAGES.flatMap(missionsOn);
    const start = order.indexOf(m);
    return order.slice(start + 1).concat(order.slice(0, start)).find((x) => !(x.id in done));
  }

  function showDiscovery(m) {
    const next = nextMission(m);
    disc.innerHTML = `
      <div class="disc-head"><span class="disc-check" aria-hidden="true">✓</span><span class="gp-eyebrow">Mission complete · `
      + `${doneCount()} of ${MISSIONS.length}</span><button type="button" class="gp-close" aria-label="Close">×</button></div>
      <h3>${esc(m.title)}</h3>
      <div class="disc-body">${done[m.id]}</div>
      <div class="disc-actions">
        ${next ? `<button type="button" class="btn btn-primary" data-next="${next.id}">Next mission${next.page !== m.page ? `: ${esc(PAGE_NAMES[next.page])}` : ""} →</button>`
          : `<span class="disc-all">You've done every mission. Well done!</span>`}
        <button type="button" class="btn" data-close-disc>Close</button>
      </div>`;
    disc.hidden = false;
  }
  disc.addEventListener("click", (e) => {
    if (e.target.closest(".gp-close, [data-close-disc]")) { disc.hidden = true; return; }
    const next = e.target.closest("[data-next]");
    if (next) {
      const m = MISSIONS.find((x) => x.id === next.dataset.next);
      selected[m.page] = m.id;
      disc.hidden = true;
      renderMissions();
      if (ctx.page !== m.page) location.hash = m.page;
      setTimeout(() => $(`[data-missions="${m.page}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 80);
    }
  });

  // --- checks: each mission completes when the student has actually done it
  const runs = new Map(); // every future the student ran: key -> {s, r}
  const runKey = (s) => `${s.warming.toFixed(1)}|${s.precip_pct}|${s.gradual}|${s.end_year}`;
  let snowCheck = null;

  function checkFuture() {
    const { s, d } = ctx.future;
    const r = rowOf(d, d.label);
    if (!r) return;

    if (d.is_baseline) {
      const rise = snowlineStat();
      complete("f-today", `Even if the climate stops warming today, Yala ${outcomeOf(r)}.`
        + (rise ? ` The snowline already sits <strong>${esc(rise.value)}</strong> higher than in ${site().start_year}–`
          + `${site().period_end}, so the glacier is too big for today's climate.` : "")
        + " It keeps shrinking until it fits the climate again. Scientists call this <em>committed</em> ice loss.");
    }

    if (d.is_baseline && s.end_year >= 2150) {
      const ser = seriesOf(d, BASELINE);
      const i2100 = ser.year.findIndex((y) => y >= 2100);
      const pct = (i) => Math.round((100 * ser.volume_million_m3[i]) / ser.volume_million_m3[0]);
      const last = ser.year.length - 1;
      const head = `Ice left: <strong>${pct(i2100)} %</strong> in 2100 and <strong>${pct(last)} %</strong> in ${ser.year[last]}. `;
      const why = "As the glacier pulls back up the mountain, a bigger share of what is left sits above the snowline, where "
        + "it gains snow. A glacier shrinks until its gains and losses balance again.";
      complete("f-memory", r.gone_by
        ? `${head}It never finds a new balance: it is gone by about <strong>${r.gone_by}</strong>.`
        : `${head}${pct(i2100) - pct(last) <= 5 ? "The shrinking almost stops." : "The glacier keeps shrinking, but more slowly."} ${why}`);
    }

    // tipping point: two runs ≤ 0.5 °C apart (same rain/snow and timing, end 2100), one survives and one doesn't
    let best = null;
    runs.forEach((a) => runs.forEach((b) => {
      const sa = a.s;
      const sb = b.s;
      if (sa.end_year !== 2100 || sb.end_year !== 2100 || sa.precip_pct !== sb.precip_pct || sa.gradual !== sb.gradual) return;
      const gap = sb.warming - sa.warming;
      if (a.r.gone_by === null && b.r.gone_by !== null && gap > 0 && gap <= 0.5 + 1e-9 && (!best || gap < best.gap)) best = { a, b, gap };
    }));
    if (best) {
      complete("f-tipping", `With <strong>${signed(best.a.s.warming, 1, " °C")}</strong> a little ice is still left in 2100 `
        + `(${pctText(best.a.r.ice_left_pct)} of today's). With <strong>${signed(best.b.s.warming, 1, " °C")}</strong> Yala is gone by `
        + `about <strong>${best.b.r.gone_by}</strong>. Just ${best.gap.toFixed(1)} °C decides whether any of the glacier is left `
        + "in 2100. Each bit of warming lifts the snowline, and once it climbs above nearly all of the glacier, there is "
        + "almost nowhere left to gain snow.");
    }

    if (s.warming >= 1.5 && s.precip_pct >= 30 && !snowCheck && !("f-snow" in done)) {
      const dry = { ...s, precip_pct: 0 };
      snowCheck = post("/api/future", { scenario: dry }).then((dd) => {
        const dr = rowOf(dd, dd.label);
        if (!dr) return;
        const extra = r.gone_by && dr.gone_by ? ` The extra snow buys only <strong>${r.gone_by - dr.gone_by} years</strong>.` : "";
        complete("f-snow", `With ${signed(s.warming, 1, " °C")} and <strong>${s.precip_pct} % more</strong> rain and snow, Yala `
          + `${outcomeOf(r)}. Without the extra snow it ${outcomeOf(dr)}.${extra} Warmer air turns some of the snow into `
          + "rain, and the melting season gets longer, so extra snow can't make up for much warming.");
      }).catch((err) => console.warn("guide", err)).finally(() => { snowCheck = null; });
    }

    // slow or sudden: the same warming run both ways
    if (s.warming >= 0.5) {
      const other = runs.get(runKey({ ...s, gradual: !s.gradual }));
      if (other) {
        const sudden = s.gradual ? other.r : r;
        const slow = s.gradual ? r : other.r;
        complete("f-sudden", `All at once, Yala ${outcomeOf(sudden)}. Gradually, it ${outcomeOf(slow)}. A glacier reacts `
          + "to the heat it gets year after year. With the change all at once it feels the full warming for decades longer, "
          + "so it melts sooner.");
      }
    }

    checkWhy();

    if (s.warming <= -0.5) {
      const grows = r.ice_left_pct > 100;
      complete("f-cool", grows
        ? `With ${esc(d.label)}, Yala grows: it ends with <strong>${r.ice_left_pct} %</strong> of today's ice. In cooler air the `
          + "snowline drops, so a bigger part of the glacier gains snow each year."
        : `With ${esc(d.label)}, Yala still ends with only <strong>${r.ice_left_pct} %</strong> of today's ice. `
          + (s.gradual ? "The cooling arrives slowly, and for decades the climate stays close to today's, which is too warm "
            + "for this glacier. Try the same cooling \"All at once\"."
            : "This much cooling isn't enough for the glacier to stop shrinking."));
    }
  }

  function checkWhy() {
    if (!ctx.future || ctx.view !== "why" || ctx.future.s.warming < 1.5) return;
    const text = endSnowline(ctx.future.d);
    if (text) complete("f-why", text);
  }

  function bindPlot(id, el) {
    if (!el.on) return;
    if (id === "past-3d" && !("meet-play" in done)) {
      let frames = 0;
      el.removeAllListeners?.("plotly_animatingframe");
      el.on("plotly_animatingframe", () => {
        frames += 1;
        if (frames >= 6) complete("meet-play", "The lowest part of the glacier, the <strong>tongue</strong>, thins and pulls "
          + "back the most, because it sits in the warmest air. The high parts change much less. That's why scientists "
          + "watch a glacier's tongue so closely.");
      });
    }
    if (id === "past-volume" && !("meet-radar" in done)) {
      el.removeAllListeners?.("plotly_hover");
      el.removeAllListeners?.("plotly_click");
      const seen = (ev) => {
        if (!ev.points.some((p) => /radar/i.test(p.data.name || ""))) return;
        const r = ctx.overview && ctx.overview.radar[0];
        if (r) complete("meet-radar", `In ${r.year}, scientists measured the ice with radar: <strong>${r.measured_million_m3} `
          + `million m³</strong>. The model, which was never shown this number, gives <strong>${r.model_million_m3}</strong>. `
          + "Checking a model against measurements it never saw is how scientists test whether it can be trusted.");
      };
      el.on("plotly_hover", seen);
      el.on("plotly_click", seen);
    }
  }

  // ------------------------------------------------------------ welcome tour
  const tour = { open: false, step: 0, back: null };
  const TOUR = [
    {
      art: `<svg viewBox="0 0 120 80" aria-hidden="true"><path d="M4 74 L40 22 L58 46 L72 30 L116 74 Z" fill="#1f5fa8"/><path d="M40 22 L49 35 L43 33 L37 39 L34 32 Z M72 30 L80 41 L75 39 L70 44 L68 38 Z" fill="#fff"/></svg>`,
      title: "Welcome to HimSim",
      body: () => `<p>You're about to explore <strong>Yala Glacier</strong>, a real glacier in Nepal's Langtang valley. `
        + "Scientists have measured it for over 40 years.</p><p>HimSim is a <strong>computer model</strong> of it: it melts and "
        + "moves the ice using physics and real weather records, so you can replay the past and try out futures.</p>",
    },
    {
      art: `<div class="tour-steps"><span><b>1</b>Meet Yala</span><span><b>2</b>Change the climate</span><span><b>3</b>Can we trust it?</span></div>`,
      title: "Three steps",
      body: () => `<ol class="tour-list">
          <li><strong>Meet Yala</strong>: replay what really happened to the glacier since the first survey.</li>
          <li><strong>Change the climate</strong>: choose a future and see what happens to the ice.</li>
          <li><strong>Can we trust it?</strong>: see how the model did against real measurements.</li>
        </ol><p>The buttons at the top take you to each step. <strong>Learn more</strong> explains how the model works.</p>`,
    },
    {
      art: `<svg viewBox="0 0 240 110" aria-hidden="true" class="tour-chart">
          <line x1="20" y1="96" x2="232" y2="96" stroke="#dde5ee" stroke-width="2"/>
          <path d="M20 20 C50 24 80 34 110 44" fill="none" stroke="#52514e" stroke-width="5" stroke-linecap="round"/>
          <path d="M110 44 C140 52 175 58 228 64" fill="none" stroke="#52514e" stroke-width="2.5" stroke-dasharray="6 5"/>
          <path d="M110 44 C135 58 160 80 186 96" fill="none" stroke="#2a78d6" stroke-width="3" stroke-linecap="round"/>
          <line x1="110" y1="8" x2="110" y2="96" stroke="#9aa6b2" stroke-width="1.5" stroke-dasharray="2 4"/>
          <text x="110" y="7" text-anchor="middle" font-size="10" fill="#4a5868">today</text>
          <path d="M84 27 l6 6 -6 6 -6 -6 z" fill="#1baf7a" stroke="#fff" stroke-width="1.5"/>
        </svg>`,
      title: "Reading the main chart",
      body: () => `<p>Time runs left to right; the higher the line, the more ice in the glacier.</p>
        <ul class="tour-key">
          <li><span class="k k-past"></span>Thick grey line: the past, replayed by the model</li>
          <li><span class="k k-base"></span>Dashed line: if today's climate simply continues</li>
          <li><span class="k k-you"></span>Coloured line: the climate you chose</li>
          <li><span class="k k-dia"></span>Green diamond: a real measurement</li>
        </ul><p>When a line reaches the bottom, the glacier is gone.</p>`,
    },
    {
      art: `<svg viewBox="0 0 120 80" aria-hidden="true"><circle cx="60" cy="40" r="30" fill="#fdeee4"/><text x="60" y="52" text-anchor="middle" font-size="36" font-weight="800" fill="#e07a3f">?</text></svg>`,
      title: "\"What if\", not a forecast",
      body: () => "<p>Nobody knows exactly how warm the future will be. The model answers <strong>what would happen if</strong> "
        + "the climate changed the way you choose.</p><p>It isn't perfect either. Step 3 shows where it matches real "
        + "measurements and where it struggles, so you can judge it yourself.</p>",
    },
    {
      art: `<svg viewBox="0 0 120 80" aria-hidden="true"><circle cx="60" cy="40" r="26" fill="none" stroke="#1f5fa8" stroke-width="5"/><circle cx="60" cy="40" r="14" fill="none" stroke="#1f5fa8" stroke-width="5"/><circle cx="60" cy="40" r="4" fill="#e07a3f"/></svg>`,
      title: "Help is always nearby",
      body: () => `<p><strong>${canHover ? "Rest your mouse on" : "Tap the small <span class=\"guide-btn guide-btn-demo\">?</span> next to"} `
        + "any part of a page</strong> to see what it shows, how to read it and what it means.</p>"
        + `<p>Each step has <strong>Try this</strong> missions: ${MISSIONS.length} small challenges that reveal how glaciers `
        + "behave. Can you complete them all?</p><p>The <strong>Guide</strong> button at the top brings this tour back and "
        + "switches the tips on or off.</p>",
    },
  ];

  const tourEl = document.createElement("div");
  tourEl.className = "tour-backdrop";
  tourEl.hidden = true;
  tourEl.innerHTML = `<div class="tour-card" role="dialog" aria-modal="true" aria-labelledby="tour-title"></div>`;
  document.body.appendChild(tourEl);
  const tourCard = $(".tour-card", tourEl);

  function renderTour() {
    const t = TOUR[tour.step];
    const last = tour.step === TOUR.length - 1;
    tourCard.innerHTML = `
      <button type="button" class="gp-close tour-skip" data-tour="close" aria-label="Close the tour">×</button>
      <div class="tour-art">${t.art}</div>
      <p class="gp-eyebrow">Step ${tour.step + 1} of ${TOUR.length}</p>
      <h2 id="tour-title">${t.title}</h2>
      <div class="tour-body">${t.body()}</div>
      <div class="tour-foot">
        <div class="tour-dots">${TOUR.map((_, i) => `<button type="button" data-tour-go="${i}" aria-label="Go to step ${i + 1}"
          ${i === tour.step ? 'aria-current="step"' : ""}></button>`).join("")}</div>
        <div class="tour-buttons">
          ${tour.step ? `<button type="button" class="btn" data-tour="back">Back</button>` : `<button type="button" class="btn btn-ghost" data-tour="close">Skip</button>`}
          <button type="button" class="btn btn-primary" data-tour="${last ? "close" : "next"}">${last ? "Start exploring" : "Next"}</button>
        </div>
      </div>`;
    $(".tour-buttons .btn-primary", tourCard).focus({ preventScroll: true });
  }

  function openTour() {
    hideTip();
    tour.back = document.activeElement;
    tour.open = true;
    tour.step = 0;
    tourEl.hidden = false;
    document.body.classList.add("no-scroll");
    renderTour();
  }
  function closeTour() {
    tour.open = false;
    tourEl.hidden = true;
    document.body.classList.remove("no-scroll");
    store.set(KEY.tour, true);
    tour.back?.focus?.({ preventScroll: true });
  }
  function goTour(i) {
    tour.step = Math.max(0, Math.min(TOUR.length - 1, i));
    renderTour();
  }
  tourEl.addEventListener("click", (e) => {
    if (e.target === tourEl) { closeTour(); return; }
    const act = e.target.closest("[data-tour]")?.dataset.tour;
    if (act === "close") closeTour();
    else if (act === "next") goTour(tour.step + 1);
    else if (act === "back") goTour(tour.step - 1);
    const go = e.target.closest("[data-tour-go]");
    if (go) goTour(parseInt(go.dataset.tourGo, 10));
  });
  document.addEventListener("keydown", (e) => {
    if (tour.open) {
      if (e.key === "Escape") closeTour();
      else if (e.key === "ArrowRight") goTour(tour.step + 1);
      else if (e.key === "ArrowLeft") goTour(tour.step - 1);
      else if (e.key === "Tab") { // keep focus inside the tour
        const f = $$("button", tourCard);
        const i = f.indexOf(document.activeElement);
        if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
        else if (!e.shiftKey && i === f.length - 1) { e.preventDefault(); f[0].focus(); }
      }
      return;
    }
    if (e.key === "Escape") { hideTip(); disc.hidden = true; closeMenu(); }
  });

  // ------------------------------------------------------------ Guide menu in the top bar
  const menuBtn = $("#guide-btn");
  const menu = $("#guide-menu");
  function closeMenu() {
    if (!menu || menu.hidden) return;
    menu.hidden = true;
    menuBtn.setAttribute("aria-expanded", "false");
  }
  function renderMenu() {
    if (!menu) return;
    $("#guide-badge").textContent = `${doneCount()}/${MISSIONS.length}`;
    $("#tips-switch").setAttribute("aria-checked", String(tipsOn()));
    $("#tips-row").hidden = !canHover;
    $("#menu-missions").innerHTML = PAGES.map((p) => {
      const list = missionsOn(p);
      return `<a href="#${p}" data-menu-page="${p}"><span>${esc(PAGE_NAMES[p])}</span><span class="mm-count${doneCount(list) === list.length ? " all" : ""}">`
        + `${doneCount(list)}/${list.length}</span></a>`;
    }).join("");
  }
  menuBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    const open = menu.hidden;
    menu.hidden = !open;
    menuBtn.setAttribute("aria-expanded", String(open));
    if (open) renderMenu();
  });
  menu?.addEventListener("click", (e) => {
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (act === "tour") { closeMenu(); openTour(); }
    if (act === "tips") {
      store.set(KEY.tips, !tipsOn());
      hideTip();
      renderMenu();
    }
    if (act === "reset") {
      const btn = e.target.closest("[data-act]");
      if (btn.dataset.armed) {
        done = {};
        store.set(KEY.missions, done);
        Object.keys(selected).forEach((k) => delete selected[k]);
        delete btn.dataset.armed;
        btn.textContent = "Start the missions over";
        renderMissions();
      } else {
        btn.dataset.armed = "1";
        btn.textContent = "Click again to clear your progress";
      }
    }
    const page = e.target.closest("[data-menu-page]");
    if (page) {
      closeMenu();
      setTimeout(() => $(`[data-missions="${page.dataset.menuPage}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 80);
    }
  });
  document.addEventListener("click", (e) => { if (menu && !menu.hidden && !e.target.closest(".guide-menu-wrap")) closeMenu(); });

  // ------------------------------------------------------------ events from app.js
  const on = (name, fn) => document.addEventListener(`himsim:${name}`, (e) => {
    try { fn(e.detail); } catch (err) { console.warn("guide", err); }
  });
  on("page", (page) => { ctx.page = page; hideTip(); closeMenu(); });
  on("overview", (o) => { ctx.overview = o; });
  on("future", (f) => {
    ctx.future = f;
    const r = rowOf(f.d, f.d.label);
    if (r) runs.set(runKey(f.s), { s: f.s, r });
    checkFuture();
  });
  on("view", (view) => { ctx.view = view; checkWhy(); });
  on("reality", (d) => { ctx.reality = d; });
  on("plotted", ({ id, el }) => bindPlot(id, el));

  renderMissions();
  if (!store.get(KEY.tour, false)) setTimeout(openTour, 400);
})();
