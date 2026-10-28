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
from pds.strategy.signup import env_name

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
    "bigdata.kepco.co.kr": {"name": "한전 전력데이터 개방포털", "env": "BIGDATA_KEPCO_API_KEY", "how": "회원가입 → 오픈API 인증키 신청"},
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

# 2026-10-06 가입·검증 결과 (mode: key 인증키 · session 로그인 세션 · sample 견본 키(가입 불필요) · per_api 서비스마다 키 · pending 승인·신청 대기)
SITES.update({
    "data.ex.co.kr": {"name": "한국도로공사 고속도로 공공데이터 포털", "env": "", "mode": "sample", "how": "가입 없이 key=test로 오픈API 호출 확인 (운영은 회원가입 → 인증키)"},
    "www.foodsafetykorea.go.kr": {"name": "식품안전나라 (식약처)", "env": "", "mode": "sample", "how": "가입 없이 sample 키로 견본 5행 (전수는 회원가입 → 인증키)"},
    "openapi.foodsafetykorea.go.kr": {"name": "식품안전나라 오픈API", "env": "", "mode": "sample", "how": "sample 키 견본"},
    "www.safemap.go.kr": {"name": "생활안전지도 (행안부)", "env": "SAFEMAP_API_KEY", "mode": "pending", "how": "가입·인증키 신청 완료 — 승인 대기 (등록되지 않은 서비스키)"},
    "apihub.kma.go.kr": {"name": "기상청 API허브", "env": "KMA_APIHUB_API_KEY", "mode": "pending", "how": "가입·인증키 완료 — API마다 활용신청 필요(키는 같음)"},
    "www.lofin365.go.kr": {"name": "지방재정365 (행안부)", "env": "LOFIN365_API_KEY", "mode": "key", "how": "회원가입 → 마이페이지 인증키. 포털 링크는 공시 화면이라 제목 유사도로 데이터셋 짝짓기"},
    "open.assembly.go.kr": {"name": "열린국회정보", "env": "OPEN_ASSEMBLY_API_KEY", "mode": "key", "how": "회원가입 → 인증키(즉시). 상세 시트는 키 없이도 조회"},
    "opendart.fss.or.kr": {"name": "OpenDART (금감원 전자공시)", "env": "OPEN_DART_API_KEY", "mode": "key", "how": "인증키 신청(이메일 인증) → 즉시"},
    "www.safetydata.go.kr": {"name": "재난안전데이터공유플랫폼 (행안부)", "env": "", "mode": "session", "how": "회원가입·로그인 → 데이터별 샘플 다운로드(첫 100건). 전수 API는 데이터별 이용신청"},
    "www.culture.go.kr": {"name": "문화공공데이터광장", "env": "CULTURE_API_KEY", "mode": "per_api", "how": "회원가입 → API마다 활용신청 → API별 서비스키가 메일로 (115건 신청)"},
    "culture.go.kr": {"name": "문화공공데이터광장", "env": "CULTURE_API_KEY", "mode": "per_api", "how": "API마다 활용신청 → API별 서비스키 메일 (115건 신청)"},
    "data.gg.go.kr": {"name": "경기데이터드림", "env": "", "mode": "session", "how": "로그인 세션 · 상세 시트(searchSheetData)와 오픈API(키 없이 견본)"},
    "www.work24.go.kr": {"name": "고용24 (고용노동부)", "env": "", "mode": "per_api", "how": "회원가입 → 서비스별 인증키(11개 승인). 채용정보는 기업회원 전용"},
    "data.mafra.go.kr": {"name": "농림축산식품 공공데이터 포털", "env": "DATA_MAFRA_API_KEY", "mode": "key", "how": "회원가입 시 인증키 자동 발급. 파일은 로그인 없이, API는 sample 키 견본"},
    "www.jejudatahub.net": {"name": "제주데이터허브", "env": "JEJU_DATA_HUB_API_KEY", "mode": "key", "how": "가입·키 완료. 상세 미리보기 표로 확인 — 원본·API는 데이터별 프로젝트 담기 필요"},
    "jejudatahub.net": {"name": "제주데이터허브", "env": "JEJU_DATA_HUB_API_KEY", "mode": "key", "how": "상세 미리보기 표로 확인"},
    "www.nongsaro.go.kr": {"name": "농사로 (농촌진흥청)", "env": "NONGSARO_API_KEY", "mode": "pending", "how": "회원가입 없음 — 공공데이터 신청서 제출 → 승인 대기"},
    "nongsaro.go.kr": {"name": "농사로 (농촌진흥청)", "env": "NONGSARO_API_KEY", "mode": "pending", "how": "공공데이터 신청 → 승인 대기"},
    "openapi.jigu.go.kr": {"name": "택지정보시스템 (LX)", "env": "", "mode": "sample", "how": "가입 없이 월별 파일(/openApi/down.do)"},
    "data.gm.go.kr": {"name": "광명시 데이터", "env": "", "mode": "pending", "how": "파일 다운로드에 로그인 필요 — 보류"},
    "eis.work24.go.kr": {"name": "고용24 고용행정통계", "env": "", "mode": "per_api", "how": "통계 화면 — 오픈API 대응 없음"},
})

