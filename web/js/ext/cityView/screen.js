// The city screen: a docked dashboard (a bottom sheet on phones) with the header, Overview (population and the
// city's hexes), Economy (yields, GDP and its three sectors), Workforce (when cities.json has jobs by industry),
// Transport & wonders (airports, ports and wonders in the city), Resources and Compare (peer cities). Plain HTML
// strings + inline SVG charts; render(el, model, handlers) fills `el`. Phase 1 of chinaciv has no citizens or
// districts (those usaciv sections are gone).
import { esc, int, pct, isMoneyUnit } from "../../format.js";
import { compact, money, popShort, yieldValue } from "./fmt.js";
import { icon, glyph } from "../../ui/icon.js";
import { css } from "../../color.js";
import { isCapital } from "../../world.js";
import { sparkline, meter, bar } from "./charts.js";
import { popSeries, rankCount, resourceValue, LAND } from "./model.js";

const TABS = [
  ["overview", "概况", "pop"],
  ["economy", "经济", "y-gold"],
  ["workforce", "就业", "y-production"],
  ["hubs", "交通与奇观", "d-harbor"],
  ["resources", "资源", "resources"],
  ["compare", "比较", "layers"],
];

const signed = (g, d = 1) => (g == null ? "–" : `${g >= 0 ? "+" : "−"}${Math.abs(g * 100).toFixed(d)}%`);
const rankCache = new WeakMap();
function countOf(cities, key) {
  let m = rankCache.get(cities);
  if (!m) rankCache.set(cities, (m = new Map()));
  if (!m.has(key)) m.set(key, rankCount(cities, key));
  return m.get(key);
}

function rankBadge(rank, of, label, tip) {
  if (rank == null) return "";
  const tier = rank <= 10 ? "gold" : rank <= 50 ? "silver" : "bronze";
  return `<div class="cv-rank ${tier}" title="${esc(tip || `${label}：在 ${of} 个城市中排第 ${rank} 位（1 为最高）`)}">
    <span class="cv-medal">${rank}</span><span class="cv-rank-l">${esc(label)}</span></div>`;
}

function lqBadge(lq) {
  if (lq == null) return "";
  const tip = `区位商：该比重为全国的 ${lq.toFixed(2)} 倍`;
  const cls = lq >= 1.25 ? "hi" : lq <= 0.75 ? "lo" : "mid";
  return `<span class="cv-lq ${cls}" title="${esc(tip)}">×${lq.toFixed(1)}</span>`;
}

function medallion(id, fallback, bg, size = 18) {
  return `<span class="cv-med" style="--bg:${esc(bg)}">${icon(id, fallback, { size })}</span>`;
}

