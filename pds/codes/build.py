"""코드표(CodeList) 생성 — knowledge/codes/{id}.yaml (+ .parquet). 적용 메모 6 (구름 2026-09-30 제안).

"코드와 이름이 있는 데이터는 코드표를 설명에 담아야 AI가 필터를 정확히 넣고 결과를 풀 수 있다."
원천 4갈래 (completeness):
  complete     공식 원천 전체 — 법정동코드 파일(15123287), 지목(공간정보관리법 제67조 + 관측으로 번호 확인)
  master_scan  전수 원장을 훑어 실제로 쓰이는 값 전부 — 심평원 요양종별·시도·시군구, NMC 기관구분, 사회복지시설 종류, TAGO 도시
  observed     표본에서 본 값만 — 토지특성(용도지역·지형·도로접면·이용상황), 검증 데이터의 코드+이름 쌍
개체 식별자(수요기관코드·단지코드처럼 값이 수천 개)는 코드표가 아니라 조인 키라 뺀다.
"""
from __future__ import annotations

import datetime as dt
import glob
import hashlib
import re
from collections import defaultdict

import pandas as pd

from pds import config
from pds.schema import CodeList
from pds.schema import store

CODEDIR = config.KNOWLEDGE / "codes"
P = config.ROOT / "probe" / "data"
M = config.DATA / "master"
TODAY = dt.date.today().isoformat()
INLINE_MAX = 3000


def _latest(dsid: str, pattern: str = "*.parquet") -> pd.DataFrame:
    return pd.read_parquet(sorted(glob.glob(str(P / dsid / pattern)))[-1])


def _pairs(df: pd.DataFrame, code: str, name: str) -> pd.DataFrame:
    x = df[[code, name]].dropna().astype(str)
    x = x[(x[code].str.strip() != "") & (x[name].str.strip() != "") & (x[code] != "nan")]
    x = x.assign(code=x[code].str.strip(), name=x[name].str.strip())
    return x.groupby(["code", "name"]).size().reset_index(name="count").sort_values("code")


def _write(rec: dict, table: pd.DataFrame | None = None) -> dict:
    CODEDIR.mkdir(parents=True, exist_ok=True)
    if table is not None and len(table) > INLINE_MAX:
        table.to_parquet(CODEDIR / f"{rec['id']}.parquet", index=False)
        rec["file"] = f"codes/{rec['id']}.parquet"
        rec["rows"] = len(table)
    elif table is not None:
        rec["values"] = [{k: (int(v) if k == "count" and pd.notna(v) else v) for k, v in r.items() if pd.notna(v)}
                         for r in table[[c for c in ("code", "name", "count", "valid", "note") if c in table]].to_dict("records")]
        rec["rows"] = len(rec["values"])
    CodeList.model_validate(rec)
    store.dump(rec, CODEDIR / f"{rec['id']}.yaml", header=f"코드표 {rec['id']} — pds/codes/build.py 생성 ({TODAY})")
    return rec


# ─────────────────────────── complete
def bjd() -> dict:
    d = _latest("15123287")
    t = pd.DataFrame({"code": d["법정동코드"].astype(str).str.zfill(10), "name": d["법정동명"].astype(str),
                      "valid": d["폐지여부"].astype(str).str.strip().ne("폐지")})
    return _write({"id": "bjd_cd", "name": "법정동코드 (시도·시군구·읍면동·리)", "key": "bjd_cd", "completeness": "complete",
                   "evidence": [{"type": "measured", "source": "probe/data/15123287/ (국토교통부_법정동코드 파일)", "observed_at": TODAY,
                                 "detail": f"{len(t):,}행, 폐지 {int((~t.valid).sum()):,}"}],
                   "aliases": ["법정동코드", "ldCode", "bjdCode", "bjd_cd", "legaldongCode", "emd_cd", "LAWD_CD(앞 5자리)", "sggCd+umdCd"],
                   "notes": "앞 2자리 시도 · 5자리 시군구(=sgg_cd, R-02) · 8자리 읍면동 · 10자리 리. 폐지 코드도 남긴다(과거 데이터 해석용)"}, t)


JIMOK_ORDER = ["전", "답", "과수원", "목장용지", "임야", "광천지", "염전", "대", "공장용지", "학교용지", "주차장", "주유소용지", "창고용지", "도로",
               "철도용지", "제방", "하천", "구거", "유지", "양어장", "수도용지", "공원", "체육용지", "유원지", "종교용지", "사적지", "묘지", "잡종지"]


