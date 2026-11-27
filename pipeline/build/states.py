"""Provinces (省级行政区, 34): the same economic shape as a city, ranks, a label anchor, land cover and energy.

China edition (docs/CN_PLAN.md §5.4). The file keeps its legacy name `states.json` and key names (`fips` = the
2-digit province code, `abbr` = the one-character 简称). Rows follow world.json `states` (sorted by code).

Economy (cn_stats_city, the 2023 bulletins / 七普; cn_city_industry for employment and R&D):

* Gold = GDP (元, current prices) of the stats year; Hong Kong and Macau from their own statistics converted to
  CNY (see cn_stats_city), Taiwan null.
* Food / Production / Science / Culture use the same basis as the city yields (CN_PLAN §5.3): the basis published
  in nation.json by the cities builder when it exists; otherwise the §5.3 rule is applied here to the same
  interims (the first basis with data for ≥ yields.BASIS_SHARE (75%) of banner cities; else null everywhere). A province never gets a
  yield on a basis the cities do not use, so the two can be compared.
* growth = population(year) / 七普 2020 − 1 where the province's population is of the stats year, else null.

Ranks are among provinces with a value (台湾/香港/澳门 included when they have one; 1 = largest). The label anchor is
the province's "pole of inaccessibility" on the hex map (the hex farthest from the border, by hex steps, or one
nearly as deep that fits a bigger name), turned along the province's long axis when that helps, and sized to fit
the run of the province's own hexes through the anchor. `size` assumes ~1 em per Chinese character (0.6 em per
Latin one); for very small provinces (香港, 澳门, 上海) the 14 km minimum can exceed the province, so the frontend
should still clamp or hide those labels.
"""

from __future__ import annotations

import json
import math
from collections import deque
from pathlib import Path

from ..core import china
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web
from . import growth
from .yields import CNY_FIELD, YIELD_KEYS, basis_value, choose_bases
from .phase2_stats import DATA, census, population_sources, supplement_state

REQUIRES = ["_world", "cn_boundaries", "cn_stats_city", "cn_city_industry", "nation.json", "resources.json"]
PRODUCES = ["states.json"]
LOCAL_INPUTS = [DATA / "population_2023.json", DATA / "economic_census_employment.json"]

MIN_LABEL_KM, MAX_LABEL_KM = 14.0, 110.0  # suggested font height range, map km
MAX_GROWTH = growth.MAX_GROWTH
CENSUS_YEAR = growth.CENSUS_YEAR


def text_em(name: str) -> float:
    """Approximate label width in em: ~1 em per CJK character, ~0.6 em per Latin one."""
    return sum(1.0 if ord(ch) >= 0x2E80 else 0.6 for ch in name or "")


