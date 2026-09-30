"""Edge 자동 후보 (KNOWLEDGE-SPEC §7-5) — 실측 키·매핑·호출 체인·공간 규칙에서 knowledge/edges.yaml 후보를 만든다.

원칙: LLM은 Edge를 만들지 않는다. 이 스크립트가 규칙으로 후보(source: auto)를 내고, 사람이 확정하면 source: admin (재생성해도 보존).
같은 (src, dst, rel, on)은 재생성해도 같은 id를 유지한다 — 레시피·전략 응답이 id로 인용하기 때문.

갈래
  K 같은 키: 엔티티 키(사업자번호·PNU·기관코드…)는 키 원장 데이터(master) 또는 대표 데이터로 모으는 별(star) 모양 — n² 피함
  A 지역 키: 법정동·시군구는 법정동코드 파일(15123287)로 — many_to_many(지역 단위 집계 후 결합)
  M 매핑: 코드 체계가 다른 두 키 — via_mapping
  S 공간: 좌표만 → 연속지적도(15123899) R-12(좌표→PNU), 주소만 → R-13(주소→좌표→PNU)
  L 호출 체인: 필수 파라미터가 다른 데이터의 코드 (lookup)
  F 패밀리: pps-procurement family.yaml의 lookup·join
  R 맥락: 위에서 Edge가 하나도 없는 데이터 — 같은 맥락(context) 멤버와 related_to
"""
from __future__ import annotations

import re
from collections import defaultdict

import yaml

from pds import config
from pds.schema import Edge
from pds.schema import store

CADASTRE = "15123899"   # 연속지적도 (PNU 폴리곤) — 공간 조인 허브
BJD_MASTER = "15123287"  # 법정동코드 파일
AREA_KEYS = {"bjd_cd", "sgg_cd", "admin_area_code"}
WEAK_KEYS = {"address", "coord"}
# 호출 파라미터 이름 → Key (lookup 후보)
PARAM_KEY = {"ykiho": "ykiho", "kaptCode": "apt_complex_cd", "pnu": "pnu", "LAWD_CD": "sgg_cd", "bjdCode": "bjd_cd",
             "sigunguCode": "sgg_cd", "ATPT_OFCDC_SC_CODE": "neis_school_cd", "SD_SCHUL_CODE": "neis_school_cd", "hpid": "hpid",
             "brno": "bizno", "b_no": "bizno", "crno": "corp_rgst_no", "lcgvmnInstCd": "instt_cd", "fctryManageNo": "factory_rgst_no"}


def _datasets() -> dict[str, dict]:
    return {d["id"]: d for d, _ in store.iter_raw("dataset") if d.get("tier") == "verified"}


def _fk(d: dict) -> dict[str, list[str]]:
    out = defaultdict(list)
    for f in (d.get("schema") or {}).get("foreign_keys") or []:
        out[f["reference"]["key"]] += f["fields"]
    return out


def _sig(e: dict) -> tuple:
    on = e.get("on") or {}
    return (e["src"], e["dst"], e["rel"], tuple(on.get("left") or []), tuple(on.get("right") or []), on.get("via_mapping"))