// --- header --------------------------------------------------------------------------------------------------------
function header(m) {
  const c = m.city, n = m.nation.nation;
  const cities = m.cityList;
  const col = css(m.stateRGB);
  const chips = m.states.map((s) => (s.index >= 0
    ? `<button class="chip" data-state="${s.index}" title="打开${esc(s.name)}">${esc(s.name)}</button>`
    : `<span class="chip">${esc(s.name)}</span>`)).join("");
  const g = Number.isFinite(c.growth) ? c.growth : null;
  const yrs = Array.isArray(c.growth_years) ? c.growth_years : null;
  const growth = g == null ? "" : `<span class="cv-growth ${g >= 0 ? "good" : "bad"}" title="${yrs ? `${yrs[0]}–${yrs[1]} 年` : ""}常住人口变化。全国：${signed(n.growth)}">${g >= 0 ? "▲" : "▼"} ${Math.abs(g * 100).toFixed(1)}%${yrs ? ` <small>较 ${yrs[0]} 年</small>` : ""}</span>`;
  const perCap = c.gdp != null && c.population ? c.gdp / c.population : null;
  const r = c.ranks || {};
  const N = (k) => countOf(cities, k);
  return `
  <div class="sheet-grip cv-grip" aria-hidden="true"></div>
  <header class="cv-head" style="--sc:${col}">
    <div class="cv-ribbon" aria-hidden="true"></div>
    <button class="icon-btn cv-close" data-close aria-label="关闭城市界面（Esc）" title="回到地图（Esc）">${icon("close", "✕", { size: 13 })}</button>
    <div class="cv-kind">城市界面 · ${esc(c.kind_label || "城市")}</div>
    <div class="cv-title">
      <div class="cv-crest" aria-hidden="true"><span>${esc(popShort(c.population))}</span></div>
      <div class="cv-tt">
        <h2 class="cv-name" tabindex="-1">${isCapital(c) ? `<span class="cv-cap" title="首都">★</span> ` : ""}${esc(c.name)}</h2>
        <div class="cv-full">${esc(c.full && c.full !== c.name ? c.full : "")}</div>
        ${chips ? `<div class="chips">${chips}</div>` : ""}
      </div>
    </div>
    <div class="cv-headline">
      <div class="cv-big"><span class="lbl">${icon("pop", "👥", { size: 13 })} 常住人口${c.population_year ? ` ${c.population_year}` : ""}</span><b>${int(c.population)}</b>${growth}</div>
      <div class="cv-big"><span class="lbl">${icon("y-gold", "💰", { size: 13 })} GDP${c.gdp_year ? ` ${c.gdp_year}` : ""}</span><b>${money(c.gdp)}</b>${
        perCap != null ? `<span class="cv-sub">人均 ${money(perCap)}</span>` : ""}</div>
    </div>
    <div class="cv-ranks" aria-label="在 ${cities.length} 个城市中的排名">
      ${rankBadge(r.population, N("population"), "人口")}
      ${rankBadge(r.gdp, N("gdp"), "GDP")}
      ${rankBadge(r.gdp_per_capita, N("gdp_per_capita"), "人均 GDP")}
      ${rankBadge(r.growth, N("growth"), "人口增长", r.growth != null ? `人口增长：在 ${N("growth")} 个城市中排第 ${r.growth} 位（1 为最快）` : "")}
    </div>
  </header>
  <nav class="cv-tabs" aria-label="城市界面分区">
    ${TABS.filter(([id]) => id !== "workforce" || m.inds.length).map(([id, label, ic]) => `<button type="button" data-tab="${id}">${icon(ic, "•", { size: 14 })}<span>${label}</span></button>`).join("")}
  </nav>`;
}

