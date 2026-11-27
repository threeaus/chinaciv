"""Cities = prefecture-level divisions (地级市/地区/自治州/盟), the 4 municipalities, 香港, 澳门 and the six largest
Taiwan cities: one banner each (docs/CN_PLAN.md §3, §5.2). Writes cities.json and nation.json.

* Rows: `cn_boundaries.prefectures` whose kind is in `core.china.BANNER_KINDS`, minus 三沙 (460300, no land hex;
  a labelled point instead). 省直辖县级行政区 are counties, not banners. id = 6-digit adcode (municipality / SAR =
  the province adcode; Taiwan cities use the project-assigned ids 710100–710600).
* Position: the seat of government (DataV `center`; Wikidata for Taiwan cities), projected to map km.
* Banner cell: a Chinese land cell (owner >= 0), unique where possible. The SARs go first (their forced seat hexes),
  then the other cities by size (the stats-year population, else the 2020 census population, so a city whose 2023
  figure is unread still chooses before its smaller neighbours). A seat on water/abroad snaps to the nearest
  Chinese land cell (own province preferred); a seat in another province's hex is pulled back into the own province
  when a free cell is within 2 rings; a taken cell moves to the nearest free cell within 2 rings (own province
  preferred), else the cell is shared.
* Footprint: Chinese land cells where ≥ 4 of 7 county samples map (via `_world.county_prefecture`) to the city;
  municipalities and SARs: every cell of their province; Taiwan cities (no counties in DataV): their own cell. The
  own cell is always included.
* Economy (cn_stats_city: 七普 2020 + the 2023 统计公报; cn_city_industry: employment by industry, R&D): population and
  GDP only of the stats year (else null, no older year substituted); yields per build/yields.py (§5.3); growth per
  build/growth.py (nulled for the SCOPE_CHANGES cities, whose 2023 bulletins count a narrower area than the census).
* Sort order: population desc, nulls last; ties and nulls ordered by the 2020 census population desc, then id (so
  the banner placement order is still roughly by size where a 2023 figure is missing).
* capital: 北京 (110000) only (the national capital). province_capital: the seat of a province's / autonomous
  region's government (省会/首府; 台湾省: 台北 as on the standard map); `capital_label` 首都/省会/首府 or null.
* ranks: over all cities, 1 = highest, null where the value is null (population, gdp, gdp_per_capita, growth, each
  yield). The population rank uses the stats-year population where present, else the 2020 census population
  (cities without a 2023 figure would otherwise drop out and push the ranks of smaller cities up). peers: the 5 cities closest by 2020 census population (|log ratio|; one same-year count for every city);
  a city without a census figure (the Taiwan cities) takes the nearest cities of its own province first (by
  distance), i.e. the other five Taiwan cities.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from ..core import china
from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web
from . import growth
from .yields import YIELD_KEYS, choose_bases, coverage, yield_defs, yields_of
from .phase2_stats import (DATA, apply_census_definitions, apply_employment, census, employment_yields,
                           population_sources, supplement_city)

REQUIRES = ["_world", "cn_boundaries", "cn_stats_city", "cn_city_industry"]
PRODUCES = ["cities.json", "nation.json"]
LOCAL_INPUTS = [DATA / "population_2023.json", DATA / "economic_census_employment.json"]

SANSHA = "460300"  # 三沙市: no land hex, no banner (CN_PLAN §3.1)
# 省会 / 首府 (seat of the provincial-level government) of each province and autonomous region; 民政部 行政区划.
PROVINCE_CAPITALS = {
    "13": "130100", "14": "140100", "15": "150100", "21": "210100", "22": "220100", "23": "230100",
    "32": "320100", "33": "330100", "34": "340100", "35": "350100", "36": "360100", "37": "370100",
    "41": "410100", "42": "420100", "43": "430100", "44": "440100", "45": "450100", "46": "460100",
    "51": "510100", "52": "520100", "53": "530100", "54": "540100", "61": "610100", "62": "620100",
    "63": "630100", "64": "640100", "65": "650100", "71": "710100",
}
# Cities whose 2023 bulletin counts its population on a narrower area than the 2020 census (the managing new area is
# reported separately), so population / census − 1 measures the change of scope, not of people: growth is nulled
# and the reason added to `note`. Found by the |growth| > 15% screen printed at build time.
SCOPE_CHANGES = {
    "130600": "保定市 2023 年公报常住人口不含雄安新区（容城、安新、雄县）等单独统计的区域，与七普口径不同，人口增长率置空。",
    "610400": "咸阳市 2023 年公报常住人口不含由西咸新区托管的区域，与七普口径不同，人口增长率置空。",
}
SCREEN_GROWTH = 0.15  # |growth| above this is printed for review (real 2020–2023 changes stay within ±11%)
FOOTPRINT_MAJORITY = 4  # of a cell's 7 county samples
PEERS = 5
RANK_KEYS = ["population", "gdp", "gdp_per_capita", "growth"] + YIELD_KEYS
SCOPE = "全国数据为 31 个省、自治区、直辖市合计，不含香港、澳门和台湾"


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# --- cells ------------------------------------------------------------------------------------------------------


def ring_search(grid: HexGrid, start: int, max_rings: int):
    """Yield (ring, cell) for every cell within `max_rings` steps of `start`, nearest rings first."""
    seen = {start}
    frontier = [start]
    yield 0, start
    for ring in range(1, max_rings + 1):
        nxt = []
        for c in frontier:
            for n in grid.neighbours(c):
                if n not in seen:
                    seen.add(n)
                    nxt.append(n)
                    yield ring, n
        frontier = nxt


def nearest_land(grid: HexGrid, owner: list[int], cell: int, x: float, y: float, state: int, max_rings=8):
    """Nearest Chinese land cell to (x, y), preferring province index `state`: the first ring with land, plus one."""
    found_ring = None
    best = None
    for ring, c in ring_search(grid, cell, max_rings):
        if found_ring is not None and ring > found_ring + 1:
            break
        if owner[c] < 0:
            continue
        found_ring = ring if found_ring is None else found_ring
        cx, cy = grid.center(*grid.col_row(c))
        score = (owner[c] != state, math.hypot(cx - x, cy - y))
        if best is None or score < best[0]:
            best = (score, c)
    return best[1] if best else -1


def free_cell(grid: HexGrid, owner, taken: set, cell: int, x: float, y: float, state: int, max_rings=2):
    """Nearest untaken Chinese land cell within `max_rings`, preferring `state`; None if there is none."""
    best = None
    for ring, c in ring_search(grid, cell, max_rings):
        if owner[c] < 0 or c in taken:
            continue
        cx, cy = grid.center(*grid.col_row(c))
        score = (owner[c] != state, math.hypot(cx - x, cy - y))
        if best is None or score < best[0]:
            best = (score, c)
    return best[1] if best else None


def place_banners(cities: list[dict], grid: HexGrid, owner: list[int], state_index: dict) -> dict[str, list[str]]:
    """Set each city's `cell` (see module doc); SARs first, then list order. Returns {event: [names]}."""
    log = {"snapped": [], "pulled": [], "moved": [], "shared": []}
    taken: set[int] = set()
    def size(c):  # placement priority: the stats-year population, else the 2020 census (else last)
        return c["population"] if c["population"] is not None else (c["pop_census_2020"] or 0)

    order = sorted(range(len(cities)), key=lambda i: (cities[i]["kind"] != "sar", -size(cities[i]), i))
    for i in order:
        c = cities[i]
        state = state_index.get(c["states"][0], -1)
        cell = grid.cell_at(c["x"], c["y"])
        if cell < 0 or owner[cell] < 0:
            cell = nearest_land(grid, owner, max(cell, 0), c["x"], c["y"], state)
            log["snapped"].append(c["name"])
        elif owner[cell] != state:
            alt = free_cell(grid, owner, taken, cell, c["x"], c["y"], state)
            if alt is not None and owner[alt] == state:
                cell = alt
                log["pulled"].append(c["name"])
        if cell in taken:
            alt = free_cell(grid, owner, taken, cell, c["x"], c["y"], state)
            if alt is None:
                log["shared"].append(c["name"])
            else:
                cell = alt
                log["moved"].append(c["name"])
        taken.add(cell)
        c["cell"] = cell
    return log


