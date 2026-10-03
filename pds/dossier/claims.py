"""자동 claim — Phase 1 결정·Phase 2 실측을 근거 있는 진술로 (KNOWLEDGE-SPEC §3.5, §7-3).

번호 규약 (id가 레시피·전략 응답의 인용 대상이라 재생성해도 바뀌지 않게 kind별 고정 슬롯):
  01 access · 02 cadence · 03 key · 04 coverage · 05 legal_basis(보유근거) · 06~09 admin_note · 10~19 pitfall ·
  20 legal_basis(부문 법 계층)
  50 이상은 사람이 쓰는 claim (생성기가 건드리지 않는다)
생성한 claim에는 qualifiers.generated_by가 붙고, 재생성 때 이것만 교체된다.
"""
from __future__ import annotations

import datetime as dt
import re
from functools import lru_cache

import yaml

from pds import config

GEN = "pds.dossier.claims"
REVIEW = config.KNOWLEDGE / "sectors" / "_review_log.md"
REVIEW_REL = "knowledge/sectors/_review_log.md"
SUBS_REL = "knowledge/sectors/subsectors.yaml"
MEASURED_TTL = dt.timedelta(days=183)  # 실측은 반년 뒤 재확인 큐 (recheck)


def _norm(s: str) -> str:
    return re.sub(r"[\s·및()]|교육$", "", s)


@lru_cache
def review_sections() -> list[dict]:
    """_review_log.md → [{heading, line, at, by, bullets: [{label, text, line}]}]"""
    out, cur = [], None
    for n, ln in enumerate(REVIEW.read_text(encoding="utf-8").splitlines(), 1):
        if ln.startswith("## "):
            h = ln[3:].strip()
            m = re.search(r"(20\d{2}-\d{2}-\d{2})(?:,\s*([^)]+))?", h)
            by = (m.group(2) or "").strip() if m else ""
            cur = {"heading": re.sub(r"\s*\(20\d{2}.*$", "", h).strip(), "line": n, "at": m.group(1) if m else None,
                   "by": "구름" if by == "구름" else (f"Claude({by})" if by else None), "bullets": []}
            out.append(cur)
        elif cur and ln.startswith("- "):
            m = re.match(r"- \*\*(.+?)\*\*:?\s*(.*)", ln) or re.match(r"- (결정|기준|이유|규칙|이관|전역 키|주의)(?: \(.+?\))?:\s*(.*)", ln)
            if m:
                cur["bullets"].append({"label": m.group(1).strip(), "text": m.group(2).strip(), "line": n})
    return out


def review_for(sector: str) -> list[tuple[dict, dict]]:
    """부문 'F - A'에 해당하는 결정 줄: ①머리말이 영역 이름인 줄 ②제목에 영역이 있는 절의 결정·기준 ③제목에 분야가 있는 절의 기준."""
    field_, area = sector.split(" - ", 1)
    na = _norm(area)
    secs = review_sections()

    def same(x: str) -> bool:  # 두 글자 이름('관광'·'금융')은 정확히 같을 때만
        x = _norm(x)
        return bool(x) and (x == na or (min(len(x), len(na)) >= 3 and (x in na or na in x)))

    hits = [(s, b) for s in secs for b in s["bullets"] if same(re.sub(r"\(.*?\)", "", b["label"]))]
    if hits:
        return hits[:2]
    for s in secs:  # 제목의 영역 부분(' - ' 뒤, ' · '로 나열)만 비교
        h = re.sub(r"^20\d{2}-\d{2}-\d{2}\s+", "", s["heading"])
        areas = (h.split(" - ", 1)[1] if " - " in h else h).split(" · ")
        if any(same(a) for a in areas):
            got = [(s, b) for b in s["bullets"] if b["label"] in ("결정", "기준", "이유")]
            if got:
                return got[:2]
    for s in secs:  # 분야 전체를 다룬 절만 (예: '과학기술', '국토관리 재구성 …') — 다른 영역 절로 새지 않게
        h = s["heading"]
        if h.startswith(field_) and not h[len(field_):].lstrip().startswith("-"):
            got = [(s, b) for b in s["bullets"] if b["label"] in ("기준", "결정")]
            if got:
                return got[:1]
    return []


@lru_cache
def _subsector_defs() -> dict:
    out = {}
    for s in yaml.safe_load((config.KNOWLEDGE / "sectors" / "subsectors.yaml").read_text(encoding="utf-8")) or []:
        for x in s["subsectors"] + ([s["default"]] if s.get("default") else []):
            out[(s["sector"], x["slug"])] = x | {"_at": str(s.get("decided_at")), "_by": s.get("decided_by")}
    return out


