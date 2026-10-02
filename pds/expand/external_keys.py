"""외부 키가 필요한 데이터 → 발급처(사이트)별 정리 문서 (python -m pds.expand.external_keys).

입력: knowledge/targets.json round "external" + knowledge/expansion/external_links.json (포털 '바로가기'가 가리키는 제공처 URL —
      selectApiLinkUrl.do / selectLinkUrl.do 조회. 활용신청 기록을 남기는 addApiLink는 부르지 않는다)
출력: 추가외부키.md — 사이트마다 발급 방법·.env 변수 이름·보유 여부·데이터 목록(우선순위순)
키 값은 읽지 않는다 — 보유 여부는 변수가 비어 있지 않은지만 본다.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from urllib.parse import urlparse

from pds import config

# 사이트별 안내 — 발급 절차는 2026-10 기준 각 사이트 공지를 요약한 것. '확인 필요'는 사이트에서 절차를 다시 볼 것
SITES: dict[str, dict] = {
    "www.vworld.kr": {"name": "브이월드 (국토부 공간정보 오픈플랫폼)", "env": "VWORLD_API_KEY", "have": "secrets", "how": "회원가입 → 오픈API 인증키 신청(서비스 URL 기재) → 즉시 발급. WMS/WFS·데이터 API 모두 같은 키"},
    "data.ex.co.kr": {"name": "한국도로공사 고속도로 공공데이터 포털", "env": "EX_API_KEY", "how": "회원가입 → 마이페이지 인증키 발급(즉시)"},
    "www.foodsafetykorea.go.kr": {"name": "식품안전나라 (식약처)", "env": "FOODSAFETY_API_KEY", "how": "회원가입 → 공공데이터 활용 → 인증키 신청 → 승인(보통 당일)"},
    "data.seoul.go.kr": {"name": "서울 열린데이터광장", "env": "DATA_SEOUL_API_KEY", "how": "보유 — 일반 인증키 하나로 대부분 호출"},
    "openapi.seoul.go.kr:8088": {"name": "서울 열린데이터광장 (OpenAPI 서버)", "env": "DATA_SEOUL_API_KEY", "how": "보유 — 열린데이터광장 키와 같음"},
    "open.law.go.kr": {"name": "국가법령정보 공동활용 (법제처)", "env": "OPEN_LAW_GO_KR_API_KEY", "how": "보유(OC) — 신규 API는 사이트에서 서비스 추가 신청"},
    "www.law.go.kr": {"name": "국가법령정보센터 (법제처)", "env": "OPEN_LAW_GO_KR_API_KEY", "how": "보유(OC) — open.law.go.kr 키와 같음"},
    "www.safemap.go.kr": {"name": "생활안전지도 (행안부)", "env": "SAFEMAP_API_KEY", "how": "회원가입 → 오픈API → 인증키 신청 → 승인"},
    "apihub.kma.go.kr": {"name": "기상청 API허브", "env": "KMA_APIHUB_KEY", "how": "회원가입 → 마이페이지 인증키(즉시). API마다 활용신청 버튼"},
    "data.kma.go.kr": {"name": "기상자료개방포털 (파일)", "env": "(로그인 다운로드)", "how": "회원가입 → 로그인 후 파일 다운로드 — 키 없음, 계정만"},
    "www.lofin365.go.kr": {"name": "지방재정365 (행안부)", "env": "LOFIN365_API_KEY", "how": "회원가입 → 오픈API 인증키 신청 — 확인 필요"},
    "open.assembly.go.kr": {"name": "열린국회정보", "env": "OPEN_ASSEMBLY_API_KEY", "how": "회원가입 → 인증키 신청(즉시)"},
    "plus.kipris.or.kr": {"name": "KIPRIS Plus (특허정보)", "env": "KIPRIS_API_KEY", "how": "회원가입 → 서비스별 신청(무료/유료 구분) → 승인"},
    "opendart.fss.or.kr": {"name": "OpenDART (금감원 전자공시)", "env": "OPENDART_API_KEY", "how": "인증키 신청(이메일 인증) → 즉시. 개인 일 2만 회"},
    "www.safetydata.go.kr": {"name": "재난안전데이터공유플랫폼 (행안부)", "env": "SAFETYDATA_API_KEY", "how": "회원가입 → 데이터별 활용신청 → 승인"},
    "bigdata.kepco.co.kr": {"name": "한전 전력데이터 개방포털", "env": "KEPCO_API_KEY", "how": "회원가입 → 오픈API 인증키 신청"},
    "www.culture.go.kr": {"name": "문화공공데이터광장", "env": "CULTURE_API_KEY", "how": "회원가입 → 서비스키 신청 — 확인 필요"},
    "data.gg.go.kr": {"name": "경기데이터드림", "env": "DATA_GG_API_KEY", "how": "회원가입 → 인증키 발급(즉시)"},
    "www.lawmaking.go.kr": {"name": "국민참여입법센터 (법제처)", "env": "LAWMAKING_API_KEY", "how": "오픈API 인증키 신청 — 확인 필요"},
    "www.its.go.kr": {"name": "국가교통정보센터 ITS", "env": "ITS_API_KEY", "how": "회원가입 → 오픈API 인증키 신청 → 승인"},
    "www.work24.go.kr": {"name": "고용24 (고용노동부)", "env": "WORK24_API_KEY", "how": "회원가입 → 오픈API 인증키 신청 → 승인"},
    "open.neis.go.kr": {"name": "나이스 교육정보 개방 포털", "env": "OPEN_NEIS_API_KEY", "how": "보유"},
    "info.childcare.go.kr": {"name": "보육통합정보시스템 (어린이집)", "env": "CHILDCARE_API_KEY", "how": "어린이집정보공개포털 오픈API 인증키 신청 → 승인 — 전국 어린이집 원장(현재 공백)"},
    "data.floodmap.go.kr": {"name": "침수흔적도·홍수위험지도 (환경부)", "env": "FLOODMAP_API_KEY", "how": "회원가입 → 인증키 신청 — 확인 필요 (현재 공백: 침수흔적도)"},
    "opendata.koroad.or.kr": {"name": "도로교통공단 TAAS", "env": "KOROAD_API_KEY", "how": "회원가입 → 인증키 신청(즉시)"},
    "www.utic.go.kr": {"name": "도시교통정보센터 UTIC (경찰청)", "env": "UTIC_API_KEY", "how": "회원가입 → 인증키 신청 → 승인"},
    "data.kric.go.kr": {"name": "철도산업정보센터", "env": "KRIC_API_KEY", "how": "회원가입 → 인증키 신청"},
    "www.juso.go.kr": {"name": "도로명주소 (행안부)", "env": "JUSO_API_KEY", "how": "business.juso.go.kr에서 API별 승인키(검색·좌표·영문) — 개발 90일/운영 신청"},
    "kopis.or.kr": {"name": "공연예술통합전산망 KOPIS", "env": "KOPIS_API_KEY", "how": "회원가입 → 서비스키 신청(즉시)"},
    "www.kobis.or.kr": {"name": "영화관입장권통합전산망 KOBIS", "env": "KOBIS_API_KEY", "how": "회원가입 → 키 발급(즉시)"},
    "www.opinet.co.kr": {"name": "오피넷 (석유공사 유가)", "env": "OPINET_API_KEY", "how": "무료 API 키 신청(이메일)"},
    "www.ntis.go.kr": {"name": "국가과학기술지식정보서비스 NTIS", "env": "NTIS_API_KEY", "how": "회원가입 → 오픈API 신청 → 승인"},
    "eum.go.kr": {"name": "토지이음 (토지이용계획)", "env": "(파일 다운로드)", "how": "사이트 파일 다운로드 — 키 없음"},
    "file.localdata.go.kr": {"name": "지방행정 인허가(LOCALDATA) 파일", "env": "(없음)", "how": "키 없이 파일 다운로드 — 바로 처리 가능"},
}


def _have(env: str) -> bool:
    if not env or env.startswith("("):
        return False
    if env == "VWORLD_API_KEY":
        p = config.ROOT / "secrets" / "keys.json"
        return p.exists() and bool(json.loads(p.read_text(encoding="utf-8")).get("vworld", {}).get("key"))
    return bool(os.environ.get(env, "").strip())


def _priority(t: dict) -> int:
    m = re.search(r"p(\d)", t.get("note") or "")
    return int(m.group(1)) if m else 2


def build() -> str:
    links = {r["id"]: r for r in json.loads((config.KNOWLEDGE / "expansion" / "external_links.json").read_text(encoding="utf-8"))}
    by = defaultdict(list)
    for i, r in links.items():
        host = urlparse(r.get("link") or "").netloc or "(주소 없음)"
        by[host].append(r)
    groups = []
    for host, rows in by.items():
        s = SITES.get(host, {"name": host, "env": "PDS_KEY_" + re.sub(r"\W", "_", host.split(":")[0].removeprefix("www.")).upper(),
                             "how": "사이트에서 회원가입 → 오픈API 인증키 신청 — 확인 필요"})
        pr = [_priority(r) for r in rows]
        groups.append((host, s, rows, pr.count(1), len(rows)))
    have = [g for g in groups if _have(g[1]["env"])]
    need = sorted([g for g in groups if not _have(g[1]["env"])], key=lambda g: (-g[3], -g[4]))
    total_need = sum(g[4] for g in need)

    L = ["# 추가 외부 키", "",
         f"외부 사이트 키가 있어야 검증·편입할 수 있는 데이터 **{len(links):,}건** — 제공처 {len(groups)}곳. "
         f"이미 키가 있는 곳 {len(have)}곳({sum(g[4] for g in have):,}건) · **새로 받아야 하는 곳 {len(need)}곳({total_need:,}건)**.",
         "",
         "- 받은 키는 `.env`에 아래 **변수 이름**으로 넣어 주세요 (값은 git에 올라가지 않습니다).",
         "- 순서는 1순위(바로 편입) 데이터가 많은 곳부터. 1순위는 2·3차 부문 검토에서 '전국 원장·실시간·많이 이어짐'으로 판정된 것.",
         "- 각 데이터의 포털 링크로 들어가 '바로가기'를 누르면 제공처 페이지로 갑니다. 아래 '제공처 예'가 그 주소입니다.",
         f"- 생성: `python -m pds.expand.external_keys` (제공처 주소는 포털 조회값, {len(links)}건 모두 확인)",
         "", "## 새로 받아야 하는 키", "",
         "| # | 제공처 | 데이터 | 1순위 | .env 변수 | 발급 |", "|---:|---|---:|---:|---|---|"]
    for n, (host, s, rows, p1, cnt) in enumerate(need, 1):
        L.append(f"| {n} | [{s['name']}](https://{host}) | {cnt} | {p1} | `{s['env']}` | {s['how']} |")
    L += ["", "## 이미 있는 키 (바로 편입 진행 가능)", "", "| 제공처 | 데이터 | 1순위 | .env 변수 |", "|---|---:|---:|---|"]
    for host, s, rows, p1, cnt in sorted(have, key=lambda g: -g[4]):
        L.append(f"| [{s['name']}](https://{host}) | {cnt} | {p1} | `{s['env']}` |")
    L += ["", "## 제공처별 데이터", ""]
    for host, s, rows, p1, cnt in need + sorted(have, key=lambda g: -g[4]):
        status = "보유" if _have(s["env"]) else "필요"
        L += [f"### {s['name']} — {cnt}건 · 키 {status}", "",
              f"제공처 예: {rows[0].get('link')}", "", "| 우선 | 데이터 | 기관 | 포털 |", "|---:|---|---|---|"]
        for r in sorted(rows, key=lambda r: (_priority(r), r["title"])):
            L.append(f"| {_priority(r)} | {r['title']} | {r['agency']} | [{r['id']}]({r['url']}) |")
        L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    out = config.ROOT / "추가외부키.md"
    out.write_text(build(), encoding="utf-8")
    print(out)
