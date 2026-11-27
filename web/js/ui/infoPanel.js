// Shared building blocks for the city and state panels (both render into #city-panel).
import { compact, dollars, esc, int, money, pct, yieldValue } from "../format.js";
import { icon, glyph } from "./icon.js";

// Industry → a "district" glyph: SVG icons i-<key> from icons.js; these emoji are only the fallback.
export const DISTRICT_ICON = {
  agriculture: "🌾", mining: "⛏️", construction: "🏗️", manufacturing: "🏭", wholesale: "📦", retail: "🛍️",
  transportation: "🚢", utilities: "⚡", information: "📡", finance: "🏦", real_estate: "🏘️", professional: "🔬",
  management: "🏢", admin: "🗂️", education: "🎓", health: "🏥", arts: "🎭", accommodation: "🍽️", other: "🔧",
  public_admin: "🏛️",
};

// GB/T 4754 sections (chinaciv jobs keys A–S) → the district glyph of the closest usaciv industry.
export const SECTION_ICON = {
  A: "agriculture", B: "mining", C: "manufacturing", D: "utilities", E: "construction", F: "retail", G: "transportation",
  H: "accommodation", I: "information", J: "finance", K: "real_estate", L: "admin", M: "professional", N: "utilities",
  O: "other", P: "education", Q: "health", R: "arts", S: "public_admin",
};
export const industryIconKey = (k) => SECTION_ICON[k] || k;
// The three-sector GDP split (cities.json / states.json gdp_by_industry).
export const SECTOR_LABEL = { primary: "第一产业", secondary: "第二产业", tertiary: "第三产业" };
export const SECTOR_ICON = { primary: ["y-food", "🌾"], secondary: ["y-production", "⚙️"], tertiary: ["y-gold", "💰"] };

const panelEl = () => document.getElementById("city-panel");

// Yield tiles; `ranks` (optional) adds "第 3 / 34 位" under each.
export function yieldGrid(nation, yields, ranks = null, rankOf = 0) {
  return nation.yields
    .map((y) => {
      const v = yields?.[y.key];
      const r = ranks?.[y.key];
      const label = y.key === "gold" ? "GDP" : y.label;
      return `<div class="yield-tile" title="${esc(y.label)}${y.key === "gold" ? "（GDP）" : ""}：${esc(y.description || "")}">
        <div class="ico" style="color:${esc(y.color)}">${glyph(y, 20)}</div>
        <div class="val" style="color:${esc(y.color)}">${yieldValue(y, v)}</div>
        <div class="lbl">${esc(label)}</div>
        ${r ? `<div class="rank" title="在 ${rankOf} 个省级行政区中的排名（1 为最大）">第 ${r} / ${rankOf} 位</div>` : ""}</div>`;
    })
    .join("");
}

// One "value ▲ national value" row. higherIsGood: true / false / null (neutral). No row when the value is unknown.
export function statRow(ic, fallback, label, v, nv, fmt, higherIsGood) {
  if (v == null) return "";
  let cmp = "";
  if (v != null && nv != null && nv !== 0) {
    const ratio = v / nv;
    const cls = Math.abs(ratio - 1) < 0.03 || higherIsGood == null ? "" : (higherIsGood ? ratio >= 1 : ratio <= 1) ? "good" : "bad";
    // Within 3% of the national value reads as level: no arrow, no colour (the colour uses the same band).
    const arrow = Math.abs(ratio - 1) < 0.03 ? "≈" : ratio > 1 ? "▲" : "▼";
    cmp = `<span class="cmp ${cls}">${arrow} 全国 ${fmt(nv)}</span>`;
  }
  return `<div class="stat-row"><span class="sl">${icon(ic, fallback, { size: 14 })}${esc(label)}</span><span><b>${fmt(v)}</b>${cmp}</span></div>`;
}

// Living-standard rows; chinaciv files omit these fields (CN_PLAN §3.3), so the rows simply do not appear.
export function amenities(o, n) {
  return `
    ${statRow("unemployment", "😐", "失业率", o.unemployment, n.unemployment, (x) => pct(x), false)}
    ${statRow("l-income", "💵", "家庭收入中位数", o.median_income, n.median_income, dollars, true)}
    ${statRow("l-home", "🏠", "房价中位数", o.home_value, n.home_value, dollars, null)}
    ${statRow("l-homeownership", "🔑", "月租金中位数", o.median_rent, n.median_rent, dollars, false)}
    ${statRow(null, "⚖️", "租金 ÷ 收入", o.rent_burden, n.rent_burden, (x) => pct(x), false)}`.trim();
}

