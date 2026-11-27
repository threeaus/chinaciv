"""sources.json – the Almanac's bibliography (资料来源), generated from the registry + manifests.

Lists every source the map actually uses: a registered source is cited when a builder REQUIRES it or when it has
a processed interim (some sources are read by other sources' process(), e.g. cn_boundaries). A registered source
that is neither (a spare) is left out, so the Almanac never cites data the map does not
show. Each source cites only the raw files its latest process() used (interim "files"), or every manifest entry if
it did not say. `used_by` names the builders that read it. A per-list `vintage` dict is flattened to one Chinese
string so the Almanac can print it.
"""

from ..core.fetch import read_manifest
from ..core.store import load_interim_payload, write_web
from ..sources import SOURCES
from .phase2_stats import add_stat_sources
from .infrastructure import add_hmt_sources
from .history import add_history_sources
from .counties import add_geography_sources
from .lenses import add_lens_sources

REQUIRES: list[str] = []
PRODUCES = ["sources.json"]
RUN_LAST = True


def _vintage(v):
    if isinstance(v, dict):
        return "；".join(str(x) for x in v.values() if x) or None
    return v


def _users() -> dict[str, list[str]]:
    from . import BUILDERS  # late import: this module is itself discovered by the build package

    users: dict[str, list[str]] = {}
    for name, mod in BUILDERS.items():
        for r in getattr(mod, "REQUIRES", []):
            users.setdefault(r, []).append(name)
    return users


def build() -> None:
    users = _users()
    out, skipped = [], []
    for s in SOURCES:
        try:
            payload = load_interim_payload(s.id)
        except FileNotFoundError:
            payload = None
        if payload is None and s.id not in users:
            skipped.append(s.id)
            continue
        payload = payload or {}
        manifest = read_manifest(s.id)
        used = payload.get("files")  # raw files the latest process() said it used, else cite them all
        names = sorted(manifest) if used is None else [f for f in sorted(used) if f in manifest]
        if used is not None and len(names) < len(used):
            print(f"    ! {s.id}: {len(used) - len(names)} used file(s) missing from manifest")
        files = [
            {"file": name, "url": m["url"], "retrieved": m["retrieved"], "sha256": m["sha256"], "bytes": m["bytes"]}
            for name in names
            for m in [manifest[name]]
        ]
        out.append({**s.info.to_dict(), "vintage": _vintage(payload.get("vintage")), "files": files,
                    "used_by": sorted(users.get(s.id, []))})
    add_stat_sources(out)
    add_hmt_sources(out)
    add_history_sources(out)
    add_geography_sources(out)
    add_lens_sources(out)
    write_web("sources.json", out)
    print(f"    {len(out)} sources, {sum(len(x['files']) for x in out)} files"
          + (f"; not used by the map (left out): {skipped}" if skipped else ""))
