# Data contracts (chinaciv phase 1)

> chinaciv is a fork of usaciv (Andrej Karpathy, MIT). This document is the **China contract** between the pipeline and
> the browser. `docs/CN_PLAN.md` keeps the design decisions and the Decisions log behind it.
>
> * **Projection/frame**: Albers equal-area for China (sphere; lat1 25°N, lat2 47°N, lat0 0°, lon0 105°E) with a
>   **fixed** frame (`core/geo.py`: `china_projection()`, 5471 × 4455 km, grid 128 × 120 at 25 km). world.json is
>   version 3 and publishes `projection`, the 南海诸岛 `inset`, `dash_line`, `islands`, `labels` and `notice`.
> * **Ids**: provinces = 2-digit adcode prefix (`"44"`; kept under the legacy keys `fips` / `state`), cities = 6-digit
>   prefecture adcodes (`"440300"`; municipalities/SARs `"110000"`, `"810000"`; Taiwan's six cities `710100`–`710600`
>   are project-assigned), counties = 6-digit adcodes (legacy keys `geoid` / `county`); `cbsa` in site rows holds the
>   city id. Money is **CNY (元)**.
> * **Files**: world, cities, nation, states (eager), resources, infrastructure, wonders, sources. Phase 1 publishes
>   **no** lenses.json, counties.json, citizens.json, districts.json, trade.json, military.json or disasters.json
>   (out of scope: military, faith, freight routes, disasters, county lenses, citizens, districts). The browser does
>   not request them.

The pipeline (Python) and the browser (web/js) agree on these files in `web/data/`. Change a contract here first, then on
both sides. All coordinates are **map km**: Albers equal-area, origin top-left, y **down** (see `pipeline/core/geo.py`).
Per-cell arrays have length `grid.cols * grid.rows`, with index `row * cols + col` (pointy-top, odd-r layout, see
`pipeline/core/hexgrid.py` ⇄ `web/js/hex.js`). `null` always means "no data". Never write `0` as a stand-in for "unknown".

## Pipeline conventions

* **Sources** (`pipeline/sources/*.py`) are discovered automatically: any `Source` subclass with `info = SourceInfo(...)`.
  `process()` returns a dict. It may include `"vintage"` (str) and `"_files"` (list of raw-file paths relative to
  `data/raw/<id>/` that this processing actually used; the Almanac cites only those).
* **Builders** (`pipeline/build/*.py`) are discovered automatically: a module with `REQUIRES`, `PRODUCES` and `build()`.
  They run in dependency order. Interims made by builders start with `_`. Helpers without `build()` (e.g. `yields.py`) are fine.
* The **`_world` interim** (made by `world`) holds: `grid`, `projection` (`MapProjection` kwargs incl. `lat1, lat2, lat0,
  lon0`), `owner`, `county`, `county_samples` (7 county indices per Chinese land cell, `[]` for other cells; sample 0 =
  centre), `states` (province codes, same order as world.json states), `counties` (county adcodes, sorted; all 2,874
  cn_boundaries counties), `county_prefecture` (parallel to `counties`: the prefecture adcode; a 省直辖县级 unit maps to
  itself), `water`, `cover`, `pct` (same as world.json) and `inset` (same as world.json). Builders that need to know whether
  a cell is Chinese land must use `owner[cell] >= 0`. Use `build/locate.py` `Locator` for lon/lat → cell/county/city/province.
* Python is **standard library only**. Downloads go through `Source.download()` (or `Source.download_prefix()` for the
  leading block of a big sorted file), which cache them and record provenance in `data/raw/<id>/manifest.json`;
  `Source.discard(rel_path)` forgets a cached file that turned out to be bad. All three wrap `core.fetch`.
* Under `--offline` (`core.fetch.OFFLINE`, `Source.offline`) sources skip discovery requests and use the newest complete
  cached data; a download of a file that is not cached raises `OfflineError`.
