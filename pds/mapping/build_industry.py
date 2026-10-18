"""업종 이름 → KSIC 11차 매핑 — 통계 분해 연구안(knowledge/expansion/stats_decomposition.md) 1단계 산출물.

미시 데이터(인허가·공장등록·상가·점포 현황)의 '업종명·업태구분명' 값을 KSIC 11차 세세분류(5자리)에 붙인다.
그래야 서비스업조사·ECOS 업종별 대출 같은 통계의 산업 축과 이을 수 있다 (benchmark Edge).

만드는 것
  ksic9__ksic10 · ksic10__ksic    국가데이터처 연계표(15159305) 세세분류 행. 1:N이면 confidence = 1/N
  sbiz_inds__ksic                  상가(상권)정보(15083033) 실측 — 상권업종소분류 코드마다 가장 많이 붙은 표준산업분류(10차→11차)
  industry_nm__ksic                업종 이름 → KSIC. 단계(앞에서 정해지면 뒤로 안 넘김):
    code_in_name   이름 끝 '(25922)'처럼 적어 둔 5자리 코드 — 11차에 있으면 그대로, 10차에만 있으면 연계    1.0 (1:N이면 1/N)
    exact_ksic11   정규화 이름 == KSIC 11차 항목명, 모든 단계 (공장등록 계열은 KSIC 이름을 그대로 쓴다)   1.0
    exact_ksic10   정규화 이름 == KSIC 10차 항목명 → 연계표로 11차                                  1.0 (1:N이면 1/N)
    sbiz_measured  정규화 이름 == 상권업종소분류명 → 상가정보 실측 최빈 KSIC                          그 업종에서 최빈 KSIC 비율
    curated        knowledge/expansion/industry_dict.yaml entries — 인허가 업종 어휘를 Opus가 판정 (구름 검토 전)  사전의 confidence
                   confidence < HOLD(0.65)인 항목은 붙이지 않고 보류 — industry_review.csv 로 검토를 기다린다
    curated_pattern  같은 사전의 patterns (어업 종류처럼 변형이 많은 이름 규칙)                       사전의 confidence
  값이 '일반미용업, 네일미용업'처럼 여러 업종을 쉼표로 묶었으면 낱말마다 붙이고 confidence를 나눈다.
어휘 원천: 검증 데이터(tier=verified) 중 업종 이름 필드(FIELD_RX)가 있는 것의 실측 표본(probe/data) 값 전부.
"""
from __future__ import annotations

import glob
import re
from collections import Counter, defaultdict

import pandas as pd
import yaml
from rapidfuzz import fuzz

from pds import config
from pds.mapping.common import write
from pds.schema import store

DICT = config.KNOWLEDGE / "expansion" / "industry_dict.yaml"
P = config.ROOT / "probe" / "data"
FIELD_RX = re.compile(r"^(업종명|업종|업태명|업태구분명|업종구분|업종분류|UPTAENM|SNTUPTAENM|CULPHYEDCOBNM|BFGAMEOCPTECTCOBNM|uptaeNm|indutyNm)$", re.I)
HOLD = 0.65  # 사전 판정이 이보다 낮으면 매핑에 안 쓰고 검토 목록으로 (구름 결정 2026-10-15)
JUNK = {"", "nan", "none", "null", "-", "기타", "해당없음", "미분류"}


def nz(s) -> str:
    """'김치류 제조업 외 1 종' · '채소; 화훼 및 과실작물 시설 재배업' · '화장ㆍ분장 미용업' → 비교용 키."""
    s = re.sub(r"\s*외\s*\d+\s*종$", "", str(s or "").strip())
    s = re.sub(r"\(\s*\d+\s*~\s*\d+\s*\)$", "", s)  # 대분류 '(01~03)'
    return re.sub(r"[\s,;ㆍ·.\-_/]", "", s)


def _codes(cid: str) -> pd.DataFrame:
    d = yaml.safe_load((config.KNOWLEDGE / "codes" / f"{cid}.yaml").read_text(encoding="utf-8"))
    return pd.DataFrame(d["values"]) if d.get("values") else pd.read_parquet(config.KNOWLEDGE / d["file"])


def _latest(dsid: str) -> pd.DataFrame:
    return pd.read_parquet(sorted(glob.glob(str(P / dsid / "file_*.parquet")))[-1])


# ─────────────────────────── 차수 연계
def link(new: str) -> pd.DataFrame:
    d = _latest("15159305")
    d = d[(d["분류종류"] == "KSIC") & (d["분류차순정보"].astype(str) == new) & (d["분류범위"].astype(str) == "5")]
    t = pd.DataFrame({"left_value": d["구분류코드"].astype(str).str.strip(), "right_value": d["신분류코드"].astype(str).str.strip()})
    n = t.groupby("left_value")["right_value"].transform("size")
    t["confidence"] = (1 / n).round(3)
    t["method"] = n.map(lambda k: "1:1" if k == 1 else "1:N")
    t["left_kind"] = d["구분류항목명"].astype(str).str.strip().values
    return t.reset_index(drop=True)


