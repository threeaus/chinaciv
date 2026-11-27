"""Create the optional detailed built-up overlay.

Run `uv run --with pillow --with numpy --with shapely python -m pipeline.ghsl_built`
after fetching DataV boundaries. The delivered viewer needs none of those packages.
"""

import concurrent.futures
import json
from io import BytesIO
from zipfile import ZipFile

from .core import fetch
from .core.geo import MapProjection
from .core.paths import RAW, WEB_DATA
from .core.store import write_web

SOURCE = "ghsl_built"
PRODUCT = "GHS_BUILT_S_E2020_GLOBE_R2023A_4326_30ss"
TILES = f"https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_BUILT_S_GLOBE_R2023A/{PRODUCT}/V1-0/tiles/"
MINIMUM = 50_000


def names():
    # The GHSL 10° tiles spanning the populated Chinese land area fit these rows and columns.
    return [f"{PRODUCT}_V1_0_R{row}_C{col}.zip" for row in range(4, 9) for col in range(26, 33)]


def tile_paths():
    paths = []
    for name in names():
        path = RAW / SOURCE / name
        if path.exists():
            paths.append(path)
            continue
        print(f"Fetching {name}", flush=True)
        paths.append(fetch.download(SOURCE, TILES + name, name, timeout=35, expect_binary=True))
    return paths


def main():
    import numpy as np
    from PIL import Image
    from shapely import contains_xy, make_valid, prepare, union_all
    from shapely.geometry import shape

    world = json.loads((WEB_DATA / "world.json").read_bytes())
    project = MapProjection(**world["projection"])
    outline = json.loads((RAW / "cn_boundaries" / "datav" / "100000_full.json").read_bytes())
    land = union_all([make_valid(shape(f["geometry"])) for f in outline["features"]
                      if f["properties"].get("level") == "province"])
    prepare(land)

    def convert(path):
        with ZipFile(path) as archive:
            name = next(n for n in archive.namelist() if n.lower().endswith(".tif"))
            with Image.open(BytesIO(archive.read(name))) as raster:
                dx, dy, _ = raster.tag_v2[33550]
                _, _, _, lon0, lat0, _ = raster.tag_v2[33922]
                pixels = np.asarray(raster)
                rows, cols = np.where((pixels >= MINIMUM) & (pixels < 1_000_000))
        lons = lon0 + (cols + 0.5) * dx
        lats = lat0 - (rows + 0.5) * dy
        inside = contains_xy(land, lons, lats)
        points = []
        for lon, lat, val in zip(lons[inside], lats[inside], pixels[rows[inside], cols[inside]]):
            x, y = project(float(lon), float(lat))
            points.append([round(x, 1), round(y, 1), int(val // MINIMUM)])
        return points

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pools:
        groups = list(pools.map(convert, tile_paths()))
    points = [point for group in groups for point in group]
    write_web("builtup.json", {
        "source": SOURCE, "year": 2020, "resolution": "30 弧秒（约 1 公里）", "minimum_square_metres": MINIMUM,
        "note": "卫星推算的建筑表面面积超过阈值的格网。栅格与县界来自不同坐标数据源，近看可能有轻微偏移。",
        "tiles": names(), "points": points,
    })


if __name__ == "__main__":
    main()