def jimok(landchar: pd.DataFrame | None) -> dict:
    """지목 28종 — 공간정보관리법 제67조 ①의 열거 순서 = 지적 전산 코드 01~28. 관측값으로 번호를 대조한다."""
    law = next((d for d, _ in store.iter_raw("law") if d["name"] == "공간정보의 구축 및 관리 등에 관한 법률"), None)
    art = next((a for a in (law or {}).get("articles", []) if a["no"] == "67"), None)
    in_law = [j for j in JIMOK_ORDER if art and j in art["text"]]
    t = pd.DataFrame({"code": [f"{i:02d}" for i in range(1, 29)], "name": JIMOK_ORDER})
    ev = [{"type": "law", "source": f"law:{law['law_id']}#67", "detail": f"제67조 지목 {len(in_law)}/28종 확인"}] if law else []
    note = ""
    if landchar is not None and "lndcgrCode" in landchar:
        obs = _pairs(landchar, "lndcgrCode", "lndcgrCodeNm")
        bad = obs.merge(t, on="code", suffixes=("_obs", "")).query("name_obs != name")
        t = t.merge(obs[["code", "count"]], on="code", how="left")
        ev.append({"type": "measured", "source": "data/master/vworld_landchar/sample.parquet", "observed_at": TODAY,
                   "detail": f"관측 {len(obs)}종, 번호·이름 불일치 {len(bad)}"})
        note = f"관측 {len(obs)}종 번호 일치" if bad.empty else f"불일치: {bad[['code', 'name_obs', 'name']].values.tolist()}"
    return _write({"id": "land_category", "name": "지목 (28종)", "completeness": "complete", "evidence": ev,
                   "aliases": ["lndcgrCode", "jimok", "지목코드", "지목"], "notes": f"법 제67조 ①의 열거 순서가 코드 01~28. {note}"}, t)


# ─────────────────────────── master_scan
def master_scans() -> list[dict]:
    out = []
    specs = [
        ("hira_cl_cd", "요양종별 (심평원 clCd)", "15001698", "hosp_basis", "clCd", "clCdNm", ["clCd"]),
        ("hira_sido_cd", "심평원 시도코드 (행안부 코드와 다름)", "15001698", "hosp_basis", "sidoCd", "sidoCdNm", ["sidoCd"]),
        ("hira_sggu_cd", "심평원 시군구코드 (행안부 코드와 다름)", "15001698", "hosp_basis", "sgguCd", "sgguCdNm", ["sgguCd"]),
        ("nmc_duty_div", "응급의료 기관구분 (NMC dutyDiv)", "15000736", "hsptl_mdcnc", "dutyDiv", "dutyDivNam", ["dutyDiv"]),
        ("nmc_duty_emcls", "응급의료기관 분류 (NMC dutyEmcls)", "15000736", "hsptl_mdcnc", "dutyEmcls", "dutyEmclsName", ["dutyEmcls"]),
        ("welfare_fclt_kind", "사회복지시설 종류 (사회보장정보원)", "15001848", "fclt_list", "fcltKindCd", "fcltKindNm", ["fcltKindCd"]),
        ("tago_city_cd", "TAGO 도시코드 (옛 행정구역 체계)", "15098534", "sttn_no_list", "_q_cityCode", None, ["cityCode"]),
    ]
    for cid, name, dsid, f, code, nm, aliases in specs:
        path = M / dsid / f"{f}.parquet"
        if not path.exists():
            continue
        d = pd.read_parquet(path)
        if nm is None or nm not in d:
            continue
        t = _pairs(d, code, nm)
        if t.code.duplicated().any():  # 같은 코드에 이름 여럿 — 가장 흔한 이름
            t = t.sort_values("count", ascending=False).drop_duplicates("code").sort_values("code")
        out.append(_write({"id": cid, "name": name, "completeness": "master_scan",
                           "evidence": [{"type": "measured", "source": f"data/master/{dsid}/{f}.parquet", "observed_at": TODAY,
                                         "detail": f"전수 {len(d):,}행 스캔"}],
                           "aliases": aliases, "used_by": [{"dataset": dsid, "field": code, "name_field": nm}]}, t))
    return out


