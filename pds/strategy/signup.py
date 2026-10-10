"""외부 가입 안내 — data.go.kr 활용신청과 별개로 제공처 사이트에 가입·인증키가 필요한 데이터를 전략 응답에 밝힌다.

검증 데이터: access.channel = external, 발급처는 services[0].security.issuer
목록 데이터: catalog api_type = LINK (포털 '바로가기'가 제공처 사이트로 감) — 제공처 주소는 external_links.json에 있으면 쓴다
사이트별 절차는 아래 GUIDE (사용자 안내용).
"""
from __future__ import annotations

import json
from functools import lru_cache
from urllib.parse import urlparse

from pds import config

GENERIC = "제공처 사이트 회원가입 → 오픈API 인증키 신청 (절차는 사이트에서 확인)"

# 사용자에게 보이는 가입 절차 (2026-10 각 사이트 기준). pds/expand/external_keys.py SITES는 우리 가입 진행 기록이라 따로 둔다.
GUIDE: dict[str, tuple[str, str]] = {
    "data.gg.go.kr": ("경기데이터드림", "회원가입 → 인증키 발급(즉시)"),
    "data.seoul.go.kr": ("서울 열린데이터광장", "회원가입 → 인증키 신청(즉시) — URL 경로에 키를 넣는 방식"),
    "openapi.seoul.go.kr": ("서울 열린데이터광장", "회원가입 → 인증키 신청(즉시) — URL 경로에 키를 넣는 방식"),
    "jejudatahub.net": ("제주데이터허브", "회원가입 → 인증키 발급, 원본·API는 데이터별로 프로젝트에 담아 신청"),
    "safetydata.go.kr": ("재난안전데이터공유플랫폼 (행안부)", "회원가입 → 데이터별 이용신청 → 승인 후 API 키 (샘플은 로그인만으로 100건)"),
    "open.assembly.go.kr": ("열린국회정보", "회원가입 → 인증키 발급(즉시)"),
    "vworld.kr": ("브이월드 (국토부 공간정보 오픈플랫폼)", "회원가입 → 오픈API 인증키 신청(서비스 URL 기재) → 즉시 발급"),
    "api.vworld.kr": ("브이월드 (국토부 공간정보 오픈플랫폼)", "회원가입 → 오픈API 인증키 신청(서비스 URL 기재) → 즉시 발급"),
    "lofin365.go.kr": ("지방재정365 (행안부)", "회원가입 → 마이페이지에서 오픈API 인증키 발급"),
    "foodsafetykorea.go.kr": ("식품안전나라 (식약처)", "회원가입 → 공공데이터 활용 → 인증키 신청 → 승인(보통 당일). 견본 5행은 sample 키로"),
    "openapi.foodsafetykorea.go.kr": ("식품안전나라 (식약처)", "회원가입 → 공공데이터 활용 → 인증키 신청 → 승인(보통 당일). 견본 5행은 sample 키로"),
    "api.kcisa.kr": ("문화공공데이터광장", "회원가입 → API마다 활용신청 → API별 서비스키가 메일로"),
    "culture.go.kr": ("문화공공데이터광장", "회원가입 → API마다 활용신청 → API별 서비스키가 메일로"),
    "open.law.go.kr": ("국가법령정보 공동활용 (법제처)", "회원가입 → OPEN API 신청(사용 IP·도메인 등록) → 승인 후 OC(이메일 ID)로 호출"),
    "law.go.kr": ("국가법령정보 공동활용 (법제처)", "회원가입 → OPEN API 신청(사용 IP·도메인 등록) → 승인 후 OC(이메일 ID)로 호출"),
    "data.mafra.go.kr": ("농림축산식품 공공데이터 포털", "회원가입 시 인증키 자동 발급 (파일은 로그인 없이 다운로드)"),
    "data.ex.co.kr": ("한국도로공사 고속도로 공공데이터 포털", "회원가입 → 마이페이지 인증키 발급(즉시). 견본은 key=test로"),
    "apihub.kma.go.kr": ("기상청 API허브", "회원가입 → 인증키 발급(즉시) → 쓰려는 API마다 활용신청 버튼"),
    "data.kma.go.kr": ("기상자료개방포털", "회원가입 → 로그인 후 파일 다운로드"),
    "opendart.fss.or.kr": ("OpenDART (금감원 전자공시)", "인증키 신청(이메일 인증) → 즉시 발급"),
    "work24.go.kr": ("고용24 (고용노동부)", "회원가입 → 오픈API 서비스별 인증키 신청 → 승인 (채용정보는 기업회원 전용)"),
    "open.neis.go.kr": ("나이스 교육정보 개방 포털", "로그인(SNS) → 인증키 신청(즉시)"),
    "safemap.go.kr": ("생활안전지도 (행안부)", "회원가입 → 오픈API 인증키 신청 → 승인"),
    "nongsaro.go.kr": ("농사로 (농촌진흥청)", "공공데이터 이용 신청서 제출 → 승인 후 키"),
    "plus.kipris.or.kr": ("KIPRIS Plus (특허정보)", "회원가입 → 서비스별 신청(무료/유료 구분) → 승인"),
    "bigdata.kepco.co.kr": ("한전 전력데이터 개방포털", "회원가입 → 오픈API 인증키 신청"),
    "its.go.kr": ("국가교통정보센터 ITS", "회원가입 → 오픈API 인증키 신청 → 승인"),
    "opendata.koroad.or.kr": ("도로교통공단 TAAS", "회원가입 → 인증키 신청(즉시)"),
    "utic.go.kr": ("도시교통정보센터 UTIC (경찰청)", "회원가입 → 인증키 신청 → 승인"),
    "data.kric.go.kr": ("철도산업정보센터", "회원가입 → 인증키 신청"),
    "juso.go.kr": ("도로명주소 (행안부)", "회원가입 없이 신청서 → 승인키(즉시)"),
    "kopis.or.kr": ("공연예술통합전산망 KOPIS", "회원가입 → 서비스키 신청(즉시)"),
    "kobis.or.kr": ("영화관입장권통합전산망 KOBIS", "회원가입 → 키 발급(즉시)"),
    "opinet.co.kr": ("오피넷 (석유공사 유가)", "회원가입 → 오픈API 키 신청"),
    "ntis.go.kr": ("국가과학기술지식정보서비스 NTIS", "회원가입 → 오픈API 신청 → 승인"),
    "info.childcare.go.kr": ("보육통합정보시스템", "인증키 신청 → 승인"),
    "data.floodmap.go.kr": ("홍수위험지도 정보시스템 (환경부)", "회원가입 → 인증키 신청 (절차는 사이트에서 확인)"),
    "eum.go.kr": ("토지이음", "가입 없이 파일 다운로드"),
    "file.localdata.go.kr": ("지방행정 인허가(LOCALDATA)", "가입 없이 파일 다운로드"),
    "openapi.jigu.go.kr": ("택지정보시스템 (LX)", "가입 없이 월별 파일 다운로드"),
}
NO_SIGNUP = {"eum.go.kr", "file.localdata.go.kr", "openapi.jigu.go.kr"}


