"""Tile improvements (China): high-speed rail, conventional rail and expressways rasterised onto hex links, plus the
busiest airports and the principal ports as sites. docs/CN_PLAN.md §5.5, docs/DATA_CONTRACTS.md infrastructure.json.

Lines are never shipped as polylines. Each OpenStreetMap line of `cn_rail_roads` is projected to map km and sampled
every SAMPLE_KM along its length; each sample is mapped to its hex, repeats in a row are dropped, samples on foreign
land (owner -2) break the run, a cell whose neighbours on the line already touch is dropped (the line only clipped
its corner; this keeps a line along a row boundary from zigzagging), and every step between two cells becomes a link
between neighbouring cells (a step that skips cells is filled with a hex line walk). The browser draws a link as a
road or rail segment from hex centre to hex centre. A link needs at least one end on Chinese land (owner >= 0) and
neither end on foreign land, so the 1° buffer the source keeps around China is clipped here.

Rail tiers: 0 = 高速铁路, every OSM `highspeed=yes` line (the source's `hsr` list, ≥ 250 km/h or untagged, plus its
`rail` lines flagged `highspeed`, 200–249 km/h; China's own high-speed network statistics count lines from
200 km/h), 1 = 普速铁路 (other `usage=main` lines). Where both pass between the same two hexes, tier 0 wins. Road
class 0 = 高速公路 (`highway=motorway`). Link names: the expressway's route number (国家高速 G before 省级 S, then
fewer digits, then the lower number; the line name only when it has no number) and, for rail, the line name seen
most often on that link.

Airports (rule `AIRPORT_MIN_PASSENGERS`): every airport in the CAAC annual bulletin with at least 1,000,000
passengers that year, hub size by CAAC's own groups (L ≥ 10 million, M 2–10 million, S below 2 million). Ports
(rule `PORT_TOP_N`): the 30 largest of the Ministry of Transport's 主要港口 by cargo tonnage. Hong Kong, Macau and
Taiwan are not in either publisher's tables and are left out (not given zeros).

A site's `cell` is the Chinese land cell at its point, else the nearest within SITE_RINGS rings; `x`/`y` stay the
true position. `county` is the source's county adcode when the hex map knows it, else the county polygon at the
point (Locator); `cbsa` the cities.json id holding that county; `state` the province code.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim_payload, write_web
from .locate import Locator
from .phase2_stats import DATA, catalogue, read_curated

REQUIRES = ["_world", "cn_boundaries", "cn_rail_roads", "cn_transport_air", "cn_transport_ports", "cities.json"]
PRODUCES = ["infrastructure.json"]
LOCAL_INPUTS = [DATA / "hmt_transport.json"]

VERSION = 2  # China: passengers/cargo_t replace enplanements/tons
SAMPLE_KM = 4.0
SITE_RINGS = 2
FOREIGN = -2
AIRPORT_MIN_PASSENGERS = 1_000_000
HUB_L, HUB_M = 10_000_000, 2_000_000
PORT_TOP_N = 30
SOURCES = ["cn_rail_roads", "cn_transport_air", "cn_transport_ports", "cn_boundaries"]

ROAD_CLASSES = [{"id": "expressway", "name": "高速公路"}]
RAIL_TIERS = [{"id": "hsr", "name": "高速铁路"}, {"id": "rail", "name": "普速铁路"}]
HUBS = {"L": "年旅客吞吐量1000万人次以上", "M": "200万–1000万人次", "S": "200万人次以下"}
PORT_TYPES = {"coastal": "沿海港口", "inland": "内河港口"}

RULES = {
    "roads": "OpenStreetMap 中标注为 highway=motorway 的高速公路（不含匝道），每 4 公里取样一次并吸附到相邻六边形中心之间的"
             "连线；只保留至少一端在中国陆地、且两端都不在外国的连线。路线名优先取国家高速编号（G），其次省级高速（S），"
             "没有编号时取路名。OSM 由志愿者绘制，与交通运输部统计里程略有出入。",
    "rail": "OpenStreetMap 铁路，每 4 公里取样一次并吸附到相邻六边形中心之间的连线。高速铁路：所有标注 highspeed=yes 的"
            "线路（设计时速 250 公里及以上，以及 200–249 公里的快速线，与我国高铁统计口径一致）；普速铁路：其余标注"
            " usage=main 的干线铁路（不含支线、专用线和站场）。同一对六边形之间既有高铁又有普速铁路时按高铁显示。",
    "airports": "中国民用航空局年度《全国民用运输机场生产统计公报》中旅客吞吐量不少于 100 万人次的全部机场，按旅客吞吐量排序；"
                "规模分级沿用民航局分组：1000 万人次以上、200 万–1000 万人次、200 万人次以下。旅客吞吐量为进出港合计。"
                "香港、澳门、台湾地区机场不在民航局公报范围内，暂未列入。",
    "ports": f"交通运输部年度《全国港口货物、集装箱吞吐量》所列全国主要港口中货物吞吐量最大的 {PORT_TOP_N} 个，按货物吞吐量排序；"
             "位置取主要港区所在区县（或地级市）的政府驻地，港口群只标一个点，属近似位置。香港、澳门、台湾地区港口不在交通"
             "运输部统计范围内，暂未列入。",
}


# ------------------------------------------------------------------ hex helpers


def _axial(grid: HexGrid, cell: int) -> tuple[int, int]:
    col, row = grid.col_row(cell)
    return col - (row - (row & 1)) // 2, row


def _from_axial(grid: HexGrid, q: int, r: int) -> int:
    col = q + (r - (r & 1)) // 2
    if 0 <= col < grid.cols and 0 <= r < grid.rows:
        return grid.index(col, r)
    return -1


def hex_distance(grid: HexGrid, a: int, b: int) -> int:
    (q1, r1), (q2, r2) = _axial(grid, a), _axial(grid, b)
    return (abs(q1 - q2) + abs(r1 - r2) + abs((q1 + r1) - (q2 + r2))) // 2


def hex_walk(grid: HexGrid, a: int, b: int) -> list[int]:
    """Cells on the hex line from a to b, both included (cube lerp with a tiny nudge to break ties)."""
    n = hex_distance(grid, a, b)
    if n <= 1:
        return [a, b] if a != b else [a]
    (q1, r1), (q2, r2) = _axial(grid, a), _axial(grid, b)
    out = []
    for i in range(n + 1):
        t = i / n
        x = q1 + (q2 - q1) * t + 1e-6
        z = r1 + (r2 - r1) * t + 1e-6
        y = -x - z
        rx, ry, rz = round(x), round(y), round(z)
        dx, dy, dz = abs(rx - x), abs(ry - y), abs(rz - z)
        if dx > dy and dx > dz:
            rx = -ry - rz
        elif dy <= dz:
            rz = -rx - ry
        c = _from_axial(grid, rx, rz)
        if c >= 0 and (not out or out[-1] != c):
            out.append(c)
    return out


def sample_cells(grid: HexGrid, pts: list[tuple[float, float]], keep=None) -> list[list[int]]:
    """Runs of distinct consecutive cells along a projected line, sampled every SAMPLE_KM. `keep(cell)` False
    breaks the run (the sample is dropped)."""
    runs, run = [], []

    def add(x, y):
        nonlocal run
        c = grid.cell_at(x, y)
        if c < 0 or (keep is not None and not keep(c)):
            if len(run) > 1:
                runs.append(run)
            run = []
            return
        if not run or run[-1] != c:
            run.append(c)

    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        steps = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / SAMPLE_KM))
        for i in range(steps):
            t = i / steps
            add(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
    if pts:
        add(*pts[-1])
    if len(run) > 1:
        runs.append(run)
    return runs


def straighten(grid: HexGrid, run: list[int]) -> list[int]:
    """Drop detour cells: where the cells before and after a cell are neighbours themselves, the line only clipped
    that cell's corner. Without this, a line running along a row boundary zigzags between two rows."""
    out = []
    for c in run:
        while len(out) >= 2 and c in grid.neighbours(out[-2]):
            out.pop()
        if not out or out[-1] != c:
            out.append(c)
    return out