// --- overview ------------------------------------------------------------------------------------------------------
function overview(m) {
  const c = m.city, n = m.nation.nation;
  const series = popSeries(c);
  const ch = series.length >= 2 ? series.at(-1).value / series[0].value - 1 : null;
  const row = (ic, fb, label, v, nat, fmt, better, max, sub = nat != null ? `全国 ${fmt(nat)}` : "", tick = nat) => v == null ? "" : `
    <div class="cv-stat">
      <div class="cv-stat-top"><span class="sl">${icon(ic, fb, { size: 14 })}${esc(label)}</span>
        <span class="sv"><b>${fmt(v)}</b>${sub ? `<small>${sub}</small>` : ""}</span></div>
      ${meter(v, tick, max ?? Math.max(v || 0, nat || 0) * 1.35, better)}
    </div>`;
  const popShare = c.population != null && n.population > 0 ? c.population / n.population : null;
  const gdpShare = c.gdp != null && n.gdp > 0 ? c.gdp / n.gdp : null;
  const empShare = c.employed != null && c.population > 0 ? c.employed / c.population : null;
  const multi = m.tiles.length > 1;
  const area = m.tiles.length * m.hexArea;
  const tilesNote = multi
    ? `地图上该市占 <b>${m.tiles.length}</b> 个六边形（约 ${compact(area)} km²）：所辖区县覆盖六边形 7 个采样点中至少 4 个的格子。${
      m.residentsSum > 0 ? `各格标注的 ≈ 人口为人口密度 × 六边形面积的估算值，合计约 ${compact(m.residentsSum)} 人。` : ""}`
    : `该市在地图上只占一个六边形（约 ${compact(m.hexArea)} km²），与城市图标画在一起。`;
  const census = c.pop_census_2020;
  return `
  <section class="cv-sec" id="cv-overview" data-sec="overview" aria-labelledby="cv-h-overview">
    <h3 id="cv-h-overview">${icon("pop", "👥", { size: 15 })}概况</h3>
    ${series.length >= 2 ? `<div class="cv-card">
      <div class="cv-card-h"><span>常住人口 ${series[0].year}–${series.at(-1).year}</span>${
        ch != null ? `<span class="${ch >= 0 ? "good" : "bad"}">${signed(ch)}</span>` : ""}</div>
      ${sparkline(series, { fmt: (v) => popShort(v), title: `${c.name}历年常住人口` })}
    </div>` : ""}
    <div class="cv-stats">
      ${row("pop", "👥", "常住人口", c.population, null, int, null, n.population ? Math.max(c.population || 0, 3e7) : null,
        popShare != null ? `占全国 ${pct(popShare, 2)}` : "")}
      ${row("pop", "👥", "七普人口（2020）", census, null, int, null, Math.max(census || 0, 3e7), "第七次全国人口普查")}
      ${row("y-gold", "💰", "GDP 占全国", gdpShare, null, (x) => pct(x, 2), null, Math.max(gdpShare || 0, 0.05), "")}
      ${row("pop", "👥", "从业人员", c.employed, null, int, null, c.population, empShare != null ? `占常住人口 ${pct(empShare)}` : "")}
    </div>
    ${c.note ? `<p class="cv-note">${esc(c.note)}</p>` : ""}
    <div class="cv-legend-tiles">${tileLegend(m)}<p>${tilesNote}</p></div>
    ${(c.counties || []).length ? `<p class="cv-note">所辖县级行政区 ${(c.counties || []).length} 个。</p>` : ""}
  </section>`;
}

function tileLegend(m) {
  const counts = new Map();
  for (const t of m.tiles) if (t.land) counts.set(t.land.key, (counts.get(t.land.key) || 0) + 1);
  return `<div class="cv-tl">${LAND.filter((g) => counts.has(g.key)).map((g) =>
    `<span class="cv-tl-i"><i style="background:${esc(m.landColor(g.key))}"></i>${esc(g.label)} <small>${counts.get(g.key)}</small></span>`).join("")}</div>`;
}