@lru_cache(maxsize=1)
def _links() -> dict[str, str]:
    p = config.KNOWLEDGE / "expansion" / "external_links.json"
    if not p.exists():
        return {}
    return {r["id"]: urlparse(r.get("link") or "").netloc for r in json.loads(p.read_text(encoding="utf-8")) if r.get("link")}


@lru_cache(maxsize=1)
def _agency_hosts() -> dict[str, str]:
    """기관 → 검증된 외부 데이터의 발급처 (가장 많은 것) — 목록 데이터의 제공처 주소를 모를 때 같은 기관 사례로 추정."""
    from collections import Counter, defaultdict
    from pds.service import index as sindex
    by: dict[str, Counter] = defaultdict(Counter)
    for d in sindex.get().datasets.values():
        if d.get("channel") == "external":
            iss = (((d.get("services") or [{}])[0]).get("security") or {}).get("issuer")
            if iss:
                by[(d.get("agency") or {}).get("name") or ""][iss] += 1
    return {a: c.most_common(1)[0][0] for a, c in by.items() if a}


def _site(host: str) -> tuple[str, str, str] | None:
    """(정규 호스트, 사이트 이름, 가입 절차)"""
    bare = (host or "").lower().split(":")[0].removeprefix("www.")
    if bare in GUIDE:
        return (bare, *GUIDE[bare])
    return None


def note(ds_id: str, external: bool, issuer: str | None = None, agency: str | None = None) -> dict | None:
    """외부 가입이 필요하면 {site, host, how, required, estimated, text}, 포털 데이터면 None. required=False는 제공처 사이트지만 가입 없이 받는 경우."""
    if not external:
        return None
    host = issuer or _links().get(ds_id)
    estimated = not host and bool(agency and _agency_hosts().get(agency))
    host = host or (_agency_hosts().get(agency) if agency else None)
    s = _site(host) if host else None
    if s and s[0] in NO_SIGNUP:
        return {"site": s[1], "host": host, "how": s[2], "required": False, "estimated": estimated,
                "text": f"외부 사이트 {s[1]}: {s[2]}"}
    name = s[1] if s else (host or "제공처 사이트(포털 '바로가기'로 확인)")
    how = s[2] if s else GENERIC
    return {"site": name, "host": host, "how": how, "required": True, "estimated": estimated,
            "text": f"외부 가입 필요 — {name}{'(같은 기관 사례로 추정)' if estimated else ''}: {how} (data.go.kr 활용신청과 별개)"}


def catalog_external(row: dict) -> bool:
    return str(row.get("api_type") or "") == "LINK"


