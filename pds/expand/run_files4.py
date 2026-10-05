"""4차 확대 파일 검증 — logs/wave4_targets.json의 FILE·STD를 받아 셀 통계까지 (이미 오늘 받은 것은 건너뛴다, 보안문자 한도면 멈춤)."""
import asyncio
import datetime as dt
import json
import os
import sys

from pds import config
from pds.probe.files import run_files

sys.stdout.reconfigure(encoding="utf-8")
t = json.loads((config.ROOT / "logs" / os.environ.get("PDS_TARGETS_LOG", "wave4_targets.json")).read_text(encoding="utf-8"))
today = dt.date.today().isoformat()
todo = []
for x in t:
    if x["kind"] not in ("FILE", "STD"):
        continue
    p = config.ROOT / "probe" / "runs" / f"{x['id']}.json"
    if p.exists() and json.loads(p.read_text(encoding="utf-8")).get("started_at", "").startswith(today):
        continue
    todo.append((x["id"], x["url"]))
shard = os.environ.get("PDS_SHARD")  # "i/k" — 여러 프로세스로 나눠 받기
if shard:
    i, k = map(int, shard.split("/"))
    todo = todo[i::k]
if os.environ.get("PDS_REVERSE"):  # 같은 묶음을 반대쪽 끝부터 — 두 프로세스가 가운데서 만난다
    todo = todo[::-1]
print(f"파일 {len(todo)}건", flush=True)
B = 25
def _done(dsid):
    p = config.ROOT / "probe" / "runs" / f"{dsid}.json"
    return p.exists() and json.loads(p.read_text(encoding="utf-8")).get("started_at", "").startswith(today)


for i in range(0, len(todo), B):
    batch = [x for x in todo[i:i + B] if not _done(x[0])]  # 다른 프로세스가 이미 받은 것은 건너뛴다
    if not batch:
        print("  남은 것 없음 — 다른 프로세스가 받았다", flush=True)
        break
    r = asyncio.run(run_files(batch))
    ok = sum(1 for x in r if x.get("ok_ops"))
    print(f"  {i + len(r)}/{len(todo)} 성공 {ok}/{len(r)}", flush=True)
    if any(x.get("captcha") for x in r):
        print("보안문자 한도 — 멈춤", flush=True)
        break
