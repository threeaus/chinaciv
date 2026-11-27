import { compact, esc, int, money } from "../../format.js";
import { formatLensValue } from "../../ui/lenses.js";
import { VIEWS, ECONOMY, WONDERS, byPlace, explorerMetrics, rankRows } from "./model.js";

const MODE = "advisor";
const defaultView = "energy";
const SOURCES = { energy: "resources", economy: "yields", culture: "wonders", explorer: "sources" };
const measure = (v, fmt) => {
  if (!Number.isFinite(v)) return "—";
  if (fmt === "MW") return `${int(v)} MW`;
  if (fmt === "people") return `${compact(v)} 人`;
  return formatLensValue({ format: fmt }, v);
};

function options(items, selected) {
  return Object.entries(items).map(([key, label]) =>
    `<option value="${esc(key)}"${key === selected ? " selected" : ""}>${esc(label)}</option>`).join("");
}

export function install(app) {
  const button = app.ui.addTopButton({
    id: "btn-advisors", icon: "📊", label: "顾问", title: "打开顾问仪表盘",
    onClick: () => app.setMode(app.mode === MODE ? null : MODE, { id: defaultView }),
  });
  button?.setAttribute("aria-expanded", "false");
  let dock, active, focus, highlighted = null;
  let rows = [];
  const choices = {
    energy: { kind: "all" },
    economy: { scope: "city", metric: "gdp" },
    culture: { kind: "all" },
    explorer: { scope: "state", metric: "gdp", sort: "desc", query: "" },
  };

  function makeModel() {
    const cfg = choices[active];
    if (active === "energy") {
      const energy = (app.data.resources?.types || []).filter((item) => item.unit === "MW");
      const labels = { all: "全部发电类型", ...Object.fromEntries(energy.map((t) => [t.id, t.name])) };
      const tally = app.data.resources?.summary?.national || {};
      const value = (s) => cfg.kind === "all" ? s.energy?.total : s.energy?.by_type?.[cfg.kind];
      const stats = byPlace(app, "state", (s) => {
        const amount = value(s);
        return amount > 0 ? amount : null;
      });
      const totals = energy.filter((t) => cfg.kind === "all" || cfg.kind === t.id).map((t) => tally[t.id]);
      return { rows: rankRows(stats), format: "MW", bars: true,
        summary: [["地图收录装机", measure(totals.reduce((a, s) => a + (s?.value || 0), 0), "MW")],
          ["在运站点", int(totals.reduce((a, s) => a + (s?.count || 0), 0))]],
        filters: [["kind", "发电类型", labels]],
      };
    }
    if (active === "culture") {
      const wonders = app.data.wonders?.wonders;
      if (!wonders) return { pending: app.data.wonders === undefined };
      const selected = wonders.filter((w) => cfg.kind === "all" || w.rule === cfg.kind);
      const places = new Map((app.data.states || []).map((s) => [s.fips, s.name]));
      return { rows: selected.map((w) => ({ ...w, detail: [WONDERS[w.rule], places.get(w.state)].filter(Boolean).join(" · ") })),
        summary: [["可定位奇观", int(selected.length)], ["覆盖省级地区", int(new Set(selected.map((w) => w.state)).size)]],
        filters: [["kind", "奇观类别", { all: "全部类别", ...WONDERS }]],
      };
    }

    const fields = active === "economy" ? ECONOMY : explorerMetrics(app, cfg.scope);
    const metric = fields[cfg.metric] || fields.gdp;
    const values = byPlace(app, cfg.scope, metric.value);
    const filtered = cfg.query ? values.filter((r) => [r.name, r.id].some((s) => s.includes(cfg.query))) : values;
    const coverage = filtered.filter((r) => Number.isFinite(r.value));
    const n = app.data.nation.nation;
    const summary = active === "economy"
      ? [["全国现价 GDP", money(n.gdp)], ["全国人口", measure(n.population, "people")]]
      : [["有值地区", `${coverage.length} / ${filtered.length}`], ["当前范围", cfg.scope === "city" ? "地级城市" : "省级地区"]];
    const filters = [["scope", "地区级别", { city: "城市", state: "省级地区" }],
      ["metric", "指标", Object.fromEntries(Object.entries(fields).map(([id, m]) => [id, m.label]))]];
    if (active === "explorer") filters.push(["sort", "排序", { desc: "从高到低", asc: "从低到高" }]);
    return { rows: rankRows(filtered, cfg.sort), summary, filters, format: metric.format, bars: true };
  }

  function paintRows(model) {
    rows = model.rows || [];
    const host = dock.querySelector(".advisor-list");
    const hi = rows.reduce((a, r) => Number.isFinite(r.value) ? Math.max(a, Math.abs(r.value)) : a, 1);
    const fragment = rows.map((r, i) => {
      const value = measure(r.value, model.format);
      const available = Number.isFinite(r.value);
      const bar = model.bars && available
        ? `<i class="advisor-bar${r.value < 0 ? " negative" : ""}" aria-hidden="true" style="--share:${100 * Math.abs(r.value) / hi}%"></i>` : "";
      return `<li><button type="button" data-row="${i}" aria-pressed="${r.id === focus}"${!Number.isFinite(r.x) ? " disabled" : ""}>
        <span>${esc(r.name)}${r.detail ? `<small>${esc(r.detail)}</small>` : ""}</span>
        ${model.bars ? `<strong title="${available ? esc(model.format === "cny" ? `${int(r.value)} 元` : value) : "无数据"}">${esc(value)}</strong>` : '<span aria-hidden="true">↗</span>'}
        ${bar}</button></li>`;
    });
    host.innerHTML = fragment.length ? fragment.join("") : `<li class="advisor-empty">${model.pending ? "正在读取奇观数据…" : "当前条件下暂无数据"}</li>`;
    dock.querySelector(".advisor-stats").innerHTML = (model.summary || []).map(([k, v]) =>
      `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("");
  }

  function render() {
    if (!active) return;
    const view = VIEWS[active];
    const model = makeModel();
    const cfg = choices[active];
    dock.dataset.advisor = active;
    dock.innerHTML = `<header class="advisor-head">
      <nav aria-label="顾问主题">${Object.entries(VIEWS).map(([id, v]) =>
        `<button type="button" data-view="${id}" aria-pressed="${id === active}">${esc(v.label)}</button>`).join("")}</nav>
      <button type="button" class="icon-btn" data-close aria-label="关闭顾问">✕</button>
    </header>
    <div class="advisor-body">
      <div class="advisor-title"><h2>${esc(view.title)}</h2><button type="button" data-source>数据说明</button></div>
      <p class="advisor-note">${esc(view.note)}</p>
      <dl class="advisor-stats" aria-live="polite"></dl>
      <div class="advisor-filters">${(model.filters || []).map(([id, label, values]) =>
        `<label>${esc(label)}<select data-filter="${id}">${options(values, cfg[id])}</select></label>`).join("")}
        ${active === "explorer" ? `<label class="advisor-search">地区名称或代码<input type="search" data-query value="${esc(cfg.query)}"></label>` : ""}
      </div>
      <ol class="advisor-list" aria-label="地区与设施"></ol>
    </div>`;
    paintRows(model);
  }

  function point(row, move) {
    if (app.state.highlight === highlighted) app.setHighlight(null);
    focus = row.id;
    highlighted = row.state != null ? { states: new Set([row.state]), color: "#f3cf7c" }
      : { cells: new Set([row.cell]), color: "#f3cf7c" };
    app.setHighlight(highlighted);
    if (move) app.flyTo(row.x, row.y, Math.max(app.cam.scale, (row.state == null ? 34 : 13) / app.w.grid.R));
    const buttons = [...dock.querySelectorAll("[data-row]")];
    buttons.forEach((item, i) => item.setAttribute("aria-pressed", String(row === rows[i])));
    if (!move) buttons[rows.indexOf(row)]?.scrollIntoView({ block: "nearest" });
  }

  app.registerMode(MODE, {
    enter({ id }) {
      active = Object.hasOwn(VIEWS, id) ? id : defaultView;
      app.clearSelection();
      dock = app.ui.dock("right", { width: 398, label: "顾问仪表盘" });
      button?.setAttribute("aria-expanded", "true");
      render();
      dock.onclick = (e) => {
        if (e.target.closest("[data-close]")) {
          app.setMode(null);
          button?.focus();
        }
        if (e.target.closest("[data-source]")) app.pedia.open(SOURCES[active]);
        const view = e.target.closest("[data-view]")?.dataset.view;
        if (view && view !== active) {
          app.setMode(MODE, { id: view });
          dock.querySelector(`[data-view="${view}"]`)?.focus();
        }
        const item = e.target.closest("[data-row]");
        if (item) point(rows[Number(item.dataset.row)], true);
      };
      dock.onchange = (e) => {
        const key = e.target.dataset.filter;
        if (!key) return;
        const cfg = choices[active];
        cfg[key] = e.target.value;
        if (active === "explorer" && key === "scope" && !explorerMetrics(app, cfg.scope)[cfg.metric]) cfg.metric = "gdp";
        render();
        dock.querySelector(`[data-filter="${key}"]`)?.focus();
      };
      dock.oninput = (e) => {
        if (!e.target.hasAttribute("data-query")) return;
        choices.explorer.query = e.target.value.trim();
        paintRows(makeModel());
      };
    },
    exit() {
      if (app.state.highlight === highlighted) app.setHighlight(null);
      active = focus = highlighted = null;
      delete dock.dataset.advisor;
      dock.onclick = dock.onchange = dock.oninput = null;
      app.ui.undock("right");
      button?.setAttribute("aria-expanded", "false");
    },
  });

  app.hash.register("advisor", {
    get: () => active || null,
    set(id) {
      if (Object.hasOwn(VIEWS, id) && id !== active) app.setMode(MODE, { id });
      else if (!id && active) app.setMode(null);
    },
  });

  app.on("data", ({ name }) => { if (name === "wonders" && active === "culture") render(); });
  app.on("mapclick", (event) => {
    if (!active) return false;
    const row = active === "culture" ? rows.find((r) => r.id === event.item?.id)
      : rows.find((r) => r.state != null ? r.state === event.state : r.id === event.city?.id);
    if (row) point(row, false);
    return true;
  });
}
