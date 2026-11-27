"""The game-concept → real-data mapping for the five yields, in one place (docs/CN_PLAN.md §5.3).

Helper module (no build()): used by cities.py (cities.json, nation.json) and states.py (states.json). The YIELDS list
is published in nation.json, so the UI and the Almanac describe exactly what was computed.

* Gold 💰 = 地区生产总值 (GDP, 元, current prices) of the stats year (cn_stats_city).
* Food 🌾 / Production ⚙️ / Science 🔬 / Culture 🎭 each use **one basis for every city**, the first in this priority
  order that has data for ≥ BASIS_SHARE (75%; the plan said 90%) of the banner cities; otherwise the yield is null everywhere (never a
  mix of bases, never 0 for unknown) and its description says why:

  | Yield      | Priority 1: employment (persons, cn_city_industry)          | Priority 2: value (元)                       |
  |------------|-------------------------------------------------------------|----------------------------------------------|
  | Food       | A 农、林、牧、渔业                                          | 第一产业增加值 (cn_stats_city va_primary)     |
  | Production | B 采矿业 + C 制造业 + D 电力热力燃气水 + E 建筑业           | 第二产业增加值 (cn_stats_city va_secondary)   |
  | Science    | I 信息传输软件和信息技术服务业 + M 科学研究和技术服务业     | R&D 经费内部支出 (cn_city_industry rd_expenditure) |
  | Culture    | R 文化、体育和娱乐业                                        | –                                            |

  An employment sum needs every listed section known for that city (else null for that city).
"""

from __future__ import annotations

BASIS_SHARE = 0.75  # CN_PLAN §5.3 said 90%; lowered to 75% at integration so the three-sector value added
# (267/344 cities, 78%) can drive Food/Production. Cities without it stay null; bases are still never mixed.
YIELD_KEYS = ["food", "production", "gold", "science", "culture"]

# Per yield, in priority order: (unit, industry sections | field name).
BASES: dict[str, list[tuple[str, object]]] = {
    "food": [("persons", ["A"]), ("cny", "va_primary")],
    "production": [("persons", ["B", "C", "D", "E"]), ("cny", "va_secondary")],
    "gold": [("cny", "gdp")],
    "science": [("persons", ["I", "M"]), ("cny", "rd_expenditure")],
    "culture": [("persons", ["R"])],
}
CNY_FIELD = {"food": "va_primary", "production": "va_secondary", "gold": "gdp", "science": "rd_expenditure"}

# Display metadata (labels are Chinese, the frontend shows them as is).
META = {
    "food": {"icon": "y-food", "emoji": "🌾", "label": "粮食", "color": "#7fbf3f"},
    "production": {"icon": "y-production", "emoji": "⚙️", "label": "生产力", "color": "#d9823b"},
    "gold": {"icon": "y-gold", "emoji": "💰", "label": "金币", "color": "#f2c94c"},
    "science": {"icon": "y-science", "emoji": "🔬", "label": "科研", "color": "#4fa3e0"},
    "culture": {"icon": "y-culture", "emoji": "🎭", "label": "文化", "color": "#b07ce0"},
}

# What each basis is, in words (Chinese, for the yield description).
BASIS_TEXT = {
    ("food", "persons"): "农、林、牧、渔业（A 门类）城镇非私营单位就业人员",
    ("food", "cny"): "第一产业增加值（元，当年价）",
    ("production", "persons"): "采矿业、制造业、电力热力燃气及水生产和供应业、建筑业（B–E 门类）城镇非私营单位就业人员",
    ("production", "cny"): "第二产业增加值（元，当年价）",
    ("gold", "cny"): "地区生产总值（元，当年价）",
    ("science", "persons"): "信息传输、软件和信息技术服务业与科学研究和技术服务业（I、M 门类）城镇非私营单位就业人员",
    ("science", "cny"): "研究与试验发展（R&D）经费内部支出（元）",
    ("culture", "persons"): "文化、体育和娱乐业（R 门类）城镇非私营单位就业人员",
}


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def basis_name(basis) -> str | None:
    """A short machine name of a basis: 'employment:A', 'employment:B+C+D+E', 'va_primary', 'gdp', … or None."""
    if basis is None:
        return None
    unit, what = basis
    return "employment:" + "+".join(what) if unit == "persons" else str(what)


def basis_value(basis, stats: dict | None, ind: dict | None):
    """The value of one yield basis for a record pair (stats = cn_stats_city record, ind = cn_city_industry record);
    None when unknown. Employment sums need every section known."""
    if basis is None:
        return None
    unit, what = basis
    if unit == "persons":
        emp = (ind or {}).get("emp") or {}
        vals = [emp.get(k) for k in what]
        return sum(vals) if vals and all(_is_num(v) for v in vals) else None
    src = ind if what == "rd_expenditure" else stats
    v = (src or {}).get(what)
    return v if _is_num(v) else None