def label_anchor(grid: HexGrid, owner: list[int], s: int, name: str) -> dict | None:
    """{x, y, angle, size} for province index `s`, or None if it owns no hex.

    angle: degrees, clockwise on screen (y down), in (-90, 90]. size: suggested font height in map km.
    """
    cells = [i for i, o in enumerate(owner) if o == s]
    if not cells:
        return None
    em = max(text_em(name), 2.4)
    # Multi-source BFS from the border hexes inward.
    dist = {}
    queue = deque()
    for c in cells:
        nb = grid.neighbours(c)
        if len(nb) < 6 or any(owner[n] != s for n in nb):
            dist[c] = 0
            queue.append(c)
    while queue:
        c = queue.popleft()
        for n in grid.neighbours(c):
            if owner[n] == s and n not in dist:
                dist[n] = dist[c] + 1
                queue.append(n)
    pts = {c: grid.center(*grid.col_row(c)) for c in cells}
    mx = sum(p[0] for p in pts.values()) / len(cells)
    my = sum(p[1] for p in pts.values()) / len(cells)

    # Principal axis of the hex centres. Labels stay horizontal unless tilting them along a clearly elongated
    # province (at most 45°) allows a much bigger name.
    sxx = sum((p[0] - mx) ** 2 for p in pts.values())
    syy = sum((p[1] - my) ** 2 for p in pts.values())
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts.values())
    theta = 0.5 * math.atan2(2 * sxy, sxx - syy)  # (-90°, 90°], clockwise on screen
    angles = [0.0] + ([theta] if 1 <= abs(math.degrees(theta)) <= 45 else [])
    step = grid.radius / 4

    def reach(x: float, y: float, ux: float, uy: float) -> float:
        """Distance (km) from (x, y) along (ux, uy) before leaving the province's hexes."""
        t = 0.0
        while True:
            c = grid.cell_at(x + (t + step) * ux, y + (t + step) * uy)
            if c < 0 or owner[c] != s:
                return t + step / 2
            t += step

    def fit(c: int, t: float) -> float:
        """Font height (km) for a label centred on hex c at angle t: the name's em width over 90% of the local run
        through c, and no taller than 80% of the local breadth. The run is then re-measured along the label's top
        and bottom edges (twice), so the whole box, not just its centre line, stays inside the province."""
        (x, y), ux, uy = pts[c], math.cos(t), math.sin(t)
        across = 2 * min(reach(x, y, -uy, ux), reach(x, y, uy, -ux))
        h, offsets = 0.8 * across, [0.0]
        for _ in range(3):
            along = min(
                2 * min(reach(x - o * uy, y + o * ux, ux, uy), reach(x - o * uy, y + o * ux, -ux, -uy))
                for o in offsets
            )
            h = min(h, 0.9 * along / em)
            offsets = [0.0, h / 2, -h / 2]
        return h

    # Candidates: the pole of inaccessibility and hexes nearly as deep; pick the one (and angle) that fits the
    # biggest label, a tilted label only if it is 25% bigger than a flat one.
    far = max(dist.values())
    best = None
    for c in cells:
        if dist[c] < far - 1:
            continue
        for t in angles:
            size = fit(c, t) / (1.25 if t else 1.0)
            score = (round(size), -math.hypot(pts[c][0] - mx, pts[c][1] - my))
            if best is None or score > best[0]:
                best = (score, c, t, size * (1.25 if t else 1.0))
    _, pole, angle, size = best
    px, py = pts[pole]
    return {
        "x": round(px, 1),
        "y": round(py, 1),
        "angle": round(math.degrees(angle), 1),
        "size": round(max(MIN_LABEL_KM, min(MAX_LABEL_KM, size)), 1),
    }


PCT_KEYS = ["forest", "crop", "pasture", "grass", "shrub", "wetland", "developed"]
ENERGY_NOTE = ("只统计作为资源标在地图上的电厂（各类型均有规模门槛），并非该省级行政区的全部装机容量。")


def land_shares(world: dict, s: int) -> dict | None:
    """Mean world `pct` (0..100) over the province's cells with land-cover samples, as 0..1 fractions."""
    pct, cover, owner = world.get("pct"), world.get("cover"), world["owner"]
    if not pct or not cover:
        return None
    cells = [i for i, o in enumerate(owner) if o == s and cover[i]]
    if not cells:
        return None
    return {k: round(sum(pct[k][i] for i in cells) / len(cells) / 100, 3) for k in PCT_KEYS}


def energy_by_state(web_dir: Path = WEB_DATA) -> dict[str, dict] | None:
    """province code → {unit, total, by_type, sites, note} summed from resources.json items of every MW type
    (provinces without a mapped site get zeros under "", the default row); None if resources.json is not built or
    is not in the China format (items keyed by a 2-digit province code)."""
    path = Path(web_dir) / "resources.json"
    if not path.exists():
        return None
    res = json.loads(path.read_text())
    items = res.get("items") or []
    if any(it.get("state") and str(it["state"]) not in china.PROVINCES for it in items):
        print("    resources.json is not keyed by province code (US file?): energy left null")
        return None
    mw_types = [t["id"] for t in res.get("types", []) if t.get("unit") == "MW"]
    mw: dict[str, dict] = {}
    sites: dict[str, dict] = {}
    for it in items:
        if it["type"] in mw_types and it.get("state"):
            mw.setdefault(it["state"], dict.fromkeys(mw_types, 0))[it["type"]] += it["value"] or 0
            sites.setdefault(it["state"], dict.fromkeys(mw_types, 0))[it["type"]] += 1
    out = {}
    for code in ["", *mw]:
        by_type = {k: round(v) for k, v in mw.get(code, dict.fromkeys(mw_types, 0)).items()}
        out[code] = {"unit": "MW", "total": sum(by_type.values()), "by_type": by_type,
                     "sites": sites.get(code, dict.fromkeys(mw_types, 0)), "note": ENERGY_NOTE}
    return out