def links_of(grid: HexGrid, run: list[int]) -> list[tuple[int, int]]:
    out = []
    run = straighten(grid, [c for path in ([run[0]], *(hex_walk(grid, a, b)[1:] for a, b in zip(run, run[1:])))
                            for c in path])
    for a, b in zip(run, run[1:]):
        path = hex_walk(grid, a, b)
        for u, v in zip(path, path[1:]):
            if u != v:
                out.append((u, v) if u < v else (v, u))
    return out


# ------------------------------------------------------------------ roads and rail


def route_key(ref: str) -> tuple:
    """Sort key for expressway numbers: G before S, fewer digits first, then the number."""
    head = ref[:1].upper()
    digits = "".join(ch for ch in ref if ch.isdigit())
    return ({"G": 0, "S": 1}.get(head, 2), len(digits) or 9, int(digits) if digits else 9999, ref)


def _clean(s) -> str | None:
    s = (s or "").strip() if isinstance(s, str) else None
    return s or None


def road_label(f: dict) -> str | None:
    """Route number of an expressway line (first of a `;` list by route_key), else its name."""
    ref = _clean(f.get("ref"))
    if ref:
        refs = [r.strip() for r in ref.replace("；", ";").split(";") if r.strip()]
        if refs:
            return min(refs, key=route_key)
    return _clean(f.get("name"))