def footprints(world: dict) -> dict[str, set[int]]:
    """prefecture adcode → Chinese land cells where ≥ FOOTPRINT_MAJORITY of the 7 county samples are its counties."""
    pref = world["county_prefecture"]
    owner = world["owner"]
    out: dict[str, set[int]] = {}
    for cell, s in enumerate(world["county_samples"]):
        if not s or owner[cell] < 0:
            continue
        votes: dict[str, int] = {}
        for k in s:
            if k >= 0:
                votes[pref[k]] = votes.get(pref[k], 0) + 1
        for code, n in votes.items():
            if n >= FOOTPRINT_MAJORITY:
                out.setdefault(code, set()).add(cell)
    return out


# --- economy ----------------------------------------------------------------------------------------------------


def economy(stats: dict | None, ind: dict | None, bases: dict, year: int, window: list | None) -> dict:
    """The economic shape shared by a city, a province and the nation (CN_PLAN §5.2)."""
    stats, ind = stats or {}, ind or {}
    pop = stats.get("pop") if stats.get("pop_year") == year and _is_num(stats.get("pop")) else None
    gdp = stats.get("gdp") if stats.get("gdp_year") == year and _is_num(stats.get("gdp")) else None
    census = stats.get("pop_census") if _is_num(stats.get("pop_census")) else None
    emp = ind.get("emp") or {}
    va = {k: stats.get(f"va_{k}") for k in ("primary", "secondary", "tertiary")}
    g = growth.rate(pop, census)
    return {
        "population": pop,
        "population_year": year if pop is not None else None,
        "pop_census_2020": census,
        "employed": ind.get("emp_total") if _is_num(ind.get("emp_total")) else None,
        "yields": yields_of(bases, stats, ind, year),
        "jobs": dict(emp) if any(_is_num(v) for v in emp.values()) else None,
        "gdp": gdp,
        "gdp_year": year if gdp is not None else None,
        "currency": "CNY",
        "gdp_by_industry": va if gdp is not None and all(_is_num(v) for v in va.values()) else None,
        "growth": g,
        "growth_years": window,
    }