# --- yields -----------------------------------------------------------------------------------------------------


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def local_bases(stats: dict, ind: dict, banner_ids: list[str]) -> dict:
    """CN_PLAN §5.3 applied here (build/yields.py choose_bases): per yield, the first basis with data for ≥ BASIS_SHARE of
    banner cities, else None."""
    return choose_bases(stats, ind, banner_ids)


def published_bases(web_dir: Path = WEB_DATA) -> dict | None:
    """Bases as published by the cities builder (nation.json yields + cities.json values), or None if those files
    are missing or not in the China format. A yield that is null for every city is null here too."""
    nat_p, cit_p = Path(web_dir) / "nation.json", Path(web_dir) / "cities.json"
    if not nat_p.exists():
        return None
    try:
        nat = json.loads(nat_p.read_text())
        cities = json.loads(cit_p.read_text()) if cit_p.exists() else None
    except ValueError:
        return None
    ys = {y.get("key"): y for y in nat.get("yields") or [] if isinstance(y, dict)}
    if set(ys) != set(YIELD_KEYS) or any(y.get("unit") not in ("persons", "cny") for y in ys.values()):
        return None
    out = {}
    for key, y in ys.items():
        if y["unit"] == "persons":
            basis = ("persons", list(y.get("industries") or [])) if y.get("industries") else None
        else:
            basis = ("cny", CNY_FIELD[key]) if key in CNY_FIELD else None
        if basis and isinstance(cities, list) and cities and all((c.get("yields") or {}).get(key) is None for c in cities):
            basis = None
        out[key] = basis
    return out


def growth_rate(pop, census) -> float | None:
    return growth.rate(pop, census)


def economy(stats: dict | None, ind: dict | None, bases: dict, year: int) -> dict:
    """The city economic shape (CN_PLAN §5.2) for a province record."""
    stats, ind = stats or {}, ind or {}
    pop = stats.get("pop") if stats.get("pop_year") == year else None
    gdp = stats.get("gdp") if stats.get("gdp_year") == year else None
    emp = ind.get("emp") or {}
    va = {k: stats.get(f"va_{k}") for k in ("primary", "secondary", "tertiary")}
    yields = {k: basis_value(bases.get(k), stats, ind) for k in YIELD_KEYS}
    if stats.get("gdp_year") != year:
        yields["gold"] = None
    return {
        "population": pop,
        "population_year": year if pop is not None else None,
        "pop_census_2020": stats.get("pop_census"),
        "employed": ind.get("emp_total") if _is_num(ind.get("emp_total")) else None,
        "yields": yields,
        "jobs": emp if any(_is_num(v) for v in emp.values()) else None,
        "gdp": gdp,
        "gdp_year": year if gdp is not None else None,
        "currency": "CNY",
        "gdp_by_industry": va if any(_is_num(v) for v in va.values()) and gdp is not None else None,
        "growth": growth_rate(pop, stats.get("pop_census")),
    }


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("cn_boundaries")
    stats = load_interim("cn_stats_city")
    ind = load_interim("cn_city_industry")
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    year = stats["year"]
    banner_ids = sorted(p["adcode"] for p in bounds["prefectures"]
                        if p["kind"] in china.BANNER_KINDS and p["adcode"] != "460300")

    bases = published_bases()
    if bases is None:
        bases = local_bases(stats, ind, banner_ids)
        print("    yield bases from CN_PLAN §5.3 applied here (nation.json not in the China format yet): "
              + ", ".join(f"{k}={'null' if b is None else b[0] + ':' + (b[1] if isinstance(b[1], str) else '+'.join(b[1]))}"
                          for k, b in bases.items()))
    else:
        print("    yield bases as published in nation.json: " + ", ".join(f"{k}={'null' if b is None else b[0]}" for k, b in bases.items()))

    energy = energy_by_state()
    if energy is None:
        print("    resources.json not built (or not China format) yet: energy left null")
    states = []
    for i, code in enumerate(world["states"]):
        full, short, abbr, kind = china.PROVINCES[code]
        srec = stats["provinces"].get(code)
        irec = ind["provinces"].get(code)
        econ = economy(srec, irec, bases, year)
        notes = [n for n in ((srec or {}).get("note"), (irec or {}).get("note")) if n]
        states.append(
            {
                "fips": code,
                "abbr": abbr,
                "name": short,
                "full": full,
                "kind": kind,
                "kind_label": china.PROVINCE_KIND_LABEL[kind],
                **econ,
                "growth_years": None,
                "ranks": {},
                "label": label_anchor(grid, owner, i, short),
                "land": land_shares(world, i),
                "energy": dict(energy.get(code) or energy[""]) if energy is not None else None,
                "note": "；".join(notes) or None,
            }
        )
    populations, employment = population_sources(), census()
    for s in states:
        supplement_state(s, populations, employment)
    window = [CENSUS_YEAR, year] if any(s["growth"] is not None for s in states) else None
    for s in states:
        s["growth_years"] = window
    rank_yields(states)
    write_web("states.json", states)
    no_label = [s["name"] for s in states if not s["label"]]
    have = {k: sum(1 for s in states if s["yields"][k] is not None) for k in YIELD_KEYS}
    print(f"    {len(states)} provinces; yields present {have}; population {sum(1 for s in states if s['population'] is not None)}, "
          f"growth {sum(1 for s in states if s['growth'] is not None)}"
          + (f"; no hexes (no label anchor): {', '.join(no_label)}" if no_label else ""))


