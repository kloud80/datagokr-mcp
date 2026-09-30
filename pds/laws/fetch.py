"""법령 층 — 법제처 open.law.go.kr에서 현행 법령 원문을 받아 knowledge/laws/{법령ID}.yaml로 (KNOWLEDGE-SPEC §7-6).

대상: Dataset.applicable_legislation(포털 보유근거에서 읽은 법령명) + sectors/sector_tree.yaml domain 법(약칭 → ALIAS로 정식 명칭).
검색 결과는 이름이 정확히 같은 현행 법률·시행령·시행규칙만 채택한다 — 약칭 검색은 엉뚱한 법을 돌려준다(도시정비법 → 노후계획도시법).
OC 값은 파일·로그에 남기지 않는다 (법제처 응답의 상세 링크에 OC가 들어 있어 쓰지 않는다).
"""
from __future__ import annotations

import datetime as dt
import os
from functools import lru_cache
import re
import time

import httpx
import yaml

from pds import config
from pds.schema import Law
from pds.schema import store

BASE = "https://www.law.go.kr/DRF"
LAWDIR = config.KNOWLEDGE / "laws"
# sector_tree·검토 기록에 쓰인 약칭 → 정식 명칭 (법제처 제명 그대로)
ALIAS = {
    "국토계획법": "국토의 계획 및 이용에 관한 법률", "도시정비법": "도시 및 주거환경정비법",
    "부동산거래신고법": "부동산 거래신고 등에 관한 법률", "부동산공시법": "부동산 가격공시에 관한 법률",
    "공간정보관리법": "공간정보의 구축 및 관리 등에 관한 법률", "산업입지법": "산업입지 및 개발에 관한 법률",
    "도시재생법": "도시재생 활성화 및 지원에 관한 특별법", "지역특구법": "규제자유특구 및 지역특화발전특구에 관한 규제특례법",
    "댐건설관리법": "댐건설·관리 및 주변지역지원 등에 관한 법률", "수자원법": "수자원의 조사·계획 및 관리에 관한 법률",
    "공공주택특별법": "공공주택 특별법", "국가균형발전특별법": "지방자치분권 및 균형성장에 관한 특별법",
    "국가균형발전 특별법": "지방자치분권 및 균형성장에 관한 특별법",  # 2023-07 통합 → 현행 제명 (2026-09-30 법제처 조회) "국가공간정보기본법": "국가공간정보 기본법",
    "문화재보호법": "문화유산의 보존 및 활용에 관한 법률",  # 2024-05 국가유산 체제 개편으로 보호 조항 승계
}
LAW_NAME = re.compile(r"([가-힣A-Za-z0-9·ㆍ\s]{2,60}?(?:법률|특별법|기본법|법|시행령|시행규칙))")


def _oc() -> str:
    oc = os.getenv("OPEN_LAW_GO_KR_API_KEY")
    if not oc:
        raise RuntimeError(".env OPEN_LAW_GO_KR_API_KEY 없음")
    return oc


def wanted() -> dict[str, list[str]]:
    """{정식 법령명: [참조한 곳]}"""
    out: dict[str, list[str]] = {}
    for d, path in store.iter_raw("dataset"):
        for lg in d.get("applicable_legislation") or []:
            if not lg["law"].endswith(("조례", "규칙")) or lg["law"].endswith("시행규칙"):  # 자치법규는 target=ordin (범위 밖)
                out.setdefault(ALIAS.get(lg["law"], lg["law"]), []).append(f"dataset:{d['id']}")
    tree = yaml.safe_load((config.KNOWLEDGE / "sectors" / "sector_tree.yaml").read_text(encoding="utf-8")) or []
    for t in tree:
        text = re.split(r"\s—\s", t.get("law") or "")[0]
        for part in re.split(r"[·,]", text):
            m = LAW_NAME.search(part.strip())
            if m:
                name = m.group(1).strip()
                out.setdefault(ALIAS.get(name, name), []).append(f"domain:{t['id']}")
    return out


