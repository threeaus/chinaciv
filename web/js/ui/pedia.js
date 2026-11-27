// The Almanac: what every number means and exactly where it comes from.
import { resolveTables } from "../terrain.js";
import { esc } from "../format.js";
import { parseHex, luminance } from "../color.js";
import { icon, glyph } from "./icon.js";
import { noticeHtml, ATTRIBUTION } from "../app/help.js";

// A short SVG sample of a line symbol for the map legend: dash pattern in px ("" = solid), colour, width, and the
// casing under it (a pale halo for boundaries; a dark case, dashed like the line, for the 断续线).
const legendLine = (dash, color, width = 2, casing = "rgba(255,232,160,.55)", dashedCase = false) => {
  const da = dash ? ` stroke-dasharray="${dash}"` : "";
  return `<svg width="44" height="10" viewBox="0 0 44 10" aria-hidden="true" style="vertical-align:middle"><line x1="1" y1="5" x2="43" y2="5" stroke="${casing}" stroke-width="${width + 2}"${dashedCase ? da : ""}/><line x1="1" y1="5" x2="43" y2="5" stroke="${color}" stroke-width="${width}"${da}/></svg>`;
};

// Chinese headings of the wonder rule ids in wonders.json (used when a rule carries no `name`).
const WONDER_RULE_NAMES = { unesco_whs: "世界遗产", national_park: "国家公园", scenic_5a: "5A 级景区", university: "一流大学" };