// --- economy -------------------------------------------------------------------------------------------------------
function economy(m) {
  const c = m.city, nat = m.nation, n = nat.nation;
  const r = c.ranks || {};
  const cities = m.cityList;
  const perCap = c.gdp != null && c.population ? c.gdp / c.population : null;
  const natPerCap = n.gdp && n.population ? n.gdp / n.population : null;
  const yields = nat.yields.map((y) => {
    const v = c.yields?.[y.key];
    const rk = r[y.key];
    return `<div class="cv-yield" style="--yc:${esc(y.color)}" title="${esc(y.label)}：${esc(y.description || "")}">
      <div class="ico">${glyph(y, 20)}</div><div class="val">${yieldValue(y, v)}</div>
      <div class="lbl">${esc(y.key === "gold" ? "GDP" : y.label)}</div>
      ${rk != null ? `<div class="rk">第 ${rk} <small>/ ${countOf(cities, y.key)}</small></div>` : ""}</div>`;
  }).join("");
  const gi = m.gdpInds;
  const maxShare = gi.length ? Math.max(...gi.map((d) => Math.max(d.share, d.natShare))) : 1;
  const gdpRow = (d) => `<div class="cv-ind${d.undisclosed ? " und" : ""}" title="${esc(d.label)}：${money(d.value)}（占本市 GDP ${pct(d.share)}；全国 ${pct(d.natShare)}）">
      <span class="cv-ind-ic" style="--bg:${esc(d.color)}">${icon(d.icon, "•", { size: 13 })}</span>
      <span class="cv-ind-n">${esc(d.short)}${lqBadge(d.lq)}</span>
      <span class="cv-ind-v">${money(d.value)} <small>${pct(d.share, 0)}</small></span>
      ${bar(d.share / maxShare, d.lq != null && d.lq >= 1.25 ? "#9fd76a" : "#c9a45c", d.natShare / maxShare)}
    </div>`;
  const moneyYields = nat.yields.filter((y) => y.key !== "gold" && isMoneyUnit(y.unit));
  return `
  <section class="cv-sec" id="cv-economy" data-sec="economy" aria-labelledby="cv-h-economy">
    <h3 id="cv-h-economy">${icon("y-gold", "💰", { size: 15 })}经济</h3>
    <div class="cv-gdp">
      <div><span class="lbl">地区生产总值${c.gdp_year ? `（${c.gdp_year}）` : ""}</span><b>${money(c.gdp)}</b>${r.gdp != null ? `<small>第 ${r.gdp} / ${countOf(cities, "gdp")} 位</small>` : ""}</div>
      <div><span class="lbl">人均 GDP</span><b>${money(perCap)}</b>${
        natPerCap ? `<small class="${perCap >= natPerCap ? "good" : "bad"}">全国 ${money(natPerCap)}</small>` : ""}</div>
      <div><span class="lbl">占全国 GDP</span><b>${c.gdp != null && n.gdp ? pct(c.gdp / n.gdp, 2) : "–"}</b><small>${c.population != null && n.population ? `人口占 ${pct(c.population / n.population, 2)}` : ""}</small></div>
    </div>
    <h4 class="cv-h4">产出 <span class="muted">在全部城市中的排名</span></h4>
    <div class="cv-yields">${yields}</div>
    <h4 class="cv-h4">三次产业 <span class="muted">刻度 = 全国比重</span></h4>
    ${gi.length ? `<div class="cv-inds">${gi.slice(0, 8).map(gdpRow).join("")}</div>
      ${gi.length > 8 ? `<details class="cv-more"><summary>全部 ${gi.length} 项</summary><div class="cv-inds">${gi.slice(8).map(gdpRow).join("")}</div></details>` : ""}`
      : `<p class="muted cv-note">该市没有分产业的 GDP 数据。</p>`}
    <p class="cv-note">${esc(nat.gdp_vintage || nat.vintage || "")}，当年价格，按生产地计算；比重为占本市 GDP 的比例。×N = 该产业占本市 GDP 的比重为全国比重的 N 倍。${
      moneyYields.length ? `${moneyYields.map((y) => y.label).join("、")}产出按增加值（元）计。` : ""}</p>
  </section>`;
}

// --- workforce -----------------------------------------------------------------------------------------------------
function workforce(m) {
  if (!m.inds.length) return "";
  const cards = m.inds.map((d) => {
    const spec = d.lq != null && d.lq >= 1.25;
    return `<div class="cv-bld${spec ? " spec" : ""}" title="${esc(d.label)}：${int(d.jobs)} 人（${pct(d.share)}；全国 ${pct(d.natShare)}）">
      ${medallion(d.icon, "•", d.color, 17)}
      <div class="cv-bld-t"><span class="cv-bld-n">${esc(d.short)}</span>
        <span class="cv-bld-v">${compact(d.jobs)} <small>${pct(d.share, 1)}</small></span></div>
      ${lqBadge(d.lq)}
    </div>`;
  }).join("");
  return `
  <section class="cv-sec" id="cv-workforce" data-sec="workforce" aria-labelledby="cv-h-workforce">
    <h3 id="cv-h-workforce">${icon("y-production", "⚙️", { size: 15 })}就业</h3>
    <p class="cv-lead">${m.city.employed != null ? `本市 ${int(m.city.employed)} 名从业人员` : "本市从业人员"}按行业的分布。<span class="cv-lq hi">×N</span> 表示该行业就业占比为全国的 N 倍。</p>
    <div class="cv-blds">${cards}</div>
    <p class="cv-note">${esc(m.nation.industry_vintage || m.nation.vintage || "")}。行业按《国民经济行业分类》（GB/T 4754）门类。</p>
  </section>`;
}