def rasterise(grid: HexGrid, proj, owner: list[int], features, cls_of_feature, label_of_feature, name_key):
    """Links [a, b, class, name] for a family of lines; lower class wins per pair, names of the winning class
    are counted and the best (by name_key) is kept."""
    n = len(owner)
    best: dict[tuple[int, int], int] = {}
    names: dict[tuple[int, int], Counter] = defaultdict(Counter)

    def keep(c):
        return owner[c] != FOREIGN

    for f in features:
        cls = cls_of_feature(f)
        if cls is None:
            continue
        name = label_of_feature(f)
        pts = [proj(lon, lat) for lon, lat in f["line"]]
        for run in sample_cells(grid, pts, keep):
            for a, b in links_of(grid, run):
                if not (0 <= a < n and 0 <= b < n):
                    continue
                if owner[a] == FOREIGN or owner[b] == FOREIGN or (owner[a] < 0 and owner[b] < 0):
                    continue
                cur = best.get((a, b))
                if cur is None or cls < cur:
                    best[(a, b)] = cls
                    names[(a, b)].clear()
                    cur = cls
                if cls == cur and name:
                    names[(a, b)][name] += 1
    out = []
    for (a, b), cls in sorted(best.items()):
        cnt = names.get((a, b))
        out.append([a, b, cls, min(cnt, key=lambda k: name_key(k, cnt)) if cnt else None])
    return out


def build_roads(grid, proj, owner, data) -> list:
    return rasterise(grid, proj, owner, data.get("expressway") or [], lambda f: 0, road_label,
                     lambda k, cnt: route_key(k))


def rail_tier(f: dict) -> int:
    return 0 if f.get("_hsr") or f.get("highspeed") else 1


def build_rail(grid, proj, owner, data) -> list:
    feats = [dict(f, _hsr=True) for f in data.get("hsr") or []] + list(data.get("rail") or [])
    return rasterise(grid, proj, owner, feats, rail_tier, lambda f: _clean(f.get("name")),
                     lambda k, cnt: (-cnt[k], len(k), k))


# ------------------------------------------------------------------ sites


def _num(v):
    if v is None or isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return int(v) if float(v).is_integer() else round(float(v), 1)