def coverage(stats: dict, ind: dict, banner_ids: list[str]) -> dict[str, list[tuple[tuple, int]]]:
    """yield key → [(basis, number of banner cities with a value)] for every basis in priority order."""
    out = {}
    for key, options in BASES.items():
        out[key] = [(b, sum(1 for cid in banner_ids
                            if basis_value(b, stats["cities"].get(cid), ind["cities"].get(cid)) is not None))
                    for b in options]
    return out


def choose_bases(stats: dict, ind: dict, banner_ids: list[str]) -> dict[str, tuple | None]:
    """CN_PLAN §5.3: per yield, the first basis with data for ≥ BASIS_SHARE of banner cities, else None.
    Gold is GDP by definition (cities without GDP are null)."""
    cov = coverage(stats, ind, banner_ids)
    n = len(banner_ids)
    out = {}
    for key, rows in cov.items():
        chosen = None
        for basis, have in rows:
            if n and have / n >= BASIS_SHARE:
                chosen = basis
                break
        if key == "gold":
            chosen = rows[0][0]
        out[key] = chosen
    return out


def _pct(have: int, n: int) -> str:
    return f"{have}/{n}（{have / n:.0%}）" if n else "0"


def yield_defs(stats: dict, ind: dict, banner_ids: list[str], bases: dict | None = None) -> list[dict]:
    """The nation.json YIELDS list for the chosen bases: {key, icon, emoji, label, color, unit, industries, basis,
    coverage, description}. `unit` is the chosen basis' unit (the priority-1 unit when the yield is null)."""
    bases = bases if bases is not None else choose_bases(stats, ind, banner_ids)
    cov = coverage(stats, ind, banner_ids)
    n = len(banner_ids)
    year, ind_year = stats.get("year"), ind.get("year")
    emp_label = ind.get("basis_label") or "城镇非私营单位就业人员年末人数"
    out = []
    for key in YIELD_KEYS:
        basis = bases.get(key)
        have = dict((basis_name(b), h) for b, h in cov[key])
        tried = "；".join(f"{BASIS_TEXT[(key, b[0])]}仅 {_pct(h, n)} 个城市有数据" for b, h in cov[key] if b != basis)
        if key == "gold":
            desc = (f"金币 = {year} 年{BASIS_TEXT[(key, 'cny')]}，取自各市（州、盟）及各省 {year} 年国民经济和社会发展统计公报"
                    f"（国家统计局及各地统计局；港澳与台湾地区合计取当地统计，按年均汇率折算人民币）。"
                    f"有数据的城市 {_pct(have['gdp'], n)}，其余置空（非 0）。")
        elif basis is None:
            desc = (f"{META[key]['label']}暂缺（全部置空，非 0）：按规则，每项产出须对所有城市使用同一口径，且该口径须覆盖至少 "
                    f"{BASIS_SHARE:.0%} 的城市；{tried}。")
        elif basis[0] == "persons":
            desc = (f"{META[key]['label']} = {BASIS_TEXT[(key, 'persons')]}（{emp_label}，{ind_year} 年，各省统计年鉴分市分行业表）。"
                    f"有数据的城市 {_pct(have[basis_name(basis)], n)}。")
        else:
            src = (f"{ind_year} 年，各省统计年鉴及《全国科技经费投入统计公报》" if basis[1] == "rd_expenditure"
                   else f"{year} 年，各市（州、盟）统计公报")
            desc = (f"{META[key]['label']} = {BASIS_TEXT[(key, 'cny')]}（{src}）。有数据的城市 {_pct(have[basis_name(basis)], n)}，"
                    f"其余置空（非 0）。" + (f"未采用：{tried}。" if tried else ""))
        unit, what = basis if basis is not None else BASES[key][0]
        out.append({
            "key": key,
            **META[key],
            "unit": unit,
            "industries": list(what) if unit == "persons" else [],
            "basis": basis_name(basis),
            "coverage": round(have[basis_name(basis)] / n, 3) if basis is not None and n else None,
            "description": desc,
        })
    return out


def yields_of(bases: dict, stats: dict | None, ind: dict | None, year: int) -> dict:
    """{yield key: value | None} for one record; Gold only when the GDP is of the stats `year`."""
    out = {k: basis_value(bases.get(k), stats, ind) for k in YIELD_KEYS}
    if (stats or {}).get("gdp_year") != year:
        out["gold"] = None
    return out
