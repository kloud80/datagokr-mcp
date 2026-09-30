"""코드표 필요 목록 — 대상 데이터의 필드마다 "코드표가 있으면 훨씬 이해가 쉬운가"를 먼저 판정한다 (구름 2026-09-30).

순서: 필드 전수 판정(이 파일) → 사람이 목록 확인 → 원천 확보(pds/codes/build.py·fullpull).
판정 입력: Dataset yaml schema.fields(명세 설명·타입) + probe/stats(상위 값 10·유니크 수).

분류
  A 불투명 코드   값이 짧은 영숫자 코드(01·B10·UQA111)이고 같은 응답에 이름 컬럼이 없음 → 코드표 필수
  B 코드+이름     같은 응답에 이름 컬럼이 있음 → 응답으로 해독 가능, 필터에 넣을 전체 목록만 필요
  C 행정·조인 키  법정동·시군구·시도 등 (bjd_cd 코드표로 해결) 또는 개체 식별자(값이 수백 개 이상)
  D 여부(Y/N)     값이 Y/N·0/1 — 뜻(무엇의 여부)만 명시
  E 한글 범주     한글 범주값이 그대로 옴 — 값 목록(도메인)이면 충분
출력: knowledge/codes/_needs.yaml (필드별) · reports/code_needs.md (코드 체계별 묶음 + 확보 상태)
"""
from __future__ import annotations

import json
import re
from collections import defaultdict

import pandas as pd
import yaml

from pds import config
from pds.schema import store

CODE_NAME = re.compile(r"(Cd|Code|CD|_cd|_CD|_code|코드|Cde|SeCd|Se|Div|Dv|Kind|Knd|Ty|Type|Clsf|Cl|Gbn|Gb|Grd|Grade|Stts|Sttus|Status|Lvl|Level)$")
CODE_TITLE = re.compile(r"(코드|구분|종류|유형|분류|등급|상태|종별|단계|방법|형태)")
NAME_SUF = ("Nm", "Name", "NM", "_nm", "_NM", "_name", "명", "Nam", "CdNm", "CodeNm")
ADMIN = re.compile(r"(sido|sigungu|sggu?|signgu|ctpv|ctprvn|ldong|legaldong|bjd|emd|umd|adong|lawd|ldCode|시도|시군구|법정동|행정동|읍면동)", re.I)
YN_VALUES = {"Y", "N", "y", "n", "0", "1", "예", "아니오", "true", "false", "True", "False"}
OPAQUE = re.compile(r"^[A-Za-z0-9_\-.]{1,12}$")
HANGUL = re.compile(r"[가-힣]")
NOT_CODE_NAME = re.compile(r"(tel|fax|phone|전화|팩스|연락처|zip|우편|bonbun|bubun|본번|부번|지번|flr|floor|층|ymd|date|dt$|Dt$|일자|일시|연월|YM$|_ym$|년월|"
                           r"time|시각|lat|lon|lng|좌표|위도|경도|url|mail|homepage|hmpg|addr|주소|nm$|Nm$|name$|명$)", re.I)
NOT_CODE_VALUE = re.compile(r"^(\d{2,4}-\d{3,4}-\d{4}|\d{4}[-./]\d{1,2}([-./]\d{1,2})?\.?|1\d{3}-\d{4})$")
ID_NAME = re.compile(r"(Id$|ID$|_id$|No$|_no$|Sn$|Seq$|번호$|아이디|고유)", re.I)


def uniq_le(u, n) -> bool:
    return u is None or u <= n


def _stats(dsid: str) -> dict:
    f = config.ROOT / "probe" / "stats" / f"{dsid}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def _covered() -> dict[tuple[str, str], str]:
    out = {}
    for c, _ in store.iter_raw("code"):
        for u in c.get("used_by") or []:
            out[(u["dataset"], u["field"])] = c["id"]
    return out