def summarize(p: dict) -> list[dict]:
    """응답 전체(datasets·candidates·unverified_leads)에서 외부 가입이 필요한 사이트별로 묶는다."""
    by: dict[str, dict] = {}
    for sec in ("datasets", "candidates", "unverified_leads"):
        for x in p.get(sec) or []:
            n = (x.get("access") or {}).get("signup")
            if not n or not n["required"]:
                continue
            g = by.setdefault(n["site"], {"site": n["site"], "host": n["host"], "how": n["how"], "required": n["required"], "datasets": []})
            g["datasets"].append({"id": x["id"], "title": x["title"], "tier": x.get("tier", "verified")})
    return list(by.values())


# ─────────────────────────── 키 요청 절차 (에이전트 규약)
ENV_BY_HOST = {  # .env.example과 같은 이름 — 없는 사이트는 호스트에서 만든다
    "data.go.kr": "DATA_GO_KR_SERVICE_KEY", "vworld.kr": "VWORLD_API_KEY", "api.vworld.kr": "VWORLD_API_KEY",
    "data.seoul.go.kr": "DATA_SEOUL_API_KEY", "openapi.seoul.go.kr": "DATA_SEOUL_API_KEY",
    "open.neis.go.kr": "OPEN_NEIS_API_KEY", "open.law.go.kr": "OPEN_LAW_GO_KR_API_KEY", "law.go.kr": "OPEN_LAW_GO_KR_API_KEY",
}
PORTAL_HOW = "data.go.kr 로그인 → 데이터마다 '활용신청'(대부분 자동승인) → 마이페이지 '일반 인증키(Decoding)'"
AGENT_PROTOCOL = [
    "credentials.required가 true면 데이터를 받기 전에 사용자에게 키가 필요하다고 먼저 알린다 — 키 없이 호출하거나 키를 지어내지 않는다.",
    "env 항목마다 사이트·발급 절차(how)·해당 데이터(datasets)를 사용자에게 보여 준다.",
    "프로젝트 폴더에 .env 파일을 env_sample 내용으로 만들어(이미 있으면 빠진 줄만 덧붙여) 값은 비워 두고, 사용자에게 직접 채워 달라고 요청한다.",
    "사용자가 채웠다고 하면 .env에서 읽어 쓴다. 키 값을 대화·코드·로그에 그대로 옮겨 적지 않고, .env는 .gitignore에 넣는다.",
]


def env_name(host: str | None) -> str:
    bare = (host or "").lower().split(":")[0].removeprefix("www.")
    if bare in ENV_BY_HOST:
        return ENV_BY_HOST[bare]
    import re
    stem = re.sub(r"^(api|openapi|open)\.", "", bare) or "external"
    return re.sub(r"[^A-Z0-9]+", "_", stem.upper()).strip("_") + "_API_KEY"


def credentials(p: dict) -> dict:
    """전략에 쓰인 데이터(datasets)를 받는 데 필요한 키 — 사이트별 .env 변수·발급 절차·대상 데이터, .env 견본, 에이전트 절차.
    후보·미검증 단서는 고르기 전이라 넣지 않는다 (external_signup에 따로 있다)."""
    by: dict[str, dict] = {}

    def add(var: str, site: str, how: str, ds: dict | None):
        e = by.setdefault(var, {"name": var, "site": site, "how": how, "datasets": []})
        if ds and ds["id"] not in e["datasets"]:
            e["datasets"].append(ds["id"])
    for d in p.get("datasets") or []:
        acc = d.get("access") or {}
        n = acc.get("signup")
        if acc.get("channel") == "portal" and str(acc.get("scheme") or "file") != "file":
            add("DATA_GO_KR_SERVICE_KEY", "공공데이터포털 (data.go.kr)", PORTAL_HOW, d)
        elif n and n.get("required"):
            add(env_name(n.get("host")), n["site"], n["how"], d)
    if any((j.get("on") or {}).get("transform") in ("R-12", "R-13") for j in p.get("joins") or []):  # 좌표·주소 → 필지(PNU)
        add("VWORLD_API_KEY", "브이월드 (국토부 공간정보 오픈플랫폼)", GUIDE["vworld.kr"][1] + " — 좌표·주소를 필지(PNU)로 바꿀 때", None)
    env = list(by.values())
    sample = "\n".join(["# 공공데이터 키 — 값을 채워 저장한다. 이 파일은 git에 올리지 않는다 (.gitignore에 .env)"]
                       + [f"# {e['site']}: {e['how']}" + (f" · 데이터 {', '.join(e['datasets'][:6])}" if e["datasets"] else "")
                          + f"\n{e['name']}=" + ("\nVWORLD_DOMAIN=  # 키에 등록한 서비스 URL" if e["name"] == "VWORLD_API_KEY" else "") for e in env]) + "\n" if env else ""
    return {"required": bool(env), "env": env, "env_sample": sample, "agent_protocol": AGENT_PROTOCOL if env else []}