const COVER_ICON = { forest_deciduous: "l-forest", forest_evergreen: "l-forest", forest_mixed: "l-forest", cropland: "l-farmland", pasture: "l-farmland", urban: "l-developed" };
// Glyph colour that reads on a resource medallion (dark on light faces such as nuclear yellow or silver).
const inkOn = (hex) => {
  try { return /^#[0-9a-f]{6}$/i.test(hex || "") && luminance(parseHex(hex)) > 0.4 ? "#1c1710" : "#f8f0d8"; } catch { return "#f8f0d8"; }
};
const CATEGORY = { energy: "能源", mineral: "矿产", agri: "农业" };
const fmtNum = (v) => (Number.isFinite(v) ? v.toLocaleString("zh-CN") : "–");

/**
 * data: {world, nation, lenses, sources, w, resources, states, getData(name) → app.data[name] (infrastructure,
 * wonders: loaded after the first frame, so read when a page opens)}
 */
export function initPedia(data) {
  const modal = document.getElementById("pedia");
  const card = modal.querySelector(".modal-card");
  const nav = document.getElementById("pedia-nav");
  const body = document.getElementById("pedia-body");
  const srcName = (id) => data.sources?.find((s) => s.id === id)?.title || id || "";
  const later = (name) => (typeof data.getData === "function" ? data.getData(name) : null) || null;
  let restoreFocus = null;

  const h2 = (ic, fb, text) => `<h2>${icon(ic, fb, { size: 24 })}<span>${esc(text)}</span></h2>`;
  const g = data.world.grid || {};
  const notice = data.world.notice || null;
  const hasLenses = (data.lenses?.lenses || []).length > 0;
  const nScope = data.nation?.scope ? `<p class="muted">${esc(data.nation.scope)}</p>` : "";

  // Page ids (stable: other modules open pages by id) → [title, render].
  const pages = {
    about: ["关于本图", () => `
      ${h2("pedia", "📖", "关于本图")}
      <p>这是用策略游戏风格绘制的真实中国。地图上没有虚构内容：每一块地形、每一座城市和每一个数字都来自公开数据，
      出处列在<i>数据来源</i>中。</p>
      <p class="pedia-notice">${noticeHtml(notice)}</p>
      <h4>制作方法</h4>
      <p>全国采用 Albers 等积圆锥投影（标准纬线 ${esc(data.world.projection?.lat1 ?? 25)}°N、${esc(data.world.projection?.lat2 ?? 47)}°N，
      中央经线 ${esc(data.world.projection?.lon0 ?? 105)}°E），切分为 ${fmtNum(g.cols)}×${fmtNum(g.rows)} 个六边形，每格对角宽
      ${fmtNum((g.radius || 25) * 2)} 公里。每个六边形归属于其中心所在的省级行政区。地形来自格内的高程采样与土地覆盖数据。</p>
      <p><b>城市</b>为全部地级行政区（地级市、地区、自治州、盟）以及 4 个直辖市、香港和澳门特别行政区和台湾省的主要城市，
      标在政府驻地；城市的数字覆盖整个行政区（含所辖县区），不只是市区。</p>
      <p><b>南海诸岛</b>按标准地图惯例以附图形式画在右下角，附图内绘有完整的南海断续线；钓鱼岛、赤尾屿等岛屿在主图上标注。</p>
      <h4>操作</h4>
      <p>拖动或方向键 / WASD 平移 · 滚轮、+/– 或双击缩放 · 点击城市或省份打开详情 · / 或 ⌘K 搜索 ·${hasLenses ? " L 切换透镜 ·" : ""}
      R 显示或隐藏资源 · ? 查看全部快捷键 · Esc 关闭。</p>
      <p>地址栏中始终保存着当前视图（${hasLenses ? "透镜、" : ""}选中对象和视角）的链接；用<i>分享</i>复制链接或下载图片。</p>
      <h4>致谢</h4>
      <p>${esc(ATTRIBUTION)}</p>`],
    notice: ["地图说明", () => `
      ${h2("terrain", "🗺️", "地图说明")}
      <p class="pedia-notice"><b>${noticeHtml(notice)}</b></p>
      ${notice?.boundary ? `<h4>边界数据</h4><p>${esc(notice.boundary)}</p>` : ""}
      ${(notice?.sources || []).length ? `<p class="muted">对应数据来源：${notice.sources.map((id) => esc(srcName(id))).join("、")}</p>` : ""}
      <h4>疆域</h4>
      <p>国界、省界和县界只采用依据标准地图的行政区划数据：台湾省、香港特别行政区、澳门特别行政区、海南省及南海诸岛、
      藏南地区和阿克赛钦地区均在中国境内。南海诸岛及断续线绘于右下角附图（与主图同一投影，按比例缩小），钓鱼岛及其附属岛屿
      （含赤尾屿）在主图上以中国地名标注。邻国轮廓仅作背景，取自 Natural Earth 的中国视角版本。</p>
      <h4>图例</h4>
      <p class="pedia-legend">${legendLine("11 3 2.5 3", "#7a184a", 2.2)} 国界　${legendLine("5 5", "#7a184a", 1.5)} 未定国界　${
        legendLine("", "rgba(15,10,5,.6)", 1.4)} 省级界　${legendLine("12 5", "#f2d58a", 3, "rgba(28,16,6,.8)", true)} 南海断续线</p>
      ${data.world.boundary?.note ? `<p class="muted">${esc(data.world.boundary.note)}</p>` : ""}
      <h4>统计口径</h4>
      <p>全国合计采用国家统计局口径（31 个省、自治区、直辖市，不含香港、澳门和台湾）。香港、澳门和台湾的数字若能取得，
      取自其官方统计并在相应城市中注明；无法取得时留空（显示为“–”），而不是记为 0。</p>
      <p class="muted">本图仅供个人学习，不含任何军事内容。</p>`],
    yields: ["产出", () => `
      ${h2("y-production", "⚙️", "产出")}
      <p>把《文明》的产出对应到真实指标。<b>金币即地区生产总值（GDP）</b>：按当年价格计算的年度产出，计在生产发生的地方。
      其余产出的口径见下表（每项对所有城市使用同一口径；没有数据的城市留空）。</p>
      <table>${data.nation.yields.map((y) => `<tr><td class="ic" style="color:${esc(y.color)}">${glyph(y, 26)}</td><td><b style="color:${esc(y.color)}">${esc(y.label)}${y.key === "gold" ? "（GDP）" : ""}</b><br>${esc(y.description)}</td></tr>`).join("")}</table>
      ${nScope}`],
    states: ["省份", () => `
      ${h2("terrain", "🗺️", "省份")}
      <p>点击没有城市的陆地六边形即可打开所在的省级行政区（省、自治区、直辖市、特别行政区；台湾省按省份处理）。
      省份的数字取自全省统计（${esc(data.nation.vintage || "")}${data.nation.gdp_vintage ? `；GDP：${esc(data.nation.gdp_vintage)}` : ""}），
      不是各城市的简单相加，因此农村地区也计算在内。</p>
      <p><b>排名</b>（“第 3 / 34 位”）在有数据的省级行政区之间比较，1 为最大；缺少数据的省份不参与排名。</p>
      ${data.states ? "" : `<p class="muted">本次数据构建没有 states.json，省份面板只显示名称和城市。</p>`}`],
    terrain: ["地形", () => {
      const t = data.w?.tables || resolveTables(data.world.tables);
      const hasCover = Array.isArray(data.world.cover);
      const row = (x) => `<tr><td class="nm">${x.color ? `<span class="swatch" style="background:${esc(x.color)}"></span>` : ""}${
        COVER_ICON[x.key] ? icon(COVER_ICON[x.key], "", { size: 15 }) + " " : ""}<b>${esc(x.name)}</b></td><td>${esc(x.rule || "")}</td></tr>`;
      return `
      ${h2("terrain", "🗺️", "地形")}
      <p>每个六边形取格内 ETOPO 高程采样的平均值。地势由平均高程和起伏度（采样的标准差）决定；明暗由与相邻六边形的高差决定，
      光线来自西北方向。</p>
      <h4>${icon("l-forest", "🌲", { size: 16 })} 土地覆盖</h4>
      ${hasCover
        ? `<p>每个六边形的底色是格内陆地采样中占比最大的土地覆盖类型。小符号显示混合情况：树木随森林比例增减，田块、芦苇、
           灌丛和草丛分别表示耕地、湿地、灌木和草地。</p>
           <table>${t.cover.filter((x) => x.id > 0).map(row).join("")}</table>`
        : `<p class="muted">本次数据构建还没有土地覆盖图层，陆地按高程着色。</p>`}
      <h4>地势</h4>
      <table>${t.relief.map(row).join("")}</table>
      <h4>${icon("r-hydro", "💧", { size: 16 })} 水域</h4>
      <table>${t.water.filter((x) => x.id > 0).map(row).join("")}</table>
      <h4>境外</h4>
      <p class="muted">邻国国土覆盖一层淡雾：仅作为背景显示，不作详细绘制。</p>`;
    }],
    lenses: ["透镜", () => `
      ${h2("layers", "▤", "透镜")}
      <p>透镜按某一项指标给地图重新着色（${esc(data.lenses.vintage || "")}）。图例显示各取值上有多少个六边形；
      在图例上悬停或拖动，地图上只显示该区间。</p>
      ${data.lenses.lenses.length ? "" : `<p class="muted">本次数据构建没有透镜（lenses.json）。</p>`}
      ${(data.lenses.groups || [{ id: null, name: "" }]).map((gr) => {
        const ls = data.lenses.lenses.filter((l) => !gr.id || l.group === gr.id);
        if (!ls.length) return "";
        return `${gr.name ? `<h3 class="grp">${icon(`g-${gr.id}`, "", { size: 16 })} ${esc(gr.name)}</h3>` : ""}${ls.map((l) => `
          <div class="lens-entry"><div class="le-ic">${glyph(l, 26)}</div><div>
          <h4>${esc(l.name)}</h4><p>${esc(l.description)}<br>
          <i class="le-ramp" style="background:linear-gradient(90deg, ${(l.ramp || []).map(esc).join(",")})"></i>
          <span class="muted">刻度：${l.scale === "log" ? "对数" : "线性"}，${fmtNum(l.domain?.[0])}–${fmtNum(l.domain?.[1])} ${esc(l.unit || "")}${
            l.higher_is === "good" ? " · 越高越好" : l.higher_is === "bad" ? " · 越高越差" : ""}${l.source ? " · " + esc(srcName(l.source)) : ""}</span></p></div></div>`).join("")}`;
      }).join("")}`],
    resources: ["资源", () => {
      const r = data.resources;
      if (!r?.types?.length) return `${h2("resources", "⛏️", "资源")}<p class="muted">本次数据构建没有资源图层。</p>`;
      const count = new Map();
      for (const it of r.items || []) count.set(it.type, (count.get(it.type) || 0) + 1);
      const cats = [...new Set(r.types.map((t) => t.category || "other"))];
      return `
      ${h2("resources", "⛏️", "资源")}
      <p>资源标出全国最大的发电厂、矿山和油气田所在的地块。只显示达到门槛的站点：每类的门槛写在其说明中。缩小时每个六边形
      只显示排位最高的资源，放大可看到更多。按 <b>R</b> 显示或隐藏。</p>
      ${cats.map((c) => `<h4>${esc(CATEGORY[c] || c)}</h4><table class="res-table">
        <tr><th></th><th>类型</th><th>入选条件</th><th>站点数</th></tr>
        ${r.types.filter((t) => (t.category || "other") === c).map((t) => `<tr>
          <td class="ic"><span class="res-ic" style="background:${esc(t.color || "#24384f")};color:${inkOn(t.color)}">${glyph(t, 20)}</span></td>
          <td class="nm"><b>${esc(t.name)}</b>${t.unit ? `<br><span class="muted">单位：${esc(t.unit)}</span>` : ""}</td>
          <td>${esc(t.description || "")}<br><span class="muted">来源：${esc(srcName(t.source))}</span></td>
          <td class="num">${count.get(t.id) || 0}</td></tr>`).join("")}</table>`).join("")}`;
    }],
    improvements: ["地块改良", () => {
      const inf = later("infrastructure");
      const rules = inf?.rules || {};
      const names = { hsr: "高速铁路", rail: "普速铁路", roads: "高速公路", expressway: "高速公路", ports: "港口", airports: "机场" };
      const ruleRows = Object.entries(rules).map(([k, v]) => `<tr><td class="nm"><b>${esc(names[k] || k)}</b></td><td>${esc(v)}</td></tr>`).join("");
      return `
      ${h2("t-rail", "🚄", "地块改良")}
      <p>铁路和高速公路画成相邻六边形中心之间的连线：<b>高速铁路</b>为带红色刻度的亮色线条，从全国视图起即可看到；
      <b>普速铁路</b>为深色钢轨加道砟；<b>高速公路</b>为浅色路面。港口按货物吞吐量、机场按旅客吞吐量排名，规模越大图标越大，
      越早出现。在“图层”菜单中可分别开关。</p>
      ${inf ? `${ruleRows ? `<table>${ruleRows}</table>` : ""}
        <p class="muted">${(inf.airports || []).length} 个机场 · ${(inf.ports || []).length} 个港口${inf.vintage ? ` · ${esc(typeof inf.vintage === "string" ? inf.vintage : Object.values(inf.vintage).join("；"))}` : ""}</p>
        ${(inf.sources || []).length ? `<p class="muted">来源：${inf.sources.map((id) => esc(srcName(id))).join("、")}</p>` : ""}`
        : `<p class="muted">交通数据（infrastructure.json）尚未加载或未构建。</p>`}`;
    }],
    wonders: ["奇观", () => {
      const won = later("wonders");
      const list = won?.wonders || [];
      const per = new Map();
      for (const x of list) per.set(x.rule, (per.get(x.rule) || 0) + 1);
      return `
      ${h2("w-landmark", "🏛️", "奇观")}
      <p>奇观按公开的规则选取，而不是凭印象挑选：世界遗产、国家公园、5A 级景区和一流大学。规则原文如下。</p>
      ${won ? `<table>${(won.rules || []).map((r) => `<tr><td class="nm"><b>${esc(r.name || WONDER_RULE_NAMES[r.id] || r.id)}</b><br><span class="muted">${per.get(r.id) || 0} 处</span></td><td>${esc(r.text || "")}</td></tr>`).join("")}</table>
        ${(won.sources || []).length ? `<p class="muted">来源：${won.sources.map((id) => esc(srcName(id))).join("、")}</p>` : ""}`
        : `<p class="muted">奇观数据（wonders.json）尚未加载或未构建。</p>`}`;
    }],
    sources: ["数据来源", () => `
      ${h2("pedia", "📖", "数据来源")}
      <p class="pedia-notice">${noticeHtml(notice, { long: true })}</p>
      ${(data.sources || []).length ? "" : `<p class="muted">本次数据构建没有 sources.json。</p>`}
      ${(data.sources || []).map((s) => `
        <h4>${esc(s.title)}</h4>
        <p>${esc(s.description || "")}${s.used_for ? `<br><span class="muted">用途：${esc(s.used_for)}</span>` : ""}<br>
        <span class="muted">${esc(s.publisher || "")} · ${esc(s.license || "")}${s.vintage ? " · " + esc(s.vintage) : ""}${
          s.homepage ? ` · <a href="${esc(s.homepage)}" target="_blank" rel="noopener">主页</a>` : ""}</span></p>
        ${fileTable(s.files || [])}`).join("")}
      <h4>致谢</h4><p>${esc(ATTRIBUTION)}</p>`],
  };
  // A source's raw files: the first few inline, the rest (DataV and Overpass have hundreds) folded away.
  const FILES_SHOWN = 6;
  const fileRow = (f) => f.retrieved
    ? `<tr><td><code>${esc(f.url)}</code></td><td class="muted" style="white-space:nowrap">${esc(f.retrieved.slice(0, 10))}<br>${((f.bytes || 0) / 1e6).toFixed(1)} MB</td></tr>`
    : `<tr><td><a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.file)}</a></td><td class="muted">原始资料</td></tr>`;
  const fileTable = (files) => `<table>${files.slice(0, FILES_SHOWN).map(fileRow).join("")}</table>${files.length > FILES_SHOWN
    ? `<details><summary class="muted">另有 ${files.length - FILES_SHOWN} 个文件</summary><table>${files.slice(FILES_SHOWN).map(fileRow).join("")}</table></details>` : ""}`;
  // Omit the lens page when a stripped-down deployment has no lens file.
  if (!hasLenses) delete pages.lenses;
  // Old English page names (links, other modules) still open the right page.
  const ALIAS = { "About this map": "about", Yields: "yields", States: "states", Terrain: "terrain", Lenses: "lenses", Resources: "resources", Sources: "sources" };

  const show = (name) => {
    name = ALIAS[name] || name;
    if (!pages[name]) name = "about";
    body.innerHTML = pages[name][1]();
    body.scrollTop = 0;
    nav.querySelectorAll("button").forEach((b) => {
      const on = b.dataset.page === name;
      b.classList.toggle("active", on);
      b.setAttribute("aria-current", on ? "page" : "false");
    });
  };
  nav.innerHTML = `<div class="hd">百科</div>` + Object.entries(pages).map(([p, [title]]) => `<button data-page="${esc(p)}">${esc(title)}</button>`).join("");
  nav.onclick = (e) => {
    const b = e.target.closest("button[data-page]");
    if (b) show(b.dataset.page);
  };
  const close = () => {
    if (modal.hidden) return;
    modal.hidden = true;
    if (restoreFocus && document.contains(restoreFocus)) restoreFocus.focus();
    restoreFocus = null;
  };
  modal.onclick = (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) close();
  };
  // Keep Tab inside the dialog.
  modal.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const f = [...card.querySelectorAll("button, a[href], [tabindex]:not([tabindex='-1'])")].filter((x) => x.offsetParent);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  return {
    open(page = "about") {
      if (modal.hidden) restoreFocus = document.activeElement;
      show(page);
      modal.hidden = false;
      (nav.querySelector("button.active") || card.querySelector("[data-close]"))?.focus();
    },
    close,
    get isOpen() {
      return !modal.hidden;
    },
  };
}
