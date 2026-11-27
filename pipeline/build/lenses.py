"""Build 2023 statistical lenses from published geographies and city statistics."""

import json
import math

from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web
from .phase2_stats import DATA, catalogue, population_sources, read_curated

REQUIRES = ["world.json", "cities.json", "states.json", "cn_stats_city"]
PRODUCES = ["lenses.json"]
LOCAL_INPUTS = [DATA / "population_2023.json", DATA / "province_lenses_2023.json"]
YEAR = 2023
SOURCE = "cn_stats_city"
PROVINCIAL_SOURCE = "provincial_lens_2023"

METRICS = (
    ("gdp-per-capita", "人均 GDP", "元/人", "cny", [20000, 220000],
     ["#21405b", "#3e8889", "#c3bc73", "#edbf4d"], "2023 年现价 GDP ÷ 同年人口"),
    ("growth", "人口增长", "%", "signed-pct", [-0.12, 0.12],
     ["#a34454", "#d57773", "#ded1a3", "#549f93", "#285973"], "七普到 2023 年的累计人口变化"),
    ("urbanization", "城镇化率", "%", "pct", [0.25, 1],
     ["#38433a", "#749165", "#d4b474", "#f3d082"], "2023 年常住人口城镇化率"),
    ("income", "人均可支配收入", "元/人", "cny", [12000, 85000],
     ["#352c50", "#765581", "#c48382", "#f5ca89"], "2023 年全体居民人均可支配收入"),
)
GLYPHS = (("y-gold", "💰"), ("people", "👥"), ("city", "🏙️"), ("y-gold", "¥"))


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def metric_values(row, stats):
    pop, gdp = number(row.get("population")), number(row.get("gdp"))
    same_year = row.get("population_year") == row.get("gdp_year") == YEAR
    per_capita = round(gdp / pop) if pop and gdp is not None and same_year else None
    growth = number(row.get("growth")) if row.get("growth_years") == [2020, YEAR] else None
    urban = number(stats.get("urban_pct"))
    income = number(stats.get("income_pc"))
    return (per_capita, growth, urban / 100 if urban is not None and 0 <= urban <= 100 else None,
            income if income is not None and income >= 0 else None)


def make_lenses(world, cities, states, stats):
    state_rows = {s["fips"]: s for s in states}
    city_rows = {c["id"]: c for c in cities}
    county_rows = {county: c for c in cities for county in c["counties"]}
    city_cells = {cell: c for c in cities if c.get("kind") == "taiwan_city" for cell in c.get("footprint", [])}
    cells = {"city": [], "state": []}
    for i, owner in enumerate(world["owner"]):
        province = world["states"][owner]["fips"] if owner >= 0 else None
        county = world["county"][i]
        city = county_rows.get(world["counties"][county]["geoid"]) if county >= 0 else None
        if city is None and province:
            city = city_rows.get(province + "0000") or city_cells.get(i)
        cells["state"].append(province)
        cells["city"].append(city["id"] if city and province in city["states"] else None)

    groups = [{"id": "city", "name": "地级城市"}, {"id": "state", "name": "省级地区"}]
    lenses = []
    for group, rows, table in zip(groups, (city_rows, state_rows), ("cities", "provinces")):
        region = group["id"]
        values = {code: metric_values(row, stats.get(table, {}).get(code, {})) for code, row in rows.items()}
        for j, (key, label, unit, fmt, domain, ramp, description) in enumerate(METRICS):
            icon, emoji = GLYPHS[j]
            by_region = {code: value[j] for code, value in values.items()}
            covered = sum(v is not None for v in by_region.values())
            source = PROVINCIAL_SOURCE if region == "state" and j >= 2 and stats.get("provincial_lens_data") else SOURCE
            lenses.append({
                "id": f"{region}-{key}", "name": f"{label} · {'城市' if region == 'city' else '省级'}",
                "icon": icon, "emoji": emoji,
                "group": region, "unit": unit, "format": fmt, "domain": domain, "scale": "linear",
                "higher_is": "neutral", "ramp": ramp, "source": source, "description": description,
                "note": f"有数据 {covered}/{len(rows)} 个地区，灰色为缺值。城市边界按地图格概化。",
                "region_values": by_region,
                "values": [by_region.get(code) for code in cells[region]],
            })
    return {"vintage": "2023 年统计公报与年鉴", "groups": groups, "lenses": lenses}


def build():
    world, cities, states = (json.loads((WEB_DATA / name).read_bytes()) for name in REQUIRES[:3])
    stats = load_interim(SOURCE)
    provincial = read_curated("province_lenses_2023.json")
    if provincial:
        stats["provincial_lens_data"] = True
        for code, values in provincial["provinces"].items():
            stats["provinces"].setdefault(code, {}).update(values)
            if code in ("11", "12", "31", "50"):
                stats["cities"].setdefault(code + "0000", {}).update(values)
    for code, row in population_sources().items():
        if "urban_pct" in row:
            result = stats["cities"].setdefault(code, {})
            if result.get("urban_pct") is None:
                result["urban_pct"] = 100 * row["urban_pct"]
    write_web(PRODUCES[0], make_lenses(world, cities, states, stats))


def add_lens_sources(sources):
    provincial = read_curated("province_lenses_2023.json")
    if not provincial:
        return
    urls = provincial["sources"]
    catalogue(sources, PROVINCIAL_SOURCE, "省级城镇化率与居民收入", "国家统计局",
              "城镇人口占常住人口的比重及全体居民人均可支配收入。",
              [("中国统计年鉴 2024 表 2-7", urls["urban_pct"]), ("中国统计年鉴 2025 表 6-18", urls["income_pc"])],
              ["lenses"])
