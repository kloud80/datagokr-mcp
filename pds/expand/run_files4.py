"""4차 확대 파일 검증 — logs/wave4_targets.json의 FILE·STD를 받아 셀 통계까지 (이미 오늘 받은 것은 건너뛴다, 보안문자 한도면 멈춤)."""
import asyncio
import datetime as dt
import json
import sys

from pds import config
from pds.probe.files import run_files

sys.stdout.reconfigure(encoding="utf-8")
t = json.loads((config.ROOT / "logs" / "wave4_targets.json").read_text(encoding="utf-8"))
today = dt.date.today().isoformat()
todo = []
for x in t:
    if x["kind"] not in ("FILE", "STD"):
        continue
    p = config.ROOT / "probe" / "runs" / f"{x['id']}.json"
    if p.exists() and json.loads(p.read_text(encoding="utf-8")).get("started_at", "").startswith(today):
        continue
    todo.append((x["id"], x["url"]))
print(f"파일 {len(todo)}건", flush=True)
B = 25
for i in range(0, len(todo), B):
    r = asyncio.run(run_files(todo[i:i + B]))
    ok = sum(1 for x in r if x.get("ok_ops"))
    print(f"  {i + len(r)}/{len(todo)} 성공 {ok}/{len(r)}", flush=True)
    if any(x.get("captcha") for x in r):
        print("보안문자 한도 — 멈춤", flush=True)
        break