# 2026-10-27 가입·검증 (pds/probe/kosis_sites.py · reb_sites.py)
SITES.update({
    "kosis.kr": {"name": "KOSIS 국가통계포털 (국가데이터처)", "env": "KOSIS_API_KEY", "mode": "key",
                 "how": "회원가입 → 공유서비스 활용신청 → 인증키(즉시). 통계표는 Param/statisticsParameterData.do(orgId·tblId), 목록은 statisticsList.do. 분당 200건·4만 셀"},
    "stat.kosis.kr": {"name": "KOSIS 기관 통계 (stat.kosis.kr)", "env": "KOSIS_API_KEY", "mode": "key", "how": "kosis.kr 키와 같음 — 같은 OpenAPI로 orgId·tblId 호출"},
    "www.reb.or.kr": {"name": "한국부동산원 부동산통계정보 R-ONE", "env": "REB_API_KEY", "mode": "key",
                      "how": "회원가입 → 오픈API 인증키(즉시). SttsApiTbl·SttsApiTblItm·SttsApiTblData (STATBL_ID·DTACYCLE_CD)"},
    "reb.or.kr": {"name": "한국부동산원 부동산통계정보 R-ONE", "env": "REB_API_KEY", "mode": "key", "how": "R-ONE 오픈API 인증키"},
    "plus.kipris.or.kr": {"name": "KIPRIS Plus (특허정보)", "env": "KIPRIS_API_KEY", "mode": "pending",
                          "how": "키 발급 완료 — 서비스마다 장바구니 → 이용 신청(무료·유료)이 필요. 신청 전에는 resultCode 101/30 Not Registered. "
                                 "REST 서비스 90건 신청 대기, BULK 전용 81건은 신청 후 파일 (pds/probe/kipris_sites.py)"},
})



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
        s = SITES.get(host, {"name": host, "env": env_name(host),
                             "how": "사이트에서 회원가입 → 오픈API 인증키 신청 — 확인 필요"})
        pr = [_priority(r) for r in rows]
        groups.append((host, s, rows, pr.count(1), len(rows)))
    ok_ = lambda st: st.get("mode") in ("session", "sample", "per_api") or (st.get("mode") != "pending" and _have(st["env"]))  # noqa: E731
    have = [g for g in groups if ok_(g[1])]
    wait = [g for g in groups if g[1].get("mode") == "pending"]
    need = sorted([g for g in groups if not ok_(g[1]) and g[1].get("mode") != "pending"], key=lambda g: (-g[3], -g[4]))
    total_need = sum(g[4] for g in need)

    L = ["# 추가 외부 키", "",
         f"외부 사이트 키가 있어야 검증·편입할 수 있는 데이터 **{len(links):,}건** — 제공처 {len(groups)}곳. "
         f"키·접근 확보 {len(have)}곳({sum(g[4] for g in have):,}건) · 승인·신청 대기 {len(wait)}곳({sum(g[4] for g in wait):,}건) · "
         f"**새로 받아야 하는 곳 {len(need)}곳({total_need:,}건)**.",
         "",
         "- 2026-10-06 가입·검증: 경기데이터드림·제주데이터허브·재난안전·농식품·국회·지방재정365·문화(API별 키)·OpenDART·고용24 확보, "
         "식품안전나라·도로공사·택지정보는 가입 없이 견본 키. 생활안전지도·농사로·기상청 API허브는 승인·활용신청 대기.",
         "",
         "- 받은 키는 `.env`에 아래 **변수 이름**으로 넣어 주세요 (값은 git에 올라가지 않습니다).",
         "- 순서는 1순위(바로 편입) 데이터가 많은 곳부터. 1순위는 2·3차 부문 검토에서 '전국 원장·실시간·많이 이어짐'으로 판정된 것.",
         "- 각 데이터의 포털 링크로 들어가 '바로가기'를 누르면 제공처 페이지로 갑니다. 아래 '제공처 예'가 그 주소입니다.",
         f"- 생성: `python -m pds.expand.external_keys` (제공처 주소는 포털 조회값, {len(links)}건 모두 확인)",
         "", "## 새로 받아야 하는 키", "",
         "| # | 제공처 | 데이터 | 1순위 | .env 변수 | 발급 |", "|---:|---|---:|---:|---|---|"]
    for n, (host, s, rows, p1, cnt) in enumerate(need, 1):
        L.append(f"| {n} | [{s['name']}](https://{host}) | {cnt} | {p1} | `{s['env']}` | {s['how']} |")
    L += ["", "## 승인·신청 대기", "", "| 제공처 | 데이터 | .env 변수 | 상태 |", "|---|---:|---|---|"]
    for host, s, rows, p1, cnt in sorted(wait, key=lambda g: -g[4]):
        L.append(f"| [{s['name']}](https://{host}) | {cnt} | `{s['env']}` | {s['how']} |")
    L += ["", "## 확보한 키·접근 (바로 편입 진행 가능)", "", "| 제공처 | 데이터 | 1순위 | .env 변수 | 방식 |", "|---|---:|---:|---|---|"]
    for host, s, rows, p1, cnt in sorted(have, key=lambda g: -g[4]):
        L.append(f"| [{s['name']}](https://{host}) | {cnt} | {p1} | `{s['env'] or '-'}` | {s.get('how', '')} |")
    L += ["", "## 제공처별 데이터", ""]
    for host, s, rows, p1, cnt in need + wait + sorted(have, key=lambda g: -g[4]):
        status = "확보" if ok_(s) else ("대기" if s.get("mode") == "pending" else "필요")
        L += [f"### {s['name']} — {cnt}건 · 키 {status}", "",
              f"제공처 예: {rows[0].get('link')}", "", "| 우선 | 데이터 | 기관 | 포털 |", "|---:|---|---|---|"]
        for r in sorted(rows, key=lambda r: (_priority(r), r["title"])):
            L.append(f"| {_priority(r)} | {r['title']} | {r['agency']} | [{r['id']}]({r['url']}) |")
        L.append("")
    return "\n".join(L) + "\n"