# ─────────────────────────── observed — 토지특성 표본
LANDCHAR = [("zoning_area", "용도지역 (토지특성 prposArea1)", "prposArea1", "prposArea1Nm"),
            ("zoning_district", "용도지구 (토지특성 prposArea2)", "prposArea2", "prposArea2Nm"),
            ("land_use_status", "토지이용상황", "ladUseSittn", "ladUseSittnNm"),
            ("terrain_height", "지형높이", "tpgrphHgCode", "tpgrphHgCodeNm"),
            ("terrain_shape", "지형형상", "tpgrphFrmCode", "tpgrphFrmCodeNm"),
            ("road_side", "도로접면", "roadSideCode", "roadSideCodeNm"),
            ("register_div", "대장구분 (토지·임야)", "regstrSeCode", "regstrSeCodeNm")]


def landchar_codes(lc: pd.DataFrame) -> list[dict]:
    out = []
    zoning_law = _zoning_names()
    for cid, name, code, nm in LANDCHAR:
        if code not in lc:
            continue
        t = _pairs(lc, code, nm)
        note = f"전국 {lc['_site'].nunique()}곳 필지 {len(lc):,}개 표본에서 본 값"
        if cid == "zoning_area" and zoning_law:
            miss = [z for z in zoning_law if z not in set(t.name)]
            note += f" · 국토계획법 제36조 용도지역 {len(zoning_law)}종 중 미관측 {len(miss)}: {', '.join(miss[:12])}"
        out.append(_write({"id": cid, "name": name, "completeness": "observed",
                           "evidence": [{"type": "measured", "source": "data/master/vworld_landchar/sample.parquet", "observed_at": TODAY,
                                         "detail": note}],
                           "aliases": [code], "used_by": [{"dataset": "15124014", "field": code, "name_field": nm}],
                           "notes": note + ". 브이월드 토지특성정보(getLandCharacteristics)"}, t))
    return out


def _zoning_names() -> list[str]:
    law = next((d for d, _ in store.iter_raw("law") if d["name"] == "국토의 계획 및 이용에 관한 법률"), None)
    art = next((a for a in (law or {}).get("articles", []) if a["no"] == "36"), None)
    if not art:
        return []
    names = re.findall(r"(제\d종(?:전용|일반)?주거지역|준주거지역|(?:중심|일반|근린|유통)상업지역|(?:전용|일반|준)공업지역|(?:보전|생산|자연)녹지지역|"
                       r"(?:보전|생산|계획)관리지역|농림지역|자연환경보전지역)", art["text"])
    return list(dict.fromkeys(names))


# ─────────────────────────── observed — 검증 데이터의 코드+이름 쌍
def _stem(c: str, suf: str) -> str | None:
    m = re.match(rf"^(.*?)({suf})$", c)
    return m.group(1) if m else None


CODE_SUF = r"Cd|Code|CD|_cd|_CD|_code|코드|Cde"
NAME_SUF = r"Nm|Name|NM|_nm|_NM|_name|명|Nam"


def observed_pairs() -> list[dict]:
    groups: dict[tuple, dict] = defaultdict(lambda: {"frames": [], "uses": []})
    for d, _ in store.iter_raw("dataset"):
        dsid, agency = d["id"], (d.get("agency") or {}).get("id") or "x"
        for f in glob.glob(str(P / dsid / "*.parquet")):
            try:
                df = pd.read_parquet(f)
            except Exception:  # noqa: BLE001
                continue
            cols = list(df.columns)
            names = {}
            for c in cols:
                s = _stem(str(c), NAME_SUF)
                if s is not None:
                    names[s] = c
            for c in cols:
                s = _stem(str(c), CODE_SUF)
                nm = names.get(s) if s is not None else None
                nm = nm or next((n for n in cols if n in (f"{c}Nm", f"{c}Name", f"{c}명")), None)
                if not nm:
                    continue
                t = _pairs(df, c, nm)
                k = t.code.nunique()
                if k < 2 or k > 300 or len(t) == 0 or t.groupby("code").name.nunique().max() > 1:
                    continue
                if k / max(1, int(t["count"].sum())) > 0.5 and k > 30:  # 거의 행마다 다른 값 = 식별자
                    continue
                gid = (agency, str(c))
                groups[gid]["frames"].append(t)
                groups[gid]["uses"].append({"dataset": dsid, "field": str(c), "name_field": str(nm)})
    out = []
    for (agency, col), g in groups.items():
        t = pd.concat(g["frames"]).groupby(["code", "name"], as_index=False)["count"].sum()
        if t.code.duplicated().any():
            t = t.sort_values("count", ascending=False).drop_duplicates("code").sort_values("code")
        slug = col.lower() if re.fullmatch(r"[A-Za-z0-9_]+", col) else "k" + hashlib.sha1(col.encode()).hexdigest()[:6]
        uses = {(u["dataset"], u["field"]): u for u in g["uses"]}
        out.append(_write({"id": f"obs.{agency}.{slug}".lower(), "name": f"{col} ({agency})", "completeness": "observed",
                           "evidence": [{"type": "measured", "source": "probe/data/", "observed_at": TODAY,
                                         "detail": f"검증 표본 {len(uses)}개 데이터셋에서 본 값"}],
                           "aliases": [col], "used_by": list(uses.values())}, t))
    return out


