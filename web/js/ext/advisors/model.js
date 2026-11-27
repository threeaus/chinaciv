export const VIEWS = {
  energy: { label: "能源", title: "能源与资源", note: "装机仅统计地图收录的在运站点，单位为兆瓦。" },
  economy: { label: "经济", title: "区域经济", note: "以 2023 年现价人民币比较，各地公布的人口与产业口径见详情。" },
  culture: { label: "文化", title: "文化与自然遗产", note: "按地图的收录规则浏览。分布数量随收录范围变化。" },
  explorer: { label: "探索", title: "数据探索", note: "按地区和指标查询。点击列表条目可在地图上定位。" },
};

export const ECONOMY = {
  gdp: { label: "GDP", format: "cny", value: (r) => r.gdp },
  "gdp-per-capita": {
    label: "人均 GDP", format: "cny",
    value: (r) => r.population > 0 && r.gdp_year === r.population_year && r.gdp != null ? r.gdp / r.population : null,
  },
  population: { label: "人口", format: "people", value: (r) => r.population },
  primary: { label: "第一产业增加值", format: "cny", value: (r) => r.gdp_by_industry?.primary },
  secondary: { label: "第二产业增加值", format: "cny", value: (r) => r.gdp_by_industry?.secondary },
  tertiary: { label: "第三产业增加值", format: "cny", value: (r) => r.gdp_by_industry?.tertiary },
};

export const WONDERS = {
  unesco_whs: "世界遗产", national_park: "国家公园", scenic_5a: "5A 级景区", university: "一流大学",
};

export function rankRows(rows, direction = "desc") {
  const order = direction === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (!Number.isFinite(a.value)) return Number.isFinite(b.value) ? 1 : 0;
    if (!Number.isFinite(b.value)) return -1;
    return order * (a.value - b.value);
  });
}

export function byPlace(app, scope, value) {
  const national = scope === "state";
  const rows = national ? app.data.states : app.data.cities;
  return (rows || []).map((place, index) => ({
    id: national ? place.fips : place.id,
    name: place.full || place.name,
    value: value(place),
    state: national ? index : null,
    x: national ? place.label?.x : place.x,
    y: national ? place.label?.y : place.y,
    cell: place.cell,
  }));
}

export function explorerMetrics(app, scope) {
  const fields = {
    ...ECONOMY,
    science: { label: "科研行业从业人员", format: "people", value: (r) => r.yields?.science },
    culture: { label: "文体娱乐业从业人员", format: "people", value: (r) => r.yields?.culture },
  };
  for (const lens of app.data.lenses?.lenses || []) {
    if (lens.group !== scope || lens.id.endsWith("gdp-per-capita")) continue;
    fields[lens.id.slice(scope.length + 1)] = {
      label: lens.name.split(" · ")[0], format: lens.format,
      value: (r) => lens.region_values?.[r.fips || r.id],
    };
  }
  return fields;
}
