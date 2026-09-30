"""갱신 관찰 (BUILD-PLAN §2.1 i, KNOWLEDGE-SPEC §7-9) — 검증된 포털 API를 가볍게 다시 불러 스냅샷을 쌓고, 이전 스냅샷과 비교해 실측 갱신 주기를 낸다.

스냅샷 (probe/observe/{YYYYMMDD}/{id}.json): 오퍼레이션별 전체 건수(totalCount) · 날짜 컬럼 최대값 · 첫 페이지 지문(sha1) · 호출 조건
비교 (probe/observe/_diff.json): 같은 데이터의 가장 이른·늦은 스냅샷 → 건수 증감·최신 날짜 이동·지문 변화 → 판정
  changed(바뀜) / unchanged(그대로) / insufficient(스냅샷 1개)
cadence claim(02)은 판정이 있으면 measured 근거로 이것을 인용한다 (pds/dossier/claims.py).
주기 실행: 매주 `python -m pds.probe.observe` (첫 실행이 기준선 — 2026-09-30).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import build_params, call_op, overrides, service_key
from pds.schema import store

OUT = config.ROOT / "probe" / "observe"
DATE_COL = re.compile(r"(ymd|date|dt$|Dt$|de$|De$|일자|일시|년월|stdr|crtr|base|load|updt|modf|mdfcn|regist|rgst)", re.I)


def _latest(df: pd.DataFrame) -> str | None:
    best = None
    for c in df.columns:
        if not DATE_COL.search(str(c)):
            continue
        s = df[c].astype(str).str.replace(r"[^\d]", "", regex=True).str[:8]
        d = pd.to_datetime(s[s.str.len() == 8], format="%Y%m%d", errors="coerce").dropna()
        d = d[d <= pd.Timestamp.today() + pd.Timedelta(days=1)]  # 미래 일정은 최신성이 아니다
        if len(d):
            m = d.max().date().isoformat()
            best = max(best, m) if best else m
    return best


def snapshot(dsid: str, client: httpx.Client, key: str) -> dict | None:
    spec_p = config.ROOT / "probe" / "specs" / f"{dsid}.json"
    run_p = config.ROOT / "probe" / "runs" / f"{dsid}.json"
    if not spec_p.exists() or not run_p.exists():
        return None
    spec, run = json.loads(spec_p.read_text(encoding="utf-8")), json.loads(run_p.read_text(encoding="utf-8"))
    if run.get("channel") == "external" or run.get("kind") == "file":
        return None
    ok_ops = [o for o in run.get("ops") or [] if o.get("ok")]
    if not ok_ops:
        return None
    if spec.get("swagger"):
        scheme = "https" if "https" in (spec.get("schemes") or ["https"]) else "http"
        base, ops = f"{scheme}://{spec['host']}{spec.get('base_path') or ''}", spec["operations"]
    else:
        base, ops = "", [o for o in spec.get("operations") or [] if o.get("path")]
    ops = [o for o in ops if o["path"] in {x["op"] for x in ok_ops} or o["path"] in {x.get("url") for x in ok_ops}][:2]
    out = {"id": dsid, "at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
    for op in ops:
        extra = overrides(dsid, op["path"])
        prev = next((x for x in ok_ops if x["op"] == op["path"]), {})
        if prev.get("date_refreshed"):
            extra = {**extra, **prev["date_refreshed"]}
        rec = call_op(client, base, op, key, 100, rows=100, extra=extra)
        df = rec.pop("_df")
        fp = hashlib.sha1(df.head(50).astype(str).to_csv(index=False).encode()).hexdigest() if df is not None else None
        out["ops"].append({"op": op["path"], "ok": rec["ok"], "total_count": rec.get("total_count"), "rows": rec.get("rows"),
                           "latest": _latest(df) if df is not None else None, "fingerprint": fp, "params": rec.get("params")})
    return out


def run(ids: list[str] | None = None) -> dict:
    day = dt.date.today().strftime("%Y%m%d")
    (OUT / day).mkdir(parents=True, exist_ok=True)
    key = service_key()
    ds = [d["id"] for d, _ in store.iter_raw("dataset") if d.get("tier") == "verified" and d.get("channel") == "portal"
          and d.get("kind") == "API"]
    n = 0
    with httpx.Client(headers={"User-Agent": "pds-observe/0.1"}) as c:
        for i in ids or ds:
            try:
                s = snapshot(i, c, key)
            except Exception as e:  # noqa: BLE001
                s = {"id": i, "error": repr(e)[:200]}
            if s:
                (OUT / day / f"{i}.json").write_text(json.dumps(s, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
                n += 1
    return {"day": day, "snapshots": n, "diff": diff()}


def diff() -> dict:
    days = sorted(p.name for p in OUT.iterdir() if p.is_dir() and p.name.isdigit()) if OUT.exists() else []
    res = {}
    ids = {f.stem for d in days for f in (OUT / d).glob("*.json")}
    for i in ids:
        snaps = [json.loads((OUT / d / f"{i}.json").read_text(encoding="utf-8")) for d in days if (OUT / d / f"{i}.json").exists()]
        snaps = [s for s in snaps if s.get("ops")]
        if len(snaps) < 2:
            res[i] = {"verdict": "insufficient", "snapshots": len(snaps), "first": snaps[0]["at"][:10] if snaps else None}
            continue
        a, b = snaps[0], snaps[-1]
        days_between = (dt.date.fromisoformat(b["at"][:10]) - dt.date.fromisoformat(a["at"][:10])).days
        ch = []
        for oa in a["ops"]:
            ob = next((o for o in b["ops"] if o["op"] == oa["op"]), None)
            if not ob:
                continue
            ch.append({"op": oa["op"], "total_delta": (ob.get("total_count") or 0) - (oa.get("total_count") or 0),
                       "latest_from": oa.get("latest"), "latest_to": ob.get("latest"), "fingerprint_changed": oa.get("fingerprint") != ob.get("fingerprint")})
        changed = any(c["total_delta"] or c["fingerprint_changed"] or c["latest_from"] != c["latest_to"] for c in ch)
        res[i] = {"verdict": "changed" if changed else "unchanged", "days": days_between, "from": a["at"][:10], "to": b["at"][:10], "ops": ch}
    (OUT / "_diff.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    return dict(Counter(v["verdict"] for v in res.values()))


if __name__ == "__main__":
    print(run())
