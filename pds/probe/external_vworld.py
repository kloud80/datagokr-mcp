"""외부 라운드 — 브이월드(국토부 공간정보 오픈플랫폼) API 검증. 포털 목록키 15123899·15124014·15124006의 실제 원천.

키: secrets/keys.json['vworld'] (개발키, 서비스URL 'bv'에 묶임 → 요청의 domain도 'bv').
절차: 연속지적도(LP_PA_CBND_BUBUN)를 작은 박스로 받아 PNU를 얻고 → 그 PNU로 개별공시지가·개별주택가격 조회.
      필지 → 가격을 PNU로 잇는 연계를 실측하는 절차이기도 하다.
출력: probe/runs|stats|data/{id} — 포털 API와 같은 형식
"""
from __future__ import annotations

import datetime as dt
import json

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import col_stats

P = config.ROOT / "probe"
BOX = "126.9680,37.5800,126.9780,37.5870"  # 종로구 청운·효자동 일대 (주거 필지 포함)


def _key() -> tuple[str, str]:
    v = json.loads((config.ROOT / "secrets" / "keys.json").read_text(encoding="utf-8"))["vworld"]
    return v["key"], v.get("domain", "bv")


def _save(dsid: str, name: str, df: pd.DataFrame, run: dict) -> None:
    (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
    df.astype(str).to_parquet(P / "data" / dsid / f"{name}_{dt.date.today():%Y%m%d}.parquet")
    (P / "stats").mkdir(exist_ok=True)
    (P / "stats" / f"{dsid}.json").write_text(json.dumps({name: col_stats(df)}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    run.update({"ok_ops": 1 if len(df) else 0, "channel": "external", "site": "vworld.kr"})
    (P / "runs" / f"{dsid}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def run() -> dict:
    key, domain = _key()
    out = {}
    with httpx.Client(timeout=40) as c:
        # 1) 연속지적도 — 박스 안 필지 (속성만)
        feats, page = [], 1
        while page <= 3:
            r = c.get("https://api.vworld.kr/req/data", params={
                "service": "data", "request": "GetFeature", "data": "LP_PA_CBND_BUBUN", "geomFilter": f"BOX({BOX})",
                "format": "json", "size": 100, "page": page, "geometry": "false", "key": key, "domain": domain})
            j = r.json()["response"]
            fc = ((j.get("result") or {}).get("featureCollection") or {}).get("features") or []
            feats += [f["properties"] for f in fc]
            if page >= int((j.get("page") or {}).get("total") or 1):
                break
            page += 1
        cad = pd.DataFrame(feats)
        _save("15123899", "LP_PA_CBND_BUBUN", cad, {"id": "15123899", "ops": [{"op": "req/data LP_PA_CBND_BUBUN", "ok": bool(len(cad)),
              "rows": len(cad), "total_count": int((j.get("record") or {}).get("total") or 0), "columns": list(cad.columns), "attempts": []}]})
        out["15123899"] = len(cad)
        pnus = cad["pnu"].dropna().astype(str).tolist()[:60] if "pnu" in cad else []
        # 2) PNU → 개별공시지가 / 개별주택가격
        for dsid, path, root in (("15124014", "getIndvdLandPriceAttr", "indvdLandPrices"),
                                 ("15124006", "getIndvdHousingPriceAttr", "indvdHousingPrices")):
            rows, hits = [], 0
            for pnu in pnus:
                r = c.get(f"https://api.vworld.kr/ned/data/{path}", params={
                    "pnu": pnu, "format": "json", "numOfRows": 10, "pageNo": 1, "key": key, "domain": domain})
                f = (r.json().get(root) or {}).get("field") or []
                hits += bool(f)
                rows += f if isinstance(f, list) else [f]
            df = pd.DataFrame(rows)
            _save(dsid, path, df, {"id": dsid, "ops": [{"op": f"ned/data/{path}", "ok": bool(len(df)), "rows": len(df),
                  "total_count": None, "columns": list(df.columns), "attempts": [], "pnu_queried": len(pnus), "pnu_hit": hits}]})
            out[dsid] = {"rows": len(df), "pnu_hit": f"{hits}/{len(pnus)}"}
    return out


if __name__ == "__main__":
    print(run())