def site_at(loc: Locator, lon, lat, county=None, province=None) -> dict | None:
    """x/y/cell/county/cbsa/state for a lon/lat point, or None when no Chinese land cell is near."""
    if lon is None or lat is None:
        return None
    x, y, cell = loc.place(lon, lat, rings=SITE_RINGS)
    if cell < 0:
        return None
    known = set(loc.world["counties"])
    if county not in known:
        county = loc.county_at(x, y, cell)
        if county not in known:
            county = None
    return {"x": round(x, 1), "y": round(y, 1), "cell": cell, "county": county, "cbsa": loc.city_of(county),
            "state": loc.province_of(county, cell, province)}


def hub_class(passengers) -> str | None:
    if passengers is None:
        return None
    return "L" if passengers >= HUB_L else "M" if passengers >= HUB_M else "S"


def build_airports(loc: Locator, air: dict, dropped: list) -> list[dict]:
    year = air.get("year")
    out = []
    for a in air["airports"]:
        p = a.get("passengers")
        if p is None or p < AIRPORT_MIN_PASSENGERS:
            continue
        at = site_at(loc, a.get("lon"), a.get("lat"), a.get("county"), a.get("province"))
        aid = a.get("iata") or a.get("icao")
        if at is None or not aid:
            dropped.append(f"机场 {a.get('name')}")
            continue
        out.append({"id": aid, "name": a["name"], "city": a.get("city"), "hub": hub_class(p),
                    "passengers": _num(p), "passengers_prev": _num(a.get("passengers_prev")),
                    "cargo_t": _num(a.get("cargo_t")), "movements": _num(a.get("movements")), "year": year,
                    "rank": a.get("rank"), **at})
    out.sort(key=lambda s: (-(s["passengers"] or 0), s["id"]))
    return out


def build_ports(loc: Locator, ports: dict, dropped: list) -> list[dict]:
    year = ports.get("year")
    ranked = sorted((p for p in ports["ports"] if p.get("cargo_t") is not None), key=lambda p: -p["cargo_t"])
    out = []
    for i, p in enumerate(ranked[:PORT_TOP_N]):
        at = site_at(loc, p.get("lon"), p.get("lat"), p.get("county"), p.get("province"))
        if at is None:
            dropped.append(f"港口 {p.get('name')}")
            continue
        out.append({"id": p["id"], "name": p["name"], "label": p.get("label"), "type": p.get("kind"),
                    "rank": p.get("rank") or i + 1, "cargo_t": _num(p["cargo_t"]), "foreign_t": _num(p.get("foreign_t")),
                    "teu": _num(p.get("teu")), "year": year, **at})
    out.sort(key=lambda s: s["rank"])
    return out


def add_hmt_sites(doc, loc, data, dropped):
    """Add locally reported sites without combining their ranks with the mainland lists."""
    for key, metric in (("airports", "passengers"), ("ports", "cargo_t")):
        rows = {row["id"]: row for row in doc[key] if not row.get("publisher")}
        for place in data.get(key, []):
            at = site_at(loc, place["lon"], place["lat"], province=place["state"])
            if at is None:
                dropped.append(place["name"])
                continue
            at["cbsa"] = place.get("cbsa")
            fields = {k: place[k] for k in ("id", "name", "year", "publisher", "source", "position_source",
                                           "cargo_source", "notes", "city") if k in place}
            site = {**fields, **at, "rank": None}
            if key == "airports":
                site.update(hub=hub_class(place.get("passengers")), passengers=place.get("passengers"),
                            passengers_prev=place.get("passengers_prev"), cargo_t=place.get("cargo_t"),
                            movements=place.get("movements"))
            else:
                site.update(type="coastal", label=place["name"], cargo_t=place.get("cargo_t"), foreign_t=place.get("foreign_t"),
                            teu=place.get("teu"), container_cargo_t=place.get("container_cargo_t"))
            rows[site["id"]] = site
        doc[key] = sorted(rows.values(), key=lambda row: (-(row.get(metric) or 0), row["id"]))
    if data.get("airports") and data.get("ports") and "rules" in doc:
        doc["sources"] = list(dict.fromkeys([*doc["sources"], "hmt_transport"]))
        doc["rules"] = {
            **doc["rules"],
            "airports": "内地使用中国民用航空局年度公报，收录旅客吞吐量至少 100 万人次的机场。港澳台使用当地官方统计或机场管理机构年报，另列数据来源。",
            "ports": "内地使用交通运输部年度统计，收录货物吞吐量前 30 的主要港口。港澳台使用当地港口统计，按原口径列示。澳门集装箱货运重量单列。",
        }