// GDP by the three sectors (gdp_by_industry {primary, secondary, tertiary}) as share bars; "" when absent.
export function sectors(o) {
  const g = o.gdp_by_industry;
  if (!g || !Object.keys(SECTOR_LABEL).some((k) => Number.isFinite(g[k]))) return "";
  const tot = Object.keys(SECTOR_LABEL).reduce((a, k) => a + (Number.isFinite(g[k]) ? g[k] : 0), 0) || 1;
  return Object.entries(SECTOR_LABEL).map(([k, label]) => {
    const v = g[k];
    if (!Number.isFinite(v)) return "";
    const share = v / tot;
    return `<div class="ind"><span aria-hidden="true">${icon(SECTOR_ICON[k][0], SECTOR_ICON[k][1])}</span>
      <span>${label}增加值</span><span class="n">${money(v)} · ${pct(share, 0)}</span>
      <div class="bar"><i style="width:${share * 100}%;background:#c9a45c"></i></div></div>`;
  }).join("");
}

// Workforce by industry with location quotients vs. the nation ("specialisation"). limit = max rows (0 = all).
export function industries(o, nation, limit = 0) {
  const n = nation.nation;
  const total = o.employed || 1;
  const nTotal = n.employed || 1;
  let rows = Object.entries(o.jobs || {})
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);
  if (limit) rows = rows.slice(0, limit);
  if (!rows.length) return `<p class="muted">没有分行业数据。</p>`;
  const maxShare = rows[0][1] / total;
  return rows
    .map(([k, v]) => {
      const share = v / total;
      const nShare = (n.jobs?.[k] || 0) / nTotal;
      const lq = nShare > 0 ? share / nShare : 1;
      const tip = `该行业就业占比为全国的 ${lq.toFixed(1)} 倍`;
      const badge = lq >= 1.3 ? `<span class="lq hi" title="${tip}">×${lq.toFixed(1)}</span>`
        : lq <= 0.6 ? `<span class="lq lo" title="${tip}">×${lq.toFixed(1)}</span>` : "";
      const ik = industryIconKey(k);
      return `<div class="ind"><span aria-hidden="true">${icon(`i-${ik}`, DISTRICT_ICON[ik] || "•")}</span>
        <span>${esc(nation.industries?.[k] || k)}${badge}</span><span class="n">${compact(v)} · ${pct(share, 0)}</span>
        <div class="bar"><i style="width:${(share / maxShare) * 100}%;background:${lq >= 1.3 ? "#9fd76a" : "#c9a45c"}"></i></div></div>`;
    })
    .join("");
}

export const gdpRow = (o) =>
  o.gdp != null
    ? `<div class="stat-row"><span class="sl">${icon("y-gold", "💰", { size: 14 })}地区生产总值${o.gdp_year ? `（${o.gdp_year}）` : ""}</span><span><b>${money(o.gdp)}</b>${
        o.population && o.population_year === o.gdp_year ? `<span class="cmp">人均 ${money(o.gdp / o.population)}</span>` : ""}${
        o.gdp_local_currency === "TWD" ? `<span class="cmp" title="1 人民币 = ${esc(o.gdp_fx_local_per_cny)} 新台币">原值 NT$${int(o.gdp_local)}</span>` : ""}</span></div>`
    : "";

// " · ▲ 3.4% 较 2020" from growth / growth_years (cities and provinces), compared with the nation in the tooltip.
// Empty when growth is missing (null means "not measured", never zero).
export function growthSpan(o, n = null) {
  if (!Number.isFinite(o?.growth)) return "";
  const yrs = Array.isArray(o.growth_years) && o.growth_years.length === 2 ? o.growth_years : null;
  const p = (g) => `${g >= 0 ? "+" : "−"}${Math.abs(g * 100).toFixed(1)}%`;
  const period = yrs ? `${yrs[0]}–${yrs[1]} 年` : "近几年";
  const us = Number.isFinite(n?.growth) ? `（全国 ${p(n.growth)}）` : "";
  const tip = `${period}常住人口变化：${p(o.growth)}${us}`;
  const cls = o.growth >= 0 ? "good" : "bad";
  return ` · <span class="growth ${cls}" title="${esc(tip)}">${o.growth >= 0 ? "▲" : "▼"} ${Math.abs(o.growth * 100).toFixed(1)}%${
    yrs ? ` <span class="since">较 ${yrs[0]} 年</span>` : ""}</span>`;
}

