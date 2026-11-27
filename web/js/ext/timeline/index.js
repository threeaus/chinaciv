import { esc, int, money } from "../../format.js";
import { prepareNetwork, drawRail } from "../../render/art/improvements.js";

const MODE = "history";
const METRICS = { population: "人口", gdp: "现价 GDP", rail: "高铁开通" };
const FIRST = 2020;
const LAST = 2024;
const railsFor = (data, year) => data.rail.filter((edge) => edge[2] <= year);

function cellPlaces(app, scope) {
  const world = app.data.world;
  const byCounty = new Map(app.data.cities.flatMap((c) => c.counties.map((id) => [id, c])));
  const byCell = new Map(app.data.cities.filter((c) => c.kind === "taiwan_city").map((c) => [c.cell, c]));
  return world.owner.map((owner, i) => {
    if (owner < 0) return null;
    const state = world.states[owner].fips;
    if (scope === "state") return state;
    const county = world.counties[world.county[i]]?.geoid;
    const city = byCounty.get(county) || app.cityById.get(state + "0000") || byCell.get(i);
    return city?.states.includes(state) ? city.id : null;
  });
}

export function install(app) {
  let active = false;
  let dock, restoreLens, lens, hsr;
  let year = LAST, metric = "population", scope = "state", picked = "";
  const masks = new Map();
  const historyNetworks = new Map();
  const file = () => app.data.history;
  const places = () => scope === "state" ? app.data.states || [] : app.data.cities;
  const series = () => scope === "state" ? file()?.provinces : file()?.cities;
  const placeId = (place) => place.fips || place.id;
  const isRail = () => active && metric === "rail" && !!file();
  app.history = { get railActive() { return isRail(); } };

  const button = app.ui.addTopButton({
    id: "btn-history", icon: "◷", label: "历年", title: "打开历年地图",
    onClick: () => app.setMode(active ? null : MODE),
  });
  button?.setAttribute("aria-expanded", "false");

  app.registerStaticLayer({
    id: "history-rail", z: 56, minRpx: 0,
    visible: () => isRail() && !!hsr && app.mapArt?.on.rail !== false,
    sig: () => String(year),
    draw(ctx, vp, _w, opts) { drawRail(ctx, hsr, vp, opts); },
  });

  function setMap() {
    if (!file()) return;
    if (isRail()) {
      if (lens && app.state.lens === lens) app.setLens(null);
      lens = null;
      if (!historyNetworks.has(year)) {
        const rail = railsFor(file(), year).map(([a, b, _year, name]) => [a, b, 0, name]);
        historyNetworks.set(year, prepareNetwork(app.w, { rail }));
      }
      hsr = historyNetworks.get(year);
    } else {
      if (!masks.has(scope)) masks.set(scope, cellPlaces(app, scope));
      const annual = series();
      const values = masks.get(scope).map((id) => annual[id]?.[year]?.[metric] ?? null);
      const max = scope === "state" ? metric === "population" ? 130e6 : 15e12
        : metric === "population" ? 32e6 : 5e12;
      lens = {
        id: `history-${scope}-${metric}-${year}`, transient: true, name: `${year} 年${METRICS[metric]}`,
        icon: metric === "gdp" ? "y-gold" : "pop", emoji: metric === "gdp" ? "💰" : "👥",
        format: metric === "gdp" ? "cny" : "int", unit: metric === "gdp" ? "元" : "人",
        scale: "linear", domain: [0, max], ramp: ["#253451", "#4a888a", "#afc17e", "#f0c76d"],
        description: "颜色随数值递增，灰色为该年暂无数据。",
        source: "cn_history", values,
      };
      app.setLens(lens);
    }
    app.requestDraw();
  }

  function renderResult() {
    if (!file()) return;
    const label = dock.querySelector(".timeline-year");
    const slider = dock.querySelector("input[type=range]");
    label.textContent = `${year} 年`;
    slider.setAttribute("aria-valuetext", `${year} 年`);
    const group = dock.querySelector(".timeline-geography");
    group.hidden = isRail();
    const result = dock.querySelector(".timeline-result");
    if (isRail()) {
      const cumulative = new Set(railsFor(file(), year).map((edge) => edge[3])).size;
      const added = new Map(file().rail.filter((edge) => edge[2] === year).map((edge) => [edge[3], edge[4]]));
      const mileage = file().rail_mileage?.[year];
      result.innerHTML = `<p class="advisor-note">${esc(file().rail_note)}</p>
        ${mileage ? `<p>全国高铁营业里程约 <b>${int(mileage.km)} 公里</b> · <a href="${esc(mileage.source)}" target="_blank" rel="noopener">铁道统计公报</a></p>` : ""}
        <h3>已匹配 ${cumulative} 条高铁线路</h3><h4>${year} 年开通或全线贯通</h4>
        ${added.size ? `<ul>${[...added].map(([name, url]) => `<li><a href="${esc(url)}" target="_blank" rel="noopener">${esc(name)}</a></li>`).join("")}</ul>`
          : "<p>本年暂无匹配记录。</p>"}`;
      return;
    }
    const selection = places().find((p) => placeId(p) === picked);
    const values = picked ? series()[picked] || {} : scope === "state" ? file().nation : {};
    const note = scope === "city"
      ? "人口和现价 GDP 采用地方年鉴、公报及统计汇编。部分 GDP 序列采用经济普查修订值，数据覆盖因年份而异。"
      : metric === "population" ? file().population_note : file().gdp_note;
    const marked = Object.values(series()).filter((row) => Number.isFinite(row[year]?.[metric])).length;
    const rows = file().years.map((y) => {
      const value = values[y]?.[metric];
      const row = values[y];
      const rounded = metric === "population" && row?.population_step === 10000;
      const text = !Number.isFinite(value) ? "暂无数据" : metric === "gdp" ? money(value)
        : rounded ? `约 ${int(value / 10000)} 万人` : `${int(value)} 人`;
      const amount = metric === "gdp" && row?.gdp_local_currency
        ? `<small>原值 ${esc(row.gdp_local_currency)} ${int(row.gdp_local)}</small>` : "";
      const source = row?.[`${metric}_source`];
      const reference = source ? `<small><a href="${esc(source)}" target="_blank" rel="noopener" aria-label="${y} 年${METRICS[metric]}来源">来源</a></small>` : "";
      return `<tr${y === year ? ' aria-current="true"' : ""}><th scope="row">${y} 年</th><td>${esc(text)}${amount}${reference}</td></tr>`;
    });
    result.innerHTML = `<p class="advisor-note">${esc(note)}
      ${picked === "71" && metric === "population" ? " 台湾地区为年末户籍人口。" : ""}
      ${["71", "81", "82", "810000", "820000"].includes(picked) && metric === "gdp" ? " 当地现价 GDP 按当年平均汇率折算。" : ""}
      ${year} 年有值 ${marked}/${places().length}。</p>
      <h3>${esc(selection?.full || selection?.name || "全国")}${esc(METRICS[metric])}</h3>
      <table aria-label="历年统计"><tbody>${rows.join("")}</tbody></table>`;
  }

  function renderPlaces() {
    const field = dock.querySelector('select[data-history="place"]');
    const defaults = scope === "state" ? '<option value="">全国</option>' : "";
    const opts = places().map((place) => `<option value="${esc(placeId(place))}">${esc(place.full || place.name)}</option>`);
    field.innerHTML = defaults + opts.join("");
    field.value = picked;
  }

  function update() {
    setMap();
    renderResult();
    app.hash.update();
  }

  function mount() {
    if (!file()) {
      dock.querySelector(".timeline-content").textContent = "历年数据暂不可用。";
      return;
    }
    dock.querySelector(".timeline-content").innerHTML = `
      <div class="timeline-slider"><label for="history-year">年份</label><output class="timeline-year" for="history-year"></output>
        <input id="history-year" type="range" min="${FIRST}" max="${LAST}" step="1" value="${year}">
        <div class="timeline-ticks" aria-hidden="true">${file().years.map((y) => `<span>${y}</span>`).join("")}</div></div>
      <div class="advisor-filters">
        <label>指标<select data-history="metric">${Object.entries(METRICS).map(([k, v]) =>
          `<option value="${k}"${k === metric ? " selected" : ""}>${v}</option>`).join("")}</select></label>
        <div class="timeline-geography">
          <label>地区级别<select data-history="scope"><option value="state">省级地区</option><option value="city">地级城市</option></select></label>
          <label>查看地区<select data-history="place"></select></label>
        </div>
      </div><div class="timeline-result" aria-live="polite"></div>`;
    dock.querySelector('select[data-history="scope"]').value = scope;
    renderPlaces();
    update();
  }

  app.registerMode(MODE, {
    enter(params) {
      if (Number.isInteger(params.year) && params.year >= FIRST && params.year <= LAST) year = params.year;
      restoreLens = app.state.lens;
      active = true;
      app.clearSelection();
      dock = app.ui.dock("right", { width: 398, label: "历年地图" });
      dock.dataset.history = "";
      button?.setAttribute("aria-expanded", "true");
      dock.innerHTML = `<header class="timeline-head"><h2>历年地图</h2><button class="icon-btn" aria-label="关闭历年地图" data-close>✕</button></header>
        <div class="timeline-content">正在读取历年数据…</div>`;
      dock.onclick = (event) => {
        if (!event.target.closest("[data-close]")) return;
        app.setMode(null);
        button?.focus();
      };
      dock.oninput = (event) => {
        if (event.target.id !== "history-year") return;
        year = Number(event.target.value);
        update();
      };
      dock.onchange = (event) => {
        const key = event.target.dataset.history;
        if (!key) return;
        const value = event.target.value;
        if (key === "metric") {
          metric = value;
          if (isRail()) {
            app.ui.setMapToggle("rail", true);
            app.setLens(null);
          }
        } else if (key === "scope") {
          scope = value;
          picked = scope === "state" ? "" : places()[0]?.id || "";
          renderPlaces();
        } else {
          picked = value;
        }
        update();
      };
      if (app.data.history !== undefined) mount();
      else app.loadData("history").then(() => { if (active && !dock.querySelector("#history-year")) mount(); });
    },
    exit() {
      active = false;
      if (app.state.lens === lens || (metric === "rail" && app.state.lens == null)) app.setLens(restoreLens);
      lens = hsr = null;
      delete dock.dataset.history;
      dock.onclick = dock.onchange = dock.oninput = null;
      app.ui.undock("right");
      button?.setAttribute("aria-expanded", "false");
    },
  });
  app.hash.register("year", {
    get: () => active ? `${year},${metric},${scope},${picked}` : null,
    set(value) {
      if (!value) {
        if (active) app.setMode(null);
        return;
      }
      const [rawYear, nextMetric, nextScope, code] = value.split(",");
      const y = Number(rawYear);
      if (!Number.isInteger(y) || y < FIRST || y > LAST) return;
      metric = Object.hasOwn(METRICS, nextMetric) ? nextMetric : "population";
      scope = nextScope === "city" ? "city" : "state";
      picked = places().some((r) => placeId(r) === code) ? code : scope === "city" ? places()[0]?.id || "" : "";
      year = y;
      if (!active) app.setMode(MODE, { year });
      else if (file()) mount();
    },
  });
  app.on("mapclick", (event) => {
    if (!active) return false;
    if (!file() || isRail()) return true;
    const place = scope === "state" ? places()[event.state] : event.city;
    if (place && (scope === "city" || event.state != null)) {
      picked = placeId(place);
      renderPlaces();
      renderResult();
      app.hash.update();
    }
    return true;
  });
}
