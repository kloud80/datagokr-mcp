"""data.go.kr 전체를 보려면 가입해야 하는 사이트와 사이트별 커버리지 (python -m pds.expand.site_coverage).

포털 목록 중 링크형(API_LINK·FILE_LINK — 데이터가 기관 사이트에 있다) 전부의 제공처 주소를 포털에서 조회해
(selectApiLinkUrl.do / selectLinkUrl.do — 활용신청 기록을 남기는 호출은 하지 않는다) 사이트별로 묶는다.
결과: knowledge/expansion/site_links.parquet (데이터별 주소) · site_coverage.json (사이트별 집계, Docs가 읽는다)
사이트별: 포털 데이터 수(API·파일) · 이 시스템이 대상으로 삼은 수 · 검증한 수 · 키 상태(보유·검증 / 보유 / 미보유 / 키 불필요)
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import httpx
import pandas as pd

from pds import config
from pds.expand.external_keys import SITES, _have

OUT = config.KNOWLEDGE / "expansion"
UA = {"User-Agent": "Mozilla/5.0 (pds)"}


def _host(u: str | None) -> str | None:
    if not isinstance(u, str) or not u:
        return None
    h = urlparse(u if "://" in u else "http://" + u).netloc.lower()
    return h.removeprefix("www.") or None


def fetch(workers: int = 6) -> pd.DataFrame:
    P = config.PROCESSED
    s = pd.read_parquet(P / "score.parquet", columns=["id", "api_kind_label"])
    c = pd.read_parquet(P / "catalog.parquet", columns=["id", "title", "agency_name"])
    d = s[s["api_kind_label"].isin(["API_LINK", "FILE_LINK"])].merge(c, on="id")
    path = OUT / "site_links.parquet"
    have = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=["id", "link"])
    known = dict(zip(have["id"], have["link"]))
    for r in json.loads((OUT / "external_links.json").read_text(encoding="utf-8")):
        known.setdefault(r["id"], r.get("link"))
    todo = [r for r in d.itertuples() if r.id not in known]
    print(f"링크형 {len(d):,} · 이미 아는 주소 {len(d) - len(todo):,} · 조회 {len(todo):,}", flush=True)
    cl = httpx.Client(timeout=30, headers=UA)

    def one(r):
        ep = "selectApiLinkUrl.do" if r.api_kind_label == "API_LINK" else "selectLinkUrl.do"
        for i in range(3):
            try:
                j = json.loads(cl.get(f"https://www.data.go.kr/tcs/dss/{ep}", params={"publicDataPk": r.id}).text)
                return r.id, j.get("linkUrl") if j.get("status") else None
            except Exception:  # noqa: BLE001 — 잠깐 쉬고 다시
                time.sleep(1 + i)
        return r.id, None

    got = {}
    with ThreadPoolExecutor(workers) as ex:
        for k, (i, link) in enumerate(ex.map(one, todo), 1):
            got[i] = link
            if k % 1000 == 0:
                print(f"  {k:,}/{len(todo):,}", flush=True)
                pd.DataFrame({"id": list(known) + list(got), "link": list(known.values()) + list(got.values())}).to_parquet(path, index=False)
    known |= got
    out = d.assign(link=d["id"].map(known))
    out["host"] = out["link"].map(_host)
    out.to_parquet(path, index=False)
    return out


def aggregate(d: pd.DataFrame | None = None) -> dict:
    d = d if d is not None else pd.read_parquet(OUT / "site_links.parquet")
    if "host" not in d:
        d["host"] = d["link"].map(_host)
    t = {x["id"]: x for x in json.loads((config.KNOWLEDGE / "targets.json").read_text(encoding="utf-8"))}
    known_ds = {f.stem for f in (config.KNOWLEDGE / "datasets").rglob("*.yaml")}
    rows = []
    for host, g in d.groupby(d["host"].fillna("(주소 없음)")):
        site = SITES.get(host) or SITES.get("www." + host) or {}
        api = int((g["api_kind_label"] == "API_LINK").sum())
        fil = int((g["api_kind_label"] == "FILE_LINK").sum())
        targ = [i for i in g["id"] if i in t]
        ver = [i for i in g["id"] if i in known_ds and t.get(i, {}).get("status") == "verified"]
        env = site.get("env", "")
        if env.startswith("("):
            key = "키 불필요"
        elif _have(env):
            key = "보유·검증" if ver else "보유"
        else:
            key = "미보유" if api else "키 불필요"
        rows.append({"host": host, "name": site.get("name") or host, "api": api, "file": fil, "total": api + fil, "targets": len(targ),
                     "verified": len(ver), "key": key, "env": env if api else "", "how": site.get("how", "")})
    rows.sort(key=lambda r: -r["total"])
    portal = 96110 - len(d)
    summary = {"catalog": 96110, "portal_direct": portal, "link_total": len(d), "sites": len(rows),
               "api_sites": sum(1 for r in rows if r["api"]), "by_key": {}}
    for r in rows:
        summary["by_key"].setdefault(r["key"], {"sites": 0, "datasets": 0})
        summary["by_key"][r["key"]]["sites"] += 1
        summary["by_key"][r["key"]]["datasets"] += r["total"]
    res = {"summary": summary, "sites": rows}
    (OUT / "site_coverage.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--aggregate" not in sys.argv:
        fetch()
    r = aggregate()
    print(r["summary"])
    for s in r["sites"][:25]:
        print(f"  {s['total']:>6,} (API {s['api']:>4} · 파일 {s['file']:>5}) {s['name'][:28]:28s} 대상 {s['targets']:>3} 검증 {s['verified']:>3} · {s['key']}")