ENV_START, ENV_END = "# ── 외부 사이트 키", "# ── Postgres"
PAIRED = {"VWORLD_API_KEY": [("VWORLD_DOMAIN", "브이월드 키에 등록한 서비스 URL (개발키면 필요)")],
          "SGIS_CONSUMER_KEY": [("SGIS_CONSUMER_SECRET", "SGIS 보안 Key (서비스 ID와 한 쌍)")]}


def env_block() -> str:
    """.env.example의 외부 사이트 키 구간 — Docs의 사이트 커버리지(site_coverage.json)와 같은 상태로 변수마다 제공처·데이터 수·검증 수를 적는다.
    내 .env와 견줘 빈 곳을 채워 나간다. 값은 읽지 않는다."""
    sites = json.loads((config.KNOWLEDGE / "expansion" / "site_coverage.json").read_text(encoding="utf-8"))["sites"]
    by: dict[str, dict] = {}
    for s in sites:
        env = s.get("env") or ""
        if not env or env.startswith("("):
            continue  # API가 없거나 키 없이(견본·세션·파일) 되는 곳
        e = by.setdefault(env, {"names": [], "total": 0, "verified": 0, "keys": set()})
        e["total"] += s["total"]
        e["verified"] += s["verified"]
        e["keys"].add(s["key"])
        if s["name"] not in e["names"]:
            e["names"].append(s["name"])
    rank = lambda e: 0 if any(k.startswith("보유") for k in e["keys"]) else 1 if "승인·신청 대기" in e["keys"] else 2  # noqa: E731
    rows = sorted(({"env": k, **v} for k, v in by.items()), key=lambda e: (rank(e), -e["total"]))
    label = {0: "확보", 1: "대기", 2: "필요"}
    L = [f"{ENV_START} — 생성: python -m pds.expand.external_keys (Docs 사이트 커버리지와 같은 상태)",
         "# 상태: 확보=키로 검증 중 · 대기=신청·승인 기다림 · 필요=아직 키 없음. 숫자는 그 사이트에 링크된 포털 데이터 수(검증 수)",
         "# 비어 있는 변수를 채우면 그 사이트 검증을 돌릴 수 있다. 사이트별 발급 방법은 추가외부키.md, 발급 방법이 '확인 필요'인 곳은 아직 사이트를 살펴보지 않은 곳"]
    w = max(len(e["env"]) for e in rows) + 2
    for e in rows:
        L.append(f"{(e['env'] + '='):<{w}}# [{label[rank(e)]}] {' · '.join(e['names'])[:50]} — {e['total']:,}건 (검증 {e['verified']:,})")
        for x, note in PAIRED.get(e["env"], []):
            L.append(f"{(x + '='):<{w}}#   {note}")
    return "\n".join(L) + "\n"


def write_env_example() -> None:
    p = config.ROOT / ".env.example"
    t = p.read_text(encoding="utf-8")
    a, b = t.index(ENV_START), t.index(ENV_END)
    p.write_text(t[:a] + env_block() + "\n" + t[b:], encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    out = config.ROOT / "추가외부키.md"
    out.write_text(build(), encoding="utf-8")
    write_env_example()
    print(out, config.ROOT / ".env.example")