def add_hmt_sources(sources):
    data = read_curated("hmt_transport.json")
    links = {(row["publisher"], row["source"]) for key in ("airports", "ports") for row in data.get(key, [])}
    links.update((row["publisher"] + " · 货运", row["cargo_source"])
                 for row in data.get("airports", []) if row.get("cargo_source"))
    if links:
        catalogue(sources, "hmt_transport", "港澳台机场与港口统计", "港澳台交通及统计机构",
                  "2025 年官方机场和港口统计，各地原始口径见标记详情。", links, ["infrastructure"], year=2025)


def refresh_hmt():
    def read(name):
        return json.loads((WEB_DATA / f"{name}.json").read_bytes())

    world, cities, doc, sources = (read(name) for name in ("world", "cities", "infrastructure", "sources"))
    county_to_city = {code: row["id"] for row in cities for code in row["counties"]}
    codes = [c["geoid"] for c in world["counties"]]
    published_world = {**world, "states": [s["fips"] for s in world["states"]], "counties": codes,
                       "county_prefecture": [county_to_city.get(code) for code in codes]}
    loc = Locator(published_world, with_counties=False, cities=cities)
    dropped = []
    add_hmt_sites(doc, loc, read_curated("hmt_transport.json"), dropped)
    if dropped:
        raise ValueError(f"Could not place supplemental sites: {dropped}")
    add_hmt_sources(sources)
    write_web("infrastructure.json", doc)
    write_web("sources.json", sources)


# ------------------------------------------------------------------ build


def build() -> None:
    loc = Locator()
    if not loc.cities:
        print("    WARNING: web/data/cities.json missing or empty; every site gets cbsa null")
    grid, proj, owner = loc.grid, loc.proj, loc.owner

    rr = load_interim_payload("cn_rail_roads")
    air = load_interim_payload("cn_transport_air")
    prt = load_interim_payload("cn_transport_ports")
    roads = build_roads(grid, proj, owner, rr["data"])
    rail = build_rail(grid, proj, owner, rr["data"])

    dropped: list[str] = []
    airports = build_airports(loc, air["data"], dropped)
    ports = build_ports(loc, prt["data"], dropped)
    doc = {
        "version": VERSION,
        "vintage": {"roads": rr["vintage"], "rail": rr["vintage"], "ports": prt["vintage"], "airports": air["vintage"]},
        "sources": SOURCES,
        "rules": RULES,
        "notes": {"airports": air["data"].get("extra_note"), "ports": prt["data"].get("extra_note")},
        "units": {"passengers": "人次", "cargo_t": "吨", "foreign_t": "吨", "teu": "标准箱（TEU）", "movements": "架次"},
        "road_classes": ROAD_CLASSES,
        "rail_tiers": RAIL_TIERS,
        "hubs": HUBS,
        "port_types": PORT_TYPES,
        "roads": roads,
        "rail": rail,
        "ports": ports,
        "airports": airports,
    }
    add_hmt_sites(doc, loc, read_curated("hmt_transport.json"), dropped)
    airports, ports = doc["airports"], doc["ports"]
    if dropped:
        print(f"    WARNING: no Chinese land cell near {len(dropped)} sites: {dropped}")
    write_web("infrastructure.json", doc)
    land = sum(1 for o in owner if o >= 0)
    road_cells = {c for a, b, *_ in roads for c in (a, b) if owner[c] >= 0}
    rail_cells = {c for a, b, *_ in rail for c in (a, b) if owner[c] >= 0}
    n_hsr = sum(1 for r in rail if r[2] == 0)
    print(f"    expressways: {len(roads)} links on {len(road_cells)} of {land} land hexes; rail: {n_hsr} HSR + "
          f"{len(rail) - n_hsr} conventional links on {len(rail_cells)} hexes; {len(ports)} ports, "
          f"{len(airports)} airports")


