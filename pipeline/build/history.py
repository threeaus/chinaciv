"""Annual population and nominal GDP, with separately verified railway openings."""

import json

from .phase2_stats import DATA, TW_ACCOUNTS, TW_FX, catalogue, read_curated
from ..core.paths import WEB_DATA
from ..core.store import write_web

REQUIRES = ["cities.json", "states.json", "infrastructure.json"]
PRODUCES = ["history.json"]
LOCAL_INPUTS = [DATA / name for name in ("province_history.json", "city_history.json", "rail_openings.json")]
YEARS = range(2020, 2025)
TW_POP_URL = "https://ws.mofa.gov.tw/001/Upload/402/relfile/20/1217/88666274-860e-4eab-aa5f-8dc213cc8fc4.pdf"
MO_POP_URL = "https://yearbook.gcs.gov.mo/yearbook_pdf/2025/myb2025cAP28.pdf"
HK_POP_URL = "https://www.censtatd.gov.hk/en/data/stat_report/product/B1010002/att/B10100022025MM06B0100.pdf"
HK_GDP_URL = "https://www.censtatd.gov.hk/en/data/stat_report/product/B1010003/att/B10100032026AN26B0100.pdf"
MO_GDP_URL = "https://www.dsec.gov.mo/getAttachment/7818035F-D5D4-4481-A790-F779E1122130/C_PIBRP_PUB_2024_Y.aspx"
HK_FX = "https://www.stats.gov.cn/sj/ndsj/2025/html/C18-09.jpg"
MO_FX_PEG = "https://www.amcm.gov.mo/pt/currency/currency-in-circulation-in-macao/law-regulations-currency/currency-in-circulation-in-macao"
FX_2021 = "https://www.cbc.gov.tw/dl-190259-b982d6ead4144f47ade540a5f9baa57b.html"
FX_2022 = "https://www.cbc.gov.tw/dl-195557-aea121a9ebc648938102d0abbf1df5bd.html"
MILEAGE = {
    2020: (38000, "https://source.nra.gov.cn/xwzx/zlzx/hytj/202204/t20220405_338098.shtml"),
    2021: (40000, "https://www.nra.gov.cn/xwzx/xwxx/xwlb/202204/t20220428_326348.shtml"),
    2022: (42000, "https://www.nra.gov.cn/xwzx/xwxx/xwlb/202305/t20230529_341754.shtml"),
    2023: (45000, "https://source.nra.gov.cn/xwzx/xwxx/xwlb/202406/t20240628_345561.shtml"),
    2024: (48000, "https://www.nra.gov.cn/xwzx/xwxx/xwlb/202506/t20250606_348989.shtml"),
}


def make_rail_history(rail, openings):
    return [[a, b, openings[name][0], name, openings[name][1]] for a, b, tier, name in rail
            if tier == 0 and name in openings and openings[name][0] <= max(YEARS)]


def places_history(base, cities, states, city_history):
    for rows, data, key in ((cities, city_history, "id"), (states, base["provinces"], "fips")):
        for place in rows:
            annual = data.setdefault(place[key], {})
            for metric in ("population", "gdp"):
                year = place.get(metric + "_year")
                value = place.get(metric)
                if year in YEARS and value is not None:
                    annual.setdefault(str(year), {}).setdefault(metric, value)
    base["cities"] = city_history


def regional_history(base):
    tw_pop = [23_561_236, 23_375_314, 23_264_640, 23_420_442, 23_400_220]
    hk_pop = [7_426_700, 7_401_500, 7_472_600, 7_527_900, 7_534_200]
    mo_pop = [683100, 683200, 672800, 683700, 688300]
    tw_gdp = [20_023_752, 21_773_291, 22_820_430, 23_598_348, 25_737_088]
    hk_gdp = [2_675_793, 2_867_973, 2_808_922, 2_981_210, 3_186_526]
    mo_gdp = [201_964, 245_241, 201_060, 367_904, 397_560]
    tw_rate = [4.2862, 4.3452, 4.4198, 4.3973, 4.4610]
    hk_rate = [1 / r for r in (0.8893, 0.8300, 0.8589, 0.9002, 0.9127)]
    mo_rate = [1.03 * r for r in hk_rate]
    provinces = base["provinces"]
    for code, currency, population, gdp, rates in (("71", "TWD", tw_pop, tw_gdp, tw_rate),
                                                  ("81", "HKD", hk_pop, hk_gdp, hk_rate),
                                                  ("82", "MOP", mo_pop, mo_gdp, mo_rate)):
        provinces[code] = {
            str(y): {"population": p, "gdp": round(g * 10**6 / r), "gdp_local": g * 10**6,
                     "gdp_local_currency": currency, "gdp_fx_local_per_cny": round(r, 6)}
            for y, p, g, r in zip(YEARS, population, gdp, rates)
        }