def build_links() -> list[dict]:
    out = []
    for old, new in (("9", "10"), ("10", "11")):
        t = link(new)
        k = t.groupby("left_value").size()
        right = "ksic" if new == "11" else f"ksic{new}"  # 11차(현행)는 코드표 id 그대로 ksic
        out.append(write(f"ksic{old}__{right}", {"key": f"ksic{old}", "system": f"KSIC {old}차 세세분류"},
                         {"key": right, "system": f"KSIC {new}차 세세분류"},
                         "exact", t, "keep_left", ["15159305"],
                         f"국가데이터처 산업분류 연계표 — {old}차 {len(k):,}개 중 1:1 {int((k == 1).sum()):,} · 1:N {int((k > 1).sum()):,} "
                         f"(나뉜 코드는 confidence 1/N, 통계 시계열을 이을 때 비중을 따로 정해야 한다)"))
    return out


# ─────────────────────────── 상권업종 → KSIC (실측)
def sbiz() -> pd.DataFrame:
    """상가정보 행마다 붙은 (상권업종소분류, 표준산업분류 10차) 쌍 → 소분류별 최빈 KSIC를 11차로."""
    a = _latest("15083033")
    l10 = link("11").set_index("left_value")["right_value"]
    g = a.groupby(["상권업종소분류코드", "상권업종소분류명", "표준산업분류코드"]).size().reset_index(name="n")
    g["k10"] = g["표준산업분류코드"].astype(str).str[1:]
    tot = g.groupby("상권업종소분류코드")["n"].transform("sum")
    g = g.assign(share=g["n"] / tot).sort_values(["상권업종소분류코드", "n"], ascending=[True, False]).drop_duplicates("상권업종소분류코드")
    rows = []
    for r in g.itertuples():
        tgt = l10.get(r.k10)
        tgt = [tgt] if isinstance(tgt, str) else (list(tgt) if tgt is not None else [None])
        for t in tgt:
            rows.append({"left_value": r.상권업종소분류코드, "right_value": t, "confidence": round(r.share / len(tgt), 3),
                         "method": "measured_mode", "left_kind": r.상권업종소분류명})
    return pd.DataFrame(rows)


# ─────────────────────────── 업종 이름 어휘
def vocab() -> pd.DataFrame:
    """검증 데이터의 업종 이름 필드 실측값 전부 — 값 · 행 수 · 데이터 수 · 데이터 예시."""
    cnt, src, n_ds = Counter(), defaultdict(set), 0
    for d, _ in store.iter_raw("dataset"):
        if d.get("tier") != "verified":
            continue
        fields = [f["name"] for f in (d.get("schema") or {}).get("fields") or [] if FIELD_RX.match(str(f["name"]))]
        files = sorted(glob.glob(str(P / d["id"] / "*.parquet"))) if fields else []
        if not files:
            continue
        try:
            df = pd.read_parquet(files[-1])
        except Exception:  # noqa: BLE001
            continue
        n_ds += 1
        for f in fields:
            if f not in df:
                continue
            for v, n in df[f].astype(str).str.strip().value_counts().items():
                if v.lower() not in JUNK:
                    cnt[v] += int(n)
                    src[v].add(d["id"])
    out = pd.DataFrame([{"value": v, "rows": n, "datasets": len(src[v]), "example": sorted(src[v])[0]} for v, n in cnt.items()])
    out.attrs["datasets"] = n_ds
    return out


def _dict() -> dict:
    return yaml.safe_load(DICT.read_text(encoding="utf-8")) if DICT.exists() else {"entries": [], "skip": {}}


def skipped() -> set[str]:
    """사전 skip — 업종이 아닌 값(용도·설치 장소·너무 넓은 품목군). 어휘와 일치율 분모에서 뺀다."""
    return {nz(v) for vs in (_dict().get("skip") or {}).values() for v in vs}


