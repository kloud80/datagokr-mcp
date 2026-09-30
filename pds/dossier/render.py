"""설명서 렌더 (KNOWLEDGE-SPEC §8) — Dataset·Edge·Context·Law·CodeList yaml → docs/dossiers/{family 또는 id}.md.

패밀리가 있으면 패밀리 단위 한 장, 없으면 데이터셋 한 장. 결과는 파생물이라 커밋하지 않는다(.gitignore). MCP Resource dataset://{id}의 본문.
"""
from __future__ import annotations

import datetime as dt
import subprocess
from collections import defaultdict
from functools import lru_cache

from jinja2 import Environment, FileSystemLoader

from pds import config
from pds.schema import GROUNDED
from pds.schema import store

OUT = config.ROOT / "docs" / "dossiers"
EV_KO = {"measured": "실측", "law": "법령", "admin_review": "검토결정", "portal_meta": "포털", "inferred": "미확인", "user": "사용자"}


@lru_cache
def _laws():
    return {d["law_id"]: d for d, _ in store.iter_raw("law")}


@lru_cache
def _codes():
    return {c["id"]: c for c, _ in store.iter_raw("code")}


@lru_cache
def _titles():
    return {d["id"]: d["title"] for d, _ in store.iter_raw("dataset")}


def _env():
    env = Environment(loader=FileSystemLoader(config.ROOT / "templates"), trim_blocks=True, lstrip_blocks=True, autoescape=False)
    edges = store.load("edge")
    by_ds = defaultdict(list)
    for e in edges:
        by_ds[e["src"]].append((e, e["dst"]))
        by_ds[e["dst"]].append((e, e["src"]))
    ctx = store.load("context")

    def claims(d, kind):
        return [c for c in d.get("claims") or [] if c["kind"] == kind]

    def ev(c):
        types = sorted({e["type"] for e in c["evidence"]})
        tag = "·".join(EV_KO.get(t, t) for t in types)
        return f"`{c['id']}` [{tag}]" + ("" if any(t in GROUNDED for t in types) else " *(미확인)*")

    def law_articles(lg):
        law = _laws().get(lg.get("law_id") or "")
        if not law:
            return []
        want = set(lg.get("articles") or ["1"])
        return [a for a in law.get("articles") or [] if a["no"] in want][:3]

    def code_ref(f):
        c = _codes().get(f.get("code_list") or "")
        return f"`{c['id']}` ({c['rows']:,}, {c['completeness']})" if c else ""

    def edges_of(d):
        out = []
        for e, other in by_ds.get(d["id"], []):
            on = e.get("on") or {}
            out.append({"id": e["id"], "rel": e["rel"], "other": other, "other_title": _titles().get(other, "")[:30],
                        "on_text": f"{'+'.join(on.get('left') or [])} = {'+'.join(on.get('right') or [])}" + (f" ({on['transform']})" if on.get("transform") else ""),
                        "relationship": e.get("relationship"), "rate": (e.get("verified") or {}).get("match_rate"), "via": on.get("via_mapping")})
        return sorted(out, key=lambda x: (x["rel"] != "joinable", -(x["rate"] or 0)))[:15]

    def contexts(d):
        f, a, s = d["sector"].split("/")
        return [c for c in ctx if any(m.get("dataset") == d["id"] or (m.get("sector") == f"{f} - {a}" and m.get("subsector") in (None, s))
                                      for m in c["members"])]

    env.globals.update(claims=claims, ev=ev, law_articles=law_articles, code_ref=code_ref, edges=edges_of, contexts=contexts)
    return env


def render_all() -> dict:
    env = _env()
    tpl = env.get_template("dossier.md.j2")
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=config.ROOT).stdout.strip()
    groups = defaultdict(list)
    from pds.schema import Dataset
    for raw, _ in store.iter_raw("dataset"):
        d = Dataset.model_validate(raw).model_dump(by_alias=True, mode="json")  # 선택 필드 기본값까지 채운 형태
        groups[d.get("family") or d["id"]].append(d)
    OUT.mkdir(parents=True, exist_ok=True)
    for key, ds in groups.items():
        ds = sorted(ds, key=lambda d: d["id"])
        first = next((d.get("summary_user") for d in ds if d.get("summary_user")), None)
        title = f"패밀리 {key}" if len(ds) > 1 else ds[0]["title"]
        text = tpl.render(title=title, today=dt.date.today().isoformat(), commit=commit, datasets=ds,
                          one_line=(first or "").split(". ")[0].rstrip(".") + "." if first else None,
                          drafts=any((d.get("review") or {}).get("summary") == "draft" for d in ds))
        (OUT / f"{key.replace(':', '_')}.md").write_text(text, encoding="utf-8")
    return {"dossiers": len(groups), "datasets": sum(len(v) for v in groups.values()), "out": str(OUT)}


if __name__ == "__main__":
    print(render_all())