def link_used_by() -> int:
    """공식·스캔 코드표(aliases)를 가진 컬럼이 있는 Dataset을 used_by에 추가 (observed는 이미 스스로 채움)."""
    n = 0
    for c, path in store.iter_raw("code"):
        if c["completeness"] == "observed" and c["id"].startswith("obs."):
            continue
        al = {a.split("(")[0].strip() for a in c.get("aliases", [])}
        uses = {(u["dataset"], u["field"]) for u in c.get("used_by", [])}
        for d, _ in store.iter_raw("dataset"):
            for f in (d.get("schema") or {}).get("fields") or []:
                if f["name"] in al and (d["id"], f["name"]) not in uses:
                    c.setdefault("used_by", []).append({"dataset": d["id"], "field": f["name"]})
                    uses.add((d["id"], f["name"]))
                    n += 1
        CodeList.model_validate(c)
        store.dump(c, path, header=f"코드표 {c['id']} — pds/codes/build.py 생성 ({TODAY})")
    return n


def build_all() -> dict:
    lc = pd.read_parquet(M / "vworld_landchar" / "sample.parquet") if (M / "vworld_landchar" / "sample.parquet").exists() else None
    res = {"bjd": bjd()["rows"], "jimok": jimok(lc)["rows"], "master_scan": len(master_scans())}
    if lc is not None:
        res["landchar"] = len(landchar_codes(lc))
    res["observed_pairs"] = len(observed_pairs())
    res["linked"] = link_used_by()
    return res




# ─────────────────────────── 계획(_plan.yaml) 기준 — 목록을 먼저 정하고 원천을 확보한 것 (구름 2026-09-30)
def plan() -> list[dict]:
    import yaml as _y
    return _y.safe_load((CODEDIR / "_plan.yaml").read_text(encoding="utf-8")) or []


def _plan_entry(cid: str) -> dict:
    return next(p for p in plan() if p["id"] == cid)


def _file_ev(dsid: str, n: int) -> list[dict]:
    return [{"type": "measured", "source": f"probe/data/{dsid}/ (포털 파일 {dsid})", "observed_at": TODAY, "detail": f"{n:,}행"}]


def country_iso() -> dict:
    d = _latest("15091117")
    t = pd.DataFrame({"code": d["국제표준화기구_2자리"].astype(str).str.strip(), "name": d["한글명"].astype(str).str.strip(),
                      "note": d["국제표준화기구_3자리"].astype(str) + " / " + d["국제표준화기구_숫자"].astype(str) + " / " + d["영문명"].astype(str)})
    t = t[t.code.str.fullmatch(r"[A-Z]{2}")].drop_duplicates("code")
    return _write({"id": "country_iso", "name": "국가코드 (ISO 3166 2자리, 외교부 국가표준코드)", "key": "country_cd", "completeness": "complete",
                   "evidence": _file_ev("15091117", len(d)), "aliases": [_plan_entry("country_iso")["fields"]],
                   "notes": "비고 = ISO 3자리 / 숫자 / 영문명. 외교부 행정표준 대륙코드도 원본 파일에 있음"}, t)