* **Builder checks.** Any module in `pipeline/build/` may define `check(web_dir: Path) -> list[(level, message)]`, level one
  of `PASS`, `NOTE`, `WARN`, `FAIL`. `pipeline check` discovers and runs them after its own checks (section "builder
  checks", each line prefixed with the module name), so a new builder never edits `pipeline/check.py`. Rules: read only
  `web_dir` (tests point it at a tiny synthetic dataset); report a **missing output as a NOTE** (never WARN/FAIL: the unit
  tests run every discovered check against a dataset without your files); a check that raises is reported as a FAIL.
  Validate your file's shape against this document (keys, types, null rules, cell ranges against world.json) and add a
  short data-quality summary (counts, coverage) as PASS/NOTE lines.

## world.json

Version 3 (China; `pipeline/build/world.py`, CN_PLAN §2 and §5.1).

```jsonc
{
  "version": 3,
  "grid": {"radius": 25, "cols": 128, "rows": 120},
  "width": 5471.0, "height": 4455.0, "margin": 200,
  "projection": {"min_x": -2619.0, "max_y": 5939.0, "margin": 200.0,
                 "lat1": 25.0, "lat2": 47.0, "lat0": 0.0, "lon0": 105.0},   // spherical Albers; read it, don't hard-code
  "owner":  [int],   // -1 water, -2 foreign land (neighbours, Natural Earth China POV), >=0 index into states
  "county": [int],   // index into counties, -1 if none (water, foreign land, Taiwan: DataV has no Taiwan counties)
  "elev":   [int],   // metres. Land: mean of land samples only. Water: mean of the hex's ETOPO samples below sea
                     // level (its depth, <= 0); lakes: min(mean, 0); -4000 where ETOPO has no samples
  "elev_max": [int], // metres, the highest land sample in the hex (0 for water, capped at 9000); the art uses it for snow
  "water":  [int],   // 0 land, 1 ocean, 2 coast (next to land or shallower than 200 m), 3 lake
  "relief": [int],   // 0 flat, 1 hills, 2 mountains, 3 peaks. 0 for water. A hex whose lower 60% of land samples is
                     // flat lowland (spread < 60 m, under 400 m) is eased one class (valley floors)
  "cover":  [int],   // land-cover id (see tables.cover), for Chinese AND foreign land; 0 = none (water, no samples)
  "pct": {           // share of the cell's land samples, 0..100 ints (Chinese land cells only; 0 elsewhere)
    "forest": [int], "crop": [int], "pasture": [int], "grass": [int], "shrub": [int],
    "wetland": [int], "developed": [int]
  },
  "tables": {        // names and rules in Chinese (the Almanac/legend print them)
    "water":  [{"id": 0, "name": "陆地", "rule": "..."}, {"id": 1, "name": "远海", "color": "#1b4266", "rule": "..."}, ...],
    "relief": [{"id": 0, "name": "平原", "rule": "..."}, ...],
    "cover":  [{"id": 1, "key": "forest_deciduous", "name": "落叶林", "color": "#4f7a35", "groups": ["forest_deciduous"], "rule": "..."}, ...],
    "notes":  {"water": "...", "relief": "...", "cover": "..."}
  },
  "states":   [{"fips": "44", "abbr": "粤", "name": "广东", "full": "广东省", "kind": "province", "kind_label": "省"}],  // 34, by code
  "counties": [{"geoid": "440305", "name": "南山区"}],                          // 2,874, by adcode
  "rivers":   [{"name": "长江" | null, "name_en": "Yangtze / Chang Jiang", "rank": 1, "pts": [x0, y0, ...]}],
              // Natural Earth rank <= 8, clipped to the frame; name = Chinese name where identified, else null
  "lakes":    [{"name": "青海湖", "x": ..., "y": ..., "cells": 3}],             // label anchors of named lakes >= 1 lake hex
  "dash_line": [[x0, y0, x1, y1, ...]],  // main-map km: centre lines of the dashes (or pieces) inside the frame and
                                         // outside the inset box (today dashes 1–4)
  "boundary": {"undefined": [cell, ...],  // FOREIGN hexes whose edges with Chinese hexes are 未定国界 (all other
               "sections": [{"id": "kashmir", "name": "克什米尔地区", "a3": ["IND", "PAK"], "bbox": [lon0, lat0, lon1, lat1]}],
               "note": "…"},             // Chinese–foreign land edges are 国界); drawn in the standard-map legend symbols
  "islands":  [{"id": "diaoyu", "name": "钓鱼岛", "kind": "island|island_group|shoal", "x": ..., "y": ...}],
              // main-map labels inside the frame, outside the inset box: 钓鱼岛, 赤尾屿, 东沙群岛, 西沙群岛
  "labels":   [{"name": "三沙市", "x": ..., "y": ..., "kind": "city", "id": "460300"}],   // main-map point labels
  "inset": {                              // 南海诸岛, vector only (the cells under the box stay ordinary water)
    "title": "南海诸岛", "box": [4780.7, 3655.7, 5446.0, 4430.0], "region": [106.5, 2.8, 123.5, 24.8],
    "scale": 0.3, "pad": 12.0,
    "land":   [{"kind": "china", "code": "46", "pts": [x0, y0, ...]}, {"kind": "foreign", "name": "越南", "pts": [...]}],
              // closed rings (last point not repeated), clipped to the region, map km inside the box; draw opaque box first
    "dashes": [[x0, y0, ...]],            // all 10 dashes, centre lines, map km inside the box (stroke ~2 km wide)
    "islands": [{"id": "xisha", "name": "西沙群岛", "kind": "island_group", "x": ..., "y": ...}],
    "labels": [{"name": "三沙市", "x": ..., "y": ..., "kind": "city", "id": "460300"}]
  },
  "notice": {"text": "本地图仅供个人学习，未申请审图号。", "boundary": "国界、省界及南海断续线依据阿里云 DataV.GeoAtlas …",
             "sources": ["cn_boundaries", "natural_earth"]}   // show in the Almanac, help and share images
}
```

Ownership: each hex's 7 sample points (centre + six at 60% towards the corners) are lake (Natural Earth) → province
(cn_boundaries; tested before any Natural Earth country, so the DataV outline wins where they overlap) → foreign →
sea; the majority decides, with the tidal-bay and sliver rules in `tables.notes.water`. The hexes holding the seats of
香港 (810000) and 澳门 (820000) are forced to the SAR, with the SAR district at the seat as their county. 钓鱼岛/赤尾屿 and
the South China Sea islands are labelled points, not land hexes.

Cover ids (fixed): 0 none · 1 forest_deciduous · 2 forest_evergreen · 3 forest_mixed · 4 scrub (scrub & desert) ·
5 grassland · 6 pasture (here: 耕地与自然植被镶嵌, "农林镶嵌") · 7 cropland · 8 wetland · 9 urban · 10 barren · 11 ice.
Dominant cover per cell = the largest cn_landcover group among its ~410 land samples (MODIS MCD12Q1 IGBP 2024, 0.02°);
a cell is **urban** if the `developed` group ≥ 20% of land samples (lower than the US 30%: MODIS urban is sparse).

## cities.json

Banner cities (`pipeline/build/cities.py`, CN_PLAN §5.2): every prefecture-level division (地级市, 地区, 自治州, 盟) of
`cn_boundaries.prefectures`, the 4 municipalities, 香港, 澳门 and the six largest Taiwan cities (344 rows; 三沙 460300 has
no land hex and no banner; the 30 省直辖县级行政区 are counties, not banners). A list sorted by population (the stats
year, 2023) descending, nulls last; ties and nulls by the 2020 census population descending, then id:

```jsonc
{
  "id": "440300",                 // 6-digit adcode; municipality / SAR = province adcode (110000, 810000);
                                  // Taiwan cities 710100–710600 are project-assigned, not official codes
  "name": "深圳", "full": "深圳市", "kind": "city", "kind_label": "地级市",   // kind: city|prefecture|autonomous_prefecture|
                                  // league|municipality|sar|taiwan_city (core/china.py PREFECTURE_KIND_LABEL)
  "states": ["44"],               // [province code]
  "metro": true,                  // always true (legacy key)
  "capital": false,               // true only for 北京 110000 (the national capital)
  "province_capital": false,      // seat of a province's / autonomous region's government (省会/首府; 台湾省: 台北)
  "capital_label": null,          // "首都" | "省会" | "首府" | null
  "x": 4321.0, "y": 4410.2,       // seat of government (DataV center; Wikidata for Taiwan), map km
  "cell": 12758,                  // banner cell: Chinese land (owner >= 0), unique (no shared cell today)
  "population": 17790100 | null, "population_year": 2023 | null,   // 年末常住人口 of the stats year only
  "pop_census_2020": 17494398 | null,                              // 七普
  "employed": … | null,           // cn_city_industry emp_total (城镇非私营单位就业人员, 广西/山东 only)
  "yields": {"food": … | null, "production": … | null, "gold": 3.46e12 | null, "science": … | null, "culture": … | null},
  "jobs": {"A": …, …, "S": …} | null,          // employment by GB/T 4754 section, or null
  "gdp": 3.46e12 | null, "gdp_year": 2023 | null, "currency": "CNY",
  "gdp_by_industry": {"primary": …, "secondary": …, "tertiary": …} | null,   // 三次产业增加值 (元), all three or null
  "growth": 0.0169 | null, "growth_years": [2020, 2023],
  "counties": ["440303", …],      // the prefecture's county adcodes (cn_boundaries), sorted; [] for Taiwan cities
  "footprint": [12758, …],        // sorted cells, see below
  "ranks": {"population": 5, "gdp": 3, "gdp_per_capita": 7, "growth": 31, "food": null, …, "gold": 3, …},
  "peers": ["440100", …],         // 5 ids
  "note": "…" | null              // data notes (SARs, Taiwan, scope changes), shown in the panel
}
```

* **Banner cell**: SARs first (their forced seat hexes), then by size (population, else census). A seat on water or
  abroad snaps to the nearest Chinese land cell (own province preferred); a seat in another province's hex is pulled
  back into the own province if a free cell is within 2 rings (深圳, 珠海 next to 香港/澳门); a taken cell moves to the
  nearest free cell within 2 rings.
* **`footprint`**: Chinese land cells where ≥ 4 of 7 county samples map (via `_world.county_prefecture`) to the city;
  municipalities and SARs: every cell of their province; Taiwan cities: their own cell. The own `cell` is always in it.
* **yields**: see nation.json `yields` (CN_PLAN §5.3, `pipeline/build/yields.py`). Gold = GDP; each other yield uses
  one basis for every city, the first with data for ≥ 75% of banner cities (`BASIS_SHARE`; the plan said 90%, lowered at
  integration), else null everywhere. With the current interims 粮食 = 第一产业增加值 and 生产力 = 第二产业增加值
  (267/344 cities, the rest null); 科研 and 文化 are null (employment covers 30 cities, R&D 43).
* **`ranks`**: over all cities, 1 = highest, for `population`, `gdp`, `gdp_per_capita`, `growth` and each yield; null
  where the value is null; non-null ranks are a permutation of 1..N. The `population` rank orders by `population`
  where present, else by `pop_census_2020` (so a city lacking a stats-year figure keeps its place).
* **`peers`**: the 5 cities closest by 2020 census population (|log ratio|); a city without a census figure (Taiwan)
  takes the nearest cities of its own province first.

**Growth** (cities, states, `nation.nation`): `growth = population(year) / pop_census_2020 − 1` over `growth_years =
[2020, year]`, `year` = nation.json `year` (2023). Null when the population is not of the stats year, there is no census
figure, |growth| > 25%, or the city's 2023 bulletin counts a narrower area than the census (保定 without 雄安新区, 咸阳
without the 西咸新区 areas; `note` says so). See `pipeline/build/growth.py`. US fields (`median_income`, `pop_series`,
`gdp_undisclosed`, …) are omitted.

