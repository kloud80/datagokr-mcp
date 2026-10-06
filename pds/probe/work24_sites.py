"""고용24(work24.go.kr) 오픈API 검증 — 포털 링크형 32건.

API 안내 페이지(selectOpenApiSvcInfo.do)에 있는 호출 예시(…/cm/openApi/call/…do?authKey=[인증키]&…)를 읽어,
서비스마다 다른 인증키(secrets/work24_keys.json, 서비스명 → 키)로 부른다. 키는 제목 유사도 순으로 시도하고, 안 되면 나머지 키도 시도한다.
예시의 [자리표시] 인자는 빼고, 예전 날짜 인자는 최근 90일로 바꾼다. 통계·보고서 화면(eis.work24 등)은 '오픈API 대응 없음'.
키 값은 출력·기록에 남기지 않는다. 실행: python -m pds.probe.work24_sites
"""
from __future__ import annotations

import datetime as dt
import difflib
import html as htmlmod
import json
import re
import sys
from urllib.parse import parse_qsl, urlparse

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import _items_json, _items_xml, col_stats

P = config.ROOT / "probe"
CALL = re.compile(r"(https?://www\.work24\.go\.kr/cm/openApi/call/[\w/]+\.do\?[^\"'<\s]*authKey=\[인증키\][^\"'<\s]*)")
TODAY = dt.date.today()


def _norm(t: str) -> str:
    return re.sub(r"[\s_()\[\]·,\-]|한국고용정보원|고용노동부|워크넷|직업훈련|목록|상세|정보|및", "", str(t))


def _params(url: str) -> tuple[str, dict]:
    u = htmlmod.unescape(url)
    base = u.split("?")[0]
    q = {k: v for k, v in parse_qsl(urlparse(u).query, keep_blank_values=True) if not (v.startswith("[") or v.endswith("]")) and k != "authKey"}
    for k, v in list(q.items()):  # 예시 날짜(2014…)는 최근으로
        if re.fullmatch(r"20\d{6}", v):
            q[k] = (TODAY - dt.timedelta(days=90)).strftime("%Y%m%d") if re.search(r"(St|Start|Bgn|From)", k, re.I) else TODAY.strftime("%Y%m%d")
    return base, q


def _rows(resp: httpx.Response) -> list[dict] | None:
    t = resp.text
    if t.lstrip().startswith(("{", "[")):
        try:
            return _items_json(resp.json())
        except Exception:  # noqa: BLE001
            return None
    return _items_xml(t)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    keys = json.loads((config.ROOT / "secrets" / "work24_keys.json").read_text(encoding="utf-8"))
    secret = set(keys.values())
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet").drop_duplicates("id")
    lk = lk[[c for c in lk.columns if c not in ("title", "agency_name")]]
    cat = pd.read_parquet(config.PROCESSED / "catalog.parquet", columns=["id", "title"])
    g = lk[lk["host"].fillna("").str.contains("work24")].merge(cat, on="id")
    ok, reasons = 0, {}
    with httpx.Client(timeout=40, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as c:
        for r in g.itertuples():
            run = {"id": r.id, "kind": "external", "site": "www.work24.go.kr", "link": r.link,
                   "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
            try:
                if "selectOpenApiSvcInfo" not in r.link:
                    raise ValueError("오픈API 대응 없음 (통계·목록 화면)")
                calls = sorted(set(CALL.findall(c.get(r.link).text)), key=len)
                if not calls:
                    raise ValueError("호출 예시를 찾지 못함")
                order = difflib.get_close_matches(_norm(r.title), [_norm(k) for k in keys], n=len(keys), cutoff=0)
                names = [next(k for k in keys if _norm(k) == n) for n in order]
                names += [k for k in keys if k not in names]
                hit = None
                for call in calls[:2]:
                    base, q = _params(call)
                    for name in names:
                        resp = c.get(base, params={"authKey": keys[name], **q})
                        rows = _rows(resp)
                        if rows:
                            hit = (base, q, name, rows)
                            break
                    if hit:
                        break
                if not hit:
                    raise ValueError("어느 키로도 0행 (승인 키 범위 밖이거나 필수 인자 필요)")
                base, q, name, rows = hit
                df = pd.DataFrame(rows)
                op = base.rsplit("/", 1)[-1].removesuffix(".do")
                (P / "data" / r.id).mkdir(parents=True, exist_ok=True)
                df.astype(str).to_parquet(P / "data" / r.id / f"work24_{TODAY:%Y%m%d}.parquet")
                (P / "stats" / f"{r.id}.json").write_text(json.dumps({op: col_stats(df)}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
                run["ops"] = [{"op": op, "url": base, "ok": True, "rows": len(df), "columns": list(map(str, df.columns)), "params": q,
                               "note": f"고용24 서비스별 인증키 authKey(query) — '{name}' 키, 제목 유사도로 짝지음"}]
                run["ok_ops"] = 1
                ok += 1
            except Exception as e:  # noqa: BLE001
                msg = f"{type(e).__name__}: {str(e)[:150]}"
                run.update({"ok_ops": 0, "error": msg})
                reasons[msg[:60]] = reasons.get(msg[:60], 0) + 1
            run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
            text = json.dumps(run, ensure_ascii=False, indent=1)
            for v in secret:
                text = text.replace(v, "***")
            (P / "runs" / f"{r.id}.json").write_text(text, encoding="utf-8")
            print(f"  {r.id} {'성공' if run.get('ok_ops') else '실패'} {r.title[:35]} {run.get('error', '')[:60]}", flush=True)
    print({"대상": len(g), "성공": ok, "실패 사유": sorted(reasons.items(), key=lambda x: -x[1])[:3]})


if __name__ == "__main__":
    main()