def classify_field(name: str, title: str | None, top: list[str], unique: int | None, typ: str | None,
                   cols: set[str], semantic: str | None) -> tuple[str | None, str]:
    vals = [str(v) for v in top if str(v).strip() not in ("", "nan", "None", "-")]
    if not vals:
        return None, "값 없음"
    if NOT_CODE_NAME.search(name) or NOT_CODE_NAME.search(title or ""):
        return None, "연락처·날짜·번지·층 등"
    if sum(bool(NOT_CODE_VALUE.search(v)) for v in vals) / len(vals) >= 0.5:
        return None, "전화·날짜 형식 값"
    if set(vals) - YN_VALUES and set(vals) <= YN_VALUES | {"N1", "N2", "Y1", "Y2", "U", "X"} and uniq_le(unique, 5):
        return "D", "Y/N + 특수값 " + ",".join(sorted(set(vals) - YN_VALUES)) + " (뜻 확인 필요)"
    uniq = unique or len(vals)
    has_name = any(f"{name}{s}" in cols for s in NAME_SUF) or any(
        re.sub(r"(Cd|Code|CD|_cd|_CD|코드)$", "", name) + s in cols for s in NAME_SUF)
    if set(vals) <= YN_VALUES and uniq <= 3:
        return "D", "Y/N"
    if semantic in ("bjd_cd", "sgg_cd", "admin_area_code") or ADMIN.search(name) and re.search(r"(Cd|Code|CD|_cd|코드)", name):
        return "C", "행정구역 코드"
    if uniq > 300 or (ID_NAME.search(name) and not re.search(r"(Cd|Code|CD|코드)$", name)):
        return ("C", "개체 식별자") if all(OPAQUE.match(v) or re.fullmatch(r"[\w\-]+", v) for v in vals) else (None, "자유 텍스트")
    if all(re.fullmatch(r"[A-Za-z][a-z]+(?: [A-Za-z][a-z]+)*", v) for v in vals):
        return "E", "영문 범주"
    opaque = sum(bool(OPAQUE.match(v)) and not re.fullmatch(r"\d{8,}|\d{4}-\d{2}-\d{2}.*|\d+\.\d+", v) for v in vals) / len(vals)
    hangul = sum(bool(HANGUL.search(v)) for v in vals) / len(vals)
    named = bool(CODE_NAME.search(name) or CODE_TITLE.search(title or ""))
    if typ in ("number",) and not named:
        return None, "수치"
    if opaque >= 0.8 and (named or uniq <= 50):
        return ("B", "코드+이름 동봉") if has_name else ("A", "불투명 코드")
    if hangul >= 0.8 and uniq <= 60 and (named or uniq <= 20):
        return "E", "한글 범주"
    return None, "해당 없음"


def build() -> dict:
    covered = _covered()
    rows = []
    for d, _ in store.iter_raw("dataset"):
        if d.get("tier") != "verified":
            continue
        st = _stats(d["id"])
        fields = (d.get("schema") or {}).get("fields") or []
        by_op = defaultdict(set)
        for f in fields:
            by_op[f.get("op")].add(f["name"])
        for f in fields:
            op_stats = st.get(f.get("op")) if f.get("op") else next((v for v in st.values() if isinstance(v, dict) and f["name"] in v), {})
            s = (op_stats or {}).get(f["name"]) or {}
            top = list((s.get("top") or {}).keys())[:10] or f.get("sample_values") or []
            cls, why = classify_field(f["name"], f.get("title"), top, s.get("unique") or (f.get("stats") or {}).get("unique"),
                                      s.get("type"), by_op[f.get("op")], f.get("semantic_type"))
            if not cls:
                continue
            rows.append({"dataset": d["id"], "title": d["title"], "sector": d["sector"], "agency": d["agency"]["name"],
                         "field": f["name"], "meaning": f.get("title"), "class": cls, "why": why, "unique": s.get("unique"),
                         "samples": [str(v)[:20] for v in top[:6]], "code_list": covered.get((d["id"], f["name"]))})
    df = pd.DataFrame(rows)
    # 코드 체계 묶음: 필드 이름(대소문자·구분자 무시) 기준
    df["system"] = df["field"].str.lower().str.replace(r"[_\s]", "", regex=True)
    out = config.KNOWLEDGE / "codes" / "_needs.yaml"
    out.parent.mkdir(exist_ok=True)
    out.write_text(yaml.safe_dump(df.drop(columns=["system"]).to_dict("records"), allow_unicode=True, sort_keys=False, width=200),
                   encoding="utf-8")
    _report(df)
    return {"fields": len(df), **df["class"].value_counts().to_dict(), "covered": int(df["code_list"].notna().sum())}