def port_locode() -> dict:
    d = _latest("15114126")
    t = pd.DataFrame({"code": d["항구코드"].astype(str).str.strip(),  # 이미 국가(2)+항구(3) 5자리
                      "name": d["항구명"].astype(str).str.strip() + " (" + d["국가명"].astype(str).str.strip() + ")",
                      "note": d["항구구분자"].astype(str)})
    t = t[t.code.str.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}")].drop_duplicates("code")
    return _write({"id": "port_locode", "name": "국가·항구코드 (UN/LOCODE 5자리, 해수부)", "key": "port_cd", "completeness": "complete",
                   "evidence": _file_ev("15114126", len(d)), "aliases": [_plan_entry("port_locode")["fields"]],
                   "notes": "코드 = 국가(2)+항구(3). 비고 = 항구구분자(항구 3자리)"}, t)


def hs_cd() -> dict:
    d = _latest("15049722")
    end = pd.to_datetime(d["적용종료일자"].astype(str).str[:8], format="%Y%m%d", errors="coerce")
    t = pd.DataFrame({"code": d["HS부호"].astype(str).str.replace(r"\D", "", regex=True), "name": d["한글품목명"].astype(str).str.strip(),
                      "valid": end.isna() | (end >= pd.Timestamp.today())})
    t = t.sort_values("valid", ascending=False).drop_duplicates("code").sort_values("code")
    return _write({"id": "hs_cd", "name": "HS부호 (관세청 HSK 10자리)", "key": "hs_cd", "completeness": "complete",
                   "evidence": _file_ev("15049722", len(d)), "aliases": [_plan_entry("hs_cd")["fields"]],
                   "notes": "10자리 HSK. 6자리(HS6)·4자리 필드는 앞자리 일치로 읽는다. 적용종료일이 지난 부호는 valid=false"}, t)


def ncs() -> dict:
    d = _latest("15083321")
    t = pd.DataFrame({"code": d["분류번호"].astype(str).str.strip(), "name": d["명칭"].astype(str).str.strip(),
                      "note": "수준 " + d["수준"].astype(str)})
    t = t.drop_duplicates("code")
    return _write({"id": "ncs", "name": "국가직무능력표준(NCS) 분류·능력단위", "key": "job_code", "completeness": "complete",
                   "evidence": _file_ev("15083321", len(d)), "aliases": [_plan_entry("ncs")["fields"]],
                   "notes": "분류번호 = 대(2)·중(2)·소(2)·세(2)… 필드가 단계별로 나뉘면(ncsLclasCd…) 앞에서부터 이어 붙여 읽는다"}, t)


SPEC_PAIR = re.compile(r"(?:^|[\s,(/;])([A-Za-z0-9]{1,6})\s*[:=]\s*([^,/;:=()]{1,30}?)(?=\s*(?:[,/;)]|\s[A-Za-z0-9]{1,6}\s*[:=]|$))")


def spec_enums() -> list[dict]:
    """명세서 응답 필드 설명에 적힌 코드 정의 ('Y:가능,N:불가', 'H:Html, T:Text') → 데이터 전용 코드표."""
    import json as _j
    out, seen = [], set()
    for d, _ in store.iter_raw("dataset"):
        f = config.ROOT / "probe" / "specs" / f"{d['id']}.json"
        if not f.exists():
            continue
        spec = _j.loads(f.read_text(encoding="utf-8"))
        for o in spec.get("operations") or []:
            for r in o.get("response_fields") or []:
                desc = r.get("desc") or ""
                pairs = [(a.strip(), b.strip()) for a, b in SPEC_PAIR.findall(desc) if b.strip()]
                if len(pairs) < 2 or len({a for a, _ in pairs}) != len(pairs):
                    continue
                field = str(r["name"]).split(".")[-1]
                cid = f"spec.{d['id']}.{field}".lower()
                if not re.fullmatch(r"[a-z0-9][a-z0-9_.\-]*", cid) or cid in seen:
                    continue
                seen.add(cid)
                t = pd.DataFrame(pairs, columns=["code", "name"])
                out.append(_write({"id": cid, "name": f"{field} — {d['title'][:30]}", "completeness": "complete",
                                   "evidence": [{"type": "portal_meta", "source": f"probe/specs/{d['id']}.json#{field}", "detail": desc[:200]}],
                                   "aliases": [field], "used_by": [{"dataset": d["id"], "field": field}],
                                   "notes": "공급 기관 명세서의 필드 설명에 정의된 값"}, t))
    return out



