"""Reviewed statistical supplements used by live builds and bundled data refreshes."""

import json
from pathlib import Path

from . import growth
from ..core.paths import WEB_DATA
from ..core.store import write_web

DATA = Path(__file__).parents[1] / "sources" / "data"
YEAR = 2023
TW_GDP = 23_598_348_000_000
TW_RATE = 4.3973  # TWD per CNY, 2023 annual average
TW_ACCOUNTS = "https://ws.dgbas.gov.tw/001/Upload/463/ebook/ebook_350486/pdf/full.pdf"
TW_FX = "https://www.cbc.gov.tw/Public/Data/OpenData/%E7%B6%93%E7%A0%94%E8%99%95/Annual%20Report_CH_2024.pdf"
TW_CITY_SCOPE = "https://www.stat.gov.tw/News_Content.aspx?n=3945&s=103078"
TW_NOTE = "人口为年末户籍人口。GDP 为台湾地区主计总处公布的区域合计，按 2023 年平均汇率折算；主计总处不编制县市 GDP。"
MO_NOTE = ("澳门年末人口由澳门统计暨普查局发布。GDP 原为澳门元，按 1 港元 = 1.03 澳门元及"
           "香港金融管理局 2023 年平均汇率折算。")
CENSUS_SOURCE = "https://www.stats.gov.cn/sj/pcsj/jjpc/5jp/zk/html/A1-08.jpg"
INDUSTRIES = {"science": ("I", "M"), "culture": ("R",)}


def read_curated(name):
    path = DATA / name
    return json.loads(path.read_bytes()) if path.exists() else {}


def apply_population(row, record, comparable=True):
    if not record or row.get("population") is not None:
        return
    pop = record["population"]
    row.update(population=pop, population_year=YEAR, population_source=record["source"])
    if comparable:
        row["growth"] = growth.rate(pop, row.get("pop_census_2020"))
        if row["growth"] is not None:
            row["growth_years"] = [2020, YEAR]


def employment_yields(employment):
    output = {}
    for key, industries in INDUSTRIES.items():
        parts = [employment.get(industry) for industry in industries]
        output[key] = sum(parts) if all(type(value) is int and value >= 0 for value in parts) else None
    return output


def apply_employment(row, record):
    row["yields"].update(employment_yields(record or {}))


def apply_census_definitions(nation, cities, states):
    if not any(nation["nation"]["yields"].get(key) is not None for key in INDUSTRIES):
        return
    n_city, n_state = len(cities), len(states)
    for meta in nation["yields"]:
        key = meta["key"]
        if key not in INDUSTRIES:
            continue
        industries = INDUSTRIES[key]
        city_count = sum(c["yields"].get(key) is not None for c in cities)
        state_count = sum(s["yields"].get(key) is not None for s in states)
        label = ("信息传输、软件和信息技术服务业及科学研究和技术服务业" if key == "science" else "文化、体育和娱乐业")
        state_note = f"，省级覆盖 {state_count}/{n_state}" if n_state else ""
        meta.update(unit="persons", industries=list(industries), basis="census2023:" + "+".join(industries),
                    coverage=round(city_count / n_city, 3) if n_city else None,
                    description=f"2023 年第五次全国经济普查：{label}法人单位从业人员。"
                                f"城市覆盖 {city_count}/{n_city}{state_note}。缺失地区留空。")


def apply_taiwan_gdp(row):
    gdp = round(TW_GDP / TW_RATE)
    row.update(gdp=gdp, gdp_year=YEAR, gdp_local=TW_GDP, gdp_local_currency="TWD",
               gdp_fx_local_per_cny=TW_RATE, gdp_source=TW_ACCOUNTS, note=TW_NOTE)
    row["yields"]["gold"] = gdp


def population_sources():
    return read_curated("population_2023.json")


def census():
    return read_curated("economic_census_employment.json")


def supplement_city(row, populations, employment, comparable=True):
    apply_population(row, populations.get(row["id"]), comparable)
    if row["id"] == "820000" and row.get("population_year") == YEAR:
        row["note"] = MO_NOTE
    if employment:
        apply_employment(row, employment.get("cities", {}).get(row["id"]))


def supplement_state(row, populations, employment):
    code = row["fips"]
    apply_population(row, populations.get(code + "0000"))
    if employment:
        apply_employment(row, employment.get("provinces", {}).get(code))
    if code == "71":
        apply_taiwan_gdp(row)
    if code == "82" and row.get("population_year") == YEAR:
        row["note"] = MO_NOTE


def catalogue(sources, identifier, title, publisher, description, links, used_by, year=YEAR):
    files = [{"file": label, "url": url} for label, url in sorted(set(links))]
    entry = {"id": identifier, "title": title, "publisher": publisher, "homepage": files[0]["url"],
             "license": "公开发布，沿用发布者的数据使用条款", "description": description,
             "vintage": str(year), "used_for": [description], "used_by": used_by, "files": files, "curated": True}
    sources[:] = [s for s in sources if s["id"] != identifier] + [entry]


def add_stat_sources(sources):
    pop = population_sources()
    if pop:
        catalogue(sources, "cn_population_supplement", "2023 年城市常住人口补充", "各地统计机构",
                  "各地统计年鉴、人口抽样调查及统计公报。", [(r["title"], r["source"]) for r in pop.values()],
                  ["cities", "lenses"])
    economic = census()
    if economic:
        city_links = [(f"地级市经济普查公报（{code}）", url) for code, url in economic.get("city_sources", {}).items()]
        catalogue(sources, "cn_economic_census_2023", "中国经济普查年鉴 2023 综合卷", "国家统计局",
                  "法人单位分行业从业人员，用于科研与文化产出。",
                  [("表 1-8 法人单位从业人员", CENSUS_SOURCE), *city_links], ["cities", "states"])
    catalogue(sources, "tw_gdp", "台湾地区生产毛额与汇率", "台湾地区主计总处及中央银行",
              "地区合计现价 GDP、原币金额和按年均汇率折算的人民币金额。",
              [("主计总处《国民所得统计年报》", TW_ACCOUNTS), ("中央银行年报", TW_FX), ("县市 GDP 编制说明", TW_CITY_SCOPE)],
              ["states", "lenses"])


def refresh():
    """Apply the supplements to the prebuilt first-phase files without a raw data rebuild."""
    from .cities import SCOPE_CHANGES, add_ranks
    from .states import rank_yields

    cities, states, nation, sources = (
        json.loads((WEB_DATA / f"{name}.json").read_bytes()) for name in ("cities", "states", "nation", "sources")
    )
    populations, employment = population_sources(), census()
    for city in cities:
        supplement_city(city, populations, employment, city["id"] not in SCOPE_CHANGES)
    for state in states:
        supplement_state(state, populations, employment)
    if employment:
        apply_employment(nation["nation"], employment.get("nation"))
        apply_census_definitions(nation, cities, states)
    for definition in nation["yields"]:
        if definition["key"] == "gold":
            definition["description"] = definition["description"].replace(
                "香港、澳门为特区政府统计数据折算人民币，台湾地区暂缺",
                "港澳与台湾地区合计取当地统计，按年均汇率折算人民币")
    cities.sort(key=lambda c: (c["population"] is None, -(c["population"] or 0),
                               -(c["pop_census_2020"] or 0), c["id"]))
    add_ranks(cities)
    rank_yields(states)
    add_stat_sources(sources)
    for name, data in zip(("cities", "states", "nation", "sources"), (cities, states, nation, sources)):
        write_web(f"{name}.json", data)


if __name__ == "__main__":
    refresh()