// --- transport and wonders -----------------------------------------------------------------------------------------
function hubs(m) {
  const rows = [
    ...m.hubs.map((h) => {
      const it = h.item;
      const air = h.kind === "airport";
      const val = air ? (it.passengers ?? it.enplanements) : (it.cargo_t ?? it.tons ?? it.teu);
      const kind = air ? "机场" : it.type === "inland" ? "内河港口" : "沿海港口";
      const basis = air ? "旅客吞吐量" : it.cargo_t == null && it.teu != null ? "集装箱吞吐量" : "货物吞吐量";
      const unit = air ? "人次" : it.cargo_t == null && it.teu != null ? "标箱" : "吨";
      const what = it.publisher ? `${kind} · ${esc(it.publisher)} · ${basis}`
        : `${kind} · ${basis}${it.rank != null ? `第 ${esc(it.rank)} 位` : ""}`;
      return { icon: air ? "d-aerodrome" : "d-harbor", fb: air ? "✈️" : "⚓", name: it.name, what,
        val: val != null ? `${compact(val)} ${unit}` : "", cell: it.cell };
    }),
    ...m.wonders.map((x) => ({ icon: x.kind === "university" ? "w-university" : x.kind === "natural" ? "w-park" : "w-landmark", fb: "🏛️",
      name: x.name, what: x.rule === "unesco_whs" ? "世界遗产" : x.rule === "national_park" ? "国家公园" : x.rule === "scenic_5a" ? "5A 级景区" : x.kind === "university" ? "一流大学" : "奇观",
      val: "", cell: x.cell })),
  ];
  const list = rows.map((r) => `<div class="cv-site cv-hub">
      <span class="cv-med" style="--bg:#3a4a5e">${icon(r.icon, r.fb, { size: 16 })}</span>
      <span class="cv-site-t"><b>${esc(r.name)}</b><small>${r.what}</small></span>
      <span class="cv-site-v">${esc(r.val)}</span></div>`).join("");
  return `
  <section class="cv-sec" id="cv-hubs" data-sec="hubs" aria-labelledby="cv-h-hubs">
    <h3 id="cv-h-hubs">${icon("d-harbor", "⚓", { size: 15 })}交通与奇观</h3>
    ${rows.length ? `<div class="cv-sites">${list}</div>
      <p class="cv-note">地图上标出的机场、港口和奇观中，位于本市所辖区县内的。</p>`
      : `<p class="muted cv-note">本市没有地图上标出的主要机场、港口或奇观（或相应数据尚未加载）。</p>`}
  </section>`;
}

// --- resources -----------------------------------------------------------------------------------------------------
function resources(m) {
  const list = m.sites.map((s, k) => {
    const t = s.type;
    const val = resourceValue(s.item, t, compact);
    return `<button type="button" class="cv-site" data-site="${k}" title="飞到${esc(s.item.name || "")}">
      <span class="cv-med" style="--bg:${esc(t?.color || "#3a4a5e")}">${glyph(t, 16)}</span>
      <span class="cv-site-t"><b>${esc(s.item.name || t?.name || "")}</b><small>${esc(t?.name || s.item.type)}</small>
        ${s.item.detail ? `<small class="cv-site-d">${esc(s.item.detail)}</small>` : ""}</span>
      <span class="cv-site-v">${esc(val)}<i aria-hidden="true">›</i></span>
    </button>`;
  }).join("");
  const mw = m.sites.filter((s) => s.type?.unit === "MW").reduce((a, s) => a + (s.item.value || 0), 0);
  const summary = m.sites.length
    ? `<p class="cv-lead">地图上标出 ${m.sites.length} 处${
      mw ? ` · 发电装机 ${mw >= 1000 ? `${(mw / 1000).toFixed(1)} GW` : `${Math.round(mw)} MW`}` : ""}。点击可飞到该处。</p>`
    : `<p class="muted cv-note">本市没有地图上标出的资源点。只标出达到规模门槛的站点（门槛见百科）。</p>`;
  return `
  <section class="cv-sec" id="cv-resources" data-sec="resources" aria-labelledby="cv-h-resources">
    <h3 id="cv-h-resources">${icon("resources", "⛏️", { size: 15 })}资源</h3>
    ${summary}
    <div class="cv-sites">${list}</div>
    ${m.sites.length ? `<p class="cv-note">位于本市所辖区县内的站点；只统计地图上标出的站点，不是本市的全部产能。</p>` : ""}
  </section>`;
}