def currency_iso() -> dict:
    """통화코드 — 관세청 관세환율(15101230) 한 주치 응답의 통화부호·통화명 (수입 환율, 약 50여 통화)."""
    import json as _j
    import httpx
    from pds.probe.deep import _items_xml
    from pds.probe.deep import service_key
    key = service_key()
    day = (dt.date.today() - dt.timedelta(days=3)).strftime("%Y%m%d")
    r = httpx.get("https://apis.data.go.kr/1220000/retrieveTrifFxrtInfo/getRetrieveTrifFxrtInfo",
                  params={"serviceKey": key, "aplyBgnDt": day, "weekFxrtTpcd": "2"}, timeout=40)
    items = pd.DataFrame(_items_xml(r.text) or [])
    t = pd.DataFrame({"code": items["currSgn"].str.strip(), "name": items["mtryUtNm"].str.strip(), "note": "국가 " + items["cntySgn"].str.strip()})
    t = t.drop_duplicates("code").sort_values("code")
    return _write({"id": "currency_iso", "name": "통화코드 (ISO 4217, 관세청 관세환율 통화)", "completeness": "master_scan",
                   "evidence": [{"type": "measured", "source": f"https://apis.data.go.kr/1220000/retrieveTrifFxrtInfo (aplyBgnDt={day})",
                                 "observed_at": TODAY, "detail": f"{len(t)}개 통화"}],
                   "aliases": [_plan_entry("currency_iso")["fields"]],
                   "notes": "관세청이 주간 관세환율을 고시하는 통화 전부. KRW는 목록에 없다(기준 통화)"}, t)


def instt_cd() -> dict:
    """행정표준 기관코드 — 15077870 전수(부서 단위 포함 41만여 건). 폐지(stop_selt≠1?)도 남긴다."""
    d = pd.read_parquet(M / "15077870" / "stan_org_cd.parquet")
    t = pd.DataFrame({"code": d["org_cd"].astype(str).str.strip(), "name": d["full_nm"].astype(str).str.strip(),
                      "valid": d["cls_de"].astype(str).str.strip().isin(["", "nan", "None"]) | (d["cls_de"].astype(str) >= TODAY.replace("-", "")),
                      "note": d["typebig_nm"].astype(str) + "/" + d["typemid_nm"].astype(str) + " · 상위 " + d["high_cd"].astype(str)})
    t = t.drop_duplicates("code")
    return _write({"id": "instt_cd", "name": "행정표준 기관코드 (행정안전부)", "key": "instt_cd", "completeness": "complete",
                   "evidence": [{"type": "measured", "source": "data/master/15077870/stan_org_cd.parquet", "observed_at": TODAY,
                                 "detail": f"{len(d):,}행 (부서 단위 포함)"}],
                   "aliases": [_plan_entry("instt_cd")["fields"]],
                   "notes": "7자리. 인허가(LOCALDATA) 개방자치단체코드·포털 제공기관코드와 같은 체계. 비고 = 기관유형 · 상위기관"}, t)


def link_by_plan() -> int:
    """계획의 필드 정규식으로 used_by를 채운다 (대소문자 무시)."""
    n = 0
    rules = {p["id"]: re.compile(p["fields"], re.I) for p in plan() if p.get("fields") and p["fields"] != "*"}
    datasets = list(store.iter_raw("dataset"))
    for c, path in store.iter_raw("code"):
        rx = rules.get(c["id"])
        if not rx:
            continue
        uses = {(u["dataset"], u["field"]) for u in c.get("used_by", [])}
        for d, _ in datasets:
            for f in (d.get("schema") or {}).get("fields") or []:
                if rx.search(f["name"]) and (d["id"], f["name"]) not in uses:
                    c.setdefault("used_by", []).append({"dataset": d["id"], "field": f["name"]})
                    uses.add((d["id"], f["name"]))
                    n += 1
        CodeList.model_validate(c)
        store.dump(c, path, header=f"코드표 {c['id']} — pds/codes/build.py 생성 ({TODAY})")
    return n


def build_planned() -> dict:
    res = {}
    for fn in (country_iso, port_locode, hs_cd, ncs, currency_iso, instt_cd):
        try:
            res[fn.__name__] = fn()["rows"]
        except (IndexError, FileNotFoundError) as e:
            res[fn.__name__] = f"원천 없음: {e}"
    res["spec_enums"] = len(spec_enums())
    res["linked_by_plan"] = link_by_plan()
    return res


if __name__ == "__main__":
    print(build_all())
    print(build_planned())