def rank_yields(states):
    for key in YIELD_KEYS:
        ranked = sorted((s for s in states if s["yields"][key] is not None), key=lambda s: -s["yields"][key])
        for s in states:
            s["ranks"][key] = None
        for r, s in enumerate(ranked, 1):
            s["ranks"][key] = r


# --- builder check (pipeline/check.py part 3) ----------------------------------------------------------------


def check(web_dir: Path) -> list[tuple[str, str]]:
    """China-specific checks of states.json: 34 provinces, codes/简称/names from core/china.py, no zero stand-ins."""
    p = Path(web_dir) / "states.json"
    if not p.exists():
        return [("NOTE", "states.json missing (run: uv run python -m pipeline build states)")]
    rows = json.loads(p.read_text())
    out: list[tuple[str, str]] = []
    wp = Path(web_dir) / "world.json"
    if wp.exists():
        from .world import is_production_grid

        if not is_production_grid(json.loads(wp.read_text()).get("grid")):
            return [("NOTE", "world.json is not the production frame: province checks skipped")]
    codes = [r.get("fips") for r in rows]
    if codes != sorted(china.PROVINCES):
        out.append(("FAIL", f"states.json must list the 34 province codes in order, got {codes[:5]}…"))
    bad = [r.get("fips") for r in rows if china.PROVINCES.get(r.get("fips"), (None,) * 4)[2] != r.get("abbr")
           or china.PROVINCES.get(r.get("fips"), (None,) * 4)[0] != r.get("full")]
    if bad:
        out.append(("FAIL", f"states.json abbr/full disagree with core/china.py for {bad}"))
    tw = next((r for r in rows if r.get("fips") == china.TAIWAN), None)
    if tw is not None and tw.get("kind") != "province":
        out.append(("FAIL", "台湾 must be listed as a province (kind 'province')"))
    zeros = [(r.get("fips"), k) for r in rows for k in ("population", "gdp", "pop_census_2020") if r.get(k) == 0]
    zeros += [(r.get("fips"), k) for r in rows for k, v in (r.get("yields") or {}).items() if v == 0]
    if zeros:
        out.append(("WARN", f"states.json zero values (stand-ins for unknown?): {zeros[:8]}"))
    for code in ("71", "81", "82"):
        r = next((x for x in rows if x.get("fips") == code), None)
        if r is not None and r.get("gdp") is None and not r.get("note"):
            out.append(("WARN", f"states.json {code}: GDP null without a note saying why"))
    if not out:
        out.append(("PASS", f"states.json: {len(rows)} provinces, codes/简称/全称 match core/china.py, no zero stand-ins"))
    return out