// --- compare -------------------------------------------------------------------------------------------------------
const COMPARE = {
  size: [
    ["常住人口", (c) => c.population, (v) => popShort(v)],
    ["GDP", (c) => c.gdp ?? null, money],
    ["人均 GDP", (c) => (c.gdp != null && c.population ? c.gdp / c.population : null), money],
    ["人口增长", (c) => (Number.isFinite(c.growth) ? c.growth : null), (v) => signed(v)],
  ],
  sectors: [
    ["第一产业", (c) => share(c, "primary"), (v) => pct(v, 0)],
    ["第二产业", (c) => share(c, "secondary"), (v) => pct(v, 0)],
    ["第三产业", (c) => share(c, "tertiary"), (v) => pct(v, 0)],
  ],
};
function share(c, k) {
  const g = c.gdp_by_industry;
  if (!g || !Number.isFinite(g[k])) return null;
  const tot = (g.primary || 0) + (g.secondary || 0) + (g.tertiary || 0);
  return tot > 0 ? g[k] / tot : null;
}

export function compareTable(m, set = "size") {
  const rows = [m.city, ...m.peers];
  const cols = COMPARE[set] || COMPARE.size;
  const max = cols.map(([, f]) => Math.max(...rows.map((c) => Math.abs(f(c) ?? 0))) || 1);
  const prov = (c) => (c.states || []).map((ref) => m.provinceName?.(ref) || ref).join("–");
  return `<div class="cv-cmp" role="table" aria-label="${esc(m.city.name)}与相近城市">
    <div class="cv-cmp-r cv-cmp-h" role="row"><span role="columnheader">城市</span>${cols.map(([l]) => `<span role="columnheader">${esc(l)}</span>`).join("")}</div>
    ${rows.map((c, k) => `<div class="cv-cmp-r${k === 0 ? " me" : ""}" role="row">
      <span role="cell">${k === 0 ? `<b class="cv-cmp-n">${esc(c.name)}</b>` : `<button type="button" class="cv-cmp-n" data-peer="${esc(c.id)}" title="在城市界面中打开${esc(c.full || c.name)}">${esc(c.name)}</button>`}<small>${esc(prov(c))}</small></span>
      ${cols.map(([, f, fmt], j) => {
        const v = f(c);
        const col = v != null && v < 0 ? "#f08a6a" : k === 0 ? "#ecd08e" : "#8fa6bd";
        return `<span role="cell"><em>${v == null ? "–" : esc(fmt(v))}</em>${bar(v == null ? 0 : Math.abs(v) / max[j], col)}</span>`;
      }).join("")}
    </div>`).join("")}
  </div>`;
}

function compare(m) {
  return `
  <section class="cv-sec" id="cv-compare" data-sec="compare" aria-labelledby="cv-h-compare">
    <h3 id="cv-h-compare">${icon("layers", "⚖️", { size: 15 })}比较</h3>
    ${m.peers.length ? `<p class="cv-lead">人口规模最接近的 ${m.peers.length} 个城市。点击可打开。</p>` : `<p class="muted cv-note">没有可比较的城市。</p>`}
    <div class="cv-seg" role="group" aria-label="指标">
      <button type="button" data-set="size" aria-pressed="true">规模与财富</button>
      <button type="button" data-set="sectors" aria-pressed="false">产业结构</button>
    </div>
    <div data-compare>${compareTable(m, "size")}</div>
  </section>`;
}