def search(c: httpx.Client, name: str) -> dict | None:
    r = c.get(f"{BASE}/lawSearch.do", params={"OC": _oc(), "target": "law", "type": "JSON", "query": name, "display": 50})
    laws = (r.json().get("LawSearch") or {}).get("law") or []
    laws = [laws] if isinstance(laws, dict) else laws
    norm = lambda s: re.sub(r"\s", "", s or "").replace("ㆍ", "·")  # noqa: E731 — 법제처 제명은 ㆍ(U+318D)
    for x in laws:
        if x.get("현행연혁코드") == "현행" and (norm(x.get("법령명한글")) == norm(name) or norm(x.get("법령약칭명")) == norm(name)):
            return x
    return None


def _article_text(a: dict) -> str:
    parts = [a.get("조문내용") or ""]
    hang = a.get("항") or []
    hang = [hang] if isinstance(hang, dict) else hang
    for h in hang:
        parts.append(h.get("항내용") or "")
        ho = h.get("호") or []
        ho = [ho] if isinstance(ho, dict) else ho
        parts += [x.get("호내용") or "" for x in ho]
    return "\n".join(re.sub(r"\s+", " ", str(p)).strip() for p in parts if p and str(p).strip())


def fetch(c: httpx.Client, hit: dict) -> dict:
    r = c.get(f"{BASE}/lawService.do", params={"OC": _oc(), "target": "law", "MST": hit["법령일련번호"], "type": "JSON"})
    L = r.json()["법령"]
    info = L["기본정보"]
    arts = (L.get("조문") or {}).get("조문단위") or []
    arts = [arts] if isinstance(arts, dict) else arts
    articles = []
    for a in arts:
        if a.get("조문여부") != "조문":
            continue
        no = str(a.get("조문번호")) + (f"의{a['조문가지번호']}" if a.get("조문가지번호") else "")
        articles.append({"no": no, "title": a.get("조문제목") or None, "text": _article_text(a)})
    ymd = lambda s: dt.date(int(s[:4]), int(s[4:6]), int(s[6:8])) if s and len(s) == 8 else None  # noqa: E731
    name = info["법령명_한글"]
    rec = {"law_id": info["법령ID"], "name": name, "short_names": [x for x in [info.get("법령명약칭")] if x],
           "promulgated": ymd(info.get("공포일자")), "effective": ymd(info.get("시행일자")), "articles": articles,
           "source": f"https://www.law.go.kr/법령/{name.replace(' ', '')}", "fetched_at": dt.date.today()}
    Law.model_validate(rec)
    return {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in rec.items()}


def run() -> dict:
    LAWDIR.mkdir(parents=True, exist_ok=True)
    got, missing = {}, {}
    with httpx.Client(timeout=60) as c:
        for name, refs in sorted(wanted().items()):
            hit = search(c, name)
            if not hit:
                missing[name] = refs
                continue
            rec = fetch(c, hit)
            store.dump(rec, LAWDIR / f"{rec['law_id']}.yaml",
                       header=f"{rec['name']} — 법제처 현행 원문 ({rec['fetched_at']} 조회). 참조: {', '.join(sorted(set(refs))[:8])}")
            got[name] = rec["law_id"]
            time.sleep(0.3)
    (LAWDIR / "_index.yaml").write_text(yaml.safe_dump({"resolved": got, "not_found": missing}, allow_unicode=True, sort_keys=True),
                                        encoding="utf-8")
    return {"resolved": len(got), "not_found": missing}


@lru_cache
def index() -> dict[str, str]:
    """법령명(정식·약칭·ALIAS) → 법령ID"""
    out = {}
    for d, _ in store.iter_raw("law"):
        out[d["name"]] = d["law_id"]
        for s in d.get("short_names") or []:
            out[s] = d["law_id"]
    for a, full in ALIAS.items():
        if full in out:
            out[a] = out[full]
    return out


if __name__ == "__main__":
    print(run())