def build():
    cities, states, infra = (json.loads((WEB_DATA / name).read_bytes()) for name in REQUIRES)
    base = read_curated("province_history.json")
    additional = read_curated("city_history.json")
    regional_history(base)
    city_rows = additional.get("cities", {})
    for code in ("11", "12", "31", "50", "81", "82"):
        city_rows[code + "0000"] = base["provinces"][code]
    places_history(base, cities, states, city_rows)
    base.update(years=list(YEARS), rail=make_rail_history(infra["rail"], read_curated("rail_openings.json")),
                rail_mileage={y: {"km": km, "source": source} for y, (km, source) in MILEAGE.items()},
                city_sources=additional.get("sources", []),
                rail_note="显示已核实开通年份且能匹配底图的高铁线路。部分分段通车线路采用全线贯通年份，线形按六边形概化。")
    write_web(PRODUCES[0], base)


def add_history_sources(sources):
    stats = read_curated("province_history.json")
    if not stats:
        return
    links = [("分地区年末人口（2025 年鉴表 2-5）", stats["sources"]["2024"]["population"])]
    for year, year_links in stats["sources"].items():
        links.extend([(f"{year} 年分地区 GDP（表 3-9）", year_links["gdp"]),
                      (f"{year} 年全国 GDP（表 3-1）", year_links["national_gdp"])])
    links += [("台湾地区户籍人口", TW_POP_URL), ("台湾地区生产总值", TW_ACCOUNTS), ("2020–2021 年汇率", FX_2021),
              ("2022 年汇率", FX_2022), ("2023–2024 年汇率", TW_FX), ("澳门年末人口", MO_POP_URL),
              ("澳门现价 GDP（修订表）", MO_GDP_URL), ("香港人口统计", HK_POP_URL), ("香港现价 GDP", HK_GDP_URL),
              ("人民币兑港元年均价", HK_FX), ("澳门元与港元联系汇率", MO_FX_PEG)]
    links += [(row["title"], row["url"]) for row in read_curated("city_history.json").get("sources", [])]
    catalogue(sources, "cn_history", "2020–2024 年人口与地区生产总值", "国家统计局、地方统计机构",
              "统计年鉴与地区官方人口资料。台湾地区为户籍人口，GDP 按年均汇率折算。", links, ["history"], "2020–2024")
    rail = read_curated("rail_openings.json")
    if rail:
        catalogue(sources, "rail_history", "历年高铁开通资料", "国家铁路局与各级政府",
                  "与 OpenStreetMap 高铁路网的名称对应，部分分段通车线路采用全线贯通年份。",
                  ([(name, src) for name, (_year, src) in rail.items()]
                   + [(f"{year} 年铁道统计公报", url) for year, (_km, url) in MILEAGE.items()]), ["history"], "截至 2024")


def check(web_dir):
    path = web_dir / PRODUCES[0]
    if not path.exists():
        return [("NOTE", "history.json not built")]
    history = json.loads(path.read_bytes())
    years = {str(y) for y in YEARS}
    if years != set(history["nation"]) or len(history["provinces"]) != 34:
        return [("FAIL", "history.json missing national years or mainland provinces")]
    if any(not all(row.get(metric, 0) > 0 for metric in ("population", "gdp"))
           for data in history["provinces"].values() for y in years for row in (data.get(y, {}),)):
        return [("FAIL", "history.json has a missing population or GDP observation in the provincial series")]
    return [("PASS", f"history.json: {len(history['years'])} years, {len(history['rail'])} verified rail links")]