def add_ranks(cities: list[dict]) -> None:
    """ranks: 1 = highest among all cities, null where the value is null (cities are in file order, so ties keep
    it). peers: see the module doc."""
    def value(c, key):
        if key == "gdp_per_capita":
            return c["gdp"] / c["population"] if c.get("gdp") is not None and c.get("population") else None
        if key == "population":  # stats-year population, else the 2020 census, so every city takes its place
            return c["population"] if c.get("population") is not None else c.get("pop_census_2020")
        if key in ("gdp", "growth"):
            return c.get(key)
        return c["yields"].get(key)

    for c in cities:
        c["ranks"] = {}
    for key in RANK_KEYS:
        have = [c for c in cities if value(c, key) is not None]
        have.sort(key=lambda c: -value(c, key))  # stable
        for r, c in enumerate(have, 1):
            c["ranks"][key] = r
        for c in cities:
            c["ranks"].setdefault(key, None)
    for i, c in enumerate(cities):
        p = c.get("pop_census_2020")
        if p:
            lp = math.log(p)
            near = sorted((abs(math.log(o["pop_census_2020"]) - lp), j)
                          for j, o in enumerate(cities) if j != i and o.get("pop_census_2020"))
        else:
            near = sorted((o["states"] != c["states"], math.hypot(o["x"] - c["x"], o["y"] - c["y"]), j)
                          for j, o in enumerate(cities) if j != i)
            near = [(None, j) for *_, j in near]
        c["peers"] = [cities[j]["id"] for _, j in near[:PEERS]]