## states.json

Provinces (34; `pipeline/build/states.py`, CN_PLAN §5.4). A list in the same order as world.json `states`, each with:

```jsonc
{
  "fips": "44", "abbr": "粤", "name": "广东", "full": "广东省", "kind": "province", "kind_label": "省",
  "population": 127060000 | null, "population_year": 2023 | null,   // 年末常住人口 of the stats year, else null
  "pop_census_2020": 126012510 | null,                              // 七普
  "employed": … | null,                                             // cn_city_industry emp_total
  "yields": {"food": … | null, "production": … | null, "gold": … | null, "science": … | null, "culture": … | null},
  "jobs": {"A": …, …, "S": …} | null,                               // employment by GB/T 4754 section, or null
  "gdp": 1.3567e13 | null, "gdp_year": 2023 | null, "currency": "CNY",
  "gdp_by_industry": {"primary": …, "secondary": …, "tertiary": …} | null,
  "growth": 0.0136 | null, "growth_years": [2020, 2023] | null,     // population / pop_census_2020 − 1 (stats year only)
  "ranks": {"food": 1 | null, …},                                   // among provinces with a value, 1 = largest
  "label": {"x": …, "y": …, "angle": 0, "size": 60} | null,
  "land": {…} | null, "energy": {…} | null,
  "note": "台湾地区：…" | null                                      // data notes (Taiwan, SARs), shown in the panel
}
```