def curated(codes: dict[str, str]) -> tuple[dict[str, list[tuple[str, float]]], dict[str, dict]]:
    """사전: nz(이름) → [(KSIC 11차, confidence)]. aliases도 같은 답. codes = KSIC 11차 {코드: 이름} — 없는 코드·이름은 오류.
    confidence < HOLD 항목은 둘째 반환값(nz(이름) → 사전 항목)으로 따로 — 매핑에 안 쓴다."""
    by_name = {nz(n): c for c, n in sorted(codes.items(), key=lambda x: (x[0].isdigit(), len(x[0])))}
    out, held, bad = {}, {}, []
    for e in _dict()["entries"]:
        if "ksic_name" in e:
            ks = [by_name.get(nz(e["ksic_name"]))]
        else:
            ks = [str(k) for k in (e["ksic"] if isinstance(e["ksic"], list) else [e["ksic"]])]
        if not all(k in codes for k in ks if k) or None in ks:
            bad.append(f"{e['name']} → {e.get('ksic_name') or e.get('ksic')}")
            continue
        conf = float(e.get("confidence", 0.8))
        for name in [e["name"], *e.get("aliases", [])]:
            if conf < HOLD:
                held[nz(name)] = {**e, "ksic": ks}
            else:
                out[nz(name)] = [(k, round(conf / len(ks), 3)) for k in ks]
    if bad:
        raise ValueError("사전의 KSIC 코드·이름이 11차에 없음: " + " · ".join(bad))
    return out, held


def patterns(codes: dict[str, str]) -> list[tuple[re.Pattern, list[tuple[str, float]]]]:
    """사전 patterns — 수산업법 어업 종류처럼 변형이 많은 이름. 위에서부터 처음 맞는 규칙."""
    out = []
    for e in _dict().get("patterns") or []:
        ks = [str(k) for k in (e["ksic"] if isinstance(e["ksic"], list) else [e["ksic"]])]
        if not all(k in codes for k in ks):
            raise ValueError(f"사전 규칙의 KSIC 코드가 11차에 없음: {e['rx']} → {ks}")
        conf = float(e.get("confidence", 0.8))
        out.append((re.compile(e["rx"]), [(k, round(conf / len(ks), 3)) for k in ks]))
    return out


def resolver():
    k11, k10 = _codes("ksic"), _codes("ksic10")
    l10 = link("11").groupby("left_value")["right_value"].apply(list).to_dict()
    # 모든 단계 이름을 받되, 같은 이름이 여러 단계에 있으면(제과점업 4·5자리) 가장 세밀한 코드
    by11 = {nz(n): c for c, n in sorted(zip(k11["code"], k11["name"]), key=lambda x: (x[0].isdigit(), len(x[0])))}
    by10 = {nz(n): c for c, n in zip(k10["code"], k10["name"]) if len(c) == 5}
    sb = sbiz()
    bysb = {nz(n): list(g[["right_value", "confidence"]].itertuples(index=False, name=None)) for n, g in sb.groupby("left_kind")}
    cur, held = curated(dict(zip(k11["code"], k11["name"])))
    pats = patterns(dict(zip(k11["code"], k11["name"])))

    name11, name10 = dict(zip(k11["code"], k11["name"])), dict(zip(k10["code"], k10["name"]))
    l9 = link("10")
    name9 = dict(zip(l9["left_value"], l9["left_kind"]))
    l9 = l9.groupby("left_value")["right_value"].apply(list).to_dict()

    def by_code(c: str, word: str) -> list[tuple[str, float]]:
        """같은 번호가 차수마다 다른 업종일 수 있다(23122: 9차 판유리 가공품 · 10·11차 디스플레이용 유리) — 적힌 이름과 가장 닮은 차수로 읽는다."""
        sim = {v: fuzz.partial_ratio(nz(n[c]), nz(re.sub(r"\(\d{5}\)", "", word))) for v, n in (("11", name11), ("10", name10), ("9", name9))
               if c in n}
        if not sim:
            return []
        best = max(sim, key=lambda v: (sim[v], v == "11", v == "10"))  # 같으면 최신 차수
        if best == "11":
            return [(c, 1.0)]
        t10 = [c] if best == "10" else l9.get(c, [])  # 9차 → 10차 → 11차, 갈래마다 비중을 나눈다
        return [(t11, round(1 / len(t10) / len(l10[t]), 3)) for t in t10 if t in l10 for t11 in l10[t]]

    def one(word: str) -> tuple[str, list[tuple[str, float]]] | None:
        cs = re.findall(r"\((\d{5})\)", word)  # '도금업(25922)' — 이름에 적어 둔 세세분류 코드 (여러 개면 모두)
        if cs:
            got = [t for c in cs for t in by_code(c, word)]
            if got:
                return "code_in_name", [(t, round(c / len(cs), 3)) for t, c in got]
        k = nz(word)
        if k in by11:
            return "exact_ksic11", [(by11[k], 1.0)]
        if k in by10:
            ts = l10.get(by10[k], [])
            return ("exact_ksic10", [(t, round(1 / len(ts), 3)) for t in ts]) if ts else None
        if k in cur:
            return "curated", cur[k]
        if k in bysb:
            return "sbiz_measured", bysb[k]
        for rx, ts in pats:
            if rx.search(word.strip()):
                return "curated_pattern", ts
        return None

    def resolve(value: str) -> tuple[str, list[tuple[str, float]]] | None:
        r = one(value)
        if r:
            return r
        parts = [p for p in re.split(r"\s*[,+]\s*", value) if p.strip()]
        if len(parts) < 2:
            return None
        got = [one(p) for p in parts]
        if not all(got):
            return None
        tg = defaultdict(float)  # '실내건축공사업 +실내건축공사업'처럼 같은 업종이 겹치면 한 줄로 합친다
        for _, ts in got:
            for t, c in ts:
                tg[t] += c / len(parts)
        return "split:" + "+".join(sorted({m for m, _ in got})), [(t, round(c, 3)) for t, c in tg.items()]

    return resolve, sb, held