def _ev_measured(src: str, observed: str | None, detail: str | None = None) -> dict:
    return {k: v for k, v in {"type": "measured", "source": src, "observed_at": observed, "detail": detail}.items() if v}


def _c(dsid: str, slot: int, kind: str, value: str, evidence: list[dict], rank: str = "normal",
       valid_until: str | None = None, **qual) -> dict:
    return {"id": f"c-{dsid}-{slot:02d}", "kind": kind, "value": value, "evidence": evidence,
            "qualifiers": {"generated_by": GEN, **{k: v for k, v in qual.items() if v is not None}}, "rank": rank,
            **({"valid_until": valid_until} if valid_until else {})}


@lru_cache
def _laws() -> dict:
    from pds.schema import store
    return {d["law_id"]: d for d, _ in store.iter_raw("law")}


def _law_articles(law_id: str | None, nos: list[str]) -> list[tuple[str, str | None]]:
    """확보한 원문에 실제로 있는 조문만 [(번호, 제목)]."""
    law = _laws().get(law_id or "")
    if not law:
        return []
    have = {a["no"]: a.get("title") for a in law.get("articles") or []}
    return [(n, have[n]) for n in nos if n in have]


@lru_cache
def _tree() -> dict:
    return {d["id"]: d for d in yaml.safe_load((config.KNOWLEDGE / "sectors" / "sector_tree.yaml").read_text(encoding="utf-8")) or []}


def _domain(did: str | None) -> dict | None:
    return _tree().get(did or "")


def _domain_laws(dom: dict) -> list[tuple[str, str]]:
    from pds.laws.fetch import ALIAS, LAW_NAME, index
    idx, out = index(), []
    text = re.split(r"\s—\s", dom.get("law") or "")[0]
    for part in re.split(r"[·,]", text):
        m = LAW_NAME.search(part.strip())
        if m:
            name = m.group(1).strip()
            lid = idx.get(name) or idx.get(ALIAS.get(name, ""))
            if lid and lid not in [x[0] for x in out]:
                out.append((lid, _laws()[lid]["name"]))
    return out


DATEISH = re.compile(r"^(19|20)\d{2}(\d{2}){0,2}$|^(19|20)\d{2}-\d{2}(-\d{2})?$")


def _date_params(svcs: list[dict], run: dict) -> str:
    """검증 호출에 쓰인 날짜·연도형 조건. 실행 기록에 params가 있으면 그것(2026-09-30 이후), 없으면 명세 예시값(deep.build_params가 쓰는 값)."""
    got = {}
    for o in run.get("ops") or []:
        got.update({k: v for k, v in (o.get("params") or {}).items() if DATEISH.match(str(v))})
    if not got:
        for s in svcs:
            for p in s.get("params") or []:
                if p.get("example") and DATEISH.match(str(p["example"])) and not re.search(r"(page|rows|size)", p["name"], re.I):
                    got[p["name"]] = p["example"]
    return ", ".join(f"{k}={v}" for k, v in list(got.items())[:3])


