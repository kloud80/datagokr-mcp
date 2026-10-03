"""4차 확대 링크형 검증 — 키 보유 사이트(브이월드·서울·법제처·나이스)만, 실측 기록(probe/runs)만 남긴다 (targets 갱신은 나중에 일괄)."""
import json
import sys
from urllib.parse import urlparse

import httpx
import pandas as pd

from pds import config
from pds.probe import external_sites as ex

sys.stdout.reconfigure(encoding="utf-8")
t = json.loads((config.ROOT / "logs" / "wave4_targets.json").read_text(encoding="utf-8"))
links = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "link"]).drop_duplicates("id")
link = dict(zip(links["id"], links["link"]))
todo = [{"id": x["id"], "link": link.get(x["id"]), "title": x["title"]} for x in t if x["round"] == "external" and link.get(x["id"])]
todo = [r for r in todo if urlparse(r["link"]).netloc in ex.SITES]
import datetime as dt
_today = dt.date.today().isoformat()
def _done(i):
    p = config.ROOT / "probe" / "runs" / f"{i}.json"
    return p.exists() and json.loads(p.read_text(encoding="utf-8")).get("started_at", "").startswith(_today)
todo = [r for r in todo if not _done(r["id"])]
print(f"키 보유 사이트 링크 {len(todo)}건", flush=True)
keys = ex._keys()
ok = 0
with httpx.Client(timeout=40, follow_redirects=True, headers=ex.UA) as c:
    for r in todo:
        run = ex.run_one(c, r, keys)
        ok += bool(run.get("ok_ops"))
        print(f"  {r['id']} {'성공' if run.get('ok_ops') else '실패'} {r['title'][:36]} {run.get('skipped') or ''}"[:150], flush=True)
print({"대상": len(todo), "성공": ok})