def build() -> dict:
    links = build_links()
    resolve, sb, held = resolver()
    sb_rec = write("sbiz_inds__ksic", {"key": "sbiz_inds", "system": "소상공인 상권업종 소분류 코드 (상가정보 15083033)"},
                   {"key": "ksic", "system": "KSIC 11차 세세분류"}, "exact", sb, "keep_left", ["15083033", "15159305"],
                   f"상가정보 {len(_latest('15083033')):,}행 실측 — 소분류마다 가장 많이 붙은 10차 코드를 11차로. confidence = 그 소분류 안 최빈 비율 "
                   f"(평균 {sb.groupby('left_value')['confidence'].sum().mean():.2f})")
    v = vocab()
    n_ds = v.attrs.get("datasets", 0)
    skip = skipped()
    n_skip = int(v["value"].map(nz).isin(skip).sum())
    v = v[~v["value"].map(nz).isin(skip)]
    rows, miss, review = [], [], defaultdict(lambda: {"datasets": 0, "rows": 0, "values": []})
    for r in v.itertuples():
        got = resolve(r.value)
        if not got:
            for part in [r.value, *re.split(r"\s*[,+]\s*", r.value)]:  # 보류 항목에 걸린 값은 검토 목록에 모은다
                if nz(part) in held:
                    h = review[held[nz(part)]["name"]]
                    h["datasets"] += r.datasets
                    h["rows"] += r.rows
                    h["values"].append(r.value)
                    break
            miss.append(r)
            rows.append({"left_value": r.value, "right_value": None, "confidence": 0.0, "method": "unmatched", "left_kind": f"{r.datasets}건"})
            continue
        m, ts = got
        for t, c in ts:
            rows.append({"left_value": r.value, "right_value": t, "confidence": c, "method": m, "left_kind": f"{r.datasets}건"})
    t = pd.DataFrame(rows)
    ent = {e["name"]: e for e in held.values()}
    hit = v.set_index("value").join(t.groupby("left_value")["right_value"].apply(lambda s: s.notna().any()).rename("hit"))
    w_ds = (hit["datasets"] * hit["hit"]).sum() / hit["datasets"].sum()
    w_rows = (hit["rows"] * hit["hit"]).sum() / hit["rows"].sum()
    rec = write("industry_nm__ksic", {"key": "industry_nm", "system": "업종·업태 이름 (인허가·공장등록·점포 현황 등 검증 데이터 실측값)"},
                {"key": "ksic", "system": "KSIC 11차 세세분류"}, "composite", t, "keep_left", ["15159306", "15159305", "15083033"],
                f"검증 데이터 {n_ds:,}건의 업종 필드 실측값 {len(v):,}개 (업종이 아닌 값 {n_skip:,}개 제외). 데이터 수 가중 일치 {w_ds:.1%} · 행 수 가중 {w_rows:.1%}. "
                f"curated는 Opus 판정(구름 검토 전), confidence {HOLD} 미만 {len(ent)}항목은 보류(industry_review.csv) — left_kind = 그 이름이 나온 데이터 수")
    pd.DataFrame([{"name": n, "proposed_ksic": " ".join(ent[n]["ksic"]), "confidence": ent[n]["confidence"], "note": ent[n].get("note", ""),
                   "datasets": h["datasets"], "rows": h["rows"], "values": " | ".join(sorted(set(h["values"]))[:10])}
                  for n, h in review.items()] +
                 [{"name": n, "proposed_ksic": " ".join(e["ksic"]), "confidence": e["confidence"], "note": e.get("note", ""), "datasets": 0, "rows": 0,
                   "values": ""} for n, e in ent.items() if n not in review]
                 ).sort_values(["datasets", "name"], ascending=[False, True]).to_csv(
        config.KNOWLEDGE / "expansion" / "industry_review.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(miss).sort_values("datasets", ascending=False).to_csv(config.KNOWLEDGE / "expansion" / "industry_unmatched.csv",
                                                                        index=False, encoding="utf-8-sig")
    return {"links": [x["rows"] for x in links], "sbiz": sb_rec["rows"], "industry_nm": rec["rows"], "match_rate": rec["match_rate"],
            "w_datasets": round(float(w_ds), 4), "w_rows": round(float(w_rows), 4), "held": len(ent)}


if __name__ == "__main__":
    print(build())
