"""7차 확대 포털 API 호출 — logs/wave7_targets.json의 REST (python -m pds.expand.run_rest7 [retry|new|all]).

retry  이전에 실패·대기였던 것 (활용신청은 이미 했다) — 다시 호출하고, 그래도 실패면 pds.probe.repair(파라미터 수리)로 넘긴다
new    7차에 새로 고른 것 — 활용신청 기록(probe/apply)이 있는 것만 (신청 전에는 SERVICE KEY IS NOT REGISTERED)
이미 성공한 기록은 건너뛴다. PDS_SHARD="i/k"로 나눠 돌린다.
"""
from __future__ import annotations

import json
import os
import sys

from pds import config
from pds.probe.deep import run_one

P = config.ROOT / "probe"


def todo(which: str) -> list[str]:
    t = json.loads((config.ROOT / "logs" / "wave7_targets.json").read_text(encoding="utf-8"))
    ids = []
    for x in t:
        if x["kind"] not in ("REST", "SOAP"):
            continue
        if which == "retry" and not x["retry"] or which == "new" and x["retry"]:
            continue
        if not x["retry"] and not (P / "apply" / f"{x['id']}.json").exists():
            continue
        r = P / "runs" / f"{x['id']}.json"
        if r.exists() and json.loads(r.read_text(encoding="utf-8")).get("ok_ops"):
            continue
        ids.append(x["id"])
    shard = os.environ.get("PDS_SHARD")
    if shard:
        i, k = map(int, shard.split("/"))
        ids = ids[i::k]
    return ids


def main(which: str) -> None:
    ids = todo(which)
    print(f"API {len(ids)}건", flush=True)
    ok = 0
    for n, i in enumerate(ids, 1):
        try:
            ok += bool(run_one(i).get("ok_ops"))
        except Exception as e:  # noqa: BLE001
            print(f"  {i} 오류 {repr(e)[:120]}", flush=True)
        if n % 25 == 0:
            print(f"  {n}/{len(ids)} 성공 {ok}", flush=True)
    print({"대상": len(ids), "성공": ok}, flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1] if len(sys.argv) > 1 else "retry")
