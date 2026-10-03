"""4차 확대 대상 등록·상태 동기화 (python -m pds.expand.sync4 [register|status]).

register  logs/wave4_targets.json을 knowledge/targets.json에 덧붙인다 (status pending)
status    4차 대상과 이번에 수리한 대상의 상태를 실측 기록(probe/runs)으로 맞춘다 — 행이 나왔으면 verified, 실행했는데 0행이면 failed
"""
import json
import os
import sys

from pds import config

PATH = config.KNOWLEDGE / "targets.json"
W4 = config.ROOT / "logs" / os.environ.get("PDS_TARGETS_LOG", "wave4_targets.json")


def register() -> int:
    cur = json.loads(PATH.read_text(encoding="utf-8"))
    have = {t["id"] for t in cur}
    new = [t for t in json.loads(W4.read_text(encoding="utf-8")) if t["id"] not in have]
    PATH.write_text(json.dumps(cur + new, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(new)


def status() -> dict:
    from collections import Counter
    cur = json.loads(PATH.read_text(encoding="utf-8"))
    ids = {t["id"] for t in json.loads(W4.read_text(encoding="utf-8"))}
    c = Counter()
    for t in cur:
        if t["id"] not in ids:
            continue
        p = config.ROOT / "probe" / "runs" / f"{t['id']}.json"
        if not p.exists():
            continue
        run = json.loads(p.read_text(encoding="utf-8"))
        t["status"] = "verified" if run.get("ok_ops") else "failed"
        c[(t["round"], t["kind"], t["status"])] += 1
    PATH.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    return dict(c)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["register"]:
        print("등록", register())
    else:
        for k, v in sorted(status().items()):
            print(k, v)