function footer(m) {
  const nat = m.nation;
  return `<div class="cv-foot">来源：${esc(nat.vintage || "")}${nat.gdp_vintage ? `；GDP：${esc(nat.gdp_vintage)}` : ""}；资源、交通与奇观见百科各页。
    排名在地图上全部 ${m.cityList.length} 个城市之间比较。
    <a href="#" data-pedia>百科 ›</a></div>`;
}

/**
 * Scrolls the dock to a section (its tab id, e.g. "economy"), re-aligned as the heights above settle, for up to 4 s
 * or until the user scrolls themselves.
 */
export function goToSection(el, id) {
  const sec = el?.querySelector(`[data-sec="${id}"]`);
  if (!sec) return false;
  const align = () => {
    const nav = el.querySelector(".cv-tabs");
    el.scrollTop = Math.max(0, sec.offsetTop - (nav?.offsetHeight || 0) - 4);
    el.onscroll?.(); // the tab spy (a scroll event is not always sent for a programmatic jump)
  };
  align();
  let ro = null;
  const stop = () => {
    ro?.disconnect();
    ro = null;
    for (const t of ["wheel", "touchstart", "keydown", "pointerdown"]) el.removeEventListener(t, stop);
  };
  for (const t of ["wheel", "touchstart", "keydown", "pointerdown"]) el.addEventListener(t, stop, { passive: true });
  if (typeof ResizeObserver === "function") {
    ro = new ResizeObserver(() => { if (sec.isConnected) align(); else stop(); });
    for (const c of el.children) ro.observe(c);
  }
  setTimeout(stop, 4000);
  return true;
}

/**
 * Fill the dock. handlers: {onClose, onState(idx), onPeer(id), onSite(site), onSiteHover(site|null), onPedia}.
 */
export function render(el, m, h) {
  el.classList.add("cv-dock");
  el.style.setProperty("--sc", css(m.stateRGB));
  el.innerHTML = header(m) + overview(m) + economy(m) + workforce(m) + hubs(m) + resources(m) + compare(m) + footer(m);
  el.scrollTop = 0;

  el.querySelector("[data-close]").onclick = () => h.onClose();
  el.querySelectorAll("[data-state]").forEach((b) => (b.onclick = () => h.onState(+b.dataset.state)));
  el.querySelector("[data-pedia]").onclick = (e) => { e.preventDefault(); h.onPedia(); };

  // Sites: hover lights the hex on the map, click flies there.
  el.querySelectorAll("[data-site]").forEach((b) => {
    const s = m.sites[+b.dataset.site];
    b.onclick = () => h.onSite(s);
    b.onmouseenter = b.onfocus = () => h.onSiteHover(s);
    b.onmouseleave = b.onblur = () => h.onSiteHover(null);
  });

  // Compare: metric sets and peer links (delegated, the table is re-rendered).
  const cmp = el.querySelector("[data-compare]");
  el.querySelectorAll("[data-set]").forEach((b) => (b.onclick = () => {
    el.querySelectorAll("[data-set]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    cmp.innerHTML = compareTable(m, b.dataset.set);
  }));
  cmp.addEventListener("click", (e) => {
    const b = e.target.closest("[data-peer]");
    if (b) h.onPeer(b.dataset.peer);
  });

  // Tabs scroll to their section; the active tab follows the scroll position.
  const nav = el.querySelector(".cv-tabs");
  const tabs = [...el.querySelectorAll("[data-tab]")];
  const secs = tabs.map((t) => el.querySelector(`[data-sec="${t.dataset.tab}"]`));
  tabs.forEach((t, k) => (t.onclick = () => {
    const top = secs[k].offsetTop - nav.offsetHeight - 4;
    el.scrollTo({ top, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }));
  const spy = () => {
    const y = el.scrollTop + nav.offsetHeight + 24;
    let k = 0;
    secs.forEach((s, j) => { if (s.offsetTop <= y) k = j; });
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 4) k = secs.length - 1;
    tabs.forEach((t, j) => t.classList.toggle("on", j === k));
  };
  el.onscroll = spy;
  spy();
}