# ------------------------------------------------------------------ check


def check(web_dir: Path) -> list[tuple[str, str]]:
    path = Path(web_dir) / "infrastructure.json"
    if not path.exists():
        return [("NOTE", "infrastructure.json not built (optional; run: build infrastructure)")]
    out = []
    doc = json.loads(path.read_text())
    for k in ("version", "vintage", "sources", "rules", "road_classes", "rail_tiers", "hubs", "roads", "rail",
              "ports", "airports"):
        if k not in doc:
            out.append(("FAIL", f"infrastructure.json lacks '{k}'"))
    if any(lv == "FAIL" for lv, _ in out):
        return out
    if doc["version"] != VERSION:
        out.append(("FAIL", f"infrastructure.json version {doc['version']!r} (expected {VERSION})"))
    if [t.get("id") for t in doc["rail_tiers"]] != ["hsr", "rail"]:
        out.append(("FAIL", "infrastructure.json rail_tiers must be [hsr, rail]"))
    for key in ("roads", "rail", "ports", "airports"):
        if not isinstance(doc["rules"].get(key), str) or not doc["rules"][key]:
            out.append(("FAIL", f"infrastructure.json rules.{key} missing"))
    wpath = Path(web_dir) / "world.json"
    world = json.loads(wpath.read_text()) if wpath.exists() else None
    if not world or "grid" not in world:
        return out + [("NOTE", "infrastructure.json: world.json unavailable, cell checks skipped")]
    g = world["grid"]
    grid = HexGrid(g["radius"], g["cols"], g["rows"])
    owner = world.get("owner") or []
    n = grid.size
    county_ids = {c["geoid"] for c in world.get("counties", [])}
    codes = {s["fips"] for s in world.get("states", []) if isinstance(s, dict)}
    cpath = Path(web_dir) / "cities.json"
    city_ids = {c["id"] for c in json.loads(cpath.read_text())} if cpath.exists() else None
    spath = Path(web_dir) / "sources.json"
    if spath.exists():
        src = json.loads(spath.read_text())
        rows = src.get("sources", src) if isinstance(src, dict) else src
        ids = {s["id"] for s in rows if isinstance(s, dict) and "id" in s}
        miss = [s for s in doc["sources"] if s not in ids]
        if ids and miss:
            out.append(("WARN", f"infrastructure.json cites sources missing from sources.json: {miss}"))

    def bad_link(link, ncls):
        if not isinstance(link, list) or len(link) != 4:
            return "shape"
        a, b, c, name = link
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (a, b, c)):
            return "types"
        if not (0 <= a < b < n):
            return "order/range"
        if b not in grid.neighbours(a):
            return "not neighbours"
        if len(owner) == n and (owner[a] == FOREIGN or owner[b] == FOREIGN):
            return "foreign end"
        if len(owner) == n and owner[a] < 0 and owner[b] < 0:
            return "no Chinese land end"
        if not 0 <= c < ncls:
            return "class"
        if not (name is None or (isinstance(name, str) and name)):
            return "name"
        return None

    for key, ncls in (("roads", len(doc["road_classes"])), ("rail", len(doc["rail_tiers"]))):
        links = doc[key]
        bad = [(l, why) for l in links if (why := bad_link(l, ncls))]
        pairs = [tuple(l[:2]) for l in links if isinstance(l, list)]
        dup = len(pairs) - len(set(pairs))
        if bad or dup:
            out.append(("FAIL", f"infrastructure.json {key}: {len(bad)} bad links (e.g. {bad[:2]}), {dup} duplicates"))
        elif not links:
            out.append(("WARN", f"infrastructure.json {key}: no links"))
        else:
            cells = {c for l in links for c in l[:2]}
            per = Counter(l[2] for l in links)
            out.append(("PASS", f"infrastructure.json {key}: {len(links)} neighbour links on {len(cells)} hexes "
                                f"(by class {dict(sorted(per.items()))})"))

    def check_sites(key, num_keys, metric):
        probs = []
        for s in doc[key]:
            c = s.get("cell")
            if not isinstance(c, int) or not 0 <= c < n or (len(owner) == n and owner[c] < 0):
                probs.append(f"{s.get('id')}: cell {c!r} is not Chinese land")
                continue
            for k in num_keys:
                v = s.get(k)
                if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0):
                    probs.append(f"{s.get('id')}: bad {k} {v!r}")
            if s.get(metric) is None and not (key == "ports" and s.get("publisher") and s.get("teu") is not None):
                probs.append(f"{s.get('id')}: {metric} null (selection metric)")
            cx, cy = grid.center(*grid.col_row(c))
            if not all(isinstance(s.get(k), (int, float)) for k in ("x", "y")) or \
                    math.dist((cx, cy), (s["x"], s["y"])) > (SITE_RINGS + 1) * g["radius"] * 2:
                probs.append(f"{s.get('id')}: x/y far from its cell")
            if s.get("county") is not None and county_ids and s["county"] not in county_ids:
                probs.append(f"{s.get('id')}: unknown county {s['county']}")
            if s.get("cbsa") is not None and city_ids is not None and s["cbsa"] not in city_ids:
                probs.append(f"{s.get('id')}: unknown cbsa {s['cbsa']}")
            if codes and s.get("state") not in codes:
                probs.append(f"{s.get('id')}: state {s.get('state')!r} is not a province code")
        ids = [s.get("id") for s in doc[key]]
        if len(ids) != len(set(ids)):
            probs.append("duplicate ids")
        vals = [s.get(metric) or 0 for s in doc[key]]
        if vals != sorted(vals, reverse=True):
            probs.append(f"not sorted by {metric}")
        return probs

    for key, nums, metric in (("ports", ("cargo_t", "foreign_t", "teu", "rank", "container_cargo_t"), "cargo_t"),
                              ("airports", ("passengers", "passengers_prev", "cargo_t", "movements"), "passengers")):
        probs = check_sites(key, nums, metric)
        if probs:
            out.append(("FAIL", f"infrastructure.json {key}: {len(probs)} problems, e.g. {probs[:3]}"))
        elif not doc[key]:
            out.append(("WARN", f"infrastructure.json {key}: empty"))
        else:
            metro = sum(1 for s in doc[key] if s.get("cbsa"))
            out.append(("PASS", f"infrastructure.json {key}: {len(doc[key])} sites, {metro} in a mapped city"))
    if any(a.get("passengers") is not None and a["passengers"] < AIRPORT_MIN_PASSENGERS for a in doc["airports"]):
        out.append(("FAIL", f"infrastructure.json airports: an airport below the {AIRPORT_MIN_PASSENGERS:,} rule"))
    if sum(not p.get("publisher") for p in doc["ports"]) > PORT_TOP_N:
        out.append(("FAIL", f"infrastructure.json ports: more than the top {PORT_TOP_N}"))
    if any(a.get("hub") not in doc["hubs"] for a in doc["airports"]):
        out.append(("FAIL", "infrastructure.json airports: hub not in hubs"))
    hubs = Counter(a.get("hub") for a in doc["airports"])
    out.append(("NOTE", "infrastructure.json airports by hub: " +
                ", ".join(f"{k} {v}" for k, v in sorted(hubs.items(), key=lambda kv: str(kv[0])))))
    size = path.stat().st_size
    if size > 300_000:
        out.append(("WARN", f"infrastructure.json is {size / 1e3:.0f} kB (eager files should stay under ~300 kB)"))
    return out