* **yields**: Gold = GDP (元). Food/Production/Science/Culture use the same basis as the city yields (CN_PLAN §5.3):
  the basis nation.json publishes, or, until it exists, the §5.3 rule over the banner cities (first basis with data for
  ≥ 75% of them, else null everywhere). With the 2023 interims 粮食/生产力 use 三次产业增加值; 科研/文化 are null.
* **label**: optional suggested anchor for the big province name: `angle` in degrees clockwise, `size` a suggested font
  height in map km (≈1 em per Chinese character), clamped to 14..110 km; very small provinces (香港, 澳门, 上海) can be
  smaller than 14 km, so the frontend should still clamp or hide those labels. `null` only for a province without hexes.
* **land**: land-cover shares as **0..1 fractions**: the mean of world.json `pct` over the province's cells that have
  land-cover samples (`cover > 0`). Keys are world.json `pct` keys.
* **energy**: `{unit: "MW", total, by_type, sites, note}` summed from resources.json items whose `state` is the province
  code, for every resource type with unit `MW`. It only counts the mapped sites above each type's threshold, so it is
  not the province's total capacity (`note` says so). `null` if resources.json is not built.

## nation.json

```jsonc
{
  "vintage": "七普 2020；2023 年统计公报", "year": 2023, "census_year": 2020,
  "gdp_vintage": "2023 年国民经济和社会发展统计公报（国家统计局及各地统计局）",
  "industry_vintage": "各省统计年鉴2025（2024年数据）；2024年全国科技经费投入统计公报",
  "currency": "CNY",
  "scope": "全国数据为 31 个省、自治区、直辖市合计，不含香港、澳门和台湾",
  "nation": { /* same economic shape as a city (NBS 2023 公报, 七普) */ },
  "yields": [{"key": "food", "icon": "y-food", "emoji": "🌾", "label": "粮食", "color": "#7fbf3f",
              "unit": "persons|cny",           // the chosen basis' unit (priority-1 unit when the yield is null)
              "industries": ["A"],             // GB/T 4754 sections for an employment basis, else []
              "basis": "va_primary" | "employment:A" | "gdp" | "rd_expenditure" | null,   // null = yield null everywhere
              "coverage": 0.78 | null,         // share of banner cities with a value on that basis
              "description": "…"}],            // Chinese; names the table and year, or why the yield is null
  "industries": {"A": "农、林、牧、渔业", …, "S": "公共管理、社会保障和社会组织"},
  "rule": "…"                                  // Chinese: which units are cities, positions, null policy
}
```

## resources.json

Built by `pipeline/build/resources.py` from the `cn_energy` interim (Global Energy Monitor trackers, CC BY 4.0;
curated metal mines with Wikidata coordinates), placed with `locate.Locator`.

```jsonc
{
  "vintage": {"plants": "...", "mines": "...", "fields": "..."},   // cn_energy vintages, as published
  "rule": "资源只显示有分量的站点，规则如下 ...",                     // the published selection rule (Chinese)
  "sources": ["cn_energy"],
  "types": [{"id": "nuclear", "name": "核电站", "category": "energy|mineral",
             "emoji": "☢️", "icon": "r-nuclear", "color": "#e8d44d",
             "unit": "MW", "description": "每一座有在运机组的核电站 ...", "source": "cn_energy"}],
  "items": [{"type": "hydro", "name": "三峡水电站", "name_en": "Three Gorges Dam hydroelectric plant",
             "x": 3385.5, "y": 2841.7, "cell": 9806, "value": 22500, "detail": "2012 年投运",
             "state": "42", "county": "420506", "cbsa": "420500"}]
}
```

* `state` = 2-digit province code: GEM's area tag for Taiwan / Hong Kong / Macao (`71`/`81`/`82`), else the province
  of the county at the site, else the cell owner's. Offshore oil & gas fields that would snap onto a Taiwan/SAR hex are
  moved to the nearest mainland hex (they are mainland CNOOC fields).
* `county` = county adcode at the true point (or the hex's county just offshore), `null` in Taiwan (DataV has no
  Taiwan counties) and far offshore. `cbsa` = cities.json id holding that county (`Locator.city_of`), or `null`.