def capital_label(cid: str, province: str) -> str | None:
    if cid == china.CAPITAL_CITY:
        return "首都"
    if PROVINCE_CAPITALS.get(province) == cid:
        return "首府" if china.PROVINCES[province][3] == "autonomous_region" else "省会"
    return None


def banner_ids(bounds: dict) -> list[str]:
    return sorted(p["adcode"] for p in bounds["prefectures"] if p["kind"] in china.BANNER_KINDS and p["adcode"] != SANSHA)


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("cn_boundaries")
    stats_payload = load_interim_payload("cn_stats_city")
    stats = stats_payload["data"]
    ind_payload = load_interim_payload("cn_city_industry")
    ind = ind_payload["data"]
    proj = MapProjection(**world["projection"])
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    year = stats["year"]
    state_index = {code: i for i, code in enumerate(world["states"])}

    ids = banner_ids(bounds)
    bases = choose_bases(stats, ind, ids)
    window = growth.window(year)
    prefs = {p["adcode"]: p for p in bounds["prefectures"]}
    populations, employment = population_sources(), census()

    cities = []
    no_seat = []
    for cid in ids:
        p = prefs[cid]
        if not p.get("seat"):
            no_seat.append(p["name"])
            continue
        province = p["province"]
        srec, irec = stats["cities"].get(cid), ind["cities"].get(cid)
        x, y = proj(*p["seat"])
        label = capital_label(cid, province)
        notes = []
        inote = (irec or {}).get("note")
        for n in ((srec or {}).get("note"), inote and "分行业就业人员与 R&D 经费：" + inote, SCOPE_CHANGES.get(cid)):
            n = (n or "").strip().rstrip("；;。")
            if n and n not in notes:
                notes.append(n)
        cities.append({
            "id": cid,
            "name": p["short"],
            "full": p["name"],
            "kind": p["kind"],
            "kind_label": china.PREFECTURE_KIND_LABEL[p["kind"]],
            "states": [province],
            "metro": True,
            "capital": cid == china.CAPITAL_CITY,
            "province_capital": label in ("省会", "首府"),
            "capital_label": label,
            "x": round(x, 1),
            "y": round(y, 1),
            "cell": -1,
            **economy(srec, irec, bases, year, window),
            "counties": sorted(p.get("counties") or []),
            "_scope_change": cid in SCOPE_CHANGES,
            "note": "".join(n + "。" for n in notes) or None,
        })
    for c in cities:
        scope_changed = c.pop("_scope_change")
        supplement_city(c, populations, employment, not scope_changed)
        if scope_changed:
            c["growth"] = None
    screen = [f"{c['name']} {c['growth']:+.1%}" for c in cities if c["growth"] is not None and abs(c["growth"]) > SCREEN_GROWTH]
    if screen:
        print(f"    review: |growth| > {SCREEN_GROWTH:.0%} (scope change?): {', '.join(screen)}")
    cities.sort(key=lambda c: (c["population"] is None, -(c["population"] or 0),
                               -(c["pop_census_2020"] or 0), c["id"]))

    log = place_banners(cities, grid, owner, state_index)

    feet = footprints(world)
    province_cells: dict[int, set[int]] = {}
    for cell, o in enumerate(owner):
        if o >= 0:
            province_cells.setdefault(o, set()).add(cell)
    own_only = []
    for c in cities:
        if c["kind"] in ("municipality", "sar"):
            cells = set(province_cells.get(state_index[c["states"][0]], ()))
        elif c["kind"] == "taiwan_city":
            cells = set()
        else:
            cells = feet.get(c["id"], set())
        if not cells:
            own_only.append(c["name"])
        c["footprint"] = sorted(cells | {c["cell"]})
    add_ranks(cities)

    have = {k: sum(1 for c in cities if c["yields"][k] is not None) for k in YIELD_KEYS}
    print(f"    {len(cities)} cities (of {len(ids)} banner ids); population({year}) "
          f"{sum(1 for c in cities if c['population'] is not None)}, GDP {sum(1 for c in cities if c['gdp'] is not None)}, "
          f"census {sum(1 for c in cities if c['pop_census_2020'] is not None)}, growth "
          f"{sum(1 for c in cities if c['growth'] is not None)}; yields present {have}")
    for key, rows in coverage(stats, ind, ids).items():
        print(f"    basis {key}: " + ", ".join(f"{b[0]}:{b[1] if isinstance(b[1], str) else '+'.join(b[1])} {h}/{len(ids)}"
                                         for b, h in rows) + f" → {bases[key] and bases[key][0]}")
    for label, items in (
        ("without a seat (skipped)", no_seat),
        ("snapped off water/foreign cells", log["snapped"]),
        ("pulled back across a province line", log["pulled"]),
        ("moved to a free neighbouring cell", log["moved"]),
        ("still sharing a cell", log["shared"]),
        ("with a one-hex footprint", own_only),
    ):
        if items:
            print(f"    {len(items)} {label}: {', '.join(items[:10])}{' …' if len(items) > 10 else ''}")

    nation = economy(stats["nation"], ind["nation"], bases, year, window)
    write_web("cities.json", cities)
    document = {
        "vintage": stats_payload.get("vintage") or f"七普 2020；{year} 年统计公报",
        "year": year,
        "census_year": growth.CENSUS_YEAR,
        "gdp_vintage": f"{year} 年国民经济和社会发展统计公报（国家统计局及各地统计局）",
        "industry_vintage": ind_payload.get("vintage"),
        "currency": "CNY",
        "scope": SCOPE,
        "nation": nation,
        "yields": yield_defs(stats, ind, ids, bases),
        "industries": dict(ind.get("industries") or {}),
        "rule": ("城市 = 地级行政区（地级市、地区、自治州、盟）、4 个直辖市、香港、澳门特别行政区及台湾省 6 个主要城市"
                 "（三沙市无陆地格子，仅作标注）。位置为政府驻地；人口与 GDP 仅取统计年份数据，缺失置空（非 0）。"),
    }
    if employment:
        apply_employment(nation, employment.get("nation"))
        province_yields = [{"yields": employment_yields(employment.get("provinces", {}).get(code, {}))}
                           for code in china.PROVINCES]
        apply_census_definitions(document, cities, province_yields)
    write_web("nation.json", document)