def candidates() -> list[dict]:
    ds = _datasets()
    keys = {k["id"]: k for k in store.load("key")}
    fks = {i: _fk(d) for i, d in ds.items()}
    score = {i: (d.get("classification") or {}).get("prelim_score") or 0 for i, d in ds.items()}
    out = []

    def add(src, dst, rel, left=None, right=None, rship=None, via=None, transform=None, conf=0.5, note=None):
        if src == dst or src not in ds or dst not in ds and dst not in (CADASTRE, BJD_MASTER):
            return
        e = {"src": src, "dst": dst, "rel": rel, "source": "auto", "confidence": conf}
        if left or right or via or transform:
            e["on"] = {k: v for k, v in {"left": left or [], "right": right or [], "via_mapping": via, "transform": transform}.items() if v}
        if rship:
            e["relationship"] = rship
        if note:
            e["note"] = note
        out.append(e)

    # K·A 같은 키
    by_key = defaultdict(list)
    for i, fk in fks.items():
        for k in fk:
            by_key[k].append(i)
    for k, members in by_key.items():
        if k in WEAK_KEYS:
            continue
        if k in AREA_KEYS:
            for i in members:
                if i != BJD_MASTER:
                    add(i, BJD_MASTER, "joinable", fks[i][k][:1], ["법정동코드"], "many_to_many", transform="R-02" if k == "sgg_cd" else None,
                        conf=0.6, note=f"지역 키 {k} — 지역 단위로 집계한 뒤 결합")
            continue
        masters = [m for m in keys.get(k, {}).get("master_datasets", []) if m in ds]
        hub = masters[0] if masters else max(members, key=lambda x: score[x])
        for i in members:
            if i == hub:
                continue
            rfield = fks[hub][k][:1] if hub in fks and k in fks[hub] else [k]
            add(i, hub, "joinable", fks[i][k][:1], rfield, "many_to_one" if masters else "many_to_many", conf=0.7 if masters else 0.5,
                note=f"같은 키 {k}" + (" (키 원장으로)" if masters else " (대표 데이터로 — 원장 미지정)"))

    # M 매핑
    for m, _ in store.iter_raw("mapping"):
        lk, rk = m["left"]["key"], m["right"]["key"]
        L = [i for i in by_key.get(lk, [])] or [s for s in m.get("sources", [])[:1] if s in ds]
        R = [i for i in by_key.get(rk, [])] or [s for s in m.get("sources", [])[1:2] if s in ds]
        for a in L:
            for b in R[:3]:
                add(a, b, "joinable", fks.get(a, {}).get(lk, [lk])[:1], fks.get(b, {}).get(rk, [rk])[:1], "many_to_one",
                    via=m["id"], conf=min(0.9, 0.4 + m["match_rate"] / 2), note=f"매핑 {m['id']} (매칭률 {m['match_rate']:.0%})")

    # S 공간
    for i, fk in fks.items():
        strong = set(fk) - WEAK_KEYS
        if "pnu" in strong or i == CADASTRE:
            continue
        if "coord" in fk:
            add(i, CADASTRE, "joinable", fk["coord"][:2], ["pnu"], "many_to_one", transform="R-12", conf=0.6,
                note="좌표 → 연속지적도 점-다각형 → PNU")
        elif "address" in fk:
            add(i, CADASTRE, "joinable", fk["address"][:1], ["pnu"], "many_to_one", transform="R-13", conf=0.4,
                note="주소 → 지오코딩(브이월드) → 좌표 → PNU")

    # N 행정구역 이름만 있는 데이터 → 법정동 코드표 (R-14 이름→코드)
    admin_name = re.compile(r"^(시군구명?|시도명?|지역명?|sggNm|sigunguNm|signgu|signguNm|ctpvNm|ctprvnNm|sidoNm|관할지역명?|자치구)$", re.I)
    for i, d in ds.items():
        if AREA_KEYS & set(fks[i]):
            continue
        cols = [f["name"] for f in (d.get("schema") or {}).get("fields") or []
                if admin_name.match(f["name"]) and any(re.search(r"[가-힣](시|군|구|도)$", v) for v in f.get("sample_values") or [])]
        if cols:
            add(i, BJD_MASTER, "joinable", cols[:2], ["법정동명"], "many_to_many", transform="R-14", conf=0.5,
                note="행정구역 이름 → 코드(법정동 코드표) 후 지역 단위 결합")

    # L 호출 체인
    for i, d in ds.items():
        need = set()
        for c in d.get("claims") or []:
            if c["kind"] == "pitfall" and c["value"].startswith("필수 파라미터"):
                need |= set(re.findall(r"[A-Za-z_]+", c["value"].split("는")[0].replace("필수 파라미터", "")))
        for p in need:
            k = PARAM_KEY.get(p)
            if not k:
                continue
            provider = next((m for m in keys.get(k, {}).get("master_datasets", []) if m in ds and m != i), None) or \
                next((j for j in by_key.get(k, []) if j != i), None)
            if provider:
                add(i, provider, "lookup", [p], fks.get(provider, {}).get(k, [k])[:1], "many_to_one", conf=0.7,
                    note=f"{i} 호출에 필요한 {p}를 {provider}에서 받는다")

    # F 패밀리
    for fam_path in (config.KNOWLEDGE / "families").glob("*/family.yaml"):
        fam = yaml.safe_load(fam_path.read_text(encoding="utf-8"))
        for fe in fam.get("edges") or []:
            if fe.get("type") not in ("lookup", "join"):
                continue
            provider = str(fe.get("from"))
            for caller in (fe["to"] if isinstance(fe["to"], list) else [fe["to"]]):
                caller = str(caller)
                if provider.startswith("*.") or caller.startswith("*."):
                    continue
                # 패밀리 lookup: from이 값(from_field)을 주고 to가 파라미터(to_param)로 받는다 → Edge lookup은 src=호출자, dst=제공자
                if fe["type"] == "lookup":
                    add(caller, provider, "lookup", [str(fe.get("to_param") or fe.get("key"))], [str(fe.get("from_field") or fe.get("key"))],
                        "many_to_one", conf=0.8 if fe.get("status") == "verified" else 0.6,
                        note=f"패밀리 {fam['family']} 키 {fe.get('key')} ({fe.get('status')}) 조회구분 {fe.get('inqry_div') or ''}".strip())
                else:
                    f = str(fe.get("key") or "통합번호")
                    add(provider, caller, "joinable", [str(fe.get("from_field") or f)], [str(fe.get("to_field") or f)], "one_to_many",
                        conf=0.6, note=f"패밀리 {fam['family']} ({fe.get('status')})")

    # R 맥락 — Edge 없는 데이터만
    has = {e["src"] for e in out} | {e["dst"] for e in out}
    ctx_members = defaultdict(set)
    for c, _ in store.iter_raw("context"):
        for m in c["members"]:
            for i, d in ds.items():
                f, a, s = d["sector"].split("/")
                if m.get("sector") == f"{f} - {a}" and (not m.get("subsector") or m["subsector"] == s):
                    ctx_members[c["id"]].add(i)
    for i in ds:
        if i in has:
            continue
        for cid, mem in ctx_members.items():
            if i in mem:
                for j in sorted(mem - {i}, key=lambda x: -score[x])[:2]:
                    add(i, j, "related_to", conf=0.3, note=f"같은 맥락 {cid}")
                break
    # 중복 제거
    uniq = {}
    for e in out:
        uniq.setdefault(_sig(e), e)
    return list(uniq.values())


