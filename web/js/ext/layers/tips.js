// Hover tooltips for the map-art layers (HTML strings; every data value is escaped). Each says where the number comes
// from and the caveat that matters for it. Field names follow docs/CN_PLAN.md §5.5 / §5.7 (chinaciv); the usaciv
// names (enplanements, tons, rd_usd, visits) still read when present, so the US test data keeps working.
import { esc, compact, int, money } from "../../format.js";
import { WONDER_KINDS } from "../../render/art/sites.js";

const muted = (s) => `<span class="muted">${s}</span>`;
const num = (n) => (n == null || !Number.isFinite(n) ? "–" : compact(n));
const sign = (x) => (x > 0 ? "+" : x < 0 ? "−" : "±");

// Province name for a site row's `state` (province code "44"; usaciv: a postal code).
function provinceName(m, ref) {
  if (ref == null || ref === "") return "";
  const st = (m?.w?.raw?.states || []).find((s) => s.fips === ref || s.abbr === ref);
  return st ? st.full || st.name : String(ref);
}

// CAAC's own size groups (infrastructure.json hubs); usaciv FAA hub classes as a fallback.
const HUB_NAME = { L: "年旅客吞吐量 1000 万人次以上", M: "年旅客吞吐量 200 万–1000 万人次", S: "年旅客吞吐量 200 万人次以下", N: "非枢纽机场" };
const PORT_TYPE = { coastal: "沿海港口", inland: "内河港口", great_lakes: "湖港" };
const WONDER_KIND_NAME = { natural: "自然奇观", monument: "文化奇观", landmark: "名胜", university: "一流大学" };
const UNESCO_CAT = { cultural: "文化遗产", natural: "自然遗产", mixed: "文化与自然双重遗产" };

export const tips = {
  port(p, m) {
    const yr = p.year ?? "";
    const where = [PORT_TYPE[p.type] || "港口", provinceName(m, p.state)].filter(Boolean).join(" · ");
    const lines = [`<b>${esc(p.name)}</b> ${muted(esc(where))}`];
    if (p.publisher) {
      lines.push(`${esc(yr)} 年 · ${esc(p.publisher)}`);
      if (p.cargo_t != null) lines.push(`货物吞吐量 <b>${num(p.cargo_t)}</b> 吨`);
      if (p.container_cargo_t != null) lines.push(`集装箱货运重量 <b>${num(p.container_cargo_t)}</b> 吨`);
      if (p.teu != null) lines.push(`集装箱吞吐量 <b>${num(p.teu)}</b> 标箱`);
      if (p.notes) lines.push(muted(esc(p.notes)));
      return lines.join("<br>");
    }
    if (p.cargo_t != null || p.tons == null) {
      lines.push(`货物吞吐量第 ${esc(p.rank ?? "–")} 位 · <b>${num(p.cargo_t)}</b> 吨（${esc(yr)} 年）`);
      const extra = [p.foreign_t != null ? `外贸 ${num(p.foreign_t)} 吨` : "", p.teu != null ? `集装箱 ${num(p.teu)} 标箱` : ""].filter(Boolean);
      if (extra.length) lines.push(extra.join(" · "));
      lines.push(muted("交通运输部港口货物吞吐量统计；标在港区中心（长江等内河港口位置为近似）。"));
    } else {
      lines.push(`#${esc(p.rank)} · <b>${num(p.tons)}</b> 短吨（${esc(yr)}）`);
    }
    return lines.join("<br>");
  },
  airport(a, m) {
    const where = [a.city, provinceName(m, a.state)].filter(Boolean).join(" · ");
    const lines = [`<b>${esc(a.name)}</b> ${muted(esc([a.id, where].filter(Boolean).join(" · ")))}`];
    if (a.hub) lines.push(esc(HUB_NAME[a.hub] || a.hub));
    const pax = a.passengers ?? a.enplanements;
    const prev = a.passengers != null ? a.passengers_prev : a.enplanements_prev;
    if (pax != null) {
      let ch = "";
      if (prev > 0 && Number.isFinite(a.year)) {
        const r = pax / prev - 1;
        ch = `（比 ${a.year - 1} 年 ${sign(r)}${Math.abs(r * 100).toFixed(1)}%）`;
      }
      const rank = a.rank != null ? `第 ${esc(a.rank)} 位 · ` : "";
      lines.push(`${rank}旅客吞吐量 <b>${num(pax)}</b> 人次（${esc(a.year ?? "")} 年）${ch}`);
    }
    const more = [a.cargo_t != null ? `货邮 ${num(a.cargo_t)} 吨` : "", a.movements != null ? `起降 ${num(a.movements)} 架次` : ""].filter(Boolean);
    if (more.length) lines.push(more.join(" · "));
    lines.push(muted(esc(a.publisher || (a.passengers != null ? "中国民用航空局《全国民用运输机场生产统计公报》；旅客吞吐量含进出港。" : "FAA 数据（测试数据）。"))));
    if (a.notes) lines.push(muted(esc(a.notes)));
    return lines.join("<br>");
  },
  wonder(x, m) {
    const k = WONDER_KIND_NAME[x.kind] || WONDER_KINDS[x.kind]?.name || "奇观";
    const rule = m.data.wonders?.rules?.find((r) => r.id === x.rule);
    const mt = x.metrics || {};
    const lines = [`<b>${esc(x.name)}</b> ${muted(esc(provinceName(m, x.state)))}`];
    if (x.rule === "unesco_whs") {
      lines.push(`世界遗产 · ${esc(UNESCO_CAT[mt.category] || k)}${mt.inscribed ? ` · ${esc(mt.inscribed)} 年列入` : ""}`);
      if (mt.criteria) lines.push(`入选标准 ${esc(mt.criteria)}${mt.area_ha != null ? ` · ${int(mt.area_ha)} 公顷` : ""}`);
    } else if (x.rule === "national_park") {
      lines.push(`国家公园${mt.established ? ` · ${esc(String(mt.established).slice(0, 10))} 设立` : ""}`);
      if (mt.area_km2 != null) lines.push(`面积 ${int(mt.area_km2)} km²`);
    } else if (x.rule === "scenic_5a") {
      lines.push(`国家 5A 级旅游景区${mt.designated ? ` · ${esc(mt.designated)} 年评定` : ""}${mt.batch ? `（第 ${esc(mt.batch)} 批）` : ""}`);
    } else if (x.rule === "university" || x.kind === "university") {
      lines.push(`${esc(k)}${x.rank != null ? ` · 第 ${esc(x.rank)} 位` : ""}${mt.double_first_class ? " · “双一流”建设高校" : ""}`);
      if (mt.rd_cny != null) lines.push(`科技经费 ${money(mt.rd_cny)}${mt.rd_year ? `（${esc(mt.rd_year)} 年）` : ""}`);
      else if (mt.rd_usd != null) lines.push(`R&amp;D $${num(mt.rd_usd)}`);
    } else {
      lines.push(esc(k));
      if (mt.visits != null) lines.push(`${num(mt.visits)} 人次`);
    }
    if (rule?.text) lines.push(muted(esc(rule.text)));
    return lines.join("<br>");
  },
};