* `name` is Chinese: GEM's Chinese name (coal, nuclear, large hydro, fields; company prefixes stripped from mine
  names), else this project's translation (gas plants, a few hydro / pumped-storage / geothermal plants), else a
  descriptive name from the county (`"共和县光伏电站群"` for a hex cluster). `name_en` (GEM's English name) is present
  when it differs. Taiwan/HK names stay in traditional characters where GEM gives them so.
* `value` units per type: `MW` (plants, nameplate, operating units only), `吨/年` (mine capacity, summed per hex;
  `null` for the curated metal mines, whose capacity is not published), `桶油当量/年` (field production, GEM's latest
  reported year per field, summed per hex). Never 0 for unknown.
* Types (rank order): `nuclear, hydro, coal_mine, rare_earths, lithium, tungsten, antimony, gold, copper, lead_zinc,
  bauxite, iron, coal_plant, gas_plant, geothermal, pumped_storage, wind, solar, oil, gas`; only types with items are
  listed. There is no `battery` type (GEM does not track battery storage) and no biomass/oil-fired plants.
* Selection (also in `rule` and each `description`): every nuclear plant; hydro ≥ 1,000 MW; pumped storage ≥ 1,200 MW;
  coal ≥ 3,000 MW; gas ≥ 1,500 MW; every geothermal plant; wind and solar summed per hex, shown at ≥ 1,500 MW; coal
  mines ≥ 10 Mt/yr and iron mines ≥ 5 Mt/yr (grouped per hex); every curated metal mine; oil/gas fields ≥ 5 million
  boe/yr (grouped per hex; `oil_gas` fields count as oil when oil ≥ half the boe). About 520 items, ~215 kB.

```jsonc
"summary": {
  "note": "仅统计地图上显示的站点 ...",
  "national": {"nuclear": {"count": 18, "value": 64623, "unit": "MW"}, "oil": {"count": 41, "value": null, "unit": "桶油当量/年"}},
  "states":   {"42": {"hydro": {"count": 5, "value": 29325, "unit": "MW"}, "...": {}}}   // only types present
}
```

`summary.national` has every type in `types`; `summary.states` has, per province code with at least one item, the
types present there. `value` is the sum of the items' `value` (nulls skipped), or `null` for `oil` and `gas`, whose
field production years differ. `resources.check(web_dir)` adds China checks: published `rule`, province codes,
county in its province, no 0 values, Chinese names, no battery type, and on the production grid that 三峡, 白鹤滩,
大亚湾, a Taiwan site and a Hong Kong site are present.

## Optional map-layer files

Every file below is **optional**: the app and `check` work without it, and each owning builder validates its own file with
a `check(web_dir)` (see Pipeline conventions). Shared rules:

* Top level always has `"version"`, `"vintage"` (a human string, or `{part: string}`), and `"sources": [source ids]`
  (sources.json ids, so the Almanac can cite them).
* `cell` = a world.json cell index (pointy-top odd-r, `row * cols + col`); a site's `cell` is a Chinese land cell
  (`owner >= 0`) unless stated. `x`, `y` = map km. `county` = 6-digit adcode from world.json `counties` (or null; Taiwan
  has no counties), `cbsa` = a cities.json `id` (or null), `state` = 2-digit province code.
* Money is **yuan (CNY)**; shares are 0..1 fractions; `null` = unknown, never `0`.
* Rules that pick things (airports, ports, resources, wonders) are published inside the file as text (`rule` / `rules`)
  so the UI and the Almanac can quote them.
* **Loading** (browser): `infrastructure` and `wonders` load eagerly right after the first frame (keep each **under
  ~300 kB**); nothing is lazy in phase 1.

### infrastructure.json (eager)

Tile improvements (China, CN_PLAN §5.5): high-speed rail, conventional rail and expressways rasterised onto hex links
(no polylines), plus the busiest airports and the principal ports as sites. Built by `pipeline/build/infrastructure.py`
from `cn_rail_roads` (OpenStreetMap via Overpass, ODbL), `cn_transport_air` (CAAC 年度机场生产统计公报),
`cn_transport_ports` (交通运输部 全国主要港口吞吐量) and `cn_boundaries` (county lookup). About 230 kB.

```jsonc
{
  "version": 2,                          // 2 = China field names (passengers, cargo_t)
  "vintage": {"roads": "OpenStreetMap contributors, Overpass extract 2026-11", "rail": "…",
              "ports": "交通运输部《2025年港口货物、集装箱吞吐量》（全国主要港口）", "airports": "中国民用航空局《2025年…公报》"},
  "sources": ["cn_rail_roads", "cn_transport_air", "cn_transport_ports", "cn_boundaries"],
  "rules": {"roads": "…", "rail": "…", "ports": "…", "airports": "…"},   // Chinese selection rules, quote in the UI
  "notes": {"airports": "香港、澳门、台湾地区机场不在民航局公报范围内…", "ports": "…"},
  "units": {"passengers": "人次", "cargo_t": "吨", "foreign_t": "吨", "teu": "标准箱（TEU）", "movements": "架次"},
  "road_classes": [{"id": "expressway", "name": "高速公路"}],
  "rail_tiers": [{"id": "hsr", "name": "高速铁路"}, {"id": "rail", "name": "普速铁路"}],
  "hubs": {"L": "年旅客吞吐量1000万人次以上", "M": "200万–1000万人次", "S": "200万人次以下"},
  "port_types": {"coastal": "沿海港口", "inland": "内河港口"},
  "roads": [[3721, 3722, 0, "G4"]],      // [cell a, cell b, class index, route number / name or null]; a < b, neighbours, unique pair
  "rail": [[3721, 3845, 0, "京沪高速线"]], // [a, b, tier index, line name or null]; same rules
  "ports": [{"id": "ningbo-zhoushan", "name": "宁波舟山港", "label": "宁波舟山", "type": "coastal|inland", "rank": 1,
             "cargo_t": 1431920000, "foreign_t": 660760000 | null, "teu": 43870000 | null, "year": 2025,
             "x": …, "y": …, "cell": 9830, "county": "330206", "cbsa": "330200" | null, "state": "33"}],   // sorted by rank
  "airports": [{"id": "PVG", "name": "上海/浦东", "city": "上海", "hub": "L|M|S", "passengers": 84994548,
                "passengers_prev": 76787039 | null, "cargo_t": 4091940.9 | null, "movements": 557043 | null,
                "year": 2025, "rank": 1, "x": …, "y": …, "cell": …, "county": …, "cbsa": …, "state": "31"}]  // sorted by passengers desc
}
```

* **Links** join **neighbouring** cells, at least one end on Chinese land (`owner >= 0`) and neither end foreign
  (`owner == -2`); samples on foreign land break a line, so the source's 1° buffer is clipped. Each line is sampled
  every 4 km, gaps are filled by a hex line walk, and a cell the line only clips at a corner is dropped. A pair
  appears once, with its best class/tier.
* **Rail tiers**: 0 = 高速铁路 = every OSM `highspeed=yes` line (≥ 250 km/h, untagged, and the 200–249 km/h lines the
  source flags `highspeed: true`; China's own statistics count high-speed rail from 200 km/h); 1 = 普速铁路 = other
  `usage=main` lines. HSR wins over conventional on a shared pair. Rail link name = the line name seen most often
  on that link. **Road class** 0 = `highway=motorway` (no ramps); name = route number (G before S, fewer digits,
  lower number), else the road name.
* **Airports**: every airport in the CAAC bulletin with ≥ 1,000,000 passengers (2025: 109); `hub` by CAAC's size
  groups; `id` = IATA, else ICAO; `passengers` counts arrivals + departures (replaces US `enplanements`).
  **Ports**: the 30 largest MOT 主要港口 by cargo tonnage (`cargo_t`, tonnes, replaces US `tons`); `rank` is the
  publisher-wide rank. Hong Kong, Macau and Taiwan are in neither table and are absent (not zero); `notes` says so.
* A site's `cell` is the Chinese land cell at its point, else the nearest within 2 rings; `x`/`y` stay the true
  position. `county` = the source's county adcode when world.json knows it, else the county polygon at the point;
  `cbsa` = cities.json id (prefecture adcode) holding that county; `state` = province code. Null values stay null.

### wonders.json (eager)

Built by `pipeline/build/wonders.py` from `cn_wonders` (UNESCO open data, 新华网 national-park announcement,
文化和旅游部 5A directory, 教育部 双一流 lists, Wikidata/OSM coordinates) and `cn_boundaries`; `cities.json` (if
present) for `cbsa`. About 105 kB, 143 wonders. Version **2** (China).

```jsonc
{
  "version": 2,
  "vintage": {"unesco": "UNESCO 世界遗产名录（…截至2026年）", "parks": "…", "scenic_5a": "…", "universities": "…"},
  "sources": ["cn_wonders", "cn_boundaries"],
  "rules": [{"id": "unesco_whs", "kind": "monument", "kinds": ["monument", "natural"], "year": 2026, "text": "中国境内全部61处…"},
            {"id": "national_park", "kind": "natural", "kinds": ["natural"], "year": 2021, "text": "…"},
            {"id": "scenic_5a", "kind": "landmark", "kinds": ["landmark"], "year": 2007, "text": "…"},
            {"id": "university", "kind": "university", "kinds": ["university"], "year": 2022, "text": "…"}],
  "national": {"unesco_whs": 61, "unesco_by_category": {"cultural": 42, "natural": 15, "mixed": 4},
               "national_parks": 5, "scenic_5a": 358, "scenic_5a_first_batch": 65, "double_first_class": 144},
  "wonders": [{"id": "whc-437", "name": "泰山", "short": "泰山",       // short = map label
               "kind": "natural|monument|landmark|university",          // must be in its rule's `kinds`
               "rule": "unesco_whs", "rank": 1,                         // 1-based listing order within the rule
               "metrics": {…},                                          // per rule, below; unknown values are null
               "desc": "1987年列入联合国教科文组织《世界遗产名录》…",   // Chinese, the data-backed reason
               "x": …, "y": …, "cell": …, "cells": null,                // cells: always null (no open boundaries)
               "county": "370902" | null, "cbsa": "370900" | null, "state": "37", "curated": false,
               "geo": "unesco|wikidata|wikidata_search|osm|county_seat|prefecture_seat|province_centroid",
               "approx": false,                                         // true for seat/centroid positions
               "name_en": "…",                                          // UNESCO only
               "wikidata": "Q…" | null,                                 // parks, 5A, universities
               "point_note": "…"}],                                     // optional: why the point is not the source's
  "unplaced": [{"rule": "scenic_5a", "name": "小三峡－小小三峡旅游区", "reason": "…"}]  // listed but not on the map
}
```

* Rules (all published lists, none curated):
  * `unesco_whs`: every World Heritage site in China (61; a transnational site once, at its Chinese part). Cultural →
    `monument`; natural and mixed → `natural`. Ranked by inscription year, then WHC id. Metrics `{whc_id, category,
    inscribed, criteria, area_ha, transnational, provinces}`; UNESCO's area 0 (青城山—都江堰) is written null.
    明清故宫 is placed at 北京故宫 (UNESCO's point is the 沈阳 part), with `point_note`.
  * `national_park`: every formally established 国家公园 (the 5 of 2021-10-12), ranked by area. Metrics
    `{established, area_km2, provinces}`.
  * `scenic_5a`: the first 5A batch (2007, 65 areas) minus the 28 whose core is a World Heritage component
    (`FIVE_A_IN_WHS` in wonders.py names the WHS of each), ordered by province code (not a ranking). Metrics
    `{designated, batch}`.
  * `university`: the 41 首轮“一流大学建设高校” (2017 A/B, military excluded) still on the 2022 双一流 list; A first,
    then B, list order within. Metrics `{rd_cny, rd_year, double_first_class, world_class_2017}`; `rd_cny`/`rd_year`
    are null because 教育部 publishes no per-university R&D table (the rule text says so).
* `state` is the province code; the county decides it, except that a point whose county is in another province
  than the source files the site under takes the nearest county of the filed province within 8 km.
* Several wonders may share a hex (北京 has many); readers should not assume one wonder per cell.

## sources.json

A list of `{id, title, publisher, homepage, license, description, used_for, vintage, files: [{file, url, retrieved, sha256, bytes}], used_by}`.
Only sources the map uses are listed (a builder REQUIRES it, or it has a processed interim); `used_by` names the
builders that read it. `vintage` is a string (a source's per-list vintage dict is joined with "；").
`files` lists only files the latest `process()` used (`_files`), or every manifest entry if the source didn't say. A file
saved by `download_prefix()` has a `partial` note in the manifest, and its `sha256`/`bytes` describe the saved part.

## Browser module boundaries (web/js)

* `world.js`: `prepareWorld(world, cities, extras) → w` with `w.grid`, `w.raw`, `w.stateColor[]`, `w.cityByCell: Map<cell, city>`;
  `applyLens(w, lens, band = null)` sets `w.colors`/`w.rgb`; exports `WATER = -1`, `FOREIGN = -2`.
* `camera.js`: `Camera` with `fit()`, `toScreen()`, `toWorld()`, `zoomAt()`, `panBy()`, `centerOn()`, `flyTo(x, y, scale, ms)`,
  `step(dt) → bool stillMoving`, `view()`.
* `render/*`: map drawing and banners. `main.js` owns input, state and wiring. `ui/*` owns DOM panels.
* The `state` object (owned by `main.js`, read by `render/*`): `cities`, `lens` (a lenses.json lens or null = terrain),
  `band` (`[t0, t1]` in normalised lens units 0..1, or null: cells outside are dimmed, see `applyLens`), `hoverCell`,
  `selectedCity` (a city object or null), `selectedState` (a state index, abbr, fips or `{index|abbr|fips}`, or null;
  resolved with `world.js` `stateIndex(w, ref)`), `showResources`.
* `render/snapshot.js`: `renderToCanvas(target, cam, w, state, nation, opts) → {cam, hits}` draws a full frame off-screen
  (share images, OG cards) without touching the on-screen cache. `target` is a canvas, OffscreenCanvas or 2D context;
  `opts`: `banners = true`, `overlay = true`, `dpr = 1`, `fit = "contain"|"cover"|"same"`, or an explicit `scale`, `x`, `y`.

## Browser extension API (window.__app; main.js "extension API", app/api.js)

Extensions live in `web/js/ext/<name>/index.js` and export `install(app)`; `ext/index.js` loads `cityView` and `layers`
(expressways, rail, airports, ports and wonders). usaciv's `advisors` dashboard is not part of phase 1. The API:

**Data.**
* `app.data.<name>`: the core files (`world`, `cities`, `states`, `nation`, `resources`, `sources`) are loaded
  before anything runs (`lenses` is an empty lens file in phase 1: lenses.json is not requested). Optional files: `undefined` until loaded, `null` when missing (404) or invalid.
* `app.loadData(name) → Promise<data | null>`: loads `data/<name>.json` once (cached promise; later calls return the same
  promise) and sets `app.data[name]`. Emits `"data"` `{name, data}` when it arrives. `infrastructure` and
  `wonders` are requested automatically right after the first frame. `app.loadCounties()` resolves `null` without a
  request (no counties.json in phase 1).

**Static map layers** (art that belongs in the cached map, drawn once per cache render):

```js
const off = app.registerStaticLayer({
  id: "roads",                 // unique; registering the same id again replaces the layer
  z: 55,                       // where it draws among the built-in steps (app.layerZ / render/map.js Z)
  draw(ctx, vp, w, o) {},      // required. ctx starts in world km (saved/restored around the call)
  visible() { return on; },    // optional; false = not drawn, not hit-tested (part of the cache key)
  sig() { return "v1"; },      // optional; any string that changes when the art must re-render (cache key)
  minRpx: 6, maxRpx: Infinity, // optional zoom range in hex radius css px (drawn when minRpx <= Rpx < maxRpx)
  hit(xKm, yKm, Rpx) { return item | null; },   // optional hover / click test, pointer in world km
  tooltip(item) { return "<b>html</b>" | {text: "plain"} | null; },  // optional; a string is HTML: escape data yourself
  click(item, ev) { return true; },             // optional; true consumes the click (see below)
  warm(ctx, vp, w, o) {},      // optional; paint sprites for vp's zoom in idle time (stamps may land anywhere)
  snapshot: true,              // default true: drawn into share images too
});
off();   // or app.unregisterStaticLayer("roads" | layer)
```

* `o` = `{Rpx, s, dpr, lod, lens, selectedCity, showResources, snapshot, app, cells, range: {r0, r1, c0, c1},
  world(), screen(), toScreen(x, y) → [css px]}`. `cells` are the visible cell indices; `o.screen()` switches ctx to
  screen css px of the cache canvas (use `o.toScreen`), `o.world()` back. Use sprites (`render/art/sprites.js`
  getSprite/drawSprite) for anything richer than a few paths.
* Built-in z steps: `WATER 10`, `LAND 20` (land tiles), `GRID 30`, `GLYPHS 40` (terrain), `RIVERS_BORDERS 50`, `CITIES 60`
  (city tiles), `FOG 70` (edge mist), `RESOURCES 80` (screen-space icons), `LABELS 90` (state names). A layer with z
  between two steps draws after the lower one; equal to a step = right after it. Suggested slots: 45 terrain
  improvements, **55 roads and rail**, 58 restricted ground / protected land hatching, **65 sites** (ports, airports,
  wonders); chinaciv adds `cn-dashes` at 52 (main-map 断续线 pieces and island labels) and `cn-inset` at 92 (the opaque
  南海诸岛 box, above the province names; render/china.js).
* The cache key includes every layer's id, `visible()` and `sig()`, so toggling or restyling re-renders the cache and
  nothing else does. Errors in `draw`/`hit`/`sig`/... are logged once per layer and the layer is skipped.
* **Performance**: nothing may animate continuously (an idle map draws no frames); keep each layer under ~3 ms per cache
  render at typical zooms (time it with `drawStatic(..., {layers: app.staticLayers(), timings: T})`: it reports
  `layer:<id>`); precompute geometry once (not per draw); cull to `vp`.
* `app.staticLayers()` lists the registered layers; `app.hitLayer(mx, my)` (screen css px) → `{layer: id, item} | null`.

**Hover and click.** The hover tooltip asks the layers (highest z first, only those drawn at the current zoom) after the
city banners: the first non-null `hit()` wins and its `tooltip(item)` is shown (the cell tooltip otherwise). The
`"hover"` event payload is `{cell, city, resource, x, y, layer, item}` (`layer` = id or null). A click builds
`ev = {cell, city, resource, state, x, y, pointerType, layer, item}`; outside a mode the layer's `click(item, ev)` goes
first (true consumes it), then the `"mapclick"` handlers, then the default (select city/state). While a mode is active
(City View) the `"mapclick"` handlers go first and the layer's `click` only after them.

**Map toggles.** `app.ui.addMapToggle({id, label, icon, get() → bool, set(on), title?, default?}) → remove()`: a switch
in the "Map" menu next to the Resources toggle in the lens dock (one button + a small menu, so it fits phones). `set` is
yours (flip the state your layer's `visible()` reads); main redraws. The hash key `layers` lists the switches that are on
(`#layers=roads,rail`, `layers=none`) and is written only while some switch differs from its default; switches
added after load are set from it, and ids whose extension has not loaded yet stay in the URL. `app.ui.mapToggles()` →
`[{id, label, on}]`. `app.ui.setMapToggle(id, on) → bool` switches one from code exactly as the menu would (redraw,
hash); false if no toggle has that id (yet).

**URL.** Core keys: `lens`, `city` (6-digit city id, e.g. `440300`), `state`, `at`, plus extension keys (`view`,
`layers`, ...). `#city=440300&view=city` opens the 深圳 City View.
* `#state=` accepts a 2-digit province code (`44`), its 简称 (`粤`) or a name; a link keeps the form it was opened with.
* `at=x,y,z`: `x`, `y` = the map-km point at the centre of the screen (rounded), and `z` = **log2(camera scale ÷
  home-fit scale)**, the zoom relative to the "whole country fits" view: `0` = home framing, `1` = twice as close,
  negative = zoomed out past it. It is relative so a link frames the same area on any screen size; it is *not* the
  absolute scale (css px per km) that `app.flyTo(x, y, scale)` and `camera.scale` use. Convert with
  `scale = fitScale × 2^z`. `at` is written only once the user (or an extension) has moved the camera.
* When the hash is written: during a fly-to the link names the **destination** right away (within one 350 ms debounce
  of the flight starting); after a pan or wheel zoom it catches up 350 ms after the camera settles; `app.setMode`
  writes it on the next task. Lens, selection and mode changes push a history entry (Back undoes them); camera moves
  replace the current one. `app.hash.flush()` writes immediately (Share calls it before copying).

**Optional state and debug handles** (not data contracts; don't rely on them from other extensions without asking):
* `state.cityBadges`: an optional `Map<city id, {label, color: "#rrggbb"}>` that `render/banners.js` reads to draw a
  city-type tab on banners that show their yield row. Nothing fills it in phase 1 (no districts.json).
* City display size (`world.js` prepareWorld): `city.sizePop` = `population` ?? `pop_census_2020` (the banner shows the
  census figure dimmed when the stats year has none); `city.drawPop` adds a drawing weight of 1.5 million for Taiwan's
  six cities, which have no population in this build. Both are browser-only, never written to data files.
* `app.cityView.model`: read-only getter on the City View's current model (debugging).
* `app.mapArt = {model, on, layers}`: added by `ext/layers` for debugging. `model` holds `installations`, `ports`,
  `airports`, `wonders`, each item `{data (the json row), cell, x, y}`. The layers' hit items have the shape
  `{kind: "port"|"airport"|"wonder", data}`.

**Who reads which fields.** The City View reads cities.json, nation.json, resources.json, wonders.json and
infrastructure.json (`cbsa`, `cell`). Update `web/js/ext/cityView` when renaming a field in those files.

**Lenses.** The lens machinery (`ui/lenses.js`, `applyLens`) is kept from usaciv but idle: phase 1 ships no lenses.json,
so the lens dock and the 透镜 Almanac page are hidden. A phase-2 lens file would follow usaciv's lenses.json shape
(`{vintage, groups, lenses: [{id, name, group, unit, format, ramp, domain, values: [per cell]}]}`).
## 第二阶段数据文件

- `lenses.json` 的 `values` 与世界格网一一对应，`region_values` 按城市或省级编号提供相同指标。城镇化率使用 0–1 的比例，人口增长使用可带负号的比例。缺失指标用 `null`。
- `history.json` 按地区代码与年份存放人口和现价 GDP。地级数据可用 `population_source`、`gdp_source` 链接到原表，用 `population_step` 标记原表的取整精度。港澳台的 GDP 同时保留原币、币种和年平均汇率换算信息。高铁行依次包含起点格、终点格、核实的开通或全线贯通年、线路名和来源链接。未能匹配年份的边不进入历史线路。全国高铁营业里程来自铁道统计公报。
- `counties.json` 存放每个县区的区划代码、上级、概化边界、包围框、驻地和命中的基础地图格数。已获得常住人口等指标的县区带有 `stats`。几何和统计可分别存在。
- `builtup.json` 的行依次为投影坐标 X、Y、建筑表面面积所在的 5 万平方米档。来自 2020 年 JRC 30 弧秒 GHS-BUILT-S 数据，按阈值提取。
- `zones.json` 的地图点在 `zones`，名称、代表片区和官方名录可独立查看。点位用于定位。
- `sources.json` 中 `curated: true` 表示根据正式公开资料整理。每条文件记录保留发布方链接及表名。