def write(keep_measured: bool = True) -> dict:
    path = store.PATHS["edge"]
    old = store.read(path) if path.exists() else []
    old = old or []
    keep = [e for e in old if e.get("source") != "auto"]  # 사람이 확정·추가한 것
    old_ids = {_sig(e): e["id"] for e in old}
    old_meas = {_sig(e): (e.get("verified"), e.get("confidence")) for e in old if e.get("verified")} if keep_measured else {}
    used = {e["id"] for e in keep}
    nxt = max([int(e["id"][2:]) for e in old] + [0]) + 1
    new = []
    for e in candidates():
        if _sig(e) in {_sig(k) for k in keep}:
            continue
        eid = old_ids.get(_sig(e))
        if not eid or eid in used:
            eid = f"e-{nxt:04d}"
            nxt += 1
        used.add(eid)
        e = {"id": eid, **e}
        if _sig(e) in old_meas:
            e["verified"], e["confidence"] = old_meas[_sig(e)]
        Edge.model_validate(e)
        new.append(e)
    allv = keep + sorted(new, key=lambda x: x["id"])
    store.dump(allv, path, header="데이터셋 사이 조인·lookup 선언 (KNOWLEDGE-SPEC §3.4). source: auto는 pds/edges/auto.py가 다시 쓴다 —\n"
                                  "확정한 Edge는 source: admin으로 바꾸면 보존된다. 조인은 여기 선언된 것만 쓴다(LLM이 만들지 않는다).")
    from collections import Counter
    return {"edges": len(allv), "auto": len(new), "kept": len(keep), "by_rel": dict(Counter(e["rel"] for e in allv)),
            "datasets_with_edge": len({e["src"] for e in allv} | {e["dst"] for e in allv})}


if __name__ == "__main__":
    print(write())
