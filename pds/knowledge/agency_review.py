"""기관 분석 (Opus) — A등급 기관마다 포털 목록 전체를 읽고 운영 시스템·핵심 원장·고유 키·관계·빠진 핵심을 정리한다.

python -m pds.knowledge.agency_review [기관코드 ...]   (없으면 A등급 중 아직 분석 안 한 곳)
입력: 그 기관의 포털 목록 전체(제목·형태·검증 상태·실측 컬럼 또는 명세 컬럼) + 등록된 Key 목록.
출력(검증 후 저장):
  knowledge/agencies/{코드}.yaml  systems · core_missing · native_keys · relations · gaps · analyzed_by/at
  knowledge/keys/{id}.yaml        고유 키 — 새 키는 만들고, 기존 키는 fields만 덧붙인다 (scope family, agency)
검증: 목록에 없는 id는 버린다. 키 필드명은 그 데이터의 실측 컬럼(검증) 또는 명세 컬럼에 실제로 있어야 남긴다.
원칙: LLM은 Edge를 만들지 않는다 — 키·필드를 제안할 뿐, 조인은 edges.auto가 만들고 probe.join이 잰다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from pds import config
from pds.schema import store

MODEL = os.environ.get("PDS_AGENCY_MODEL") or "claude-opus-5-5"
LOG = config.ROOT / "probe" / "llm" / "agency"

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["systems", "native_keys", "relations", "core_missing", "gaps", "note"],
    "properties": {
        "systems": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                    "required": ["name", "description", "datasets", "core"],
                    "properties": {"name": {"type": "string"}, "description": {"type": "string"},
                                   "datasets": {"type": "array", "items": {"type": "string"}},
                                   "core": {"type": "array", "items": {"type": "string"}}}}},
        "native_keys": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                        "required": ["key_id", "name", "identifies", "fields", "master"],
                        "properties": {"key_id": {"type": "string", "description": "기존 Key id를 재사용하거나 새 snake_case id"},
                                       "name": {"type": "string"}, "identifies": {"type": "string"},
                                       "fields": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                  "required": ["name", "datasets"],
                                                  "properties": {"name": {"type": "string"},
                                                                 "datasets": {"type": "array", "items": {"type": "string"}}}}},
                                       "master": {"type": "array", "items": {"type": "string"}}}}},
        "relations": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                      "required": ["to", "via", "datasets", "note"],
                      "properties": {"to": {"type": "string", "description": "상대 기관명 또는 self:<시스템명>"},
                                     "via": {"type": "string", "description": "잇는 Key id"},
                                     "datasets": {"type": "array", "items": {"type": "string"}}, "note": {"type": "string"}}}},
        "core_missing": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "note": {"type": "string"},
    },
}

SYSTEM = """당신은 한국 공공데이터포털의 기관별 데이터 구조를 분석하는 데이터 아키텍트입니다.
한 기관이 개방한 데이터 목록 전체를 보고, 그 기관의 데이터가 어떤 원천 시스템에서 나오고 무엇이 핵심 원장이며 무엇으로 서로 이어지는지 정리합니다.

1. systems: 원천 업무 시스템 단위로 묶는다 (예: 국토교통부 → 실거래가 신고, 건축행정 세움터, 공동주택관리 K-apt …). 시스템마다 그 시스템에서 나온 데이터 id 전부(datasets)와 핵심 원장(core: 개체 단위·전수·다른 데이터의 기준이 되는 것 — 통계·집계·보조는 제외). 지역판이 여럿이면 대표만 core에.
2. native_keys: 그 기관(시스템)이 부여하는 고유 식별자 — 같은 개체를 여러 데이터가 같은 값으로 가리키는 열 (예: 입찰공고번호, 브랜드관리번호, 사업장관리번호, 단지코드).
   - 아래 '등록된 Key'와 같은 개념이면 그 key_id를 재사용한다 (사업자번호는 bizno, 필지는 pnu, 법정동코드는 bjd_cd …). 새 키면 영문 snake_case id.
   - fields: 그 키가 들어 있는 실제 열 이름과 데이터 id — 반드시 목록에 적힌 '열'에 있는 이름만. 없는 열 이름을 지어내지 않는다.
   - master: 그 키의 원장(전수 목록) 데이터 id.
   - 주소·좌표·시군구 같은 지역 키는 쓰지 않는다 (이미 규칙으로 처리됨).