def make(rec: dict, target: dict, run: dict, apply: dict | None, catalog_row) -> list[dict]:
    dsid = rec["id"]
    ver = rec.get("verification") or {}
    observed = ver.get("probed_at")
    until = (dt.date.fromisoformat(observed) + MEASURED_TTL).isoformat() if observed else None
    run_src = f"probe/runs/{dsid}.json"
    out = []

    # 01 access — 어떻게 받나 (승인·키·실호출 결과)
    svcs = rec.get("services") or []
    if rec["channel"] == "external":
        iss = next((s["security"]["issuer"] for s in svcs), None) or "외부 사이트"
        sec = next((s["security"] for s in svcs), {})
        if sec.get("scheme") == "session":  # 브이월드 공간정보 다운로드 — 키 없이 로그인만
            fm = ", ".join(next((s.get("format") for s in svcs), []) or []).upper()
            val = (f"{iss} 로그인 후 공간정보 다운로드 페이지에서 시도별 파일({fm}) — 인증키 불필요, 포털 활용신청과 별개. "
                   f"{ver.get('probed_at')} 한 시도 파일 다운로드·파싱 성공")
        else:
            val = (f"외부 사이트 {iss} 인증키 필요 ({sec.get('in', '?')} 파라미터 {sec.get('name', '?')}) — 포털 활용신청과 별개. "
                   f"{ver.get('probed_at')} 실호출 {ver.get('ops_ok') or ''} 성공")
        ev = [_ev_measured(run_src, observed, f"ops_ok {ver.get('ops_ok')}"),
              {"type": "admin_review", "source": "knowledge/key_issuers.yaml", "by": "구름", "detail": f"발급처 {iss}"}]
    elif rec["kind"] in ("FILE", "STD") and rec.get("distributions"):
        d = rec["distributions"][0]
        val = f"포털 파일 다운로드 ({d.get('format') or '?'}, {d.get('size') or '?'} bytes) — 활용신청 없이 받음. {observed} 다운로드·파싱 성공"
        ev = [_ev_measured(run_src, observed, f"rows {ver.get('rows')}")]
    else:
        appr = {"auto": "자동승인", "review": "심의 후 승인", "unknown": "승인유형 미기록"}.get(
            next((s.get("approval") for s in svcs), "unknown"), "승인유형 미기록")
        dev = next((s.get("traffic", {}).get("dev") for s in svcs if s.get("traffic")), None)
        val = (f"포털 활용신청 {appr}, serviceKey(query)" + (f", 개발계정 일 {dev:,}회" if dev else "")
               + f". {observed} 실호출 성공 오퍼레이션 {ver.get('ops_ok') or '?'}")
        ev = [_ev_measured(run_src, observed, f"ops_ok {ver.get('ops_ok')}")]
        if apply:
            ev.append(_ev_measured(f"probe/apply/{dsid}.json", (apply.get("at") or "")[:10] or None, f"심의여부 {apply.get('심의여부')}"))
        if dev:
            ev.append({"type": "portal_meta", "source": "catalog:daily_traffic_dev", "detail": f"{dev}"})
    out.append(_c(dsid, 1, "access", val, ev, "preferred", until))

    # 02 cadence — 명세상 주기 + 실측 최신 날짜
    cyc = rec.get("accrual_periodicity")
    ev, parts = [], []
    if cyc:
        parts.append(f"명세상 {cyc}")
        ev.append({"type": "portal_meta", "source": "catalog:update_cycle", "detail": cyc})
    probe_cond = _date_params(svcs, run)
    if ver.get("latest"):
        lag = ver.get("lag_days")
        note = " — 미래 날짜(일정·계획형) 포함" if isinstance(lag, int) and lag < 0 else ""
        if probe_cond:
            note += f" — 검증 호출 조건({probe_cond}) 기준이라 데이터 자체의 최신성과 다를 수 있음"
        parts.append(f"실측 최신 행 날짜 {ver['latest']} (관측일 기준 {lag}일 전){note}")
        ev.append(_ev_measured(f"probe/synthesis#{dsid}", observed, f"latest {ver['latest']}, lag {lag}"))
    elif rec.get("cycle") == "event":
        parts.append("이벤트 주기 (선거 등 이벤트 때 생성 후 불변)")
        ev.append({"type": "admin_review", "source": SUBS_REL, "by": "구름", "detail": "cycle: event"})
    if not ev:
        parts.append("주기 정보 없음 — 갱신 관찰(7일 재호출) 필요")
        ev.append({"type": "portal_meta", "source": "catalog:update_cycle", "detail": "비어 있음"})
    out.append(_c(dsid, 2, "cadence", " · ".join(parts), ev, valid_until=until))

    # 03 key — 실측 조인 키 (없으면 없다는 사실도 claim)
    fks = (rec.get("schema") or {}).get("foreign_keys") or []
    if fks:
        val = "실측 조인 키: " + ", ".join(f"{f['reference']['key']}({'+'.join(f['fields'])})" for f in fks)
    else:
        val = "실측 컬럼에서 전역 조인 키를 찾지 못함 — 이름·코드 매핑 또는 같은 기관 코드로만 연결 가능"
    out.append(_c(dsid, 3, "key", val, [_ev_measured(f"probe/stats/{dsid}.json", observed, f"컬럼 {len((rec.get('schema') or {}).get('fields') or [])}개 값 패턴 판정")],
                  valid_until=until))

    # 04 coverage — 전체 규모·범위
    tot, rows = ver.get("total_count"), ver.get("rows")
    cov = rec.get("coverage") or {}
    parts = []
    if tot:
        parts.append(f"API 전체 건수 {tot:,}")
    if rows is not None:
        parts.append(f"검증 수신 {rows:,}행")
    parts += [x for x in (f"범위 {cov['spatial']}" if cov.get("spatial") else None,
                          f"행정단위 {cov['admin_unit']}" if cov.get("admin_unit") else None,
                          f"기간 {cov['temporal']}" if cov.get("temporal") else None) if x]
    out.append(_c(dsid, 4, "coverage", " · ".join(parts) or "규모 미상",
                  [_ev_measured(run_src, observed, f"total {tot}, rows {rows}"),
                   {"type": "portal_meta", "source": "class:coverage,admin_unit"}], valid_until=until))

    # 05 legal_basis — 포털 보유근거 + 법제처 원문 조문 (원문을 확보한 법령만 law 근거)
    if rec.get("legal_basis_portal"):
        laws = rec.get("applicable_legislation") or []
        val = ("포털 보유근거: " + "; ".join(f"{x['law']}" + (f" 제{', '.join(x['articles'])}조" if x.get("articles") else "")
                                         for x in laws)) if laws else f"포털 보유근거(법령 아님): {rec['legal_basis_portal'][:120]}"
        ev = [{"type": "portal_meta", "source": "catalog:legal_basis", "detail": rec["legal_basis_portal"][:200]}]
        for x in laws:
            art = _law_articles(x.get("law_id"), x.get("articles") or ["1"])
            ev += [{"type": "law", "source": f"law:{x['law_id']}#{no}", "detail": f"{x['law']} 제{no}조" + (f"({t})" if t else "")}
                   for no, t in art]
        out.append(_c(dsid, 5, "legal_basis", val, ev))

    # 20 legal_basis — 부문이 속한 법 체계 층 (sector_tree.yaml, 구름 결정) — 데이터 개별 근거가 아니라 부문 수준
    dom = _domain(rec.get("domain"))
    if dom:
        ev = [{"type": "admin_review", "source": f"knowledge/sectors/sector_tree.yaml#{dom['id']}", "by": dom.get("decided_by") or "구름",
               "at": str(dom.get("decided_at")) if dom.get("decided_at") else None}]
        for lid, name in _domain_laws(dom)[:6]:
            ev += [{"type": "law", "source": f"law:{lid}#{no}", "detail": f"{name} 제{no}조" + (f"({t})" if t else "")}
                   for no, t in _law_articles(lid, ["1"])]
        out.append(_c(dsid, 20, "legal_basis", f"법 체계 층 '{dom['name']}': {dom.get('law', '')}",
                      [{k: v for k, v in e.items() if v} for e in ev], scope="sector"))

    # 06~09 admin_note — 사람이 내린 결정 (검토 기록·세부 부문 정의·선정 이유·외부 라운드 메모)
    slot = 6
    sector = target["sector"]
    sub = _subsector_defs().get((sector, target["subsector"]))
    if sub and sub.get("value_source"):
        out.append(_c(dsid, slot, "admin_note", f"세부 부문 '{sub['name']}'의 가치: {str(sub['value_source']).strip()}",
                      [{"type": "admin_review", "source": f"{SUBS_REL}#{target['subsector']}", "by": sub.get("_by") or "구름",
                        "at": sub.get("_at")}], "preferred"))
        slot += 1
    for s, b in review_for(sector):
        if slot > 8:
            break
        by = s["by"] or "구름"
        out.append(_c(dsid, slot, "admin_note", f"[{s['heading']} · {b['label']}] {b['text']}",
                      [{"type": "admin_review", "source": f"{REVIEW_REL}#L{b['line']}", "by": by, "at": s["at"]}]))
        slot += 1
    if target.get("note") and slot <= 9:
        out.append(_c(dsid, slot, "admin_note", target["note"],
                      [_ev_measured("knowledge/targets.json", observed, "외부 라운드·검증 메모")]))

    # 10~ pitfall — 실측에서 드러난 함정
    slot = 10
    need = sorted({p for o in run.get("ops") or [] for p in (o.get("needs_params") or [])})
    if need:
        out.append(_c(dsid, slot, "pitfall", f"필수 파라미터 {', '.join(need)}는 다른 데이터의 코드 — 먼저 받아서 넘겨야 한다 (lookup Edge 후보)",
                      [_ev_measured(run_src, observed, "needs_params")], valid_until=until))
        slot += 1
    lag = ver.get("lag_days")
    if isinstance(lag, int) and lag < 0:
        out.append(_c(dsid, slot, "pitfall", f"날짜 컬럼에 미래 값({ver.get('latest')}) — 최신성은 적재일 컬럼으로 판단해야 한다",
                      [_ev_measured(f"probe/synthesis#{dsid}", observed, f"lag {lag}")], valid_until=until))
        slot += 1
    fail = [o.get("op") for o in run.get("ops") or [] if o.get("ok") is False]
    if fail and svcs:
        out.append(_c(dsid, slot, "pitfall", f"오퍼레이션 {len(fail)}개는 최소 파라미터로 응답이 없었다: {', '.join(map(str, fail[:4]))}",
                      [_ev_measured(run_src, observed, "ok=false")], valid_until=until))
        slot += 1
    if tot and rows is not None and tot > rows * 5:
        out.append(_c(dsid, slot, "pitfall", f"전수 {tot:,}건 중 검증은 {rows:,}행만 받음 — 전량 수집은 페이지 반복 {(-(-tot // 1000)):,}회 이상",
                      [_ev_measured(run_src, observed, f"total {tot} rows {rows}")], valid_until=until))
    return out