# --- builder check (pipeline/check.py part 3) ----------------------------------------------------------------


def check(web_dir: Path) -> list[tuple[str, str]]:
    """China-specific checks of cities.json and nation.json (CN_PLAN §5.2)."""
    cp, np_ = Path(web_dir) / "cities.json", Path(web_dir) / "nation.json"
    if not cp.exists():
        return [("NOTE", "cities.json missing (run: uv run python -m pipeline build cities)")]
    wp = Path(web_dir) / "world.json"
    if wp.exists():
        from .world import is_production_grid

        if not is_production_grid(json.loads(wp.read_text()).get("grid")):
            return [("NOTE", "world.json is not the production frame: city checks skipped")]
    rows = json.loads(cp.read_text())
    out: list[tuple[str, str]] = []
    by_id = {r.get("id"): r for r in rows}
    if not 330 <= len(rows) <= 350:
        out.append(("FAIL", f"cities.json: expected ~344 banner cities, got {len(rows)}"))
    for cid, name in (("110000", "北京"), ("310000", "上海"), ("810000", "香港"), ("820000", "澳门"), ("710100", "台北")):
        if cid not in by_id:
            out.append(("FAIL", f"cities.json: {name} ({cid}) missing"))
    if SANSHA in by_id:
        out.append(("FAIL", "cities.json: 三沙 (460300) must not have a banner (CN_PLAN §3.1)"))
    county_cities = [r.get("id") for r in rows if china.is_county_city(r.get("id", ""))]
    if county_cities:
        out.append(("FAIL", f"cities.json: 省直辖县级行政区 must not be banners: {county_cities[:5]}"))
    bad_prov = [r.get("id") for r in rows if r.get("states") != [str(r.get("id", ""))[:2]]]
    if bad_prov:
        out.append(("FAIL", f"cities.json: states must be [the id's province code]: {bad_prov[:5]}"))
    tw = [r for r in rows if r.get("states") == [china.TAIWAN]]
    if any(r.get("kind") != "taiwan_city" for r in tw):
        out.append(("FAIL", "cities.json: Taiwan rows must have kind 'taiwan_city' (台湾省的城市)"))
    caps = sorted(r["id"] for r in rows if r.get("province_capital"))
    want = sorted(v for v in PROVINCE_CAPITALS.values() if v in by_id)
    if caps != want:
        out.append(("FAIL", f"cities.json: province capitals {caps[:6]}… differ from the table ({len(want)})"))
    zeros = [(r.get("id"), k) for r in rows for k in ("population", "gdp", "pop_census_2020") if r.get(k) == 0]
    zeros += [(r.get("id"), k) for r in rows for k, v in (r.get("yields") or {}).items() if v == 0]
    if zeros:
        out.append(("WARN", f"cities.json zero values (stand-ins for unknown?): {zeros[:8]}"))
    for cid in ("810000", "820000", *(f"7101{i}0" for i in range(6))):
        r = by_id.get(cid)
        if r is not None and (r.get("gdp") is None or r.get("population") is None) and not r.get("note"):
            out.append(("WARN", f"cities.json {cid}: null population/GDP without a note saying why"))
    bj = by_id.get("110000")
    if bj and bj.get("population") is not None and not 1.5e7 < bj["population"] < 3e7:
        out.append(("FAIL", f"cities.json 北京 population {bj['population']} is implausible"))
    sz = by_id.get("440300")
    if sz and sz.get("gdp") is not None and not 2e12 < sz["gdp"] < 6e12:
        out.append(("FAIL", f"cities.json 深圳 GDP {sz['gdp']} 元 is implausible (expected ~3.5 万亿)"))
    cells = [r.get("cell") for r in rows]
    shared = len(cells) - len(set(cells))
    if shared:
        out.append(("NOTE", f"cities.json: {shared} banner cells shared by two cities"))
    if np_.exists():
        nat = json.loads(np_.read_text())
        n = nat.get("nation") or {}
        if nat.get("currency") != "CNY" or not nat.get("scope"):
            out.append(("FAIL", "nation.json: currency must be CNY and scope must say 港澳台 are excluded"))
        if n.get("gdp") is not None and not 8e13 < n["gdp"] < 2e14:
            out.append(("FAIL", f"nation.json GDP {n.get('gdp')} 元 is implausible"))
        if n.get("population") is not None and not 1.3e9 < n["population"] < 1.5e9:
            out.append(("FAIL", f"nation.json population {n.get('population')} is implausible"))
        if (n.get("yields") or {}).get("gold") != n.get("gdp"):
            out.append(("FAIL", "nation.json: the nation's Gold must equal its GDP"))
        mainland = sum(r["gdp"] for r in rows if r.get("gdp") is not None and r["states"][0] not in ("71", "81", "82"))
        if n.get("gdp"):
            out.append(("NOTE", f"sum of mainland city GDP = {mainland / n['gdp']:.0%} of the national GDP "
                                f"({sum(1 for r in rows if r.get('gdp') is not None)} cities with GDP)"))
        for y in nat.get("yields") or []:
            if y.get("basis") is None and y.get("key") != "gold":
                out.append(("NOTE", f"yield {y.get('key')} is null for every city: {y.get('description', '')[:90]}"))
    else:
        out.append(("NOTE", "nation.json missing"))
    if not any(lv in ("FAIL", "WARN") for lv, _ in out):
        out.append(("PASS", f"cities.json: {len(rows)} cities, ids/provinces/capitals consistent, no zero stand-ins"))
    return out