3. relations: 기관 안 시스템 사이(to='self:<시스템명>') 또는 다른 기관(to=기관명)과 같은 키로 이어지는 관계. via는 key_id.
4. core_missing: 핵심 원장인데 상태가 '미검증'인 데이터 id.
5. gaps: 이 기관 데이터로 답하기 어려운 것 (원장이 비개방, 키 없음, 갱신 중단 등) 한 줄씩.
6. note: 기관 데이터 구조 요약 2~3문장.
목록에 없는 id는 쓰지 않는다. 한국어로."""


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else anthropic.Anthropic()


def _cols_of() -> dict[str, list[str]]:
    """데이터 id → 열 이름 (검증 데이터는 실측 schema.fields, 아니면 포털 명세 output_cols)."""
    out = {}
    cat = pd.read_parquet(config.PROCESSED / "catalog.parquet", columns=["id", "output_cols"])
    for i, c in zip(cat["id"], cat["output_cols"]):
        if isinstance(c, str) and c:
            out[i] = [x.strip() for x in c.split(",") if x.strip()]
    from pds.service import index
    for i, d in index.get().datasets.items():
        names = [f.get("name") for f in (d.get("schema") or {}).get("fields") or [] if f.get("name")]
        if names:
            out[i] = names
    return out


def packet(code: str, cols: dict) -> tuple[str, set[str]]:
    from pds.service import index
    ix = index.get()
    cat = pd.read_parquet(config.PROCESSED / "catalog.parquet", columns=["id", "title", "agency_code", "list_type"])
    g = cat[cat["agency_code"].astype(str) == code]
    lines = []
    for r in g.itertuples():
        d = ix.datasets.get(r.id)
        st = "미검증" if not d else ("후보" if d["tier"] == "candidate" else
                                   ((d.get("facets") or {}).get("grade") or ["검증·핵심"])[0])
        cs = ",".join(cols.get(r.id, [])[:18])
        lines.append(f"{r.id} | {r.title} | {r.list_type} | {st} | 열: {cs}")
    keys = [f"{k['id']}: {k['name']}" for k, _ in store.iter_raw("key")]
    return "등록된 Key:\n" + "\n".join(keys) + f"\n\n데이터 목록 {len(lines)}건 (id | 제목 | 형태 | 상태 | 열):\n" + "\n".join(lines), set(g["id"])


def analyze(code: str, cols: dict) -> dict:
    from pds.service.llm import _text
    a = next(x for x, _ in store.iter_raw("agency") if x["id"] == code)
    body, ids = packet(code, cols)
    msg = f"기관: {a['name']} ({code}, {a['type']}) — 목록 {a['counts']['catalog']} · 검증 {a['counts']['verified']}\n\n{body}"
    with _client().messages.stream(model=MODEL, max_tokens=64000, system=SYSTEM,
                                   output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
                                   messages=[{"role": "user", "content": msg}]) as s:
        r = s.get_final_message()
    out = json.loads(_text(r))
    LOG.mkdir(parents=True, exist_ok=True)
    (LOG / f"{code}.json").write_text(json.dumps({"usage": [r.usage.input_tokens, r.usage.output_tokens], "out": out},
                                                 ensure_ascii=False, indent=1), encoding="utf-8")
    return {"code": code, "ids": ids, "out": out, "usage": (r.usage.input_tokens, r.usage.output_tokens)}


def apply(res: dict, cols: dict) -> dict:
    """목록·실측 열로 걸러 저장. 버린 것 수를 돌려준다."""
    code, ids, out = res["code"], res["ids"], res["out"]
    keep = lambda xs: [x for x in xs if x in ids]  # noqa: E731
    dropped = 0
    systems = [{"name": s["name"], "description": s["description"], "datasets": keep(s["datasets"]), "core": keep(s["core"])} for s in out["systems"]]
    keys_now = {k["id"]: (k, p) for k, p in store.iter_raw("key")}
    native = []
    for nk in out["native_keys"]:
        kid = re.sub(r"[^a-z0-9_]", "_", nk["key_id"].lower()).strip("_")
        if not re.match(r"^[a-z][a-z0-9_]*$", kid):
            continue
        fields = []
        for f in nk["fields"]:
            ds = [d for d in keep(f["datasets"]) if f["name"] in cols.get(d, [])]  # 실제 열에 있는 이름만
            dropped += len(f["datasets"]) - len(ds)
            if ds:
                fields.append({"names": [f["name"]], "datasets": ds})
        if not fields:
            continue
        native.append(kid)
        if kid in keys_now:  # 기존 키: fields만 덧붙인다 (중복 제거)
            k, path = keys_now[kid]
            have = {(n, d) for x in k.get("fields") or [] for n in x["names"] for d in x.get("datasets") or ["*"]}
            add = [x for x in fields if any((n, d) not in have for n in x["names"] for d in x["datasets"])]
            if add:
                k["fields"] = (k.get("fields") or []) + add
                store.dump(k, path)
        else:
            k = {"id": kid, "name": nk["name"], "type": "natural", "scope": "family", "agency": code,
                 "master_datasets": keep(nk["master"]), "fields": fields,
                 "notes": f"{nk['identifies']} — 기관 분석({MODEL}, {dt.date.today()}) 제안, 열 이름은 실측·명세 컬럼으로 확인"}
            store.dump(k, config.KNOWLEDGE / "keys" / f"{kid}.yaml", header=f"Key {kid} — 기관 고유 키 (pds.knowledge.agency_review)")
            keys_now[kid] = (k, config.KNOWLEDGE / "keys" / f"{kid}.yaml")
    rels = [{"to": r["to"], "via": re.sub(r"[^a-z0-9_]", "_", r["via"].lower()).strip("_"), "datasets": keep(r["datasets"]),
             "status": "proposed", "note": r["note"]} for r in out["relations"]]
    path = config.KNOWLEDGE / "agencies" / f"{code}.yaml"
    a = store.read(path)
    a.update({"systems": systems, "native_keys": native, "relations": rels, "core_missing": keep(out["core_missing"]),
              "gaps": out["gaps"], "note": out["note"], "analyzed_by": MODEL, "analyzed_at": dt.date.today()})
    store.dump(a, path, header=f"Agency {code} {a['name']} — 집계는 pds.knowledge.agencies, 분석은 pds.knowledge.agency_review")
    return {"code": code, "systems": len(systems), "keys": len(native), "core_missing": len(a["core_missing"]), "dropped_fields": dropped}


def main(codes: list[str]) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ags = [a for a, _ in store.iter_raw("agency")]
    if not codes:
        codes = [a["id"] for a in ags if a["tier"] == "A" and not a.get("analyzed_at")]
    cols = _cols_of()
    print(f"기관 분석 {len(codes)}곳 · {MODEL}", flush=True)
    tin = tout = 0
    with ThreadPoolExecutor(int(os.environ.get("PDS_AGENCY_WORKERS", "6"))) as ex:
        futs = {ex.submit(analyze, c, cols): c for c in codes}
        from concurrent.futures import as_completed
        for f in as_completed(futs):
            try:
                res = f.result()
                tin += res["usage"][0]
                tout += res["usage"][1]
                print(" ", apply(res, cols), flush=True)  # 저장은 메인 스레드에서 하나씩
            except Exception as e:  # noqa: BLE001
                print(f"  ! {futs[f]} {type(e).__name__}: {str(e)[:150]}", flush=True)
    print(f"토큰 입력 {tin:,} · 출력 {tout:,}")


if __name__ == "__main__":
    main(sys.argv[1:])