export const popLine = (o, extra = "") =>
  `<div class="cp-pop">${icon("pop", "👥", { size: 16 })} ${o.fips === "71" || o.kind === "taiwan_city" ? "户籍人口" : "常住人口"} <b>${int(o.population)}</b>${o.population_year ? `（${o.population_year}）` : ""}${
    o.employed != null ? ` · 从业 ${int(o.employed)}` : ""}${extra}</div>`;

/**
 * Fill and show the panel.
 * spec: {kind: "city"|"state", stripe, title, sub, headExtra, sections: [{title, html}], foot, onClose, onPedia, wire(panel)}
 */
export function showPanel(spec) {
  const panel = panelEl();
  panel.dataset.kind = spec.kind;
  panel.setAttribute("aria-label", `${spec.kind === "state" ? "省份" : "城市"}：${spec.title}`);
  panel.innerHTML = `
    <div class="sheet-grip" aria-hidden="true"></div>
    <div class="cp-head">
      <div class="stripe" style="background:${spec.stripe}"></div>
      <button class="icon-btn cp-close" aria-label="关闭面板（Esc）" title="关闭（Esc）">${icon("close", "✕", { size: 13 })}</button>
      <div class="cp-kind">${esc(spec.kindLabel || (spec.kind === "state" ? "省份" : "城市"))}</div>
      <h2 class="cp-name">${spec.titleHtml ?? esc(spec.title)}</h2>
      ${spec.sub ? `<div class="cp-full">${spec.sub}</div>` : ""}
      ${spec.headExtra || ""}
    </div>
    ${spec.sections.filter(Boolean).map((s) => `<section class="cp-section"><h3>${s.title}</h3>${s.html}</section>`).join("")}
    <div class="cp-foot">${spec.foot || ""} <a href="#" data-pedia>百科 ›</a></div>`;
  panel.hidden = false;
  panel.scrollTop = 0;
  panel.classList.remove("dragging-sheet");
  panel.style.transform = "";
  document.body.classList.add("panel-open");
  panel.querySelector(".cp-close").onclick = spec.onClose;
  panel.querySelector("[data-pedia]").onclick = (e) => {
    e.preventDefault();
    spec.onPedia?.();
  };
  spec.wire?.(panel);
}

export function hidePanel() {
  const panel = panelEl();
  panel.hidden = true;
  panel.innerHTML = "";
  delete panel.dataset.kind;
  document.body.classList.remove("panel-open");
}

// Bottom-sheet swipe-down to close (mobile). Installed once.
export function installSheetSwipe(onClose) {
  const panel = panelEl();
  let start = null;
  panel.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" || !matchMedia("(max-width: 700px)").matches) return;
    // Only from the grip/head, or anywhere while the sheet is scrolled to the top.
    const fromHead = e.target.closest(".sheet-grip, .cp-head");
    if (!fromHead && panel.scrollTop > 0) return;
    if (e.target.closest("button, a, input")) return;
    start = { y: e.clientY, id: e.pointerId, dy: 0, head: !!fromHead };
  });
  panel.addEventListener("pointermove", (e) => {
    if (!start || e.pointerId !== start.id) return;
    start.dy = Math.max(0, e.clientY - start.y);
    if (start.dy > 6 && (start.head || panel.scrollTop <= 0)) {
      panel.classList.add("dragging-sheet");
      panel.style.transform = `translateY(${start.dy}px)`;
    }
  });
  const end = (e) => {
    if (!start || e.pointerId !== start.id) return;
    const dy = start.dy;
    start = null;
    panel.classList.remove("dragging-sheet");
    panel.style.transform = "";
    if (dy > 80) onClose();
  };
  panel.addEventListener("pointerup", end);
  panel.addEventListener("pointercancel", end);
}
