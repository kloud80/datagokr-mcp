"""통계 사이트 키 확대 — KOSIS(kosis.kr · stat.kosis.kr)와 부동산원 R-ONE(reb.or.kr) 링크형 전부 (python -m pds.expand.stat_sites).

7차(wave7)는 키가 없어 이 두 사이트를 뺐다. 키가 생겨(KOSIS_API_KEY · REB_API_KEY) 링크형 전부를 대상으로 삼는다.
검증은 pds.probe.kosis_sites · reb_sites, 등록·상태는 PDS_TARGETS_LOG=stat_sites_targets.json python -m pds.expand.sync4 register|status.
등급은 7차와 같은 규칙 (부문 판정이 없으면 '전수').
출력: logs/stat_sites_targets.json (인자 kepco_mnd: 한전·국방부 키 확대 → logs/kepco_mnd_targets.json)
"""
from __future__ import annotations

import json
import sys

import pandas as pd

from pds import config
from pds.expand.wave6 import _decisions

HOSTS = ("kosis.kr", "reb.or.kr")
SETS = {"stat": (HOSTS, "stat_sites_targets.json"), "kepco_mnd": (("bigdata.kepco.co.kr", "mnd.go.kr"), "kepco_mnd_targets.json")}


def build(hosts: tuple[str, ...] = HOSTS) -> list[dict]:
    P = config.PROCESSED
    cat = pd.read_parquet(P / "catalog.parquet", columns=["id", "title", "agency_name", "url", "usage_count"])
    sc = pd.read_parquet(P / "score.parquet", columns=["id", "api_kind_label", "prelim_score"])
    cls = pd.read_parquet(P / "class.parquet", columns=["id", "sector", "subsector", "subsector_name"])
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host"]).drop_duplicates("id")
    lk = lk[lk["host"].fillna("").str.contains("|".join(hosts).replace(".", r"\."))]
    st = {t["id"]: t["status"] for t in json.loads((config.KNOWLEDGE / "targets.json").read_text(encoding="utf-8"))}
    d = lk.merge(cat, on="id").merge(sc, on="id").merge(cls, on="id", how="left")
    d = d.merge(_decisions()[["id", "decision", "priority", "rep", "wave", "reason"]], on="id", how="left")
    out = []
    for r in d.sort_values("prelim_score", ascending=False).itertuples():
        keep, pr = r.decision in ("keep", "move"), (r.priority if r.priority == r.priority else 3)
        grade = ("" if r.rep is True else "가족판") if keep and pr <= 2 else "3순위" if keep else "보조" if r.decision == "defer" else "전수"
        note = (f"키 확대({r.host}) · 등급:{grade}" if grade else f"키 확대({r.host})") + (f" · {r.wave} 판정 {r.decision}" if isinstance(r.decision, str) else "")
        if r.id in st:
            note += f" · 재시도(이전 {st[r.id]})"
        out.append({"id": r.id, "title": r.title, "agency": r.agency_name, "sector": r.sector, "subsector": r.subsector or "misc",
                    "subsector_name": r.subsector_name if isinstance(r.subsector_name, str) else "", "kind": r.api_kind_label,
                    "prelim_score": round(float(r.prelim_score), 3), "usage": int(r.usage_count or 0), "url": r.url, "round": "external",
                    "why": (r.reason if isinstance(r.reason, str) else "")[:200], "status": "pending", "note": note, "retry": r.id in st})
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    hosts, out = SETS[sys.argv[1] if len(sys.argv) > 1 else "stat"]
    t = build(hosts)
    (config.ROOT / "logs" / out).write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(t), "신규", sum(1 for x in t if not x["retry"]))


if __name__ == "__main__":
    main()