def _report(df: pd.DataFrame) -> None:
    L = ["# 코드표 필요 목록 — 대상 데이터 필드 기준", "",
         f"검증 데이터 {df.dataset.nunique()}건의 필드 중 코드성 필드 {len(df):,}개. 생성: `python -m pds.codes.needs` · 원본 목록 `knowledge/codes/_needs.yaml`", "",
         "| 분류 | 뜻 | 필드 | 데이터셋 | 코드표 있음 |", "|---|---|---:|---:|---:|"]
    MEAN = {"A": "불투명 코드 — 코드표 필수", "B": "코드+이름 동봉 — 필터용 전체 목록", "C": "행정구역·식별자", "D": "Y/N 여부", "E": "한글 범주"}
    for c in "ABCDE":
        x = df[df["class"] == c]
        L.append(f"| {c} | {MEAN[c]} | {len(x):,} | {x.dataset.nunique()} | {int(x.code_list.notna().sum())} |")
    # 계획(_plan.yaml) 대비 확보 현황
    plan_p = config.KNOWLEDGE / "codes" / "_plan.yaml"
    if plan_p.exists():
        codes = {c["id"]: c for c, _ in store.iter_raw("code")}
        L += ["", "## 확보 계획 대비 현황 (`knowledge/codes/_plan.yaml`)", "",
              "| 우선 | 코드 체계 | 원천 | 상태 | 코드 수 | 연결 필드 |", "|---:|---|---|---|---:|---:|"]
        for pe in yaml.safe_load(plan_p.read_text(encoding="utf-8")) or []:
            c = codes.get(pe["id"])
            src = pe["source"].get("dataset") or pe["source"].get("external") or pe["source"].get("law") or pe["source"].get("spec")
            status = "확보" if c else ("포털 밖" if pe["status"] == "portal_absent" else "미확보")
            if pe["id"] == "spec_enums":
                n = [x for x in codes if x.startswith("spec.")]
                L.append(f"| {pe['priority']} | {pe['name']} | {src} | 확보 {len(n)}개 | — | {len(n)} |")
                continue
            L.append(f"| {pe['priority']} | {pe['name']} | {src} | {status} | {c['rows'] if c else ''} | {len(c.get('used_by', [])) if c else 0} |")
        a = df[df["class"] == "A"]
        L += ["", f"분류 A {len(a)}개 필드 중 코드표 연결 {int(a.code_list.notna().sum())}개 · 미연결 {int(a.code_list.isna().sum())}개"]
    for c in ("A", "B"):
        L += ["", f"## {c}. {MEAN[c]} — 코드 체계별 (여러 데이터가 같이 쓰는 것부터)", "",
              "| 필드 | 뜻(명세) | 데이터셋 수 | 유니크 | 표본 값 | 쓰는 데이터 (예) | 코드표 |", "|---|---|---:|---:|---|---|---|"]
        x = df[df["class"] == c]
        g = x.groupby("system")
        order = g["dataset"].nunique().sort_values(ascending=False).index
        for sname in order:
            y = g.get_group(sname)
            meaning = next((m for m in y["meaning"] if isinstance(m, str) and m), "")
            samples = ", ".join(dict.fromkeys(v for s in y["samples"] for v in s))[:60]
            users = "; ".join(f"{t[:22]}({i})" for i, t in y[["dataset", "title"]].drop_duplicates().head(3).itertuples(index=False))
            cl = ", ".join(sorted({v for v in y["code_list"] if isinstance(v, str)})) or "—"
            L.append(f"| `{y['field'].iloc[0]}` | {meaning[:24]} | {y.dataset.nunique()} | {int(y['unique'].max() or 0)} | {samples} | {users} | {cl} |")
    (config.REPORTS / "code_needs.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    print(build())
