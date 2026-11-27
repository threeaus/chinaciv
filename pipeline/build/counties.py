"""Project administrative county boundaries independently from the 25 km hex sampling."""

import json
from collections import Counter

from .phase2_stats import DATA, catalogue, read_curated
from ..core.geo import MapProjection
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web

REQUIRES = ["world.json", "cn_boundaries"]
PRODUCES = ["counties.json", "zones.json"]
LOCAL_INPUTS = [DATA / "development_zones.json", DATA / "county_population_2023.json"]
GHSL_URL = "https://human-settlement.emergency.copernicus.eu/ghs_buS2023.php"


def county_rows(counties, counts, project):
    rows = {}
    for row in counties:
        rings = [[[round(x, 1), round(y, 1)] for x, y in (project(*p) for p in ring)]
                 for ring in row["rings"] if len(ring) >= 4]
        if not rings:
            continue
        xx, yy = zip(*(point for ring in rings for point in ring))
        box = [min(xx), min(yy), max(xx), max(yy)]
        center = list(project(*row["seat"])) if row["seat"] else None
        code = row["adcode"]
        rows[code] = {"id": code, "name": row["name"], "city": row["prefecture"], "state": row["province"],
                      "seat": [round(v, 1) for v in center] if center else None, "bounds": box,
                      "cells": counts.get(code, 0), "rings": rings}
    return list(rows.values())


def build():
    world = json.loads((WEB_DATA / "world.json").read_bytes())
    bounds = load_interim("cn_boundaries")
    project = MapProjection(**world["projection"])
    counts = Counter(world["counties"][i]["geoid"] for i in world["county"] if i >= 0)
    rows = county_rows(bounds["counties"], counts, project)
    pop = read_curated("county_population_2023.json")
    for row in rows:
        if stat := pop.get("counties", {}).get(row["id"]):
            row["stats"] = {**stat, "year": pop["year"]}
    write_web(PRODUCES[0], {"counties": rows, "source": "cn_boundaries",
                            "stats_source": {k: pop[k] for k in ("source", "title") if k in pop},
                            "note": "县级边界取自 DataV.GeoAtlas，经简化后用于地图交互。台湾地区等未收录县级面。"})
    zones = read_curated("development_zones.json")
    for row in zones["zones"]:
        row["x"], row["y"] = (round(v, 1) for v in project(row["lon"], row["lat"]))
    write_web(PRODUCES[1], zones)


def add_geography_sources(sources):
    zones = read_curated("development_zones.json")
    if zones:
        catalogue(sources, "development_zones", "国家级新区与自由贸易试验区", "国家发展改革委、商务部",
                  "根据官方名录标注地理位置，展示代表点。",
                  [(row["title"], row["url"]) for row in zones["sources"]], ["counties"], "截至 2026 年 11 月")
    pop = read_curated("county_population_2023.json")
    if pop:
        catalogue(sources, "county_population", pop["title"], "吉林省统计局",
                  "2023 年末县区常住人口及城镇化率。", [(pop["title"], pop["source"])], ["counties"])
    catalogue(sources, "ghsl_built", "全球人类住区图层 · 建筑覆盖面积", "欧盟委员会联合研究中心（JRC）",
              "GHS-BUILT-S R2023A，2020 年 30 弧秒网格，显示建筑表面面积达到 5 万平方米的格子。",
              [("GHS-BUILT-S R2023A 产品说明", GHSL_URL)], ["builtup"], 2020)


def check(web_dir):
    path = web_dir / PRODUCES[0]
    if not path.exists():
        return [("NOTE", "counties.json not built")]
    rows = json.loads(path.read_bytes())["counties"]
    zp = web_dir / PRODUCES[1]
    if not zp.exists():
        return [("FAIL", "zones.json missing")]
    zones = json.loads(zp.read_bytes())["zones"]
    if len(rows) < 2700 or len({row["id"] for row in rows}) != len(rows):
        return [("FAIL", "counties.json has incomplete or duplicate county geometries")]
    results = [("PASS", f"county geography: {len(rows)} counties, {len(zones)} zone markers")]
    built = web_dir / "builtup.json"
    if built.exists():
        data = json.loads(built.read_bytes())
        if not data["points"] or data["year"] != 2020 or len(data["tiles"]) != 35:
            results.append(("FAIL", "builtup.json has incomplete GHSL data"))
        else:
            results.append(("PASS", f"builtup.json: {len(data['points'])} populated cells, {len(data['tiles'])} source tiles"))
    return results
