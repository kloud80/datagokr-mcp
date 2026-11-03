"""IndexNow로 공개 페이지 주소를 검색엔진에 알린다 — 빙·네이버·얀덱스·Seznam 등이 함께 받는다 (구글은 받지 않는다 → 서치 콘솔 사이트맵).

키(PDS_INDEXNOW_KEY)는 공개돼도 되는 값이고 서버가 /{키}.txt 로 서빙한다 — 검색엔진은 그 파일로 사이트 주인임을 확인한다.
보낸 주소는 받는 곳마다 seo/indexnow_sent_{곳}.txt에 남겨 다음에는 새 주소만 보낸다 (--all 이면 전부 다시).
처음 보낼 때 api.indexnow.org는 키 파일 확인이 끝날 때까지 403(SiteVerificationNotCompleted)을 줄 수 있다 — 몇 시간 뒤 다시 돌리면 된다.
  python -m pds.seo.indexnow [--all] [--dry]
"""
from __future__ import annotations

import os
import sys

import httpx
from dotenv import load_dotenv

from pds import config

ENDPOINTS = {"indexnow": "https://api.indexnow.org/indexnow", "naver": "https://searchadvisor.naver.com/indexnow"}


def _sent_file(name: str):
    return config.ROOT / "seo" / f"indexnow_sent_{name}.txt"


def main(all_: bool = False, dry: bool = False) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(config.ROOT / ".env")
    base, key = os.environ.get("PDS_PUBLIC_URL", "").rstrip("/"), os.environ.get("PDS_INDEXNOW_KEY", "")
    if not base or not key:
        raise SystemExit("PDS_PUBLIC_URL·PDS_INDEXNOW_KEY가 필요하다")
    host = base.split("://", 1)[-1].split("/")[0]
    r = httpx.get(f"{base}/{key}.txt", timeout=30)
    if r.status_code != 200 or r.text.strip() != key:
        raise SystemExit(f"키 파일이 공개 주소에서 보이지 않는다 ({r.status_code}) — 서버를 다시 띄웠는지 확인")
    from pds.seo import site
    urls = [u for part in site.urls(base).values() for u, _ in part]
    print({"전체": len(urls)})
    for name, ep in ENDPOINTS.items():
        f = _sent_file(name)
        sent = set(f.read_text(encoding="utf-8").split()) if f.exists() and not all_ else set()
        new = [u for u in urls if u not in sent]
        print(name, {"보낼 것": len(new)})
        if dry or not new:
            continue
        ok = True
        for k in range(0, len(new), 10000):  # 한 번에 1만 개까지
            res = httpx.post(ep, json={"host": host, "key": key, "keyLocation": f"{base}/{key}.txt", "urlList": new[k:k + 10000]},
                             headers={"content-type": "application/json; charset=utf-8"}, timeout=60)
            print(" ", k, res.status_code, res.text[:120].replace("\n", " "))
            ok &= res.status_code in (200, 202)
        if ok:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("\n".join(sorted(sent | set(new))) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main("--all" in sys.argv, "--dry" in sys.argv)
