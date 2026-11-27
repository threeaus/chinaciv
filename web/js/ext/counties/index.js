import { esc, int, pct } from "../../format.js";
import { bucketRows, countyPath, visible } from "./geometry.js";

const MODE = "county";
const COUNTY_ZOOM = 14;
const kinds = {
  "new-area": { label: "国家级新区", color: "#ffc46c", shape: "diamond" },
  "free-trade": { label: "自贸试验区", color: "#74dbc9", shape: "square" },
};

export function install(app) {
  let active = false, dock, chosen, zone, parent, query = "", currentCode = "";
  let countyIndex, countyById, builtIndex, zonesById;
  const paths = new WeakMap();
  const hitContext = document.createElement("canvas").getContext("2d");
  const enabled = { counties: false, builtup: false, "new-area": false, "free-trade": false };
  const promises = new Map();

  function load(name) {
    if (!promises.has(name)) {
      promises.set(name, app.loadData(name).then((data) => {
        if (!data) return null;
        if (name === "counties") {
          countyById = new Map(data.counties.map((c) => [c.id, c]));
          countyIndex = bucketRows(data.counties, (c) => c.bounds, 130);
        } else if (name === "builtup") {
          builtIndex = bucketRows(data.points, ([x, y]) => [x, y, x, y], 45);
        } else {
          zonesById = new Map(data.zones.map((z) => [z.id, z]));
        }
        app.requestDraw();
        return data;
      }));
    }
    return promises.get(name);
  }

  const button = app.ui.addTopButton({
    id: "btn-counties", icon: "▦", label: "县区", title: "打开县级界面",
    onClick: () => {
      if (active) app.setMode(null);
      else open({ city: app.cityView?.city?.id || app.state.selectedCity?.id });
    },
  });
  button?.setAttribute("aria-expanded", "false");
  const open = (params = {}) => app.setMode(MODE, params);
  const prefecture = (c) => app.cityById.get(c.city)?.full || "";
  const province = (c) => app.data.states?.find((s) => s.fips === c.state)?.name || "";
  const path = (c) => {
    if (!paths.has(c)) paths.set(c, countyPath(c));
    return paths.get(c);
  };
  function countyAt(x, y) {
    const vp = { x0: x, y0: y, x1: x, y1: y };
    for (const c of countyIndex?.(vp) || []) if (hitContext.isPointInPath(path(c), x, y, "evenodd")) return c;
    return null;
  }

  function select(c, fly = true) {
    if (!c || !active) return;
    chosen = c;
    zone = null;
    currentCode = c.id;
    if (fly) app.fitBounds(...c.bounds, { padTop: 105, padBottom: 80, maxScale: 115 / app.w.grid.R, ms: 600 });
    app.requestDraw();
    app.hash.update();
    renderDetail();
    renderList();
  }

  function selectZone(z, fly = true) {
    if (!z || !active) return;
    zone = z;
    chosen = null;
    currentCode = `zone-${z.id}`;
    if (fly) app.flyTo(z.x, z.y, Math.max(app.cam.scale, 24 / app.w.grid.R), 600);
    app.requestDraw();
    app.hash.update();
    renderDetail();
  }

  function renderList() {
    const host = dock?.querySelector(".county-results");
    if (!host) return;
    if (!countyById) {
      host.textContent = app.data.counties === null ? "县级边界暂不可用。" : "正在读取县级边界…";
      return;
    }
    const matches = [...countyById.values()].filter((c) =>
      (!parent || c.city === parent) && (!query || [c.name, c.id, prefecture(c), province(c)].some((s) => s.includes(query))));
    host.innerHTML = `<p class="advisor-note">${int(matches.length)} 个县级地区${matches.length > 45 ? "，显示前 45 个" : ""}</p>
      <ul class="advisor-list">${matches.slice(0, 45).map((c) => `<li><button type="button" data-county="${esc(c.id)}" aria-pressed="${chosen === c}">
        <span>${esc(c.name)}<small>${esc([prefecture(c), province(c)].filter(Boolean).join(" · "))}</small></span><strong>${esc(c.id)}</strong></button></li>`).join("")}</ul>`;
  }

  function renderDetail() {
    const host = dock?.querySelector(".county-detail");
    if (!host) return;
    if (zone) {
      const scheme = kinds[zone.kind];
      const data = app.data.zones;
      const index = zone.kind === "new-area" ? 0 : zone.id.startsWith("nm-") ? 3 : 1;
      host.innerHTML = `<article><span class="county-kind">${esc(scheme.label)}</span><h3>${esc(zone.name)}</h3>
        <p>代表点 · ${esc(zone.place)}</p><p class="advisor-note">${esc(data.note)}</p>
        <a href="${esc(data.sources[index].url)}" target="_blank" rel="noopener">查看官方资料</a></article>`;
      return;
    }
    if (!chosen) {
      host.innerHTML = '<p class="advisor-note">搜索县区，或放大地图后点击县级边界内的区域。</p>';
      return;
    }
    const c = chosen;
    const transport = app.data.infrastructure;
    const assets = [ ...(transport?.airports || []), ...(transport?.ports || []), ...(app.data.wonders?.wonders || []) ]
      .filter((r) => r.county === c.id);
    const resource = (app.data.resources?.items || []).filter((r) => r.county === c.id);
    const place = [province(c), prefecture(c)].filter(Boolean).join(" · ");
    const list = [...assets, ...resource];
    host.innerHTML = `<article><span class="county-kind">县级行政区 · ${esc(c.id)}</span><h3>${esc(c.name)}</h3>
      <p>${esc(place)}${c.city !== c.id && app.cityById.has(c.city) ? ` · <button type="button" class="county-link" data-city="${esc(c.city)}">查看所属城市</button>` : ""}</p>
      ${c.stats ? `<dl class="advisor-stats"><div><dt>${c.stats.year} 年末常住人口</dt><dd>${int(c.stats.population)} 人</dd></div>
        <div><dt>城镇化率</dt><dd>${pct(c.stats.urban_pct, 2)}</dd></div></dl>
        <p class="advisor-note"><a href="${esc(app.data.counties.stats_source.source)}" target="_blank" rel="noopener">${esc(app.data.counties.stats_source.title)}</a></p>` : ""}
      <dl class="advisor-stats"><div><dt>覆盖 25 公里六边形</dt><dd>${int(c.cells)}</dd></div>
      <div><dt>地图已收录设施与资源</dt><dd>${int(list.length)}</dd></div></dl>
      ${list.length ? `<ul>${list.slice(0, 10).map((r) => `<li>${esc(r.name)}</li>`).join("")}</ul>` : ""}
      <p class="advisor-note">${esc(app.data.counties.note)}</p></article>`;
  }

  function setupOpen(params) {
    parent = params.city || null;
    query = "";
    currentCode = params.code || "";
    active = true;
    app.clearSelection();
    dock = app.ui.dock("right", { width: 385, label: "县级界面" });
    dock.dataset.counties = "";
    dock.innerHTML = `<header class="timeline-head"><h2>县级界面</h2>
      <button class="icon-btn" aria-label="关闭县级界面" data-close>✕</button></header>
      <div class="timeline-content">
        <div class="county-detail" aria-live="polite"></div>
        <div class="advisor-filters"><label>县区名称或区划代码<input type="search" data-query placeholder="例如 余杭区 或 330110"></label></div>
        ${parent ? `<p class="advisor-note" data-parent>当前范围 · ${esc(app.cityById.get(parent)?.name || "")}
          <button type="button" class="county-link" data-all>查看全部县区</button></p>` : ""}
        <div class="county-results"></div>
      </div>`;
    dock.onclick = (event) => {
      if (event.target.closest("[data-close]")) {
        app.setMode(null);
        button?.focus();
        return;
      }
      if (event.target.closest("[data-all]")) {
        parent = null;
        dock.querySelector("[data-parent]").remove();
        renderList();
      }
      const code = event.target.closest("[data-county]")?.dataset.county;
      if (code) select(countyById?.get(code));
      const city = event.target.closest("[data-city]")?.dataset.city;
      if (city) app.cityView.open(app.cityById.get(city));
    };
    dock.oninput = (event) => {
      if (!event.target.hasAttribute("data-query")) return;
      query = event.target.value.trim();
      renderList();
    };
    button?.setAttribute("aria-expanded", "true");
    renderDetail();
    renderList();
    load("counties").then(() => {
      if (!active) return;
      renderList();
      if (currentCode && !currentCode.startsWith("zone-")) select(countyById?.get(currentCode), !params.fromHash);
    });
    if (currentCode.startsWith("zone-")) load("zones").then(() => {
      if (active && currentCode.startsWith("zone-")) selectZone(zonesById?.get(currentCode.slice(5)), !params.fromHash);
    });
  }

  app.registerMode(MODE, {
    enter: setupOpen,
    exit() {
      active = false;
      chosen = zone = null;
      currentCode = "";
      delete dock.dataset.counties;
      dock.onclick = dock.oninput = null;
      app.ui.undock("right");
      button?.setAttribute("aria-expanded", "false");
    },
  });
  app.hash.register("county", {
    get: () => active ? currentCode || "all" : null,
    set(code) {
      if (!code && active) app.setMode(null);
      else if (code && code !== currentCode) open({ code: code === "all" ? "" : code, fromHash: true });
    },
  });
  app.countyBrowser = { open };

  function toggle(id, label, icon, file, title) {
    app.ui.addMapToggle({
      id, label, icon, title, default: false, get: () => enabled[id],
      set(on) {
        enabled[id] = on;
        if (on) load(file).then((data) => { if (!data) app.ui.toast(`${label}暂无数据`); });
        app.requestDraw();
      },
    });
  }
  toggle("counties", "县级边界", "▦", "counties", "放大后显示县级边界，点击打开县级界面");
  toggle("builtup", "建筑覆盖", "▤", "builtup", "GHSL 2020 年约 1 公里格网，放大后查看");
  for (const [id, kind] of Object.entries(kinds)) toggle(id, kind.label, "◇", "zones", "代表点，点击查看官方资料");

  app.registerStaticLayer({
    id: "county-boundaries", z: 59, visible: () => !!countyIndex && (active || enabled.counties),
    sig: () => chosen?.id || "",
    draw(ctx, vp, _w, opts) {
      if (opts.Rpx >= COUNTY_ZOOM) {
        ctx.strokeStyle = "rgba(251,227,169,.64)";
        ctx.lineWidth = 0.75 / vp.s;
        for (const c of countyIndex(vp)) if (c !== chosen) ctx.stroke(path(c));
      }
      if (!chosen || !visible(chosen.bounds, vp)) return;
      ctx.fillStyle = "rgba(255,207,103,.16)";
      ctx.fill(path(chosen), "evenodd");
      ctx.strokeStyle = "#ffdb89";
      ctx.lineWidth = 2.2 / vp.s;
      ctx.stroke(path(chosen));
    },
    hit: (x, y, rpx) => rpx >= COUNTY_ZOOM ? countyAt(x, y) : null,
    click(c) {
      if (app.mode && !active) return false;
      if (active) select(c, false);
      else open({ code: c.id });
      return true;
    },
    tooltip: (c) => `<b>${esc(c.name)}</b> · ${esc(c.id)}<br><span class="muted">${esc(prefecture(c) || province(c))}</span>`,
  });
  app.registerStaticLayer({
    id: "built-up-grids", z: 53, minRpx: 24, visible: () => enabled.builtup && !!builtIndex,
    draw(ctx, vp) {
      const colors = ["", "#d799588f", "#eda567aa", "#f4b574c0", "#ffcc8bda"];
      for (const [x, y, density] of builtIndex(vp)) {
        ctx.fillStyle = colors[Math.min(density, colors.length - 1)];
        ctx.fillRect(x - 0.41, y - 0.41, 0.82, 0.82);
      }
    },
  });
  for (const [id, style] of Object.entries(kinds)) {
    const list = () => [...(zonesById?.values() || [])].filter((z) => z.kind === id);
    app.registerStaticLayer({
      id: `zones-${id}`, z: id === "new-area" ? 93 : 94,
      visible: () => enabled[id] && !!zonesById,
      sig: () => zone?.id || "",
      draw(ctx, vp, _w, opts) {
        const radius = (opts.Rpx < 10 ? 4 : 5.5) / vp.s;
        ctx.fillStyle = style.color;
        ctx.strokeStyle = "#252015";
        ctx.lineWidth = 1.4 / vp.s;
        for (const z of list()) {
          if (!visible([z.x, z.y, z.x, z.y], vp)) continue;
          ctx.beginPath();
          if (style.shape === "diamond") {
            ctx.moveTo(z.x, z.y - radius); ctx.lineTo(z.x + radius, z.y);
            ctx.lineTo(z.x, z.y + radius); ctx.lineTo(z.x - radius, z.y);
            ctx.closePath();
          } else ctx.rect(z.x - radius, z.y - radius, radius * 2, radius * 2);
          ctx.fill();
          ctx.stroke();
          if (zone === z) {
            ctx.beginPath();
            ctx.arc(z.x, z.y, radius * 1.8, 0, Math.PI * 2);
            ctx.strokeStyle = "#fff1cb";
            ctx.stroke();
            ctx.strokeStyle = "#252015";
          }
        }
      },
      hit(x, y, rpx) {
        const size = 8 * app.w.grid.R / rpx;
        return list().find((z) => Math.hypot(x - z.x, y - z.y) < size) || null;
      },
      tooltip: (z) => `<b>${esc(z.name)}</b><br><span class="muted">${esc(z.place)} · 代表点</span>`,
      click(z) {
        if (app.mode && !active) return false;
        if (active) selectZone(z);
        else open({ code: `zone-${z.id}` });
        return true;
      },
    });
  }
  app.on("mapclick", (event) => {
    if (!active) return false;
    if (event.layer?.startsWith("zones-")) {
      selectZone(event.item);
      return true;
    }
    const c = countyAt(...app.cam.toWorld(event.x, event.y));
    if (c) select(c, false);
    return true;
  });
  app.on("data", ({ name }) => {
    if (active && chosen && (name === "wonders" || name === "infrastructure")) renderDetail();
  });
}
